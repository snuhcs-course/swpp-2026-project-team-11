import unittest

from .. import DecisionTreeEngine
from ..contracts import question_tier, question_topic
from .helpers import october_menu


class SchedulingTests(unittest.TestCase):
    """A user who answers from one dish's features, on the 2026-10-13 lunch menu."""

    @classmethod
    def setUpClass(cls):
        cls.rows, cls.schema = october_menu()
        cls.targets = cls.rows[::5]

    def session(self, target, seed=None, rules=True):
        e = DecisionTreeEngine(self.rows, self.schema, config={"seed": seed})
        if not rules:
            e._held_questions = lambda: ()
        step, asked = e.start(), []
        for _ in range(40):
            if step["type"] == "question":
                asked.append(step["question_id"][2:])
                value = target["features"][asked[-1]]
                step = e.answer(step["question_id"], "yes" if value > .65 else "no" if value < .25 else "any")
            elif step["type"] == "guess":
                if target["food_id"] in [step["food"]["food_id"], *step.get("group", {}).get("food_ids", [])]:
                    return asked, True
                step = e.feedback(step["guess_id"], False)
        return asked, False

    def test_the_first_four_questions_are_never_detailed(self):
        for target in self.targets:
            for seed in (None, 1, 2):
                asked, _ = self.session(target, seed)
                self.assertEqual(question_tier(asked[0]), 1, (target["name"], asked))
                self.assertFalse([key for key in asked[:4] if question_tier(key) == 3], (target["name"], asked))

    def test_a_topic_is_asked_back_to_back_less_than_half_as_often(self):
        def repeats(rules):
            return sum(question_topic(a) == question_topic(b)
                       for target in self.targets for asked in [self.session(target, rules=rules)[0]]
                       for a, b in zip(asked, asked[1:]))
        self.assertLess(2 * repeats(True), repeats(False))

    def test_the_opening_question_varies_by_session_but_not_within_one(self):
        target = self.targets[0]
        openers = {self.session(target, seed)[0][0] for seed in range(10)}
        self.assertGreaterEqual(len(openers), 2)
        self.assertEqual(self.session(target, 3)[0][:2], self.session(target, 3)[0][:2])

    def test_every_session_still_finds_its_dish(self):
        for target in self.targets:
            asked, found = self.session(target, seed=4)
            self.assertTrue(found, (target["name"], asked))
            self.assertLessEqual(len(asked), 20)
