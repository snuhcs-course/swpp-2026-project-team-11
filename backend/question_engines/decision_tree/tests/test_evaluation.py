import unittest

from ..evaluation import ResponseOracle, compare_policies
from .helpers import small_catalog


class EvaluationTests(unittest.TestCase):
    def test_oracle_is_stable_across_question_order_and_instances(self):
        c = small_catalog()
        a = ResponseOracle(c, 1, 1234, 0)
        b = ResponseOracle(c, 1, 1234, 0)
        forward = {q["id"]: a.answer(q["id"]) for q in c.questions}
        backward = {q["id"]: b.answer(q["id"]) for q in reversed(c.questions)}
        self.assertEqual(forward, backward)

    def test_both_policies_use_the_same_targets_and_answers(self):
        c = small_catalog()
        rows = [x.summary() | {"features": dict(x.features)} for x in c.candidates]
        report = compare_policies(rows, [{"key": "beef"}, {"key": "soupy"}], trials=3, seed=12,
            planner_config={"depth": 1, "particles": 0, "rollout_samples": 4, "rollout_steps": 4, "time_budget_ms": 30})
        for greedy, lookahead in zip(report["records"]["greedy"], report["records"]["lookahead"]):
            self.assertEqual(greedy["target_food_id"], lookahead["target_food_id"])
            ga = {x["question_id"]: x["answer_id"] for x in greedy["trace"] if "question_id" in x}
            la = {x["question_id"]: x["answer_id"] for x in lookahead["trace"] if "question_id" in x}
            for key in set(ga) & set(la):
                self.assertEqual(ga[key], la[key])
        self.assertIn("latency_ms", report["summary"]["lookahead"])

    def test_invalid_trial_count_and_empty_candidates(self):
        for trials in (0, 201, True):
            with self.assertRaises(ValueError):
                compare_policies([], [{"key": "soupy"}], trials=trials)
