import re
import unittest

from question_engines.rl import RLEngine

from .. import DecisionTreeEngine
from ..contracts import FEATURE_PRESENTATION, FEATURE_PRESENTATION_V2, KOREAN, PHRASINGS_V2, question_text, translate
from .helpers import october_menu

HANGUL = re.compile("[가-힣]")


def first_phrasing(key, language):
    return translate(FEATURE_PRESENTATION_V2[key][0], language)


class PhrasingTableTests(unittest.TestCase):
    def test_every_v2_question_has_two_more_phrasings(self):
        self.assertEqual(set(PHRASINGS_V2), set(FEATURE_PRESENTATION_V2))
        english = [text for text, _ in FEATURE_PRESENTATION_V2.values()]
        for key, variants in PHRASINGS_V2.items():
            self.assertEqual(len(variants), 2, key)
            for text, korean in variants:
                self.assertTrue(text.isascii() and text.endswith("?"), text)
                self.assertTrue(HANGUL.search(korean) and korean.endswith("?"), korean)
                english.append(text)
        self.assertEqual(len(english), len(set(english)))

    def test_only_the_v2_question_of_a_key_takes_other_phrasings(self):
        self.assertEqual(question_text("spicy", FEATURE_PRESENTATION_V2["spicy"][0], "ko", 1), PHRASINGS_V2["spicy"][0][1])
        # v1 greasy ("rich and oily") means something else than v2 greasy (creamy, cheesy).
        v1_greasy = FEATURE_PRESENTATION["greasy"][0]
        self.assertEqual(question_text("greasy", v1_greasy, "ko", 2), KOREAN[v1_greasy])
        self.assertEqual(question_text("spicy", "Custom?", "en", 1), "Custom?")


class SessionPhrasingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.schema = october_menu()

    def test_consecutive_questions_take_turns_from_the_session_seed(self):
        e = DecisionTreeEngine(self.rows, self.schema, config={"seed": 7, "language": "ko"})
        step, shown = e.start(), []
        while step["type"] == "question" and len(shown) < 4:
            key = step["question_id"][2:]
            self.assertEqual(step["text"], question_text(key, FEATURE_PRESENTATION_V2[key][0], "ko", (7 + len(shown)) % 3))
            shown.append(step["text"])
            step = e.answer(step["question_id"], "no")
        self.assertEqual(len(set(shown)), len(shown))
        restored = DecisionTreeEngine.from_snapshot(self.rows, self.schema, e.snapshot())
        self.assertEqual(restored.next_step(), e.next_step())
        self.assertEqual(e.undo()["text"], shown[-1])

    def test_reasons_read_the_first_phrasing_in_english(self):
        e = DecisionTreeEngine(self.rows, self.schema, config={"seed": 1})
        first = e.start()
        second = e.answer(first["question_id"], "yes")
        e.answer(second["question_id"], "yes")
        self.assertNotEqual(second["text"], first_phrasing(second["question_id"][2:], "en"))
        self.assertEqual([a["text"] for a in e.answered()],
                         [first_phrasing(step["question_id"][2:], "en") for step in (first, second)])

    def test_without_a_seed_every_question_keeps_its_first_phrasing(self):
        e = DecisionTreeEngine(self.rows, self.schema, config={"language": "ko"})
        step = e.start()
        for _ in range(3):
            self.assertEqual(step["text"], first_phrasing(step["question_id"][2:], "ko"))
            step = e.answer(step["question_id"], "no")

    def test_rl_questions_take_turns_by_position(self):
        e = RLEngine(self.rows, language="ko")
        step, position = e.start(), 0
        while step["type"] == "question" and position < 3:
            key = step["question_id"][2:]
            self.assertEqual(step["text"], question_text(key, FEATURE_PRESENTATION_V2[key][0], "ko", position))
            step, position = e.answer(step["question_id"], "no"), position + 1
