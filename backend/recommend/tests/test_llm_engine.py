"""The same REST API running the P13/P14 LLM engine, with a fake LLM (no API key)."""
import functools
from unittest import mock

from django.test import override_settings

from question_engines.llm import LLMEngine
from question_engines.llm.prompt import FALLBACK_QUESTIONS
from question_engines.llm.tests.helpers import FakeLLM, ask, recommend

from .helpers import DAY, check_state, post
from .test_edge_cases import SmallMenuTestCase

BEEF, CHICKEN, RICE = "Beef noodles", "Chicken noodles", "Rice bowl"


class LLMSessionTestCase(SmallMenuTestCase):
    def use_llm(self, *replies):
        """Sessions created from here on talk to a fake LLM that plays `replies` in order."""
        llm = FakeLLM(*replies)
        patcher = mock.patch("recommend.sessions.LLMEngine", functools.partial(LLMEngine, llm=llm))
        patcher.start()
        self.addCleanup(patcher.stop)
        return llm

    def start(self, engine="llm", **body):
        """`engine=None` sends no engine, leaving the choice to the server."""
        return super().start(**body, **({"engine": engine} if engine else {}))


class EngineChoiceTests(LLMSessionTestCase):
    def test_each_session_runs_the_engine_it_asked_for(self):
        self.use_llm(ask("Do you feel like noodles?", BEEF))
        llm_state, _ = self.start()
        tree_state, _ = self.start(engine="decision_tree")
        check_state(self, llm_state)
        check_state(self, tree_state)
        self.assertEqual((llm_state["engine"], tree_state["engine"]), ("llm", "decision_tree"))
        self.assertEqual(llm_state["step"]["text"], "Do you feel like noodles?")
        self.assertTrue(llm_state["step"]["question_id"].startswith("q:llm-"))
        self.assertEqual(llm_state["candidate_count"], tree_state["candidate_count"])

    def test_the_server_default_runs_when_the_client_names_no_engine(self):
        self.assertEqual(self.start(engine=None)[0]["engine"], "decision_tree")
        self.use_llm(ask("Do you feel like noodles?", BEEF))
        with override_settings(RECOMMEND_DEFAULT_ENGINE="llm"):
            self.assertEqual(self.start(engine=None)[0]["engine"], "llm")
            self.assertEqual(self.start(engine="decision_tree")[0]["engine"], "decision_tree")

    def test_llm_without_an_api_key_is_503_and_leaves_the_tree_usable(self):
        with mock.patch.dict("os.environ", {"GOOGLE_API_KEY": "", "GEMINI_API_KEY": ""}):
            response = post(self.client, "/api/sessions/", {"date": DAY, "engine": "llm"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"]["code"], "engine_unavailable")
            self.assertIn("GOOGLE_API_KEY", response.json()["error"]["message"])
            check_state(self, self.start(engine="decision_tree")[0])


class LLMSessionFlowTests(LLMSessionTestCase):
    def test_a_whole_session_keeps_the_client_contract(self):
        llm = self.use_llm(ask("Do you feel like noodles?", BEEF), ask("Do you feel like beef?", BEEF),
                           recommend(BEEF), recommend(CHICKEN))
        state, url = self.start()
        self.assertFalse(state["can_undo"])
        state = self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "yes"})
        check_state(self, state)
        self.assertEqual((state["step"]["text"], state["step"]["question_count"]), ("Do you feel like beef?", 1))
        self.assertTrue(state["can_undo"])

        guess = self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "no"})
        check_state(self, guess)
        self.assertEqual((guess["step"]["type"], guess["step"]["target_kind"]), ("guess", "food"))
        self.assertEqual(guess["step"]["food"]["display_name"], BEEF)
        self.assertEqual(guess["step"]["food"]["offers"], [{"restaurant": "Test hall", "meal": "LU", "price": 6000}])
        self.assertNotIn("group", guess["step"])  # the LLM engine never proposes a group

        second = self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"], "accepted": False})
        check_state(self, second)
        self.assertEqual(second["step"]["food"]["display_name"], CHICKEN)
        self.assertNotIn(BEEF, llm.offered_foods())  # a rejected dish is no longer offered to the LLM

        done = self.call(url + "feedback/", {"guess_id": second["step"]["guess_id"], "accepted": True})
        check_state(self, done)
        self.assertEqual((done["step"]["type"], done["step"]["food"]["display_name"]), ("recommendation", CHICKEN))
        self.assertEqual(len(llm.calls), 4)

    def test_reads_stale_requests_and_undo_never_call_the_llm(self):
        llm = self.use_llm(ask("Do you feel like noodles?", BEEF), ask("Do you feel like beef?", BEEF))
        state, url = self.start()
        body = {"question_id": state["step"]["question_id"], "answer_id": "yes"}
        after = self.call(url + "answer/", body)
        self.assertEqual(len(llm.calls), 2)

        self.assertEqual(self.client.get(url).json(), after)
        stale = self.call(url + "answer/", body, 409)  # a retry after the phone gave up waiting
        self.assertEqual((stale["error"]["code"], stale["state"]), ("stale_step", after))
        self.call(url + "answer/", {**body, "answer_id": "maybe"}, 409)
        undone = self.call(url + "undo/")
        self.assertEqual((undone["step"], undone["can_undo"]), (state["step"], False))
        self.assertEqual(len(llm.calls), 2)

    def test_recommend_now_forces_a_guess_and_is_a_no_op_on_one(self):
        llm = self.use_llm(ask("Do you feel like noodles?", BEEF), ask("Do you feel like rice?", RICE))
        state, url = self.start()
        guess = self.call(url + "recommend-now/")
        check_state(self, guess)
        # The LLM asked again although no question was allowed: its food is shown instead.
        self.assertEqual((guess["step"]["type"], guess["step"]["food"]["display_name"]), ("guess", RICE))
        self.assertIn("Questions left: 0", llm.prompt())
        self.assertEqual(self.call(url + "recommend-now/"), guess)
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual(self.call(url + "undo/")["step"], state["step"])

    @override_settings(RECOMMEND_MAX_QUESTIONS=1)
    def test_the_server_cap_reaches_the_llm_engine(self):
        self.use_llm(ask("Do you feel like noodles?", BEEF), ask("Do you feel like beef?", CHICKEN))
        state, url = self.start()
        self.assertEqual(state["max_questions"], 1)
        state = self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "any"})
        check_state(self, state)
        self.assertEqual((state["step"]["type"], state["step"]["food"]["display_name"]), ("guess", CHICKEN))

    @override_settings(RECOMMEND_MAX_QUESTIONS=None)
    def test_no_cap_is_reported_as_null(self):
        self.use_llm(ask("Do you feel like noodles?", BEEF))
        self.assertIsNone(self.start()[0]["max_questions"])

    def test_rejecting_every_dish_ends_with_candidates_exhausted(self):
        llm = self.use_llm(recommend(BEEF), recommend(RICE))
        state, url = self.start()
        for _ in range(3):
            self.assertEqual(state["step"]["type"], "guess")
            state = self.call(url + "feedback/", {"guess_id": state["step"]["guess_id"], "accepted": False})
            check_state(self, state)
        self.assertEqual(state["step"]["reason"], "candidates_exhausted")
        self.assertEqual(len(llm.calls), 2)  # the last dish left is proposed without asking the LLM

    def test_day_without_menu_is_unavailable_without_calling_the_llm(self):
        llm = self.use_llm()
        state, _ = self.start(date="2026-01-01")
        check_state(self, state)
        self.assertEqual((state["step"]["reason"], state["candidate_count"]), ("empty_candidates", 0))
        self.assertEqual(llm.calls, [])


class LLMFailureTests(LLMSessionTestCase):
    def test_a_failing_llm_still_gives_the_client_a_step(self):
        self.use_llm(*[TimeoutError("deadline exceeded")] * 6)
        with self.assertLogs("question_engines.llm.engine", level="WARNING"):
            state, url = self.start()
            check_state(self, state)
            self.assertEqual(state["step"]["text"], FALLBACK_QUESTIONS[0])
            state = self.call(url + "answer/", {"question_id": state["step"]["question_id"], "answer_id": "yes"})
            self.assertEqual(state["step"]["text"], FALLBACK_QUESTIONS[1])
            guess = self.call(url + "recommend-now/")
        check_state(self, guess)
        self.assertEqual(guess["step"]["type"], "guess")
        self.assertIn(guess["step"]["food"]["display_name"], (BEEF, CHICKEN, RICE))
