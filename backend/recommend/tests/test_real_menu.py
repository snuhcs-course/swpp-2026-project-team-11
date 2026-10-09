# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Whole sessions against the shared 2026-09-29 fixture, the data the demo runs on."""
import random

from django.test import TestCase, override_settings

from .helpers import ANSWER_IDS, DAY, check_state, post


class RealMenuTestCase(TestCase):
    fixtures = ["menus_2026-09-29"]

    def start(self, meal="LU"):
        response = post(self.client, "/api/sessions/", {"date": DAY, "meal": meal})
        self.assertEqual(response.status_code, 201)
        state = response.json()
        check_state(self, state)
        return state, f"/api/sessions/{state['session_id']}/"

    def call(self, url, body=None, status=200):
        response = post(self.client, url, body)
        self.assertEqual(response.status_code, status, response.content)
        return response.json()

    def answer_until_guess(self, state, url, answer_id):
        answered = 0
        while state["step"]["type"] == "question":
            self.assertEqual(state["step"]["question_count"], answered)
            state = self.call(url + "answer/", {"question_id": state["step"]["question_id"],
                                                 "answer_id": answer_id})
            check_state(self, state)
            answered += 1
            self.assertLessEqual(answered, 23, "More answers than the question bank holds")
        return state, answered


class QuestionCapTests(RealMenuTestCase):
    @override_settings(RECOMMEND_MAX_QUESTIONS=10)
    def test_every_answer_choice_reaches_a_guess_within_a_cap_of_ten(self):
        for answer_id in ANSWER_IDS:
            for meal in ("LU", "DN", None):
                with self.subTest(answer=answer_id, meal=meal):
                    state, url = self.start(meal)
                    self.assertEqual(state["max_questions"], 10)
                    state, answered = self.answer_until_guess(state, url, answer_id)
                    self.assertEqual(state["step"]["type"], "guess")
                    self.assertLessEqual(answered, 10)
                    self.assertEqual(state["step"]["question_count"], answered)

    @override_settings(RECOMMEND_MAX_QUESTIONS=4)
    def test_no_more_questions_after_the_cap_even_when_guesses_are_rejected(self):
        state, url = self.start()
        state, answered = self.answer_until_guess(state, url, "unknown")
        self.assertEqual(answered, 4)
        offered = []
        for _ in range(25):
            self.assertEqual(state["step"]["type"], "guess")
            self.assertEqual(state["step"]["question_count"], 4)
            offered.append(state["step"]["guess_id"])
            state = self.call(url + "feedback/", {"guess_id": offered[-1], "accepted": False})
            check_state(self, state)
            if state["step"]["type"] == "unavailable":
                break
        self.assertEqual(len(offered), len(set(offered)), "A rejected guess was offered again")

    @override_settings(RECOMMEND_MAX_QUESTIONS=3)
    def test_undo_below_the_cap_asks_the_same_question_again(self):
        state, url = self.start()
        questions = []
        while state["step"]["type"] == "question":
            questions.append(state["step"])
            state = self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "any"})
        self.assertEqual(self.call(url + "undo/")["step"], questions[-1])
        # A different answer to the last question is allowed after undo.
        state = self.call(url + "answer/", {"question_id": questions[-1]["question_id"], "answer_id": "yes"})
        self.assertEqual(state["step"]["type"], "guess")

    @override_settings(RECOMMEND_MAX_QUESTIONS=None)
    def test_without_a_cap_the_session_still_ends_in_a_guess(self):
        state, url = self.start()
        state, answered = self.answer_until_guess(state, url, "unknown")
        self.assertEqual(state["step"]["type"], "guess")
        self.assertGreater(answered, 10)


class GroupGuessTests(RealMenuTestCase):
    def first_group_guess(self):
        """Reject guesses until the engine proposes a group."""
        state, url = self.start()
        state, _ = self.answer_until_guess(state, url, "any")
        for _ in range(40):
            if state["step"]["type"] != "guess":
                break
            if state["step"]["target_kind"] == "group":
                return state, url
            state = self.call(url + "feedback/", {"guess_id": state["step"]["guess_id"], "accepted": False})
        self.fail("The engine never proposed a group on the fixture")

    def test_accepting_a_group_recommends_the_dish_that_was_shown(self):
        guess, url = self.first_group_guess()
        step = guess["step"]
        self.assertGreater(len(step["group"]["members"]), 1)
        self.assertEqual(step["guess_id"], step["group"]["group_id"])
        final = self.call(url + "feedback/", {"guess_id": step["guess_id"], "accepted": True})
        check_state(self, final)
        self.assertEqual(final["step"]["type"], "recommendation")
        self.assertEqual(final["step"]["food"], step["food"])
        self.assertEqual(final["step"]["group"], step["group"])

    def test_rejecting_a_group_removes_all_its_dishes(self):
        guess, url = self.first_group_guess()
        gone = {member["food_id"] for member in guess["step"]["group"]["members"]}
        state = self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"], "accepted": False})
        for _ in range(30):
            if state["step"]["type"] != "guess":
                break
            self.assertNotIn(state["step"]["food"]["food_id"], gone)
            for member in state["step"].get("group", {}).get("members", []):
                self.assertNotIn(member["food_id"], gone)
            state = self.call(url + "feedback/", {"guess_id": state["step"]["guess_id"], "accepted": False})

    def test_recommend_now_always_names_one_dish(self):
        state, url = self.start()
        for _ in range(10):
            step = self.call(url + "recommend-now/")["step"]
            self.assertEqual(step["target_kind"], "food")
            self.assertEqual(step["guess_id"], f"food:{step['food']['food_id']}")
            self.assertNotIn("group", step)
            self.call(url + "feedback/", {"guess_id": step["guess_id"], "accepted": False})


class RejectEverythingTests(RealMenuTestCase):
    def test_rejecting_every_proposal_exhausts_the_lunch_menu(self):
        state, url = self.start()
        offered = []
        for _ in range(250):
            if state["step"]["type"] == "unavailable":
                break
            if state["step"]["type"] == "question":
                state = self.call(url + "recommend-now/")
            offered.append(state["step"]["food"]["food_id"])
            state = self.call(url + "feedback/", {"guess_id": state["step"]["guess_id"], "accepted": False})
            check_state(self, state)
        self.assertEqual(state["step"]["reason"], "candidates_exhausted")
        self.assertEqual(len(offered), len(set(offered)), "A rejected dish was offered again")
        self.assertLessEqual(len(offered), state["candidate_count"])


class RandomSessionTests(RealMenuTestCase):
    """Seeded random taps, including stale and repeated ones. Nothing may be a 500,
    every state must decode, and Back must return exactly the previous state."""

    def play(self, seed, meal):
        rng = random.Random(seed)
        state, url = self.start(meal)
        history = []   # states that Back should return to, oldest first

        def moved(new):
            check_state(self, new)
            self.assertEqual(new["can_undo"], bool(history) or new != state)
            return new

        for _ in range(60):
            kind = state["step"]["type"]
            roll = rng.random()
            if roll < 0.12:
                expected = history.pop() if history else state
                state = self.call(url + "undo/")
                self.assertEqual(state, expected, f"seed {seed}: undo did not restore the previous state")
                check_state(self, state)
            elif roll < 0.20:
                # A request for a step that is not on screen must change nothing.
                stale = (("feedback/", {"guess_id": "food:1", "accepted": True}) if kind == "question"
                         else ("answer/", {"question_id": "q:rice", "answer_id": "yes"}))
                body = self.call(url + stale[0], stale[1], 409)
                self.assertEqual(body["state"], state)
            elif roll < 0.30:
                new = self.call(url + "recommend-now/")
                if new != state:
                    history.append(state)
                    self.assertEqual(kind, "question")
                state = moved(new)
            elif kind == "question":
                history.append(state)
                state = moved(self.call(url + "answer/", {"question_id": state["step"]["question_id"],
                                                           "answer_id": rng.choice(ANSWER_IDS)}))
            elif kind == "guess":
                history.append(state)
                state = moved(self.call(url + "feedback/", {"guess_id": state["step"]["guess_id"],
                                                             "accepted": rng.random() < 0.25}))
            else:
                # Ended: only Back can change the session.
                self.assertEqual(self.call(url + "recommend-now/"), state)
            self.assertEqual(self.client.get(url).json(), state)

    def test_random_sessions(self):
        for seed in range(24):
            with self.subTest(seed=seed):
                self.play(seed, ("LU", "DN", None)[seed % 3])

    @override_settings(RECOMMEND_MAX_QUESTIONS=2)
    def test_random_sessions_with_a_tight_cap(self):
        for seed in range(100, 108):
            with self.subTest(seed=seed):
                self.play(seed, "LU")

    @override_settings(RECOMMEND_MAX_QUESTIONS=None)
    def test_random_sessions_without_a_cap(self):
        for seed in range(200, 206):
            with self.subTest(seed=seed):
                self.play(seed, "LU")
