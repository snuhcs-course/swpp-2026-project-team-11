from dataclasses import replace
import unittest

import numpy as np

from ..planning import Action, IntentModel, Planner, PlannerConfig
from .helpers import small_catalog


def config(**overrides):
    return replace(PlannerConfig(depth=1, particles=0, time_budget_ms=1000,
                                 rollout_samples=4, rollout_steps=4), **overrides)


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.catalog = small_catalog()
        self.model = IntentModel(self.catalog, config())

    def test_prior_split_does_not_double_count_and_preserves_marginal(self):
        self.assertAlmostEqual(self.model.prior.sum(), 1)
        np.testing.assert_allclose(self.model.prior @ self.model.intent_to_food, [1/3] * 3)

    def test_team_yes_probabilities_are_not_sharpened(self):
        self.assertEqual(self.model.values[0, self.model.node_index["food:1"]], .9)
        self.assertEqual(self.model.values[0, self.model.node_index["food:2"]], .1)

    def test_answer_channel_normalized_monotonic_and_equivalent_vectorization(self):
        row = self.model.likelihood(0, self.model.salience_prior)
        self.assertTrue(np.all(row > 0))
        np.testing.assert_allclose(row.sum(axis=0), 1)
        a, b = self.model.node_index["food:1"], self.model.node_index["food:2"]
        self.assertGreater(row[3, b], row[3, a])
        self.assertGreater(row[0, a] / row[0, b], row[1, a] / row[1, b])
        np.testing.assert_allclose(row, self.model.all_likelihoods(self.model.salience_prior, np.arange(len(self.model.prior)))[0])

    def test_indifference_changes_resolution_and_importance(self):
        m = self.model
        _, b, salience = m.observe(m.prior, m.salience_prior, 0, 2)
        group = next(i for i, node in enumerate(m.node_ids) if node.startswith("group:"))
        self.assertGreater(b[group], m.prior[group])
        importance_before = m.salience_prior[m.groups[0], 0] / m.salience_prior[m.groups[0], :2].sum()
        importance_after = salience[m.groups[0], 0] / salience[m.groups[0], :2].sum()
        self.assertLess(importance_after, importance_before)
        np.testing.assert_equal(salience[m.groups[1]], m.salience_prior[m.groups[1]])

    def test_unknown_keeps_food_direction_but_reduces_answerability(self):
        m = self.model
        _, b, salience = m.observe(m.prior, m.salience_prior, 0, 5)
        np.testing.assert_allclose(b, m.prior)
        self.assertGreater(salience[m.groups[0], 3], m.salience_prior[m.groups[0], 3])

    def test_group_rejection_suppresses_descendants_without_zeroing_belief(self):
        m = self.model
        group = next(i for i, node in enumerate(m.node_ids) if node.startswith("group:"))
        blocked = m.rejection_aliases(group)
        mask = m.proposal_mask(blocked)
        self.assertFalse(mask[group])
        self.assertFalse(mask[m.node_index["food:1"]])
        self.assertFalse(mask[m.node_index["food:2"]])
        self.assertTrue(mask[m.node_index["food:3"]])
        b = m.prior * (1 - m.acceptance[group])
        self.assertTrue(np.all(b > 0))


class SearchTests(unittest.TestCase):
    def test_exact_one_step_cost_matches_independent_enumeration(self):
        cfg = config(beam=2, guess_beam=4, outcome_samples=0)
        m = IntentModel(small_catalog(), cfg)
        p = Planner(m)
        terminal = lambda b: 2 * (1 - np.max(m.acceptance @ b))
        p.rollout = lambda b, *args: terminal(b)
        costs = []
        for qi in range(2):
            cost = cfg.question_cost
            for likelihood in m.likelihood(qi, m.salience_prior):
                mass = float(likelihood @ m.prior)
                cost += mass * terminal(m.prior * likelihood / mass)
            costs.append(cost)
        for acceptance in m.acceptance:
            mass = float((1 - acceptance) @ m.prior)
            costs.append(cfg.guess_cost + mass * (cfg.miss_cost + cfg.first_miss_cost + terminal(m.prior * (1 - acceptance) / mass)))
        _, report = p.plan(m.prior, m.salience_prior, set(), set())
        self.assertEqual(report["completed_depth"], 1)
        self.assertAlmostEqual(report["expected_interaction_cost"], min(costs))

    def test_deadline_fallback_does_not_mutate_posterior(self):
        m = IntentModel(small_catalog(), config(time_budget_ms=.001))
        before = m.prior.copy()
        ticks = iter(i / 1000 for i in range(100))
        action, report = Planner(m, clock=lambda: next(ticks)).plan(before, m.salience_prior, set(), set())
        self.assertIn(action.kind, {"question", "guess"})
        self.assertEqual(report["completed_depth"], 0)
        self.assertTrue(report["budget_exhausted"])
        np.testing.assert_equal(before, m.prior)

    def test_noisy_guess_advantage_keeps_question(self):
        m = IntentModel(small_catalog(), config())
        p = Planner(m)
        p._cost = lambda action, *args: np.array([0., 0., 0., 20.]) if action.kind == "guess" else np.full(4, 10.)
        action, report = p.plan(m.prior, m.salience_prior, set(), set())
        self.assertEqual(action.kind, "question")
        self.assertFalse(report["guess_comparison"]["accepted_by_error_guard"])

    def test_rejects_invalid_configurations(self):
        for args in ({"depth": True}, {"depth": 5}, {"time_budget_ms": "fast"}, {"particles": -1}, {"general_intent_mass": float("nan")}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                PlannerConfig(**args)
