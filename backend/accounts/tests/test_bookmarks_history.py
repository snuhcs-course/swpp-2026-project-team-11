import datetime
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from accounts import history
from accounts.models import Bookmark, HistoryEntry
from menus.models import Restaurant

from .helpers import error_code, get, post

PASSWORD = "bap-meokja-2026"
DAY = "2026-11-02"
PLACE = {"restaurant": "홍콩반점 낙성대점"}
DISH = {"food_id": 1000000053, "display_name": "짜장면", **PLACE}


def delete(client, path, token=None):
    headers = {"Authorization": f"Token {token}"} if token else {}
    return client.delete(path, headers=headers)


class SignedInTestCase(TestCase):
    def sign_up(self, username="metchu_user"):
        return post(self.client, "/api/auth/signup/", {"username": username, "password": PASSWORD}).json()["token"]


class BookmarkTests(SignedInTestCase):
    def save(self, token, place=PLACE):
        return post(self.client, "/api/auth/bookmarks/", place, token)

    def listed(self, token):
        return get(self.client, "/api/auth/bookmarks/", token).json()["bookmarks"]

    def test_save_list_and_remove(self):
        token = self.sign_up()
        saved = self.save(token)
        self.assertEqual(saved.status_code, 201)
        bookmark = saved.json()["bookmark"]
        self.assertEqual(set(bookmark), {"id", "restaurant", "address", "created_at"})
        self.assertEqual((bookmark["restaurant"], bookmark["address"]), ("홍콩반점 낙성대점", None))
        self.assertEqual(self.listed(token), [bookmark])
        self.assertEqual(delete(self.client, f"/api/auth/bookmarks/{bookmark['id']}/", token).status_code, 204)
        self.assertEqual(self.listed(token), [])

    def test_saving_a_restaurant_again_is_the_same_bookmark(self):
        token = self.sign_up()
        first = self.save(token).json()["bookmark"]
        again = self.save(token, {"restaurant": " 홍콩반점 낙성대점 "})
        self.assertEqual((again.status_code, again.json()["bookmark"]), (200, first))
        self.assertEqual(Bookmark.objects.count(), 1)

    def test_a_dish_as_older_apps_send_it_saves_its_restaurant(self):
        token = self.sign_up()
        self.assertEqual(self.save(token, DISH).status_code, 201)
        self.assertEqual(self.save(token, {**DISH, "display_name": "짬뽕"}).status_code, 200)
        self.assertEqual([b["restaurant"] for b in self.listed(token)], ["홍콩반점 낙성대점"])

    def test_another_restaurant_is_another_bookmark(self):
        token = self.sign_up()
        first = self.save(token).json()["bookmark"]
        other = self.save(token, {"restaurant": "다른 곳"})
        self.assertEqual(other.status_code, 201)
        self.assertNotEqual(other.json()["bookmark"]["id"], first["id"])
        self.assertEqual(Bookmark.objects.count(), 2)

    def test_a_restaurant_the_menus_know_comes_with_its_address(self):
        Restaurant.objects.create(code="MA0001", name="홍콩반점 낙성대점", source="naver",
                                  address="서울특별시 관악구 남부순환로 1900")
        Restaurant.objects.create(code="학생회관식당", name="학생회관식당")
        token = self.sign_up()
        self.assertEqual(self.save(token).json()["bookmark"]["address"], "서울특별시 관악구 남부순환로 1900")
        self.save(token, {"restaurant": "학생회관식당"})
        self.save(token, {"restaurant": "없는 곳"})
        self.assertEqual([(b["restaurant"], b["address"]) for b in self.listed(token)],
                         [("없는 곳", None), ("학생회관식당", None), ("홍콩반점 낙성대점", "서울특별시 관악구 남부순환로 1900")])

    def test_a_name_shared_by_two_addresses_has_none(self):
        for code, address in (("MA0001", "서울특별시 관악구 관악로 1"), ("MA0002", "서울특별시 관악구 관악로 2")):
            Restaurant.objects.create(code=code, name="김밥천국", source="naver", address=address)
        token = self.sign_up()
        self.assertIsNone(self.save(token, {"restaurant": "김밥천국"}).json()["bookmark"]["address"])

    def test_clearing_removes_only_my_bookmarks(self):
        mine, theirs = self.sign_up("first_user"), self.sign_up("second_user")
        self.save(mine)
        self.save(mine, {"restaurant": "다른 곳"})
        self.save(theirs)
        self.assertEqual(delete(self.client, "/api/auth/bookmarks/", mine).status_code, 204)
        self.assertEqual(self.listed(mine), [])
        self.assertEqual(len(self.listed(theirs)), 1)

    def test_removing_twice_is_fine(self):
        token = self.sign_up()
        bookmark_id = self.save(token).json()["bookmark"]["id"]
        for _ in range(2):
            self.assertEqual(delete(self.client, f"/api/auth/bookmarks/{bookmark_id}/", token).status_code, 204)
        self.assertFalse(Bookmark.objects.exists())

    def test_newest_first(self):
        token = self.sign_up()
        for name in ("301동식당", "학생회관식당", "버거운버거"):
            self.save(token, {"restaurant": name})
        self.assertEqual([b["restaurant"] for b in self.listed(token)], ["버거운버거", "학생회관식당", "301동식당"])

    def test_each_user_sees_and_removes_only_their_own(self):
        mine, theirs = self.sign_up("first_user"), self.sign_up("second_user")
        bookmark_id = self.save(mine).json()["bookmark"]["id"]
        self.assertEqual(self.listed(theirs), [])
        self.assertEqual(delete(self.client, f"/api/auth/bookmarks/{bookmark_id}/", theirs).status_code, 204)
        self.assertEqual(len(self.listed(mine)), 1)
        self.assertEqual(self.save(theirs).status_code, 201)
        self.assertEqual(Bookmark.objects.count(), 2)

    def test_bad_bodies_are_400(self):
        token = self.sign_up()
        for body in ({}, {"restaurant": " "}, {"restaurant": None}, {"restaurant": 5}, {"restaurant": "x" * 101}):
            with self.subTest(body=body):
                response = post(self.client, "/api/auth/bookmarks/", body, token)
                self.assertEqual((response.status_code, error_code(response)), (400, "invalid_request"))
        self.assertFalse(Bookmark.objects.exists())


class BookmarkMigrationTests(TransactionTestCase):
    """0003 and 0004 turn the dish bookmarks of 0002 into one per user and restaurant."""

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate([("accounts", target)])
        return executor.loader.project_state([("accounts", target)]).apps

    def tearDown(self):
        self.migrate("0004_bookmark_per_restaurant")

    def test_each_restaurant_keeps_its_earliest_bookmark(self):
        apps = self.migrate("0002_bookmarks_history")
        User, Bookmark = apps.get_model("auth", "User"), apps.get_model("accounts", "Bookmark")
        mine, theirs = User.objects.create(username="first_user"), User.objects.create(username="second_user")
        rows = [(mine, "짜장면", "홍콩반점 낙성대점", 2), (mine, "짬뽕", "홍콩반점 낙성대점", 1),
                (mine, "탕수육", "홍콩반점 낙성대점", 3), (mine, "제육덮밥", "학생회관식당", 4),
                (theirs, "짜장면", "홍콩반점 낙성대점", 5)]
        ids = {}
        for user, dish, restaurant, day in rows:
            row = Bookmark.objects.create(user=user, food_id=day, display_name=dish, restaurant=restaurant)
            Bookmark.objects.filter(pk=row.pk).update(created_at=datetime.datetime(2026, 11, day, tzinfo=datetime.UTC))
            ids[user.username, dish] = row.pk

        Bookmark = self.migrate("0004_bookmark_per_restaurant").get_model("accounts", "Bookmark")
        kept = Bookmark.objects.order_by("id").values_list("id", "user__username", "restaurant", "created_at__day")
        self.assertEqual(list(kept), [(ids["first_user", "짬뽕"], "first_user", "홍콩반점 낙성대점", 1),
                                      (ids["first_user", "제육덮밥"], "first_user", "학생회관식당", 4),
                                      (ids["second_user", "짜장면"], "second_user", "홍콩반점 낙성대점", 5)])
        self.assertEqual({f.name for f in Bookmark._meta.concrete_fields}, {"id", "user", "restaurant", "created_at"})


class SignedOutTests(SignedInTestCase):
    def test_every_endpoint_needs_a_valid_token(self):
        for token in (None, "not-a-token"):
            for response in (get(self.client, "/api/auth/bookmarks/", token),
                             post(self.client, "/api/auth/bookmarks/", PLACE, token),
                             delete(self.client, "/api/auth/bookmarks/1/", token),
                             delete(self.client, "/api/auth/bookmarks/", token),
                             get(self.client, "/api/auth/history/", token),
                             delete(self.client, "/api/auth/history/", token)):
                with self.subTest(token=token, path=response.request["PATH_INFO"]):
                    self.assertEqual((response.status_code, error_code(response)), (401, "not_authenticated"))

    def test_wrong_methods_are_405(self):
        token = self.sign_up()
        self.assertEqual(get(self.client, "/api/auth/bookmarks/1/", token).status_code, 405)
        self.assertEqual(post(self.client, "/api/auth/history/", {}, token).status_code, 405)


class HistoryApiTests(SignedInTestCase):
    fixtures = ["menus_v3_contract"]

    def start(self, token=None):
        response = post(self.client, "/api/sessions/", {"date": DAY, "meal": "LU"}, token)
        self.assertEqual(response.status_code, 201)
        return f"/api/sessions/{response.json()['session_id']}/"

    def history(self, token):
        response = get(self.client, "/api/auth/history/", token)
        self.assertEqual(response.status_code, 200)
        return response.json()["history"]

    def test_each_proposed_dish_is_recorded_once(self):
        token = self.sign_up()
        url = self.start(token)
        self.assertEqual(self.history(token), [])
        guess = post(self.client, url + "recommend-now/").json()["step"]
        post(self.client, url + "undo/")
        self.assertEqual(post(self.client, url + "recommend-now/").json()["step"], guess)
        self.client.get(url)
        entries = self.history(token)
        self.assertEqual(len(entries), 1)
        food = guess["food"]
        self.assertEqual(set(entries[0]), {"date", "meal", "food_id", "display_name", "restaurant", "created_at"})
        self.assertEqual((entries[0]["date"], entries[0]["meal"], entries[0]["food_id"], entries[0]["display_name"]),
                         (DAY, "LU", food["food_id"], food["display_name"]))
        self.assertEqual(entries[0]["restaurant"], food["offers"][0]["restaurant"])

        another = post(self.client, url + "feedback/", {"guess_id": guess["guess_id"], "accepted": False}).json()["step"]
        if another["type"] == "question":
            another = post(self.client, url + "recommend-now/").json()["step"]
        final = post(self.client, url + "feedback/", {"guess_id": another["guess_id"], "accepted": True}).json()["step"]
        self.assertEqual(final["type"], "recommendation")
        self.assertEqual([e["food_id"] for e in self.history(token)],
                         [another["food"]["food_id"], food["food_id"]])

    def test_guests_and_bad_tokens_record_nothing(self):
        for token in (None, "not-a-token"):
            url = self.start(token)
            self.assertEqual(post(self.client, url + "recommend-now/").json()["step"]["type"], "guess")
        self.assertFalse(HistoryEntry.objects.exists())

    def test_history_is_per_user(self):
        mine, theirs = self.sign_up("first_user"), self.sign_up("second_user")
        post(self.client, self.start(mine) + "recommend-now/")
        self.assertEqual(len(self.history(mine)), 1)
        self.assertEqual(self.history(theirs), [])

    def test_clearing_removes_only_my_history(self):
        mine, theirs = self.sign_up("first_user"), self.sign_up("second_user")
        post(self.client, self.start(mine) + "recommend-now/")
        post(self.client, self.start(theirs) + "recommend-now/")
        self.assertEqual(delete(self.client, "/api/auth/history/", mine).status_code, 204)
        self.assertEqual(self.history(mine), [])
        self.assertEqual(len(self.history(theirs)), 1)

    def test_a_failed_write_does_not_fail_the_session(self):
        token = self.sign_up()
        url = self.start(token)
        with mock.patch.object(HistoryEntry.objects, "get_or_create", side_effect=DatabaseError("connection lost")):
            response = post(self.client, url + "recommend-now/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["step"]["type"], "guess")

    def test_the_session_belongs_to_whoever_started_it(self):
        token = self.sign_up()
        url = self.start(token)
        # Later requests carry no token; the session still records for its user.
        post(self.client, url + "recommend-now/", None, "not-a-token")
        self.assertEqual(len(self.history(token)), 1)


class HistoryRecordTests(SignedInTestCase):
    def user_id(self):
        self.sign_up()
        return get_user_model().objects.get().pk

    def session(self, user_id, session_id="s1"):
        return SimpleNamespace(user_id=user_id, session_id=session_id, date=datetime.date(2026, 11, 2), meal=None)

    def step(self, food_id=1, offers=None):
        return {"type": "guess", "food": {"food_id": food_id, "display_name": "짜장면",
                                          "offers": offers or [{"restaurant": "홍콩반점 낙성대점"}]}}

    def test_the_first_restaurant_is_recorded(self):
        user_id = self.user_id()
        offers = [{"restaurant": "첫 곳"}, {"restaurant": "다음 곳"}]
        history.record(self.session(user_id), self.step(offers=offers))
        entry = HistoryEntry.objects.get()
        self.assertEqual((entry.restaurant, entry.meal), ("첫 곳", None))

    def test_a_menu_long_name_and_no_offers_are_recorded(self):
        user_id = self.user_id()
        name = "정식" * 225
        history.record(self.session(user_id), {"type": "guess", "food": {"food_id": 1, "display_name": name, "offers": []}})
        entry = HistoryEntry.objects.get()
        self.assertEqual((entry.display_name, entry.restaurant), (name, ""))
        HistoryEntry._meta.get_field("display_name").clean(name, entry)

    def test_questions_and_guests_record_nothing(self):
        user_id = self.user_id()
        history.record(self.session(user_id), {"type": "question"})
        history.record(self.session(None), self.step())
        self.assertFalse(HistoryEntry.objects.exists())

    def test_only_the_newest_entries_are_kept(self):
        user_id = self.user_id()
        with mock.patch.object(history, "LIMIT", 3):
            for food_id in range(1, 6):
                history.record(self.session(user_id, f"s{food_id}"), self.step(food_id))
        self.assertEqual(list(HistoryEntry.objects.order_by("-id").values_list("food_id", flat=True)), [5, 4, 3])
