# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Downstream impact: does the decision tree do worse with AI-extracted features
than with human-reviewed ones?

The candidates are the dishes with both a complete human reference (ratings
averaged over raters) and extracted features. For each target dish, a simulated
user answers from the human features (the decision tree's ResponseOracle), and
the engine runs one fixed policy twice: on the human features and on the AI
features. Both runs see the same answers for the same questions. Reported per
feature source: first-pick acceptance (the first proposal was accepted) and
interactions to acceptance (questions + proposals).

ResponseOracle's answer probabilities are fixed assumptions. They are what real
user logs should calibrate once the app records them.
"""

from __future__ import annotations

import random
import statistics

from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION
from menus.services import get_feature_schema
from question_engines.decision_tree import DecisionTreeEngine
from question_engines.decision_tree.catalog import CandidateCatalog
from question_engines.decision_tree.evaluation import ResponseOracle

MAX_REJECTIONS = 5
SOURCES = ("human", "ai")


def candidates(features: dict[str, tuple[dict, dict]]) -> list[dict]:
    """Decision-tree candidates for {dish: (means, stds)}; meal_variety is 0 (no set information)."""
    rows = []
    for food_id, (name, (means, stds)) in enumerate(sorted(features.items()), start=1):
        rows.append({"food_id": food_id, "name": name, "display_name": name, "food_group": "",
                     "features": {k: means.get(k, 0.0) for k in FEATURE_KEYS},
                     "feature_std": {k: stds.get(k, 0.0) for k in FEATURE_KEYS}, "offers": []})
    return rows


def play(engine_catalog, truth_catalog, food_id, seed, trial, policy) -> dict:
    engine = DecisionTreeEngine(engine_catalog, config={"policy": policy})
    oracle = ResponseOracle(truth_catalog, food_id, seed, trial)
    step, guesses, first, accepted = engine.start(), 0, None, False
    for _ in range(len(truth_catalog.questions) + MAX_REJECTIONS + 1):
        if step["type"] == "question":
            step = engine.answer(step["question_id"], oracle.answer(step["question_id"]))
        elif step["type"] == "guess":
            guesses += 1
            accepted = oracle.accepts(step)
            first = accepted if first is None else first
            if accepted or guesses >= MAX_REJECTIONS:
                break
            step = engine.feedback(step["guess_id"], False)
        else:
            break
    return {"first_pick": bool(first), "accepted": accepted, "interactions": engine.question_count + guesses}


def evaluate(runset, reference, policy, trials=None, seed=20261020) -> dict:
    title = "6. Downstream impact"
    shared = {name: reference[name] for name in reference if runset.mean(name) is not None}
    if len(shared) < 2:
        return {"title": title, "skipped": "Needs at least two dishes with both a complete human "
                "reference (--ratings) and extracted features."}
    index = {key: i for i, key in enumerate(runset.keys)}
    extracted = {name: ({k: float(runset.mean(name)[i]) for k, i in index.items()},
                        {k: float(runset.std(name)[i]) for k, i in index.items()}) for name in shared}
    schema = get_feature_schema(FEATURE_VERSION)
    catalogs = {"human": CandidateCatalog(candidates(shared), schema),
                "ai": CandidateCatalog(candidates(extracted), schema)}
    targets = [c.food_id for c in catalogs["human"].candidates]
    if trials is not None:
        targets = random.Random(seed).sample(targets, min(trials, len(targets)))
    results = {source: [play(catalogs[source], catalogs["human"], food_id, seed, trial, policy)
                        for trial, food_id in enumerate(targets)] for source in SOURCES}
    rows = []
    for source in SOURCES:
        sessions = results[source]
        accepted = [s["interactions"] for s in sessions if s["accepted"]]
        rows.append([source, len(sessions), f"{statistics.fmean(s['first_pick'] for s in sessions):.1%}",
                     f"{statistics.fmean(s['accepted'] for s in sessions):.1%}",
                     f"{statistics.fmean(accepted):.2f}" if accepted else "-",
                     f"{statistics.fmean(s['interactions'] for s in sessions):.2f}"])
    pairs = list(zip(results["human"], results["ai"]))
    lines = [f"{len(shared)} dishes, {len(targets)} targets, policy `{policy}`, simulated answers from the "
             "human features.",
             f"First pick: AI features lose {sum(h['first_pick'] and not a['first_pick'] for h, a in pairs)} and "
             f"win {sum(a['first_pick'] and not h['first_pick'] for h, a in pairs)} targets against human features."]
    return {"title": title, "lines": lines, "tables": [
        ("downstream.csv", "Per feature source",
         ["features", "sessions", "first-pick acceptance", f"accepted within {MAX_REJECTIONS} proposals",
          "interactions to acceptance", "interactions (all sessions)"], rows, len(rows))]}
