import re
import unittest

from .. import DecisionTreeEngine, EngineConfig
from ..contracts import (ANSWER_OPTIONS, FEATURE_PRESENTATION, FEATURE_PRESENTATION_V2, GUESS_TEXT, KOREAN,
                         RECOMMENDATION_TEXT, UNAVAILABLE_TEXT)
from .helpers import small_catalog

HANGUL = re.compile("[가-힣]")


def korean_engine():
    return DecisionTreeEngine(small_catalog(), config=EngineConfig(policy="greedy", language="ko"))


class KoreanTextTests(unittest.TestCase):
    def test_every_fixed_english_text_has_korean(self):
        texts = ({text for text, _ in FEATURE_PRESENTATION.values()}
                 | {text for text, _ in FEATURE_PRESENTATION_V2.values()}
                 | {option["label"] for option in ANSWER_OPTIONS}
                 | {GUESS_TEXT, RECOMMENDATION_TEXT, UNAVAILABLE_TEXT})
        self.assertEqual(texts - set(KOREAN), set())
        self.assertTrue(all(HANGUL.search(text) for text in KOREAN.values()))

    def test_korean_session_asks_guesses_and_ends_in_korean(self):
        engine = korean_engine()
        step = engine.start()
        self.assertTrue(HANGUL.search(step["text"]))
        self.assertEqual([option["id"] for option in step["options"]],
                         [option["id"] for option in ANSWER_OPTIONS])
        self.assertTrue(all(HANGUL.search(option["label"]) for option in step["options"]))
        step = engine.recommend_now()
        self.assertEqual(step["text"], KOREAN[GUESS_TEXT])
        step = engine.feedback(step["guess_id"], True)
        self.assertEqual(step["text"], KOREAN[RECOMMENDATION_TEXT])

    def test_language_survives_a_snapshot(self):
        engine = korean_engine()
        engine.answer(engine.start()["question_id"], "yes")
        restored = DecisionTreeEngine.from_snapshot(small_catalog(), None, engine.snapshot())
        self.assertEqual(restored.next_step(), engine.next_step())
        self.assertTrue(HANGUL.search(restored.next_step()["text"]))

    def test_unknown_language_is_refused(self):
        with self.assertRaises(ValueError):
            EngineConfig(language="ja")
