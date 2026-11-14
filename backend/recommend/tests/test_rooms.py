"""Group rooms over HTTP: joining, the host's controls, the shared rounds and their time limit."""
import json
from unittest import mock

import numpy as np

from django.contrib.auth.models import User
from django.test import TestCase

from accounts import tokens
from menus.allergens import ALLERGEN_VERSION
from menus.models import Food
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


class HostTests(RoomTestCase):
    def test_when_the_host_leaves_someone_else_hosts(self):
        code, host, _ = self.create()
        guests = [self.join(code, name)["token"] for name in ("Seoyeon", "Doyun")]
        with mock.patch.object(rooms.random, "choice", lambda members: members[-1]):
            self.call(code, "leave", host, status=204)
        state = self.state(code, guests[1])
        self.assertEqual((state["host"], state["me"]), (2, 2))
        self.assertEqual(self.state(code, host, status=403)["error"]["code"], "not_member")
        self.assertEqual(self.call(code, "start", guests[1])["status"], "asking")

    def test_the_new_host_is_one_of_those_still_here(self):
        code, host, _ = self.create()
        tokens_ = [self.join(code, name)["token"] for name in ("A", "B", "C")]
        self.call(code, "leave", tokens_[0], status=204)
        self.call(code, "leave", host, status=204)
        self.assertIn(self.state(code, tokens_[1])["host"], (2, 3))


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
            self.assertEqual(set(pick), {"restaurant", "kind", "lat", "lng", "distance_m", "menus", "others"})
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
        restaurant = picks[0]["restaurant"]
        self.assertEqual(self.call(code, "decide", guest, {"restaurant": restaurant}, status=403)["error"]["code"],
                         "not_host")
        self.assertEqual(self.call(code, "decide", host, {"restaurant": "Nowhere"}, status=400)["error"]["code"],
                         "invalid_request")
        self.assertEqual(self.call(code, "decide", host, {"restaurant": restaurant})["decided"], restaurant)
        self.assertEqual(self.state(code, guest)["decided"], restaurant)

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

    def test_the_host_cannot_decide_before_the_result(self):
        code, host, _, _ = self.started()
        self.assertEqual(self.call(code, "decide", host, {"restaurant": "Red hall"}, status=409)["error"]["code"],
                         "stale_step")
