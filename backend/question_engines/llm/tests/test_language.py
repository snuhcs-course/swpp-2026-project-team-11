from django.test import SimpleTestCase

from question_engines.decision_tree.contracts import GUESS_TEXT, KOREAN

from ..engine import LLMEngine
from ..prompt import FALLBACK_QUESTIONS
from ..schema import build_turn_model
from .helpers import CANDIDATES, FakeLLM, ask_ko, check_step, recommend

BROTH = "Do you feel like something with broth?"
BROTH_KO = "국물 있는 음식이 당기나요?"


class KoreanSessionTests(SimpleTestCase):
    def engine(self, *replies):
        self.llm = FakeLLM(*replies)
        return LLMEngine(CANDIDATES, llm=self.llm, config={"language": "ko"})

    def test_shows_the_korean_question_and_sends_the_english_to_the_llm(self):
        engine = self.engine(ask_ko(BROTH, f" {BROTH_KO} "), recommend("물냉면"))
        step = engine.start()
        check_step(self, step)
        self.assertEqual(step["text"], BROTH_KO)
        self.assertEqual(step["options"][0]["label"], KOREAN["Yes, sounds good"])
        step = engine.answer(step["question_id"], "no")
        self.assertIn(f"Q1. {BROTH} -> No", self.llm.prompt())
        self.assertNotIn(BROTH_KO, self.llm.prompt())
        self.assertEqual(step["text"], KOREAN[GUESS_TEXT])

    def test_undo_and_snapshot_keep_the_shown_question(self):
        engine = self.engine(ask_ko(BROTH, BROTH_KO), recommend("물냉면"))
        first = engine.start()
        engine.answer(first["question_id"], "yes")
        self.assertEqual(engine.undo(), first)
        restored = LLMEngine.from_snapshot(CANDIDATES, engine.snapshot(), llm=FakeLLM())
        self.assertEqual(restored.next_step(), first)

    def test_an_empty_korean_question_is_retried(self):
        engine = self.engine(ask_ko(BROTH, ""), ask_ko(BROTH, BROTH_KO))
        self.assertEqual(engine.start()["text"], BROTH_KO)
        self.assertIn("question_ko", self.llm.prompt())

    def test_the_fixed_fallback_questions_are_shown_in_korean(self):
        engine = self.engine(TimeoutError(), TimeoutError())
        self.assertEqual(engine.start()["text"], KOREAN[FALLBACK_QUESTIONS[0]])
        self.assertTrue(all(question in KOREAN for question in FALLBACK_QUESTIONS))

    def test_only_a_korean_session_asks_for_question_ko(self):
        self.assertIn("question_ko", build_turn_model(["육개장"], "ko").model_fields)
        self.assertNotIn("question_ko", build_turn_model(["육개장"]).model_fields)
        english = LLMEngine(CANDIDATES, llm=FakeLLM({"action": "ask", "question": BROTH, "food": "육개장"}))
        self.assertEqual(english.start()["text"], BROTH)
