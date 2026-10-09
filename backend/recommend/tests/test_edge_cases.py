# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Requests a broken or impatient client can send. None of them may be a 500."""
import datetime
import os
import threading
import unittest
from unittest import mock

from django.conf import settings
from django.test import Client, TestCase, override_settings

from recommend import sessions

from .helpers import DAY, add_food, check_state, post


class SmallMenuTestCase(TestCase):
    """Three dishes: two noodle dishes that form a group, and one rice dish."""

    def setUp(self):
        add_food("Beef noodles", "Noodles", beef=0.9, noodle=0.9, rice=0.1, price=6000)
        add_food("Chicken noodles", "Noodles", chicken=0.9, noodle=0.9, rice=0.1, price=None)
        add_food("Rice bowl", "", rice=0.9, noodle=0.1)

    def start(self, **body):
        response = post(self.client, "/api/sessions/", {"date": DAY, "meal": "LU", **body})
        self.assertEqual(response.status_code, 201)
        state = response.json()
        return state, f"/api/sessions/{state['session_id']}/"

    def call(self, url, body=None, status=200):
        response = post(self.client, url, body)
        self.assertEqual(response.status_code, status, response.content)
        return response.json()


class MalformedRequestTests(SmallMenuTestCase):
    def test_bodies_that_are_not_json_objects(self):
        _, url = self.start()
        for raw in (b"[", b"null", b"[]", b'"text"', b"42", b"\xff\xfe", b"{'single': 1}"):
            for path in ("/api/sessions/", url + "answer/", url + "feedback/"):
                response = self.client.post(path, data=raw, content_type="application/json")
                self.assertEqual(response.status_code, 400, (path, raw))
                self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_answer_fields_of_the_wrong_type(self):
        state, url = self.start()
        question_id = state["step"]["question_id"]
        for answer_id in (None, 1, True, [], ["yes"], {"id": "yes"}, "", "YES", " yes"):
            body = self.call(url + "answer/", {"question_id": question_id, "answer_id": answer_id}, 400)
            self.assertEqual(body["error"]["code"], "invalid_request", answer_id)
        for bad_question in (None, 1, [], {}, "", "q:not-a-feature", question_id.upper()):
            body = self.call(url + "answer/", {"question_id": bad_question, "answer_id": "yes"}, 409)
            self.assertEqual(body["error"]["code"], "stale_step", bad_question)
        # Nothing above was applied.
        self.assertEqual(self.client.get(url).json(), state)

    def test_feedback_fields_of_the_wrong_type(self):
        _, url = self.start()
        guess = self.call(url + "recommend-now/")
        guess_id = guess["step"]["guess_id"]
        for accepted in (None, 1, 0, "true", "false", [], {}):
            body = self.call(url + "feedback/", {"guess_id": guess_id, "accepted": accepted}, 400)
            self.assertEqual(body["error"]["code"], "invalid_request", accepted)
        self.call(url + "feedback/", {"accepted": True}, 400)
        self.call(url + "feedback/", {"guess_id": guess_id}, 400)
        for bad_guess in (None, 1, [], {}, "", "food:999999", "group:unknown"):
            self.call(url + "feedback/", {"guess_id": bad_guess, "accepted": True}, 409)
        self.assertEqual(self.client.get(url).json(), guess)

    def test_create_rejects_bad_date_meal_and_engine(self):
        for body in ({"date": "2026-13-01"}, {"date": "29/09/2026"}, {"date": 20260929},
                     {"date": ""}, {"date": ["2026-09-29"]}, {"meal": "lu"}, {"meal": ""},
                     {"meal": 1}, {"meal": ["LU"]}, {"meal": {"id": "LU"}},
                     {"engine": "other"}, {"engine": ""}, {"engine": 1}, {"engine": ["llm"]}):
            response = post(self.client, "/api/sessions/", body)
            self.assertEqual(response.status_code, 400, body)

    def test_create_ignores_unknown_fields_and_accepts_an_empty_body(self):
        state, _ = self.start(extra=[1, 2])
        check_state(self, state)
        response = self.client.post("/api/sessions/", data=b"", content_type="application/json")
        self.assertEqual(response.status_code, 201)
        check_state(self, response.json())

    def test_wrong_http_methods(self):
        _, url = self.start()
        self.assertEqual(self.client.get("/api/sessions/").status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 405)
        for action in ("answer/", "feedback/", "recommend-now/", "undo/"):
            self.assertEqual(self.client.get(url + action).status_code, 405)
            self.assertEqual(self.client.put(url + action).status_code, 405)

    def test_every_action_on_an_unknown_session_is_404(self):
        for action, body in (("answer/", {"question_id": "q:rice", "answer_id": "yes"}),
                             ("feedback/", {"guess_id": "food:1", "accepted": True}),
                             ("recommend-now/", None), ("undo/", None)):
            body = self.call("/api/sessions/missing/" + action, body, 404)
            self.assertEqual(body["error"]["code"], "session_not_found")
        # A malformed body on a missing session is still "not found", not a crash.
        response = self.client.post("/api/sessions/missing/answer/", data=b"[", content_type="application/json")
        self.assertEqual(response.status_code, 404)


class StepOrderTests(SmallMenuTestCase):
    def test_action_for_the_other_step_type_is_stale(self):
        state, url = self.start()
        body = self.call(url + "feedback/", {"guess_id": "food:1", "accepted": True}, 409)
        self.assertEqual(body["state"], state)

        guess = self.call(url + "recommend-now/")
        body = self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "yes"}, 409)
        self.assertEqual(body["state"], guess)

    def test_feedback_for_a_previous_guess_is_stale(self):
        _, url = self.start()
        first = self.call(url + "recommend-now/")["step"]
        self.call(url + "feedback/", {"guess_id": first["guess_id"], "accepted": False})
        self.call(url + "recommend-now/")
        body = self.call(url + "feedback/", {"guess_id": first["guess_id"], "accepted": True}, 409)
        self.assertEqual(body["state"]["step"]["type"], "guess")
        self.assertNotEqual(body["state"]["step"]["guess_id"], first["guess_id"])

    def test_ended_session_refuses_changes_but_allows_undo(self):
        state, url = self.start()
        guess = self.call(url + "recommend-now/")
        final = self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"], "accepted": True})
        self.assertEqual(final["step"]["type"], "recommendation")
        self.assertNotIn("guess_id", final["step"])
        check_state(self, final)

        self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"], "accepted": True}, 409)
        self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"], "accepted": False}, 409)
        self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "yes"}, 409)
        self.assertEqual(self.call(url + "recommend-now/"), final)
        self.assertEqual(self.client.get(url).json(), final)

        # Undo reopens the guess, and the user can change their mind.
        self.assertEqual(self.call(url + "undo/"), guess)
        after = self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"], "accepted": False})
        self.assertNotEqual(after["step"]["type"], "recommendation")

    def test_undo_on_a_new_session_changes_nothing(self):
        state, url = self.start()
        for _ in range(3):
            self.assertEqual(self.call(url + "undo/"), state)

    def test_undo_walks_back_every_step_in_order(self):
        state, url = self.start()
        history = [state]
        while state["step"]["type"] == "question":
            state = self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "any"})
            history.append(state)
        state = self.call(url + "feedback/", {"guess_id": state["step"]["guess_id"], "accepted": False})
        history.append(state)
        for expected in reversed(history[:-1]):
            self.assertEqual(self.call(url + "undo/"), expected)
        self.assertFalse(self.client.get(url).json()["can_undo"])

    def test_a_question_is_never_asked_twice(self):
        state, url = self.start(meal=None)
        seen = []
        while state["step"]["type"] == "question":
            seen.append(state["step"]["question_id"])
            state = self.call(url + "answer/", {"question_id": seen[-1], "answer_id": "unknown"})
        self.assertEqual(len(seen), len(set(seen)))

    def test_get_state_never_changes_the_session(self):
        state, url = self.start()
        for _ in range(3):
            self.assertEqual(self.client.get(url).json(), state)
        answered = self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "no"})
        for _ in range(3):
            self.assertEqual(self.client.get(url).json(), answered)


class ExhaustionTests(SmallMenuTestCase):
    def reject_everything(self, url):
        state = self.client.get(url).json()
        rejected = []
        for _ in range(20):
            if state["step"]["type"] == "unavailable":
                return state, rejected
            if state["step"]["type"] == "question":
                state = self.call(url + "recommend-now/")
            check_state(self, state)
            rejected.append(state["step"]["food"]["food_id"])
            state = self.call(url + "feedback/", {"guess_id": state["step"]["guess_id"], "accepted": False})
        self.fail("Rejecting every dish never ended the session")

    def test_rejecting_every_dish_ends_with_candidates_exhausted(self):
        _, url = self.start()
        state, rejected = self.reject_everything(url)
        self.assertEqual(state["step"]["reason"], "candidates_exhausted")
        self.assertEqual(len(rejected), len(set(rejected)), "A rejected dish was offered again")
        check_state(self, state)

        # The dead end is stable, and Back still works.
        self.assertEqual(self.call(url + "recommend-now/"), state)
        self.call(url + "answer/", {"question_id": "q:rice", "answer_id": "yes"}, 409)
        self.call(url + "feedback/", {"guess_id": "food:1", "accepted": True}, 409)
        self.assertEqual(self.call(url + "undo/")["step"]["type"], "guess")

    def test_rejected_dish_is_not_offered_again(self):
        _, url = self.start()
        first = self.call(url + "recommend-now/")["step"]
        self.call(url + "feedback/", {"guess_id": first["guess_id"], "accepted": False})
        second = self.call(url + "recommend-now/")["step"]
        self.assertNotEqual(second["food"]["food_id"], first["food"]["food_id"])

    def test_a_single_dish_menu_can_be_accepted_or_exhausted(self):
        add_food("Only breakfast", meal="BR")
        state, url = self.start(meal="BR")
        self.assertEqual(state["candidate_count"], 1)
        check_state(self, state)
        guess = state if state["step"]["type"] == "guess" else self.call(url + "recommend-now/")
        self.assertEqual(guess["step"]["food"]["name"], "Only breakfast")
        rejected = self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"], "accepted": False})
        self.assertEqual(rejected["step"]["reason"], "candidates_exhausted")
        self.assertEqual(self.call(url + "undo/"), guess)
        accepted = self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"], "accepted": True})
        self.assertEqual(accepted["step"]["type"], "recommendation")


class MenuDataTests(SmallMenuTestCase):
    def test_empty_menu_session_survives_every_action(self):
        state, url = self.start(date="2026-01-01")
        self.assertEqual((state["candidate_count"], state["step"]["reason"]), (0, "empty_candidates"))
        check_state(self, state)
        self.assertFalse(state["can_undo"])
        self.assertEqual(self.call(url + "recommend-now/"), state)
        self.assertEqual(self.call(url + "undo/"), state)
        self.call(url + "answer/", {"question_id": "q:rice", "answer_id": "yes"}, 409)
        self.call(url + "feedback/", {"guess_id": "food:1", "accepted": True}, 409)

    def test_meal_filter_and_whole_day(self):
        add_food("Dinner stew", meal="DN")
        self.assertEqual(self.start(meal="LU")[0]["candidate_count"], 3)
        self.assertEqual(self.start(meal="DN")[0]["candidate_count"], 1)
        self.assertEqual(self.start(meal="BR")[0]["candidate_count"], 0)
        whole_day, _ = self.start(meal=None)
        self.assertEqual((whole_day["candidate_count"], whole_day["meal"]), (4, None))

    def test_missing_price_and_several_cafeterias_reach_the_client(self):
        add_food("Chicken noodles", restaurant="Second hall", price=7000)
        _, url = self.start()
        offers = {}
        for _ in range(3):
            step = self.call(url + "recommend-now/")["step"]
            offers[step["food"]["name"]] = step["food"]["offers"]
            self.call(url + "feedback/", {"guess_id": step["guess_id"], "accepted": False})
        self.assertEqual(sorted((o["restaurant"], o["price"]) for o in offers["Chicken noodles"]),
                         [("Second hall", 7000), ("Test hall", None)])

    def test_dishes_sharing_a_display_name_keep_separate_ids(self):
        add_food("Bibimbap A", display_name="Bibimbap", restaurant="Hall A")
        add_food("Bibimbap B", display_name="Bibimbap", restaurant="Hall B")
        state, url = self.start()
        self.assertEqual(state["candidate_count"], 5)
        final = None
        for _ in range(8):
            step = self.call(url + "recommend-now/")["step"]
            if step["food"]["display_name"] == "Bibimbap":
                final = self.call(url + "feedback/", {"guess_id": step["guess_id"], "accepted": True})["step"]
                self.assertEqual(final["food"], step["food"])
                break
            self.call(url + "feedback/", {"guess_id": step["guess_id"], "accepted": False})
        self.assertIsNotNone(final, "The shared-name dish was never offered")

    def test_menu_change_does_not_disturb_a_running_session(self):
        state, url = self.start()
        add_food("Late addition", rice=0.9)
        self.assertEqual(self.client.get(url).json(), state)
        answered = self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "yes"})
        self.assertEqual(answered["candidate_count"], 3)
        self.assertEqual(self.start()[0]["candidate_count"], 4)

    def test_non_ascii_names_round_trip(self):
        add_food("닭갈비볶음밥&고구마맛탕", "볶음밥", display_name="닭갈비볶음밥", restaurant="301동식당", meal="DN")
        state, url = self.start(meal="DN")
        step = self.call(url + "recommend-now/")["step"]
        self.assertEqual((step["food"]["name"], step["food"]["display_name"]),
                         ("닭갈비볶음밥&고구마맛탕", "닭갈비볶음밥"))
        self.assertEqual(step["food"]["offers"][0]["restaurant"], "301동식당")


class SettingsTests(SmallMenuTestCase):
    def test_today_in_seoul_is_the_default_date(self):
        with override_settings(RECOMMEND_DEFAULT_DATE=None), \
                mock.patch("recommend.sessions.timezone.localdate", return_value=datetime.date(2026, 9, 29)):
            state = post(self.client, "/api/sessions/").json()
        self.assertEqual((state["date"], state["candidate_count"]), (DAY, 3))

    @override_settings(RECOMMEND_DEFAULT_DATE=datetime.date(2026, 1, 1))
    def test_client_date_overrides_the_default(self):
        self.assertEqual(self.start()[0]["candidate_count"], 3)
        self.assertEqual(post(self.client, "/api/sessions/").json()["date"], "2026-01-01")

    @unittest.skipIf(os.environ.get("METCHU_MAX_QUESTIONS"), "this environment sets a question limit")
    def test_there_is_no_question_limit_unless_the_environment_sets_one(self):
        self.assertIsNone(settings.RECOMMEND_MAX_QUESTIONS)
        state, _ = self.start()
        self.assertIsNone(state["max_questions"])

    @override_settings(RECOMMEND_MAX_QUESTIONS=None)
    def test_no_cap_is_reported_as_null(self):
        state, _ = self.start()
        self.assertIsNone(state["max_questions"])
        check_state(self, state)

    @override_settings(RECOMMEND_MAX_QUESTIONS=1)
    def test_cap_of_one_allows_exactly_one_answer(self):
        state, url = self.start()
        self.assertEqual(state["step"]["type"], "question")
        state = self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "unknown"})
        self.assertEqual(state["step"]["type"], "guess")
        state = self.call(url + "feedback/", {"guess_id": state["step"]["guess_id"], "accepted": False})
        self.assertIn(state["step"]["type"], ("guess", "unavailable"))

    def test_cap_change_does_not_affect_a_running_session(self):
        with override_settings(RECOMMEND_MAX_QUESTIONS=2):
            state, url = self.start()
        with override_settings(RECOMMEND_MAX_QUESTIONS=7):
            self.assertEqual(self.client.get(url).json()["max_questions"], 2)


class SessionStoreTests(SmallMenuTestCase):
    def test_sessions_do_not_share_state(self):
        first, first_url = self.start()
        second, second_url = self.start()
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.call(first_url + "answer/", {"question_id": first["step"]["question_id"], "answer_id": "yes"})
        self.call(first_url + "recommend-now/")
        self.assertEqual(self.client.get(second_url).json(), second)

    def test_oldest_session_is_dropped_when_the_store_is_full(self):
        with mock.patch.object(sessions, "MAX_SESSIONS", 2), mock.patch.dict(sessions._sessions, clear=True):
            first, first_url = self.start()
            _, second_url = self.start()
            _, third_url = self.start()
            self.assertEqual(self.client.get(first_url).status_code, 404)
            self.assertEqual(self.client.get(second_url).status_code, 200)
            self.assertEqual(self.client.get(third_url).status_code, 200)
            body = self.call(first_url + "answer/", {"question_id": first["step"]["question_id"], "answer_id": "yes"}, 404)
            self.assertEqual(body["error"]["code"], "session_not_found")

    def test_simultaneous_identical_answers_apply_once(self):
        state, url = self.start()
        body = {"question_id": state["step"]["question_id"], "answer_id": "yes"}
        statuses, barrier = [], threading.Barrier(8)

        def tap():
            barrier.wait()
            statuses.append(post(Client(), url + "answer/", body).status_code)

        threads = [threading.Thread(target=tap) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(statuses), [200] + [409] * 7)
        self.assertEqual(self.client.get(url).json()["step"]["question_count"], 1)

    def test_requests_for_one_session_wait_for_each_other(self):
        state, url = self.start()
        session = sessions.get(state["session_id"])
        requests = {
            "answer/": {"question_id": state["step"]["question_id"], "answer_id": "yes"},
            "feedback/": {"guess_id": "food:1", "accepted": True},
            "recommend-now/": None, "undo/": None,
        }
        done = {path: threading.Event() for path in [*requests, "state"]}

        def send(path):
            if path == "state":
                Client().get(url)
            else:
                post(Client(), url + path, requests[path])
            done[path].set()

        threads = [threading.Thread(target=send, args=(path,)) for path in done]
        with session.lock:
            for thread in threads:
                thread.start()
            for path, event in done.items():
                self.assertFalse(event.wait(0.3), f"{path} ran while another request held the session")
        for thread in threads:
            thread.join(5)
        self.assertTrue(all(event.is_set() for event in done.values()))
