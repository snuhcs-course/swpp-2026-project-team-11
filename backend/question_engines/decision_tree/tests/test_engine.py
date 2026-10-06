import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from .. import DecisionTreeEngine, EngineConfig, PlannerConfig
from ..planning import Planner
from .helpers import small_catalog, candidate


def engine(**kwargs):
    return DecisionTreeEngine(small_catalog(), config=EngineConfig(policy="greedy"), **kwargs)


class EngineTests(unittest.TestCase):
    def test_six_english_choices_and_copy_isolation(self):
        e = engine()
        step = e.start()
        self.assertEqual(step["type"], "question")
        self.assertEqual(len(step["options"]), 6)
        self.assertTrue(step["text"].isascii())
        self.assertTrue(all(o["label"].isascii() for o in step["options"]))
        step["options"][0]["id"] = "invalid"
        self.assertEqual(e.next_step()["options"][0]["id"], "yes")
        self.assertNotIn("diagnostics", step)

    def test_start_is_idempotent_and_answer_is_not_reapplied(self):
        e = engine()
        before = e.start()
        self.assertEqual(e.start(), before)
        e.answer(before["question_id"], "yes")
        snap = e.snapshot()
        with self.assertRaises(ValueError):
            e.answer(before["question_id"], "yes")
        self.assertEqual(e.snapshot(), snap)
        self.assertEqual(e.question_count, 1)

    def test_invalid_answer_and_feedback_do_not_mutate_state(self):
        e = engine()
        step, snap = e.start(), e.snapshot()
        for question, answer in (("missing", "yes"), (step["question_id"], "missing")):
            with self.assertRaises(ValueError):
                e.answer(question, answer)
            self.assertEqual(e.snapshot(), snap)
        with self.assertRaises(ValueError):
            e.feedback("missing", True)
        self.assertEqual(e.snapshot(), snap)

    def test_group_acceptance_returns_real_food_and_original_offers(self):
        e = DecisionTreeEngine(small_catalog(), config=EngineConfig(policy="greedy", greedy_acceptance_threshold=0))
        step = e.start()
        self.assertEqual(step["target_kind"], "group")
        self.assertEqual(set(step["group"]["food_ids"]), {1, 2})
        offered = step["food"]["food_id"]
        result = e.feedback(step["guess_id"], True)
        self.assertEqual(result["type"], "recommendation")
        self.assertEqual(result["food"]["food_id"], offered)
        self.assertEqual(result["food"]["offers"], small_catalog().by_id[offered].summary()["offers"])
        self.assertTrue(all(p > 0 for p in e.probabilities.values()))
        self.assertEqual(e.undo(), step)

    def test_group_rejection_suppresses_all_children_and_can_exhaust(self):
        e = DecisionTreeEngine(small_catalog(), config=EngineConfig(policy="greedy", greedy_acceptance_threshold=0))
        group = e.start()
        next_step = e.feedback(group["guess_id"], False)
        self.assertEqual(next_step["food"]["food_id"], 3)
        self.assertTrue(all(p > 0 for p in e.probabilities.values()))
        ended = e.feedback(next_step["guess_id"], False)
        self.assertEqual(ended["type"], "unavailable")
        self.assertEqual(ended["reason"], "candidates_exhausted")
        self.assertEqual(e.undo(), next_step)

    def test_duplicate_display_name_is_not_recommended_again(self):
        rows = [candidate(1, "Same dish", "", .9, .9), candidate(2, "same  DISH", "", .1, .9), candidate(3, "Other meal", "", .1, .1)]
        e = DecisionTreeEngine(rows, [{"key": "beef"}, {"key": "soupy"}], config={"policy": "greedy"})
        first = e.recommend_now()
        self.assertEqual(first["food"]["display_name"], "Same dish")
        e.feedback(first["guess_id"], False)
        second = e.recommend_now()
        self.assertEqual(second["food"]["food_id"], 3)

    def test_recommend_now_and_accept_are_undoable(self):
        e = engine()
        question = e.start()
        guess = e.recommend_now()
        e.feedback(guess["guess_id"], True)
        self.assertEqual(e.undo(), guess)
        self.assertEqual(e.undo(), question)
        self.assertEqual(e.question_count, 0)

    def test_snapshot_restores_actual_action_without_replanning(self):
        e = engine()
        e.start()
        guess = e.recommend_now()
        e.feedback(guess["guess_id"], False)
        snapshot = json.loads(json.dumps(e.snapshot()))
        with patch.object(Planner, "plan", side_effect=AssertionError("Replay must not run timed planning")):
            restored = DecisionTreeEngine.from_snapshot(small_catalog(), None, snapshot)
            self.assertEqual(restored.next_step(), e.next_step())
            np.testing.assert_allclose(restored.belief, e.belief)
            np.testing.assert_allclose(restored.salience, e.salience)
            self.assertEqual(restored.undo(), guess)

    def test_snapshot_rejects_data_and_config_changes(self):
        e = engine()
        snapshot = e.snapshot()
        bad = copy.deepcopy(snapshot)
        bad["config"]["policy"] = "lookahead"
        with self.assertRaises(ValueError):
            DecisionTreeEngine.from_snapshot(small_catalog(), None, bad)
        from ..catalog import CandidateCatalog
        c = small_catalog()
        rows = [x.summary() | {"features": dict(x.features)} for x in c.candidates]
        rows[0]["features"]["beef"] = .7
        changed = CandidateCatalog(rows, [{"key": "beef"}, {"key": "soupy"}])
        with self.assertRaises(ValueError):
            DecisionTreeEngine.from_snapshot(changed, None, snapshot)

    def test_neutral_answers_have_no_hidden_six_question_limit(self):
        schema = [{"key": f"feature_{i}"} for i in range(12)]
        rows = [{"food_id": food_id, "name": f"Meal {food_id}", "features": {q["key"]: value for q in schema}}
                for food_id, value in ((1, .1), (2, .9))]
        e = DecisionTreeEngine(rows, schema, config={"policy": "greedy", "greedy_acceptance_threshold": 1, "greedy_information_floor": 0})
        asked = []
        for _ in range(12):
            step = e.next_step()
            self.assertEqual(step["type"], "question")
            asked.append(step["question_id"])
            e.answer(step["question_id"], "any")
        self.assertEqual(len(set(asked)), 12)
        self.assertEqual(e.question_count, 12)
        self.assertEqual(e.next_step()["type"], "guess")

    def test_explicit_experiment_cap_and_empty_candidates(self):
        e = DecisionTreeEngine(small_catalog(), config={"policy": "greedy", "max_questions": 1})
        step = e.start()
        result = e.answer(step["question_id"], "any")
        self.assertEqual(result["type"], "guess")
        self.assertEqual(e.question_count, 1)
        empty = DecisionTreeEngine([], [{"key": "soupy"}])
        step = empty.start()
        self.assertEqual(step["reason"], "empty_candidates")
        snap = empty.snapshot()
        restored = DecisionTreeEngine.from_snapshot([], [{"key": "soupy"}], snap)
        self.assertEqual(restored.start(), step)
        with self.assertRaises(ValueError):
            empty.recommend_now()

    def test_lookahead_step_and_diagnostics_are_json_serializable(self):
        e = DecisionTreeEngine(small_catalog(), config={"policy": "lookahead"}, planner_config=PlannerConfig(time_budget_ms=50))
        step = e.start()
        self.assertIn(step["type"], {"question", "guess"})
        json.dumps(step, allow_nan=False)
        json.dumps(e.diagnostics(), allow_nan=False)
        json.dumps(e.snapshot(), allow_nan=False)

    def test_all_snapshots_and_results_are_detached(self):
        e = engine()
        e.start()
        snapshot = e.snapshot()
        snapshot["config"]["policy"] = "changed"
        self.assertEqual(e.snapshot()["config"]["policy"], "greedy")

    def test_malformed_snapshots_are_rejected(self):
        e = engine()
        snapshot = e.snapshot()
        for invalid in ([], snapshot | {"events": "bad"}, snapshot | {"pending": None}):
            with self.assertRaises(ValueError):
                DecisionTreeEngine.from_snapshot(small_catalog(), None, invalid)

    def test_group_metadata_excludes_a_previously_rejected_member(self):
        e = engine()
        first = e.recommend_now()
        self.assertEqual(first["food"]["food_id"], 1)
        e.feedback(first["guess_id"], False)
        group = next(key for key, node in e.catalog.food_tree.nodes.items() if node.kind == "family")
        step = e._set_pending({"kind": "guess", "id": group, "food_id": 2})
        self.assertEqual(step["group"]["food_ids"], [2])
        self.assertEqual(step["food"]["food_id"], 2)
