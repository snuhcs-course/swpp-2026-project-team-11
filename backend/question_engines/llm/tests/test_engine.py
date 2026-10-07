import datetime
import json

from django.test import SimpleTestCase, TestCase

from menus.services import get_candidates

from ..engine import EngineConfig, InvalidTurn, LLMEngine, check_turn
from ..schema import EngineTurn
from .helpers import CANDIDATES, FakeLLM, ask, candidate, check_step, recommend

BROTH = "Do you feel like something with broth?"
COLD = "Do you feel like something cold?"


class SessionTests(SimpleTestCase):
    def engine(self, *replies, **config):
        self.llm = FakeLLM(*replies)
        return LLMEngine(CANDIDATES, llm=self.llm, config=config)

    def test_start_asks_a_question_with_the_six_answers(self):
        step = self.engine(ask(f"  {BROTH} ")).start()
        check_step(self, step)
        self.assertEqual((step["type"], step["text"], step["question_count"]), ("question", BROTH, 0))

    def test_next_step_does_not_call_the_llm_again(self):
        engine = self.engine(ask(BROTH))
        self.assertEqual(engine.start(), engine.next_step())
        self.assertEqual(len(self.llm.calls), 1)

    def test_answer_then_guess_then_accept(self):
        engine = self.engine(ask(BROTH), recommend("물냉면"))
        step = engine.answer(engine.start()["question_id"], "no")
        check_step(self, step)
        self.assertEqual((step["type"], step["food"]["food_id"], step["question_count"]), ("guess", 2, 1))
        self.assertNotIn("features", step["food"])

        step = engine.feedback(step["guess_id"], True)
        check_step(self, step)
        self.assertEqual((step["type"], step["food"]["food_id"]), ("recommendation", 2))
        self.assertEqual(len(self.llm.calls), 2)  # accepting needs no LLM call

    def test_rejection_keeps_answers_and_removes_the_menu(self):
        engine = self.engine(ask(BROTH), recommend("물냉면"), recommend("왕돈까스"))
        step = engine.answer(engine.start()["question_id"], "no")
        step = engine.feedback(step["guess_id"], False)
        self.assertEqual(step["food"]["display_name"], "왕돈까스")
        self.assertEqual(self.llm.offered_foods(), ["육개장", "왕돈까스"])
        self.assertIn(f"Q1. {BROTH} -> No", self.llm.prompt())

    def test_rejecting_every_menu_exhausts_the_session(self):
        engine = self.engine(recommend("물냉면"), recommend("왕돈까스"))
        step = engine.start()
        for _ in range(3):
            step = engine.feedback(step["guess_id"], False)
        check_step(self, step)
        self.assertEqual(step["reason"], "candidates_exhausted")

    def test_stale_or_unknown_ids_are_rejected(self):
        engine = self.engine(ask(BROTH))
        step = engine.start()
        for question_id, answer_id in [("q:other", "yes"), (step["question_id"], "maybe")]:
            with self.assertRaises(ValueError):
                engine.answer(question_id, answer_id)
        with self.assertRaises(ValueError):
            engine.feedback("food:1", True)
        self.assertEqual(engine.question_count, 0)

    def test_question_limit_forces_a_guess(self):
        engine = self.engine(ask(BROTH), ask(COLD, food="왕돈까스"), max_questions=1)
        step = engine.answer(engine.start()["question_id"], "yes")
        self.assertEqual((step["type"], step["food"]["food_id"]), ("guess", 3))
        self.assertIn("Questions left: 0.", self.llm.prompt())

    def test_recommend_now_forces_a_guess(self):
        engine = self.engine(ask(BROTH), recommend("육개장"))
        engine.start()
        step = engine.recommend_now()
        self.assertEqual(step["type"], "guess")
        self.assertIn("Questions left: 0.", self.llm.prompt())

    def test_undo_restores_the_exact_step_without_the_llm(self):
        engine = self.engine(ask(BROTH), recommend("물냉면"))
        first = engine.start()
        engine.answer(first["question_id"], "yes")
        self.assertEqual(engine.undo(), first)
        self.assertEqual((engine.question_count, len(self.llm.calls)), (0, 2))
        self.assertEqual(engine.undo(), first)  # nothing left to undo

    def test_snapshot_round_trip_needs_no_llm(self):
        engine = self.engine(ask(BROTH), recommend("물냉면"))
        engine.answer(engine.start()["question_id"], "any")
        snapshot = json.loads(json.dumps(engine.snapshot()))

        restored = LLMEngine.from_snapshot(CANDIDATES, snapshot, llm=FakeLLM())
        self.assertEqual(restored.next_step(), engine.next_step())
        self.assertEqual(restored.question_count, 1)
        with self.assertRaises(ValueError):
            LLMEngine.from_snapshot(CANDIDATES[:2], snapshot, llm=FakeLLM())

    def test_diagnostics(self):
        engine = self.engine(ask(BROTH), recommend("물냉면"))
        step = engine.answer(engine.start()["question_id"], "yes")
        engine.feedback(step["guess_id"], True)
        diagnostics = engine.diagnostics()
        self.assertEqual({key: diagnostics[key] for key in ("question_count", "guess_count", "feedback_count")},
                         {"question_count": 1, "guess_count": 1, "feedback_count": 1})
        self.assertEqual(len(diagnostics["llm_calls"]), 2)

    def test_invalid_turn_reaches_the_caller(self):
        with self.assertRaises(InvalidTurn):
            self.engine(ask(" ")).start()


class CandidateTests(SimpleTestCase):
    def test_same_display_name_is_one_choice_and_single_choice_skips_the_llm(self):
        llm = FakeLLM()
        step = LLMEngine([candidate(7, "마라탕"), candidate(8, "마라탕")], llm=llm).start()
        self.assertEqual((step["type"], step["food"]["food_id"], llm.calls), ("guess", 7, []))

    def test_no_candidates(self):
        step = LLMEngine([], llm=FakeLLM()).start()
        check_step(self, step)
        self.assertEqual(step["reason"], "empty_candidates")

    def test_config(self):
        self.assertEqual(LLMEngine([], llm=None).config, EngineConfig(max_questions=10))
        self.assertIsNone(LLMEngine([], llm=None, config={"max_questions": None}).config.max_questions)
        for bad in (0, -1, 2.5, True):
            with self.assertRaises(ValueError):
                EngineConfig(max_questions=bad)


class CheckTurnTests(SimpleTestCase):
    def test_rules(self):
        history = [(BROTH, "Yes")]
        for turn in [None, EngineTurn(**ask(" ")), EngineTurn(**ask(BROTH.upper()))]:
            with self.assertRaises(InvalidTurn):
                check_turn(turn, history, questions_left=3)
        check_turn(EngineTurn(**ask(" ")), history, questions_left=0)  # will be a guess anyway
        check_turn(EngineTurn(**recommend("육개장")), history, questions_left=3)


class CafeteriaFixtureTests(TestCase):
    fixtures = ["menus_2026-09-29"]

    def test_runs_on_the_shared_snapshot(self):
        rows = get_candidates(datetime.date(2026, 9, 29), "LU")
        first = rows[0]["display_name"]
        llm = FakeLLM(ask(BROTH, food=first), recommend(first))
        engine = LLMEngine(rows, llm=llm)
        step = engine.answer(engine.start()["question_id"], "yes")
        check_step(self, step)
        self.assertEqual(step["food"]["food_id"], rows[0]["food_id"])
        names = llm.offered_foods()
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), {row["display_name"] for row in rows})
