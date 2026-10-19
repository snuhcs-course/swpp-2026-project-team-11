# AI-generated: written with Codex (OpenAI) and reviewed by the team.
import json
import unittest
from pathlib import Path

import numpy as np

from ..engine import DecisionTreeEngine, EngineConfig
from ..planning import POLICY_VERSION


def make_engine(vectors, **config):
    keys = [f"f{i}" for i in range(len(vectors[0]))]
    return DecisionTreeEngine(
        [{"food_id": i + 1, "name": f"Dish {i + 1}", "features": dict(zip(keys, values))}
         for i, values in enumerate(vectors)], [{"key": key} for key in keys], config=config)


def observe(engine, key, answer):
    """Replay a supplied history, independent of a policy's question order."""
    engine._set_pending({"kind": "question", "id": key})
    return engine.answer(key, answer)


class PreferenceTests(unittest.TestCase):
    def test_default_and_configuration_validation(self):
        self.assertEqual(EngineConfig().policy, "preference")
        for config in ({"preference_question_cost": -1}, {"preference_question_cost": float("nan")},
                       {"preference_question_cost": True}, {"preference_lookahead_beam": 0},
                       {"preference_lookahead_beam": True}, {"preference_lookahead_beam": 13}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                EngineConfig(**config)

    def test_answer_strength_is_signed_and_neutral_is_not_a_dislike(self):
        e = make_engine([[0], [1]])
        p = e.preference
        np.testing.assert_allclose(p.scores({0: 0}), [0, 1])
        np.testing.assert_allclose(p.scores({0: 1}), [0, .5])
        np.testing.assert_allclose(p.scores({0: 3}), [0, -.5])
        np.testing.assert_allclose(p.scores({0: 4}), [0, -1])
        for answer in (2, 5):
            np.testing.assert_allclose(p.scores({0: answer}), [0, 0])
            np.testing.assert_allclose(p.fit({0: answer}), [.5, .5])

    def test_fit_is_not_a_probability_distribution_over_foods(self):
        e = make_engine([[1], [1], [0]])
        np.testing.assert_allclose(e.preference.fit({0: 0}), [1, 1, 0])
        np.testing.assert_allclose(e.preference.fit({0: 4}), [0, 0, 1])

    def test_asks_when_answer_changes_the_recommendation(self):
        e = make_engine([[0], [1]])
        step = e.start()
        self.assertEqual(step["question_id"], "q:f0")
        self.assertEqual(e.answer("q:f0", "yes")["food"]["food_id"], 2)
        e.undo()
        self.assertEqual(e.answer("q:f0", "no")["food"]["food_id"], 1)

    def test_equal_foods_do_not_require_one_food_to_reach_65_percent(self):
        e = make_engine([[.8, .4]] * 20)
        self.assertEqual(e.start()["type"], "guess")
        self.assertEqual(e.question_count, 0)
        self.assertLess(max(e.probabilities.values()), .65)

    def test_tail_questions_stop_when_no_answer_changes_the_winner(self):
        e = make_engine([[1, 1, 1, 0, 0], [0, 0, 0, 1, 0], [0, 0, 0, 0, 1]])
        for i in range(3):
            step = observe(e, f"q:f{i}", "yes")
        self.assertEqual(step["type"], "guess")
        self.assertEqual(step["food"]["food_id"], 1)
        self.assertEqual(e.diagnostics()["planning"]["reason"], "question_cost_exceeds_value")
        self.assertAlmostEqual(e.diagnostics()["planning"]["best_question_gain"], 0)

    def test_two_question_check_can_unlock_a_better_recommendation(self):
        e = make_engine([[0, 0, 0, 0, 0], [.5, .5, .5, 1, 1]],
                        preference_question_cost=.01)
        answers = {0: 4, 1: 4, 2: 4}
        p = e.preference
        gains, _, _ = p._values(p.scores(answers), e.belief, e.salience, set(answers),
                                np.array([True, True]))
        self.assertAlmostEqual(max(gains), 0)
        action, diagnostic = p.plan(e.belief, e.salience, answers, set())
        self.assertEqual(action.kind, "question")
        self.assertTrue(diagnostic["lookahead_used"])
        self.assertIn(action.index, (3, 4))

    def test_unknown_and_any_have_distinct_forecast_updates(self):
        a, b = make_engine([[0, 0], [1, 1]]), make_engine([[0, 0], [1, 1]])
        observe(a, "q:f0", "any")
        observe(b, "q:f0", "unknown")
        self.assertEqual(a.recommendation_scores, b.recommendation_scores)
        self.assertFalse(np.array_equal(a.salience, b.salience))

    def test_rejection_undo_and_restore_preserve_preference_scores(self):
        e = make_engine([[0], [1], [.5]])
        question = e.start()
        guess = e.answer(question["question_id"], "yes")
        fit = e.recommendation_scores
        following = e.feedback(guess["guess_id"], False)
        self.assertNotEqual(guess["food"]["food_id"], following["food"]["food_id"])
        self.assertEqual(e.undo(), guess)
        self.assertEqual(e.recommendation_scores, fit)
        snapshot = json.loads(json.dumps(e.snapshot()))
        restored = DecisionTreeEngine.from_snapshot(e.catalog, None, snapshot)
        self.assertEqual(restored.next_step(), guess)
        self.assertEqual(restored.recommendation_scores, fit)
        self.assertEqual(restored.undo(), question)
        self.assertTrue(all(value == .5 for value in restored.recommendation_scores.values()))
        snapshot["engine_version"] = "decision-tree.2.0"
        with self.assertRaises(ValueError):
            DecisionTreeEngine.from_snapshot(e.catalog, None, snapshot)
        self.assertEqual(POLICY_VERSION, e.snapshot()["engine_version"])

    def test_one_eligible_food_does_not_trigger_more_questions(self):
        e = make_engine([[0, 0], [1, 1]])
        guess = e.recommend_now()
        step = e.feedback(guess["guess_id"], False)
        self.assertEqual(step["type"], "guess")
        self.assertNotEqual(step["food"]["food_id"], guess["food"]["food_id"])

    def test_recipe_std_softens_explicit_preference_scores(self):
        rows = [{"food_id": i, "name": str(i), "features": {"f": .8},
                 "feature_std": {"f": std}} for i, std in ((1, 0), (2, .35))]
        e = DecisionTreeEngine(rows, [{"key": "f"}])
        observe(e, "q:f", "yes")
        self.assertGreater(e.recommendation_scores[1], e.recommendation_scores[2])
        e.undo()
        observe(e, "q:f", "no")
        self.assertLess(e.recommendation_scores[1], e.recommendation_scores[2])


class OctoberPreferenceRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads((Path(__file__).parent / "fixtures/lunch_20261013.json").read_text(encoding="utf-8"))
        cls.schema = [{"key": key} for key in data["keys"]]
        cls.rows = [{"food_id": i, "name": name, "display_name": label,
                     "features": dict(zip(data["keys"], means)),
                     "feature_std": dict(zip(data["keys"], stds))}
                    for i, name, label, means, stds in data["foods"]]
        cls.answers = dict(korean="yes", soupy="yes", noodle="no", beef="no", pork="no",
                           meal_variety="no", chicken="yes", fried="no", sweet="no", wheat="no",
                           bivalve="no", fish="no", stir_fried="no", sour="no", chinese="no")

    def test_old_policy_reproduces_fifteen_question_failure(self):
        e = DecisionTreeEngine(self.rows, self.schema, config={"policy": "greedy"})
        for key, answer in self.answers.items():
            self.assertEqual(e.next_step()["question_id"], "q:" + key)
            step = e.answer("q:" + key, answer)
        self.assertEqual(e.question_count, 15)
        self.assertEqual(step["food"]["name"], "닭개장")

    def test_same_seven_answers_are_enough_to_propose_chicken_soup(self):
        e = DecisionTreeEngine(self.rows, self.schema)
        for key, answer in list(self.answers.items())[:7]:
            step = observe(e, "q:" + key, answer)
        self.assertEqual(step["type"], "guess")
        self.assertEqual(step["food"]["name"], "닭개장")
        self.assertEqual(e.question_count, 7)
        self.assertLess(max(e.probabilities.values()), .65)

    def test_new_question_order_finishes_without_tail_questions(self):
        e = DecisionTreeEngine(self.rows, self.schema)
        asked = []
        step = e.start()
        while step["type"] == "question":
            key = step["question_id"][2:]
            asked.append(key)
            # The user never supplied a spicy answer; do not invent a preference.
            step = e.answer(step["question_id"], self.answers.get(key, "unknown"))
            self.assertLessEqual(len(asked), 12)
        self.assertEqual(step["food"]["name"], "닭개장")
        self.assertLessEqual(len(asked), 10)
        self.assertNotIn("wheat", asked)
        self.assertNotIn("chinese", asked)
        self.assertEqual(asked[-1], "chicken")

    def test_independent_synthetic_preferences_are_not_forced_to_soup(self):
        for target in ("유부우동", "치즈버거"):
            with self.subTest(target=target):
                food = next(row for row in self.rows if row["name"] == target)
                e = DecisionTreeEngine(self.rows, self.schema)
                step = e.start()
                while step["type"] == "question":
                    mean = food["features"][step["question_id"][2:]]
                    answer = "yes" if mean > .65 else "no" if mean < .25 else "any"
                    step = e.answer(step["question_id"], answer)
                    self.assertLessEqual(e.question_count, 12)
                self.assertEqual(step["food"]["name"], target)
