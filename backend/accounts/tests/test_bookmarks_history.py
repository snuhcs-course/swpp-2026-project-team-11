import datetime
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase

from accounts import history
from accounts.models import Bookmark, HistoryEntry

from .helpers import error_code, get, post

PASSWORD = "bap-meokja-2026"
DAY = "2026-11-02"
DISH = {"food_id": 1000000053, "display_name": "짜장면", "restaurant": "홍콩반점 낙성대점"}


def delete(client, path, token=None):
    headers = {"Authorization": f"Token {token}"} if token else {}
    return client.delete(path, headers=headers)


class SignedInTestCase(TestCase):
    def sign_up(self, username="metchu_user"):
        return post(self.client, "/api/auth/signup/", {"username": username, "password": PASSWORD}).json()["token"]


class BookmarkTests(SignedInTestCase):
    def save(self, token, dish=DISH):
        return post(self.client, "/api/auth/bookmarks/", dish, token)

    def test_save_list_and_remove(self):
        token = self.sign_up()
        saved = self.save(token)
        self.assertEqual(saved.status_code, 201)
        bookmark = saved.json()["bookmark"]
        self.assertEqual(set(bookmark), {"id", "food_id", "display_name", "restaurant", "created_at"})
        self.assertEqual({k: bookmark[k] for k in DISH}, DISH)
        self.assertEqual(get(self.client, "/api/auth/bookmarks/", token).json(), {"bookmarks": [bookmark]})
        self.assertEqual(delete(self.client, f"/api/auth/bookmarks/{bookmark['id']}/", token).status_code, 204)
        self.assertEqual(get(self.client, "/api/auth/bookmarks/", token).json(), {"bookmarks": []})

    def test_a_name_as_long_as_a_menu_name_is_saved(self):
        token = self.sign_up()
        dish = {**DISH, "display_name": "정식" * 250}
        self.assertEqual(self.save(token, dish).status_code, 201)

    def test_the_same_dish_on_another_day_is_one_bookmark(self):
        token = self.sign_up()
        first = self.save(token).json()["bookmark"]
        again = self.save(token, {**DISH, "food_id": DISH["food_id"] + 1})
        self.assertEqual((again.status_code, again.json()["bookmark"]),
                         (200, {**first, "food_id": DISH["food_id"] + 1}))
        self.assertEqual(Bookmark.objects.count(), 1)

    def test_the_same_name_at_another_restaurant_is_another_bookmark(self):
        token = self.sign_up()
        first = self.save(token).json()["bookmark"]
        other = self.save(token, {**DISH, "restaurant": "다른 곳"})
        self.assertEqual(other.status_code, 201)
        self.assertNotEqual(other.json()["bookmark"]["id"], first["id"])
        self.assertEqual(Bookmark.objects.count(), 2)

    def test_removing_twice_is_fine(self):
        token = self.sign_up()
        bookmark_id = self.save(token).json()["bookmark"]["id"]
        for _ in range(2):
            self.assertEqual(delete(self.client, f"/api/auth/bookmarks/{bookmark_id}/", token).status_code, 204)
        self.assertFalse(Bookmark.objects.exists())

    def test_newest_first(self):
        token = self.sign_up()
        for name in ("짜장면", "짬뽕", "탕수육"):
            self.save(token, {**DISH, "display_name": name})
        listed = get(self.client, "/api/auth/bookmarks/", token).json()["bookmarks"]
        self.assertEqual([b["display_name"] for b in listed], ["탕수육", "짬뽕", "짜장면"])

    def test_each_user_sees_and_removes_only_their_own(self):
        mine, theirs = self.sign_up("first_user"), self.sign_up("second_user")
        bookmark_id = self.save(mine).json()["bookmark"]["id"]
        self.assertEqual(get(self.client, "/api/auth/bookmarks/", theirs).json(), {"bookmarks": []})
        self.assertEqual(delete(self.client, f"/api/auth/bookmarks/{bookmark_id}/", theirs).status_code, 204)
        self.assertEqual(len(get(self.client, "/api/auth/bookmarks/", mine).json()["bookmarks"]), 1)
        self.assertEqual(self.save(theirs).status_code, 201)
        self.assertEqual(Bookmark.objects.count(), 2)

    def test_bad_bodies_are_400(self):
        token = self.sign_up()
        for body in ({}, {**DISH, "food_id": "53"}, {**DISH, "food_id": True}, {**DISH, "food_id": 0},
                     {**DISH, "display_name": " "}, {**DISH, "restaurant": None}, {**DISH, "display_name": "x" * 501}):
            with self.subTest(body=body):
                response = post(self.client, "/api/auth/bookmarks/", body, token)
                self.assertEqual((response.status_code, error_code(response)), (400, "invalid_request"))
        self.assertFalse(Bookmark.objects.exists())


class SignedOutTests(SignedInTestCase):
    def test_every_endpoint_needs_a_valid_token(self):
        for token in (None, "not-a-token"):
            for response in (get(self.client, "/api/auth/bookmarks/", token),
                             post(self.client, "/api/auth/bookmarks/", DISH, token),
                             delete(self.client, "/api/auth/bookmarks/1/", token),
                             get(self.client, "/api/auth/history/", token)):
                with self.subTest(token=token, path=response.request["PATH_INFO"]):
                    self.assertEqual((response.status_code, error_code(response)), (401, "not_authenticated"))

    def test_wrong_methods_are_405(self):
        token = self.sign_up()
        self.assertEqual(delete(self.client, "/api/auth/bookmarks/", token).status_code, 405)
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
