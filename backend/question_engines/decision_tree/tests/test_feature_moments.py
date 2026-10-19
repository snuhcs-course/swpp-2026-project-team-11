# AI-generated: written with Codex (OpenAI) and reviewed by the team.
import copy
import unittest

import numpy as np

from ..catalog import CandidateCatalog
from ..engine import DecisionTreeEngine
from ..planning import IntentModel, Planner, POLICY_VERSION

SCHEMA = [{"key": "variable"}, {"key": "stable"}]


def candidates(variable_std=.35, stable_std=.05):
    return [
        {"food_id": i, "name": f"Dish {i}", "display_name": f"Dish {i}", "food_group": "",
         "features": {"variable": mean, "stable": mean},
         "feature_std": {"variable": variable_std, "stable": stable_std}, "offers": []}
        for i, mean in ((1, .8), (2, .2))
    ]


def model(rows):
    return IntentModel(CandidateCatalog(rows, SCHEMA))


class MomentCatalogTests(unittest.TestCase):
    def test_std_is_validated_and_never_silently_defaulted_when_supplied(self):
        for std in [None, {}, {"variable": .1}, {"variable": .5, "stable": .1},
                    {"variable": -.1, "stable": .1}, {"variable": True, "stable": .1},
                    {"variable": float("nan"), "stable": .1},
                    {"variable": float("inf"), "stable": .1},
                    {"variable": "0.1", "stable": .1}]:
            with self.subTest(std=std), self.assertRaises(ValueError):
                rows = candidates()
                rows[0]["feature_std"] = std
                CandidateCatalog(rows, SCHEMA)

    def test_std_is_copied_and_part_of_fingerprint_but_not_public_food(self):
        rows = candidates()
        catalog = CandidateCatalog(rows, SCHEMA)
        rows[0]["feature_std"]["variable"] = 0
        self.assertEqual(catalog.by_id[1].feature_std["variable"], .35)
        with self.assertRaises(TypeError):
            catalog.by_id[1].feature_std["variable"] = 0
        self.assertNotEqual(catalog.fingerprint, CandidateCatalog(rows, SCHEMA).fingerprint)
        self.assertEqual(set(catalog.by_id[1].summary()),
                         {"food_id", "name", "display_name", "food_group", "offers"})

    def test_missing_legacy_std_is_preserved_as_missing(self):
        rows = candidates()
        for row in rows:
            del row["feature_std"]
        catalog = CandidateCatalog(rows, SCHEMA)
        self.assertIsNone(catalog.by_id[1].feature_std)
        self.assertNotEqual(catalog.fingerprint, CandidateCatalog(candidates(0, 0), SCHEMA).fingerprint)

    def test_endpoints_require_zero_std(self):
        rows = candidates(0, 0)
        rows[0]["features"]["variable"] = 1
        CandidateCatalog(rows, SCHEMA)
        rows[0]["feature_std"]["variable"] = .01
        with self.assertRaises(ValueError):
            CandidateCatalog(rows, SCHEMA)


class MomentInferenceTests(unittest.TestCase):
    def test_zero_std_preserves_mean_only_likelihood_and_updates(self):
        rows = candidates(0, 0)
        zero = model(rows)
        for row in rows:
            del row["feature_std"]
        legacy = model(rows)
        np.testing.assert_array_equal(zero.values, legacy.values)
        for answer in range(6):
            a = zero.observe(zero.prior, zero.salience_prior, 0, answer)
            b = legacy.observe(legacy.prior, legacy.salience_prior, 0, answer)
            for left, right in zip(a, b):
                np.testing.assert_array_equal(left, right)

    def test_larger_std_softens_both_yes_and_no_posteriors(self):
        yes, no = [], []
        for std in (0, .15, .35):
            m = model(candidates(std, 0))
            yes.append(m.observe(m.prior, m.salience_prior, 0, 0)[1][0])
            no.append(m.observe(m.prior, m.salience_prior, 0, 4)[1][0])
        self.assertGreater(yes[0], yes[1])
        self.assertGreater(yes[1], yes[2])
        self.assertGreater(yes[2], .5)
        self.assertLess(no[0], no[1])
        self.assertLess(no[1], no[2])
        self.assertLess(no[2], .5)

    def test_std_is_not_a_blanket_penalty_for_a_food(self):
        rows = candidates()
        rows[1]["features"] = dict(rows[0]["features"])
        rows[1]["feature_std"]["variable"] = 0
        m = model(rows)
        yes = m.observe(m.prior, m.salience_prior, 0, 0)[1]
        no = m.observe(m.prior, m.salience_prior, 0, 4)[1]
        self.assertLess(yes[0], .5)
        self.assertGreater(no[0], .5)

    def test_recipe_std_does_not_mean_indifference_or_unknown(self):
        certain, variable = model(candidates(0, 0)), model(candidates())
        for answer in (2, 5):
            np.testing.assert_allclose(
                certain.observe(certain.prior, certain.salience_prior, 0, answer)[1],
                variable.observe(variable.prior, variable.salience_prior, 0, answer)[1])

    def test_scalar_and_vector_channels_are_normalized_and_match(self):
        m = model(candidates())
        all_rows = m.all_likelihoods(m.salience_prior, np.arange(len(m.prior)))
        for qi in range(2):
            row = m.likelihood(qi, m.salience_prior)
            np.testing.assert_allclose(row, all_rows[qi])
            np.testing.assert_allclose(row.sum(axis=0), 1)
            self.assertTrue(np.all(row > 0))

    def test_greedy_prefers_lower_std_when_mean_separation_is_identical(self):
        first = DecisionTreeEngine(candidates(0, 0), SCHEMA).start()
        uncertain = DecisionTreeEngine(candidates(), SCHEMA).start()
        self.assertEqual(first["question_id"], "q:variable")
        self.assertEqual(uncertain["question_id"], "q:stable")

    def test_lookahead_shortlist_uses_std_aware_information(self):
        m = model(candidates())
        planner = Planner(m)
        planner.support = np.arange(len(m.prior))
        order, information = planner._question_order(m.prior, m.salience_prior, set())
        self.assertEqual(list(order), [1, 0])
        self.assertGreater(information[1], information[0])
        engine = DecisionTreeEngine(candidates(), SCHEMA, config={"policy": "lookahead"},
                                    planner_config={"depth": 1, "particles": 0, "beam": 1,
                                                    "rollout_samples": 2, "rollout_steps": 2,
                                                    "time_budget_ms": 1000})
        step = engine.start()
        self.assertEqual(step["type"], "question")
        self.assertEqual(step["question_id"], "q:stable")

    def test_group_averages_preserve_recipe_variation_and_legacy_indifference(self):
        rows = candidates(.35, 0)
        for row in rows:
            row["food_group"] = "Group"
        m = model(rows)
        group = next(i for i, key in enumerate(m.node_ids) if key.startswith("group:"))
        self.assertAlmostEqual(m.values[0, group], .5)
        self.assertLess(m.resolution[0, group], 1)
        self.assertLess(m.values[0, m.node_index["food:1"]], .8)

    def test_snapshot_roundtrip_and_undo_preserve_std_effect(self):
        rows = candidates()
        engine = DecisionTreeEngine(rows, SCHEMA)
        first = engine.start()
        engine.answer(first["question_id"], "yes")
        snapshot = engine.snapshot()
        self.assertEqual(snapshot["engine_version"], POLICY_VERSION)
        restored = DecisionTreeEngine.from_snapshot(rows, SCHEMA, snapshot)
        self.assertEqual(restored.next_step(), engine.next_step())
        np.testing.assert_allclose(restored.belief, engine.belief)
        self.assertEqual(restored.undo(), first)
        changed = copy.deepcopy(rows)
        changed[0]["feature_std"]["variable"] = .2
        with self.assertRaisesRegex(ValueError, "differs"):
            DecisionTreeEngine.from_snapshot(changed, SCHEMA, snapshot)
        snapshot["engine_version"] = "decision-tree.1.0"
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            DecisionTreeEngine.from_snapshot(rows, SCHEMA, snapshot)
