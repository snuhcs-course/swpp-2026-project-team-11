"""Group rooms over HTTP: joining, the host's controls, the shared rounds and their time limit."""
import json
from unittest import mock

import numpy as np

from django.contrib.auth.models import User
from django.test import TestCase

from accounts import tokens
from menus.allergens import ALLERGEN_VERSION
from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION
from menus.models import Food, Restaurant, StoreMenu
from recommend import rooms

from .helpers import DAY, add_food, post

MENUS = [
    ("Spicy pork stew", "Red hall", ["pork"], {"spicy": .95, "soupy": .9, "pork": .9}),
    ("Pork cutlet", "Red hall", ["pork", "wheat"], {"fried": .95, "crispy": .9, "pork": .9}),
    ("Mild chicken soup", "Soup hall", [], {"spicy": .05, "soupy": .95, "chicken": .9}),
    ("Fried chicken", "Soup hall", [], {"fried": .9, "crispy": .9, "chicken": .9}),
    ("Cold noodles", "Noodle hall", ["wheat"], {"cold": .95, "noodle": .95, "soupy": .6}),
    ("Beef rice bowl", "Noodle hall", [], {"rice": .95, "beef": .9}),
]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class RoomTestCase(TestCase):
    def setUp(self):
        for name, restaurant, allergens, features in MENUS:
            add_food(name, restaurant=restaurant, **features)
            Food.objects.filter(name=name).update(allergens=allergens, allergen_version=ALLERGEN_VERSION)
        self.clock = Clock()
        patcher = mock.patch.object(rooms, "clock", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        rooms._failed_joins.clear()

    def create(self, **body):
        response = post(self.client, "/api/rooms/", {"name": "Jimin", "date": DAY, "meal": "LU", **body})
        self.assertEqual(response.status_code, 201, response.content)
        reply = response.json()
        return reply["state"]["code"], reply["token"], reply["state"]

    def join(self, code, name="Seoyeon", status=201, **body):
        response = post(self.client, "/api/rooms/join/", {"code": code, "name": name, **body})
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    def call(self, code, action, token, body=None, status=200):
        response = self.client.post(f"/api/rooms/{code}/{action}/", data=json.dumps(body or {}),
                                    content_type="application/json", HTTP_X_MEMBER_TOKEN=token)
        self.assertEqual(response.status_code, status, response.content)
        return response.json() if response.content else None

    def state(self, code, token, status=200):
        response = self.client.get(f"/api/rooms/{code}/", HTTP_X_MEMBER_TOKEN=token)
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    def started(self, people=2):
        code, host, _ = self.create()
        guests = [self.join(code, f"Guest {i}")["token"] for i in range(people - 1)]
        state = self.call(code, "start", host)
        self.assertEqual(state["status"], "asking")
        return code, host, guests, state


class LobbyTests(RoomTestCase):
    def test_the_creator_hosts_and_friends_join_with_the_code(self):
        code, host, state = self.create(allergies=["egg"])
        self.assertRegex(code, r"^\d{4}$")
        self.assertEqual((state["status"], state["me"], state["host"]), ("lobby", 0, 0))
        joined = self.join(code)["state"]
        self.assertEqual(joined["me"], 1)
        self.assertEqual([(m["name"], m["allergies"]) for m in self.state(code, host)["members"]],
                         [("Jimin", ["egg"]), ("Seoyeon", [])])

    def test_a_signed_in_member_is_shown_by_username(self):
        user = User.objects.create_user("metchu_fan", password="a-long-password-1")
        response = self.client.post("/api/rooms/", data=json.dumps({"date": DAY}), content_type="application/json",
                                    HTTP_AUTHORIZATION=f"Token {tokens.issue(user)}")
        self.assertEqual(response.json()["state"]["members"][0]["name"], "metchu_fan")

    def test_a_guest_needs_a_name_and_a_code_must_exist(self):
        self.assertEqual(post(self.client, "/api/rooms/", {"date": DAY}).status_code, 400)
        code, _, _ = self.create()
        self.assertEqual(self.join(code, name=" ", status=400)["error"]["code"], "invalid_request")
        other = "0000" if code != "0000" else "0001"
        self.assertEqual(self.join(other, status=404)["error"]["code"], "room_not_found")

    def test_only_the_host_starts_and_only_with_two_people(self):
        code, host, _ = self.create()
        self.assertEqual(self.call(code, "start", host, status=409)["error"]["code"], "too_few_members")
        guest = self.join(code)["token"]
        self.assertEqual(self.call(code, "start", guest, status=403)["error"]["code"], "not_host")
        self.assertEqual(self.call(code, "start", host)["status"], "asking")

    def test_nobody_joins_after_the_start(self):
        code, _, _, _ = self.started()
        self.assertEqual(self.join(code, status=409)["error"]["code"], "room_started")

    def test_a_room_holds_eight(self):
        code, _, _ = self.create()
        for i in range(7):
            self.join(code, f"Friend {i}")
        self.assertEqual(self.join(code, status=409)["error"]["code"], "room_full")

    def test_strangers_cannot_read_a_room(self):
        code, _, _ = self.create()
        self.assertEqual(self.state(code, "not-a-token", status=403)["error"]["code"], "not_member")

    def test_a_member_who_leaves_the_lobby_is_not_in_the_group(self):
        code, host, _ = self.create()
        guest = self.join(code)["token"]
        self.join(code, "Doyun")
        self.assertEqual(self.call(code, "leave", guest, status=204), None)
        state = self.call(code, "start", host)
        self.assertEqual([m["name"] for m in state["members"]], ["Jimin", "Doyun"])


class JoinLimitTests(RoomTestCase):
    def test_ten_wrong_codes_wait_a_minute_and_only_for_that_phone(self):
        code, _, _ = self.create()
        wrong = "0000" if code != "0000" else "0001"
        for _ in range(rooms.JOIN_ATTEMPTS):
            self.join(wrong, status=404)
        self.assertEqual(self.join(code, status=429)["error"]["code"], "too_many_attempts")
        other_phone = self.client.post("/api/rooms/join/", data=json.dumps({"code": code, "name": "Doyun"}),
                                       content_type="application/json", HTTP_CF_CONNECTING_IP="203.0.113.7")
        self.assertEqual(other_phone.status_code, 201)
        self.clock.now += rooms.JOIN_WINDOW
        self.join(code)

    def test_right_codes_do_not_count(self):
        code, _, _ = self.create()
        for i in range(rooms.JOIN_ATTEMPTS + 1):
            self.join(code, f"Friend {i}", status=201 if i < 7 else 409)


class HostTests(RoomTestCase):
    def test_when_the_host_leaves_the_next_to_join_hosts(self):
        code, host, _ = self.create()
        guests = [self.join(code, name)["token"] for name in ("Seoyeon", "Doyun", "Minji")]
        self.call(code, "leave", host, status=204)
        state = self.state(code, guests[0])
        self.assertEqual((state["host"], state["me"]), (1, 1))
        self.assertEqual(self.state(code, host, status=403)["error"]["code"], "not_member")
        self.assertEqual(self.call(code, "start", guests[0])["status"], "asking")

    def test_the_role_skips_those_who_have_left(self):
        code, host, _ = self.create()
        tokens_ = [self.join(code, name)["token"] for name in ("A", "B", "C")]
        self.call(code, "leave", tokens_[0], status=204)
        self.call(code, "leave", host, status=204)
        self.assertEqual(self.state(code, tokens_[2])["host"], 2)
        self.call(code, "leave", tokens_[1], status=204)
        self.assertEqual(self.state(code, tokens_[2])["host"], 3)

    def test_the_role_passes_on_while_asking_and_on_the_result(self):
        code, host, guests, _ = self.started(people=4)
        self.call(code, "leave", host, status=204)
        self.assertEqual(self.state(code, guests[2])["host"], 1)
        self.assertEqual(self.call(code, "recommend-now", guests[0])["status"], "done")
        self.call(code, "leave", guests[0], status=204)
        self.assertEqual(self.state(code, guests[2])["host"], 2)
        self.assertEqual(self.call(code, "decide", guests[1], {"pick": 0})["decided"], 0)


class RoundTests(RoomTestCase):
    def test_everyone_gets_the_same_question_and_cannot_change_an_answer(self):
        code, host, (guest,), state = self.started()
        question = state["question"]
        self.assertEqual(self.state(code, guest)["question"]["question_id"], question["question_id"])
        self.assertEqual([o["id"] for o in question["options"]],
                         ["yes", "probably_yes", "any", "probably_no", "no", "unknown"])
        mine = self.call(code, "answer", host, {"question_id": question["question_id"], "answer_id": "yes"})
        self.assertEqual(mine["my_answer"], "yes")
        self.assertEqual([m["answered"] for m in mine["members"]], [True, False])
        again = self.call(code, "answer", host, {"question_id": question["question_id"], "answer_id": "no"},
                          status=409)
        self.assertEqual(again["state"]["my_answer"], "yes")
        after = self.call(code, "answer", guest, {"question_id": question["question_id"], "answer_id": "no"})
        self.assertTrue(after["round"] == 1 or after["status"] == "done")
        self.assertIsNone(after["my_answer"])

    def test_each_member_reads_the_question_in_their_language(self):
        code, host, _ = self.create(language="ko")
        guest = self.join(code, language="en")["token"]
        ko = self.call(code, "start", host)["question"]
        en = self.state(code, guest)["question"]
        self.assertEqual(ko["question_id"], en["question_id"])
        self.assertNotEqual(ko["text"], en["text"])
        self.assertNotEqual(ko["options"][0]["label"], en["options"][0]["label"])

    def test_silence_counts_as_not_sure_after_fifteen_seconds(self):
        code, host, (guest,), state = self.started()
        self.assertEqual((state["seconds_left"], state["round_seconds"]), (15, 15))
        engine = rooms.get(code).engine
        given = []
        real = engine.answer
        engine.answer = lambda member, question_id, answer_id: (given.append((member, answer_id)), real(member, question_id, answer_id))
        self.clock.now += 4
        self.call(code, "answer", host, {"question_id": state["question"]["question_id"], "answer_id": "yes"})
        self.assertEqual(self.state(code, guest)["seconds_left"], 11)
        self.clock.now += 11
        later = self.state(code, guest)
        self.assertEqual(given[:2], [(0, "yes"), (1, "unknown")])
        self.assertTrue(later["round"] == 1 or later["status"] == "done")
        if later["status"] == "asking":
            self.assertEqual(later["seconds_left"], 15)
            self.assertEqual([m["answered"] for m in later["members"]], [False, False])

    def test_the_host_picks_how_long_a_round_waits(self):
        code, host, created = self.create(round_seconds=30)
        self.assertEqual(created["round_seconds"], 30)
        self.join(code)
        state = self.call(code, "start", host)
        self.assertEqual((state["seconds_left"], state["round_seconds"]), (30, 30))
        self.clock.now += 15
        waiting = self.state(code, host)
        self.assertEqual((waiting["round"], waiting["seconds_left"]), (0, 15))
        self.clock.now += 15
        later = self.state(code, host)
        self.assertTrue(later["round"] == 1 or later["status"] == "done")

    def test_a_round_waits_only_one_of_the_offered_times(self):
        for seconds in (0, 20, 600, "15", 15.0, True, None):
            response = post(self.client, "/api/rooms/", {"name": "Jimin", "date": DAY, "round_seconds": seconds})
            self.assertEqual(response.status_code, 400, seconds)
            self.assertEqual(response.json()["error"]["code"], "invalid_request")
            self.assertIn("round_seconds", response.json()["error"]["message"])
        for seconds in rooms.ROUND_CHOICES:
            self.assertEqual(self.create(round_seconds=seconds)[2]["round_seconds"], seconds)
        self.assertEqual(self.create()[2]["round_seconds"], 15)

    def test_an_answer_after_the_deadline_is_stale(self):
        code, host, _, state = self.started()
        self.clock.now += rooms.ROUND_SECONDS
        reply = self.call(code, "answer", host, {"question_id": state["question"]["question_id"], "answer_id": "yes"},
                          status=409)
        self.assertEqual(reply["error"]["code"], "stale_step")

    def test_a_member_who_leaves_mid_round_no_longer_holds_it_up(self):
        code, host, (guest,), state = self.started()
        self.call(code, "leave", guest, status=204)
        after = self.call(code, "answer", host, {"question_id": state["question"]["question_id"], "answer_id": "yes"})
        self.assertTrue(after["round"] == 1 or after["status"] == "done")
        self.assertTrue(after["members"][1]["left"])

    def test_the_rounds_end_with_a_result_within_the_limit(self):
        code, host, (guest,), state = self.started()
        while state["status"] == "asking":
            self.clock.now += rooms.ROUND_SECONDS
            state = self.state(code, host)
        self.assertLessEqual(state["round"], state["max_rounds"])
        self.assertEqual(state["status"], "done")


class FitTests(TestCase):
    def test_great_only_among_a_members_best_tenth(self):
        satisfaction = np.array([0.0, .5, .6, .7, .8, .9, .91, .92, .93, .94, .95, .99])
        self.assertEqual(rooms._fit(satisfaction, 11), "great")
        self.assertEqual(rooms._fit(satisfaction, 9), "good")
        self.assertEqual(rooms._fit(np.array([.4, 0.0]), 0), "great")


class ResultTests(RoomTestCase):
    def test_only_the_host_stops_early_and_decides(self):
        code, host, (guest,), _ = self.started()
        self.assertEqual(self.call(code, "recommend-now", guest, status=403)["error"]["code"], "not_host")
        done = self.call(code, "recommend-now", host)
        self.assertEqual(done["status"], "done")
        picks = done["picks"]
        self.assertTrue(1 <= len(picks) <= 2)
        for pick in picks:
            self.assertEqual(set(pick), {"restaurant", "kind", "batch", "lat", "lng", "menus", "others", "votes", "voted"})
            self.assertEqual((pick["batch"], pick["votes"], pick["voted"]), (0, 0, False))
            suggested = {menu["food"]["food_id"] for menu in pick["menus"]}
            served = {name for name, restaurant, _, _ in MENUS if restaurant == pick["restaurant"]}
            self.assertEqual({dish["display_name"] for dish in pick["others"]} | {menu["food"]["name"] for menu in pick["menus"]},
                             served)
            self.assertFalse(suggested & {dish["food_id"] for dish in pick["others"]})
            self.assertEqual([menu["member_id"] for menu in pick["menus"]], [0, 1])
            for menu in pick["menus"]:
                self.assertEqual(set(menu), {"member_id", "food", "fit"})
                self.assertIn(menu["fit"], ("great", "good"))
                self.assertIn(pick["restaurant"], [o["restaurant"] for o in menu["food"]["offers"]])
        last = len(picks) - 1
        self.assertEqual(self.call(code, "decide", guest, {"pick": last}, status=403)["error"]["code"], "not_host")
        for wrong in (len(picks), -1, "0", picks[0]["restaurant"]):
            self.assertEqual(self.call(code, "decide", host, {"pick": wrong}, status=400)["error"]["code"],
                             "invalid_request", wrong)
        self.assertEqual(self.call(code, "decide", host, {"pick": last})["decided"], last)
        self.assertEqual(self.state(code, guest)["decided"], last)

    def test_a_members_allergies_only_change_their_own_dish(self):
        code, host, _ = self.create()
        guest = self.join(code, allergies=["pork"])["token"]
        self.call(code, "start", host)
        done = self.call(code, "recommend-now", host)
        names = {food.name: food for food in Food.objects.all()}
        for pick in done["picks"]:
            guest_food = pick["menus"][1]["food"]["name"]
            self.assertNotIn("pork", names[guest_food].allergens)
        self.assertEqual(self.state(code, guest)["status"], "done")

    def test_find_another_shows_restaurants_the_room_has_not_seen(self):
        code, host, (guest,), _ = self.started()
        done = self.call(code, "recommend-now", host)
        first = {pick["restaurant"] for pick in done["picks"]}
        self.assertEqual(len(first), 2)
        self.assertTrue(done["more"])
        again = self.call(code, "another", host)
        new = {pick["restaurant"] for pick in again["picks"] if pick["batch"] == 1}
        self.assertEqual(new, {"Red hall", "Soup hall", "Noodle hall"} - first)
        self.assertFalse(again["more"])
        self.assertEqual(self.state(code, guest)["picks"], again["picks"])
        self.assertEqual(self.call(code, "another", host, status=409)["error"]["code"], "stale_step")

    def test_earlier_restaurants_stay_where_they_were_after_find_another(self):
        code, host, _, _ = self.started()
        done = self.call(code, "recommend-now", host)
        picks = self.call(code, "another", host)["picks"]
        self.assertEqual(picks[:2], done["picks"])
        self.assertEqual([pick["batch"] for pick in picks], [0, 0, 1])

    def test_the_host_can_decide_on_an_earlier_restaurant(self):
        code, host, (guest,), _ = self.started()
        done = self.call(code, "recommend-now", host)
        self.call(code, "another", host)
        decided = self.call(code, "decide", host, {"pick": 1})
        self.assertEqual(decided["decided"], 1)
        self.assertEqual(self.state(code, guest)["picks"][1]["restaurant"], done["picks"][1]["restaurant"])

    def test_find_another_counts_only_places_where_everyone_can_eat(self):
        code, host, _ = self.create()
        self.join(code, allergies=["pork"])
        self.call(code, "start", host)
        done = self.call(code, "recommend-now", host)
        self.assertEqual({pick["restaurant"] for pick in done["picks"]}, {"Soup hall", "Noodle hall"})
        self.assertFalse(done["more"])

    def test_only_the_host_finds_another_and_only_before_deciding(self):
        code, host, (guest,), _ = self.started()
        self.assertEqual(self.call(code, "another", host, status=409)["error"]["code"], "stale_step")
        self.call(code, "recommend-now", host)
        self.assertEqual(self.call(code, "another", guest, status=403)["error"]["code"], "not_host")
        self.call(code, "decide", host, {"pick": 0})
        self.assertEqual(self.call(code, "another", host, status=409)["error"]["code"], "stale_step")

    def test_a_finished_room_keeps_only_its_result_until_the_host_decides(self):
        code, host, _, _ = self.started()
        done = self.call(code, "recommend-now", host)
        # The engine's per-member tables go with the questions; find another needs only the result.
        self.assertIsNone(rooms.get(code).engine)
        self.assertIsNotNone(rooms.get(code).result)
        decided = self.call(code, "decide", host, {"pick": 0})
        self.assertIsNone(rooms.get(code).result)
        self.assertEqual((decided["round"], decided["max_rounds"]), (0, 4))
        self.assertEqual(decided["picks"], done["picks"])
        self.assertFalse(decided["more"])

    def test_a_room_everyone_left_lets_its_result_go(self):
        code, host, (guest,), _ = self.started()
        self.call(code, "recommend-now", host)
        self.call(code, "leave", guest, status=204)
        self.assertIsNotNone(rooms.get(code).result)
        self.call(code, "leave", host, status=204)
        self.assertIsNone(rooms.get(code).result)

    def test_a_failed_pick_leaves_the_picks_and_their_votes_as_they_were(self):
        code, host, (guest,), _ = self.started()
        self.call(code, "recommend-now", host)
        self.call(code, "vote", guest, {"pick": 1, "agree": True})
        before = self.state(code, host)["picks"]
        room = rooms.get(code)
        with mock.patch("recommend.rooms._fit", side_effect=RuntimeError("broken")):
            self.assertRaises(RuntimeError, room.another, room.member(host))
        self.assertEqual(self.state(code, host)["picks"], before)

    def test_the_host_cannot_decide_before_the_result(self):
        code, host, _, _ = self.started()
        self.assertEqual(self.call(code, "decide", host, {"pick": 0}, status=409)["error"]["code"],
                         "stale_step")

    def test_the_host_decides_only_once(self):
        code, host, (guest,), _ = self.started()
        self.call(code, "recommend-now", host)
        self.call(code, "decide", host, {"pick": 0})
        again = self.call(code, "decide", host, {"pick": 1}, status=409)
        self.assertEqual(again["error"]["code"], "stale_step")
        self.assertEqual(again["state"]["decided"], 0)
        self.assertEqual(self.state(code, guest)["decided"], 0)



class VoteTests(RoomTestCase):
    def finished(self, people=3):
        code, host, guests, _ = self.started(people)
        self.call(code, "recommend-now", host)
        return code, host, guests

    def test_everyone_sees_how_many_agree_and_only_their_own_vote(self):
        code, host, (first, second) = self.finished()
        self.call(code, "vote", first, {"pick": 0, "agree": True})
        mine = self.call(code, "vote", host, {"pick": 0, "agree": True})["picks"][0]
        self.assertEqual((mine["votes"], mine["voted"]), (2, True))
        theirs = self.state(code, second)["picks"][0]
        self.assertEqual((theirs["votes"], theirs["voted"]), (2, False))

    def test_agreeing_twice_counts_once_and_a_vote_can_be_taken_back(self):
        code, host, _ = self.finished(2)
        self.call(code, "vote", host, {"pick": 0, "agree": True})
        self.assertEqual(self.call(code, "vote", host, {"pick": 0, "agree": True})["picks"][0]["votes"], 1)
        pick = self.call(code, "vote", host, {"pick": 0, "agree": False})["picks"][0]
        self.assertEqual((pick["votes"], pick["voted"]), (0, False))

    def test_each_restaurant_counts_its_own_votes(self):
        code, host, (guest, _) = self.finished()
        self.assertEqual(len(self.state(code, host)["picks"]), 2)
        self.call(code, "vote", host, {"pick": 1, "agree": True})
        picks = self.call(code, "vote", guest, {"pick": 1, "agree": True})["picks"]
        self.assertEqual([p["votes"] for p in picks], [0, 2])

    def test_a_vote_needs_a_suggested_restaurant_and_a_yes_or_no(self):
        code, host, _ = self.finished(2)
        count = len(self.state(code, host)["picks"])
        for body in ({"pick": count, "agree": True}, {"pick": "0", "agree": True}, {"pick": 0, "agree": "yes"}):
            self.assertEqual(self.call(code, "vote", host, body, status=400)["error"]["code"], "invalid_request", body)
        self.assertEqual(self.call(code, "vote", host, {"pick": 0}, status=400)["error"]["code"], "invalid_request")

    def test_votes_wait_for_the_result_and_stop_once_the_host_decides(self):
        code, host, (guest,), _ = self.started()
        self.assertEqual(self.call(code, "vote", guest, {"pick": 0, "agree": True}, status=409)["error"]["code"],
                         "stale_step")
        self.call(code, "recommend-now", host)
        self.call(code, "vote", guest, {"pick": 0, "agree": True})
        self.call(code, "decide", host, {"pick": 0})
        refused = self.call(code, "vote", guest, {"pick": 0, "agree": False}, status=409)
        self.assertEqual(refused["error"]["code"], "stale_step")
        self.assertEqual(refused["state"]["picks"][0]["votes"], 1)

    def test_a_member_who_leaves_takes_their_votes_along(self):
        code, host, (guest,) = self.finished(2)
        self.call(code, "vote", guest, {"pick": 0, "agree": True})
        self.call(code, "leave", guest, status=204)
        self.assertEqual(self.state(code, host)["picks"][0]["votes"], 0)

    def test_the_decided_restaurant_keeps_its_votes_when_someone_leaves(self):
        code, host, (guest,) = self.finished(2)
        self.call(code, "vote", guest, {"pick": 0, "agree": True})
        self.call(code, "decide", host, {"pick": 0})
        self.call(code, "leave", guest, status=204)
        self.assertEqual(self.state(code, host)["picks"][0]["votes"], 1)

    def test_after_the_decision_every_vote_is_stale(self):
        code, host, _ = self.finished(2)
        self.call(code, "decide", host, {"pick": 0})
        for body in ({"pick": 99, "agree": True}, {"pick": 0, "agree": "yes"}, {"pick": 0}):
            self.assertEqual(self.call(code, "vote", host, body, status=409)["error"]["code"], "stale_step", body)

    def test_find_another_keeps_the_votes_and_new_restaurants_start_without(self):
        code, host, (guest,) = self.finished(2)
        self.call(code, "vote", host, {"pick": 0, "agree": True})
        self.call(code, "vote", guest, {"pick": 1, "agree": True})
        again = self.call(code, "another", host)
        self.assertEqual([(p["votes"], p["voted"]) for p in again["picks"]], [(1, True), (1, False), (0, False)])

    def test_members_still_agree_with_earlier_restaurants(self):
        code, host, (guest,) = self.finished(2)
        self.call(code, "another", host)
        picks = self.call(code, "vote", guest, {"pick": 0, "agree": True})["picks"]
        self.assertEqual([p["votes"] for p in picks], [1, 0, 0])

    def test_a_member_who_leaves_takes_their_votes_from_every_find(self):
        code, host, (guest,) = self.finished(2)
        self.call(code, "vote", guest, {"pick": 0, "agree": True})
        self.call(code, "another", host)
        self.call(code, "vote", guest, {"pick": 2, "agree": True})
        self.call(code, "leave", guest, status=204)
        self.assertEqual([p["votes"] for p in self.state(code, host)["picks"]], [0, 0, 0])


class MergedOfferTests(TestCase):
    """Equivalent store lines merge under the lowest line ID; the allergen filter drops lines first."""

    def setUp(self):
        from menus.personal import offers
        from unittest.mock import patch
        patcher=patch.object(offers,'resolve',return_value='food_009')
        patcher.start();self.addCleanup(patcher.stop)

        features = {key: 0.5 for key in FEATURE_KEYS} | {"pork": 0.9}
        stew = Food.objects.create(name="김치찌개", is_food=True, features=features,
                                   feature_std={key: 0.1 for key in FEATURE_KEYS},
                                   feature_version=FEATURE_VERSION, allergen_version=ALLERGEN_VERSION)
        places = [Restaurant.objects.create(code=f"MA000{i}", name=name, source="naver", lat=37.48 + i / 1000, lng=126.95)
                  for i, name in enumerate(("가게 A", "가게 B"))]
        # Different descriptions give the lines different IDs; the same components still merge them.
        # The line with pork comes first, so the merged menu takes its ID.
        for place, tags, description in zip(places, (["pork"], []), ("돼지고기 김치찌개", "참치 김치찌개")):
            StoreMenu.objects.create(restaurant=place, raw_name="김치찌개", description=description, food=stew,
                                     price=8000, allergens=tags, allergen_version=ALLERGEN_VERSION)

    def test_an_allergic_member_keeps_the_safe_offers_of_a_merged_menu(self):
        response = post(self.client, "/api/rooms/", {"name": "Jimin", "area": "snu_station"})
        code, host = response.json()["state"]["code"], response.json()["token"]
        post(self.client, "/api/rooms/join/", {"code": code, "name": "Seoyeon", "allergies": ["pork"]})
        started = self.client.post(f"/api/rooms/{code}/start/", content_type="application/json",
                                   HTTP_X_MEMBER_TOKEN=host)
        self.assertEqual(started.status_code, 200, started.content)
        done = started.json()  # one menu: nothing to ask
        self.assertEqual(done["status"], "done")
        self.assertEqual([pick["restaurant"] for pick in done["picks"]], ["가게 B"])

    def test_the_host_areas_reach_both_stations(self):
        response = post(self.client, "/api/rooms/", {"name": "Jimin", "areas": ["snu_station", "nakseongdae"]})
        code, host = response.json()["state"]["code"], response.json()["token"]
        post(self.client, "/api/rooms/join/", {"code": code, "name": "Seoyeon"})
        done = self.client.post(f"/api/rooms/{code}/start/", content_type="application/json",
                                HTTP_X_MEMBER_TOKEN=host).json()
        self.assertEqual(done["status"], "done")
        self.assertEqual(post(self.client, "/api/rooms/", {"name": "Jimin", "areas": []}).status_code, 400)

    def test_the_host_area_leaves_out_restaurants_near_the_other_station(self):
        response = post(self.client, "/api/rooms/", {"name": "Jimin", "area": "nakseongdae"})
        code, host = response.json()["state"]["code"], response.json()["token"]
        post(self.client, "/api/rooms/join/", {"code": code, "name": "Seoyeon"})
        started = self.client.post(f"/api/rooms/{code}/start/", content_type="application/json",
                                   HTTP_X_MEMBER_TOKEN=host)
        self.assertEqual(started.json()["error"]["code"], "group_unavailable")
