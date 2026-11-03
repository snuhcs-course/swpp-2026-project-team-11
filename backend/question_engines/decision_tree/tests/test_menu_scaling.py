import unittest

import numpy as np

from ..catalog import CandidateCatalog
from ..engine import DecisionTreeEngine
from ..planning import IntentModel, Planner, PlannerConfig


def menu_catalog(size=5):
    rows = [{"food_id": i + 1, "name": f"Menu {i + 1:04d}", "menu_profile": "rms-v1",
             "features": {"a": (i % 5) / 4, "b": ((i * 3) % 7) / 6}}
            for i in range(size)]
    return CandidateCatalog(rows, [{"key": "a"}, {"key": "b"}])


def dense_engine(catalog, policy="preference"):
    # Build the previous dense model over the same family-free catalog.
    catalog.context["candidate_kind"] = "dense-reference"
    engine = DecisionTreeEngine(catalog, config={"policy": policy})
    catalog.context["candidate_kind"] = "menu-rms-v1"
    return engine


class MenuScalingTests(unittest.TestCase):
    def test_compact_model_matches_dense_math(self):
        catalog = menu_catalog()
        compact = IntentModel(catalog)
        catalog.context["candidate_kind"] = "dense-reference"
        dense = IntentModel(catalog)
        self.assertTrue(compact.identity_intents)
        self.assertIsNone(compact.intent_to_food)
        self.assertIsNone(compact.acceptance)
        np.testing.assert_allclose(compact.prior, dense.prior)
        np.testing.assert_allclose(compact.values, dense.values)
        np.testing.assert_allclose(compact.resolution, dense.resolution)
        belief = np.array([.1, .15, .2, .25, .3])
        np.testing.assert_allclose(compact.food_belief(belief), dense.food_belief(belief))
        np.testing.assert_allclose(compact.acceptance_probabilities(belief), dense.acceptance_probabilities(belief))
        for i in range(len(belief)):
            np.testing.assert_array_equal(compact.acceptance_row(i), dense.acceptance_row(i))
        np.testing.assert_array_equal(compact.acceptance_support(np.array([0, 3])), dense.acceptance_support(np.array([0, 3])))
        for answer in range(6):
            left = compact.observe(belief, compact.salience_prior, 0, answer)
            right = dense.observe(belief, dense.salience_prior, 0, answer)
            for a, b in zip(left, right):
                np.testing.assert_allclose(a, b)

    def test_default_and_greedy_sessions_match_after_rejection_and_undo(self):
        for policy in ("preference", "greedy"):
            with self.subTest(policy=policy):
                compact = DecisionTreeEngine(menu_catalog(), config={"policy": policy})
                dense = dense_engine(menu_catalog(), policy)
                for answer in ("yes", "no"):
                    a, b = compact.next_step(), dense.next_step()
                    self.assertEqual(a["type"], b["type"])
                    if a["type"] != "question":
                        break
                    self.assertEqual(a["question_id"], b["question_id"])
                    compact.answer(a["question_id"], answer)
                    dense.answer(b["question_id"], answer)
                    np.testing.assert_allclose(compact.belief, dense.belief)
                a, b = compact.recommend_now(), dense.recommend_now()
                self.assertEqual(a["food"]["food_id"], b["food"]["food_id"])
                compact.feedback(a["guess_id"], False)
                dense.feedback(b["guess_id"], False)
                np.testing.assert_allclose(compact.belief, dense.belief)
                self.assertEqual(compact.next_step()["type"], dense.next_step()["type"])
                restored_dense = DecisionTreeEngine.from_snapshot(compact.catalog, None, dense.snapshot())
                np.testing.assert_allclose(restored_dense.belief, dense.belief)
                self.assertEqual(restored_dense.next_step(), dense.next_step())
                self.assertEqual(compact.undo()["food"]["food_id"], dense.undo()["food"]["food_id"])
                restored = DecisionTreeEngine.from_snapshot(compact.catalog, None, compact.snapshot())
                np.testing.assert_allclose(restored.belief, compact.belief)
                a, b = compact.next_step(), dense.next_step()
                self.assertEqual(compact.feedback(a["guess_id"], True), dense.feedback(b["guess_id"], True))

    def test_lookahead_forced_guess_matches_dense(self):
        catalog = menu_catalog()
        compact = IntentModel(catalog, PlannerConfig())
        catalog.context["candidate_kind"] = "dense-reference"
        dense = IntentModel(catalog, PlannerConfig())
        a, _ = Planner(compact).plan(compact.prior, compact.salience_prior, set(), set(), force_guess=True)
        b, _ = Planner(dense).plan(dense.prior, dense.salience_prior, set(), set(), force_guess=True)
        self.assertEqual(a, b)

    def test_lookahead_search_matches_dense(self):
        catalog = menu_catalog()
        config = PlannerConfig(depth=1, particles=3, rollout_samples=2,
                               rollout_steps=2, time_budget_ms=10000)
        compact = IntentModel(catalog, config)
        catalog.context["candidate_kind"] = "dense-reference"
        dense = IntentModel(catalog, config)
        left, left_report = Planner(compact).plan(compact.prior, compact.salience_prior, set(), set(), seed=7)
        right, right_report = Planner(dense).plan(dense.prior, dense.salience_prior, set(), set(), seed=7)
        self.assertEqual(left, right)
        self.assertEqual(left_report["completed_depth"], right_report["completed_depth"])
        self.assertAlmostEqual(left_report["expected_interaction_cost"], right_report["expected_interaction_cost"])

    def test_large_menu_model_has_no_dense_intent_matrices(self):
        model = IntentModel(menu_catalog(1500))
        self.assertTrue(model.identity_intents)
        self.assertIsNone(model.intent_to_food)
        self.assertIsNone(model.acceptance)
        self.assertEqual(model.values.shape, (2, 1500))
