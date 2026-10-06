"""Paired synthetic evaluation with a shared, order-independent answer oracle.

This measures internal menu matching and latency, not human acceptance. Both
policies receive the same answer for the same target/question/trial. The oracle
never reads an engine's beliefs, importance estimates, or planning policy.
"""
from dataclasses import asdict
import hashlib
import json
import platform
import random
import statistics
import time

import numpy as np

from .catalog import CandidateCatalog
from .engine import DecisionTreeEngine
from .planning import PlannerConfig, POLICY_VERSION


def _uniform(*parts):
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


class ResponseOracle:
    def __init__(self, catalog, food_id, seed, trial):
        self.catalog, self.food_id, self.seed, self.trial = catalog, food_id, seed, trial
        self.by_question = {q["id"]: q for q in catalog.questions}

    def answer(self, question_id):
        question = self.by_question[question_id]
        probability = self.catalog.by_id[self.food_id].features[question["attribute"]]
        irrelevant = _uniform(self.seed, self.trial, self.food_id, question["family"], "importance") < .2
        unknown, indifferent = .05, (.70 if irrelevant else .15)
        positive = np.array([.72, .20, .06, .02])
        directional = probability * positive + (1 - probability) * positive[::-1]
        weights = np.zeros(6)
        weights[[0, 1, 3, 4]] = (1 - unknown - indifferent) * directional
        weights[2], weights[5] = indifferent, unknown
        index = min(int(np.searchsorted(np.cumsum(weights), _uniform(self.seed, self.trial, self.food_id, question_id, "answer"))), 5)
        return ("yes", "probably_yes", "any", "probably_no", "no", "unknown")[index]

    def accepts(self, step):
        if step["target_kind"] == "group":
            return self.food_id in step["group"]["food_ids"]
        proposed = step["food"]["display_name"].strip().casefold()
        target = self.catalog.by_id[self.food_id].display_name.strip().casefold()
        return step["food"]["food_id"] == self.food_id or proposed == target


def _percentile(values, fraction):
    sorted_values = sorted(values)
    return sorted_values[min(len(values)-1, int(fraction * (len(values)-1)))]


def compare_policies(candidates, feature_schema, *, trials=12, seed=20261006,
                     context=None, planner_config=None):
    if type(trials) is not int or not 1 <= trials <= 200:
        raise ValueError("trials must be in 1..200")
    catalog = CandidateCatalog(candidates, feature_schema, context=context)
    if not catalog.candidates:
        raise ValueError("No candidates available for evaluation")
    cfg = planner_config if isinstance(planner_config, PlannerConfig) else PlannerConfig(**(planner_config or {}))
    ids = [c.food_id for c in catalog.candidates]
    random.Random(seed).shuffle(ids)
    targets = [ids[trial % len(ids)] for trial in range(trials)]
    records = {policy: [] for policy in ("greedy", "lookahead")}
    for trial, food_id in enumerate(targets):
        oracle = ResponseOracle(catalog, food_id, seed, trial)
        for policy in records:
            start = time.perf_counter()
            engine = DecisionTreeEngine(catalog, config={"policy": policy}, planner_config=cfg)
            build_ms = (time.perf_counter() - start) * 1000
            start = time.perf_counter()
            step = engine.start()
            decision_ms = [build_ms + (time.perf_counter() - start) * 1000]
            trace, guesses = [], 0
            first_match, match, exact = None, False, False
            proposal_size = 0
            # Every question and displayed alias can occur at most once. This
            # is an evaluator invariant, not an application question limit.
            action_bound = len(catalog.questions) + len(catalog.food_tree.proposal_ids) + 1
            for _ in range(action_bound):
                if step["type"] == "unavailable":
                    break
                if step["type"] == "question":
                    answer = oracle.answer(step["question_id"])
                    trace.append({"question_id": step["question_id"], "answer_id": answer})
                    start = time.perf_counter()
                    step = engine.answer(step["question_id"], answer)
                    decision_ms.append((time.perf_counter() - start) * 1000)
                    continue
                if step["type"] != "guess":
                    raise AssertionError("Unexpected benchmark step")
                guesses += 1
                matched = oracle.accepts(step)
                if first_match is None:
                    first_match = matched
                proposal_size = len(step.get("group", {}).get("food_ids", [step["food"]["food_id"]]))
                trace.append({"guess_id": step["guess_id"], "representative_food_id": step["food"]["food_id"],
                              "target_kind": step["target_kind"], "synthetic_match": matched})
                if matched:
                    match = True
                    exact = step["food"]["food_id"] == food_id
                    step = engine.feedback(step["guess_id"], True)
                    break
                start = time.perf_counter()
                step = engine.feedback(step["guess_id"], False)
                decision_ms.append((time.perf_counter() - start) * 1000)
            else:
                raise AssertionError("Engine exceeded its finite action bound")
            records[policy].append({"trial": trial, "target_food_id": food_id,
                "first_guess_menu_match": bool(first_match), "eventual_menu_match": match,
                "exact_food_id_match": exact, "questions": engine.question_count,
                "guesses": guesses, "interactions": engine.question_count + guesses,
                "proposal_size": proposal_size, "terminal_type": step["type"],
                "construction_ms": build_ms, "decision_ms": decision_ms, "trace": trace})
    summaries = {}
    for policy, runs in records.items():
        times = [value for row in runs for value in row["decision_ms"]]
        summaries[policy] = {
            "first_guess_menu_match_rate": statistics.mean(r["first_guess_menu_match"] for r in runs),
            "eventual_menu_match_rate": statistics.mean(r["eventual_menu_match"] for r in runs),
            "exact_food_id_match_rate": statistics.mean(r["exact_food_id_match"] for r in runs),
            "mean_questions": statistics.mean(r["questions"] for r in runs),
            "mean_guesses": statistics.mean(r["guesses"] for r in runs),
            "mean_interactions": statistics.mean(r["interactions"] for r in runs),
            "mean_proposal_size": statistics.mean(r["proposal_size"] for r in runs),
            "latency_ms": {"median": statistics.median(times), "p95": _percentile(times, .95), "max": max(times)},
        }
    return {"engine_version": POLICY_VERSION, "catalog_fingerprint": catalog.fingerprint,
            "context": catalog.context, "candidate_count": len(catalog.candidates), "feature_count": len(catalog.questions),
            "trials": trials, "seed": seed, "planner_config": asdict(cfg),
            "environment": {"python": platform.python_version(), "numpy": np.__version__,
                            "machine": platform.machine(), "platform": platform.platform()},
            "assumptions": ["One fixed cafeteria target per trial; answers independent of policy and question order",
                "Oracle importance is fixed per question family, not taken from engine state",
                "Group membership or identical display name counts as a synthetic menu match",
                "Exact representative food-ID matching and group size are reported separately",
                "LLM-derived features and synthetic matches are not real-user acceptance",
                "Timing includes model construction on first step; excludes interpreter imports, HTTP and Android"],
            "summary": summaries, "records": records}
