"""Paired synthetic comparison: group mode against separate sessions aggregated by Nash welfare.

Each member wants a target menu and answers through `respond` (a ResponseOracle, or the
LLM simulated user in the command). Their true satisfaction with a menu is its feature
similarity to that target (1 - mean absolute difference, as in benchmark/metrics.py),
0 for a menu they cannot eat. Every arm of a case gets the same answer for the same
member and question. Results are reported per situation, never averaged across them.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import random

import numpy as np

from question_engines.decision_tree.catalog import CandidateCatalog
from question_engines.decision_tree.engine import DecisionTreeEngine
from question_engines.decision_tree.evaluation import ResponseOracle
from .engine import EPSILON, GroupConfig, GroupEngine, restaurant_fit, restaurants, welfare

SITUATIONS = ("similar", "conflict", "restricted")
SIZES = (2, 3, 5)
ARMS = ("group", "separate", "separate_matched")
ALLERGIES = ("pork", "wheat", "milk", "egg")  # one member of a restricted group has one of these
SEPARATE_LIMIT = 20  # questions per separate session, as in the engine benchmark
# Pass criteria, per situation, fixed before the first run.
QUESTION_SHARE = .5  # group asks at most half the questions of separate sessions
REGRET_MARGIN = .02  # and loses at most .02 Nash welfare per member against them


def _similarity(catalog):
    x = np.array([[c.features[key] for key in catalog.feature_keys] for c in catalog.candidates])
    return 1 - np.abs(x[:, None] - x[None]).mean(-1)


def build_cases(catalog, safe, *, groups, seed):
    """`groups` cases per situation and size; `safe` maps each allergy to the food IDs without it.

    A restricted group's first member has one allergy that leaves at least one menu.
    """
    ids = [c.food_id for c in catalog.candidates]
    similarity = _similarity(catalog)
    usable = sorted(key for key in safe if safe[key] & set(ids))
    rng = random.Random(seed)
    cases = []
    for situation in SITUATIONS:
        for size in SIZES:
            for _ in range(groups):
                chosen, allergy = [rng.randrange(len(ids))], None
                if situation == "similar":
                    neighbours = [int(j) for j in np.argsort(-similarity[chosen[0]], kind="stable")[1:11]]
                    chosen += rng.sample(neighbours, size - 1)
                elif situation == "conflict":
                    while len(chosen) < size:
                        closeness = similarity[chosen].max(0)
                        far = [int(j) for j in np.argsort(closeness, kind="stable") if j not in chosen][:5]
                        chosen.append(rng.choice(far))
                else:
                    allergy = rng.choice(usable)
                    chosen = [ids.index(rng.choice(sorted(safe[allergy] & set(ids))))]
                    chosen += [rng.randrange(len(ids)) for _ in range(size - 1)]
                cases.append({"situation": situation, "size": size,
                              "members": [{"target": ids[j], "allergy": allergy if i == 0 else None}
                                          for i, j in enumerate(chosen)]})
    return cases


def oracle(catalog, seed):
    """`respond` of deterministic ResponseOracle members; no key or network."""
    def respond(case_no, member_no, target, step):
        return ResponseOracle(catalog, target, seed, [case_no, member_no]).answer(step["question_id"])
    return respond


def _separate(candidates, schema, catalog, excluded, ask, max_questions):
    """Each member's own preference session until it would propose a menu: (fits, questions)."""
    fits, asked = [], []
    for i, banned in enumerate(excluded):
        engine = DecisionTreeEngine([c for c in candidates if c["food_id"] not in banned], schema,
                                    config={"max_questions": max_questions})
        step = engine.start()
        while step["type"] == "question":
            step = engine.answer(step["question_id"], ask(i, step))
        scores = engine.recommendation_scores
        fits.append([scores.get(c.food_id, 0.) for c in catalog.candidates])
        asked.append(engine.question_count)
    return np.array(fits), asked


def _outcome(names, serves, truth, r, questions, rounds):
    satisfaction = restaurant_fit(serves, truth)
    nash = np.log(EPSILON + satisfaction).sum(0)
    regret = float(nash.max() - nash[r])
    return {"restaurant": names[r], "best": bool(nash[r] >= nash.max() - 1e-12), "regret": regret,
            "regret_per_member": regret / len(truth), "min_satisfaction": float(satisfaction[:, r].min()),
            "questions": questions, "rounds": rounds}


def compare(candidates, schema, safe, cases, respond, *, config=None, workers=1):
    config = config if isinstance(config, GroupConfig) else GroupConfig(**(config or {}))
    catalog = CandidateCatalog(candidates, schema)
    ids = [c.food_id for c in catalog.candidates]
    names, serves = restaurants(catalog)
    similarity = _similarity(catalog)

    def run(n, case):
        members = case["members"]
        excluded = [set(ids) - safe[m["allergy"]] if m["allergy"] else set() for m in members]
        allowed = np.array([[food_id not in banned for food_id in ids] for banned in excluded])
        truth = similarity[[ids.index(m["target"]) for m in members]] * allowed

        def ask(i, step):
            return respond(n, i, members[i]["target"], step)

        group = GroupEngine(candidates, schema, excluded, config=config)
        while not group.finished:
            for i, step in group.questions().items():
                group.answer(i, step["question_id"], ask(i, step))
        r = names.index(group.recommendation()["restaurant"])
        result = dict(case, group=_outcome(names, serves, truth, r,
                                           sum(len(m.answers) for m in group.members), group.round))
        # Separate sessions as they stop by themselves, and capped at the group's round count.
        for arm, cap in (("separate", SEPARATE_LIMIT), ("separate_matched", group.round)):
            fits, asked = _separate(candidates, schema, catalog, excluded, ask, cap)
            result[arm] = _outcome(names, serves, truth, int(welfare(serves, fits).argmax()), sum(asked), max(asked))
        return result

    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(run, range(len(cases)), cases))
    return {"config": {"epsilon": EPSILON, "group": asdict(config), "separate_limit": SEPARATE_LIMIT,
                       "safe_menus": {key: len(safe[key]) for key in sorted(safe)},
                       "catalog": catalog.fingerprint},
            "summary": summarize(results), "cases": results}


def _means(rows):
    return {arm: {"best_restaurant": float(np.mean([c[arm]["best"] for c in rows])),
                  **{key: float(np.mean([c[arm][key] for c in rows]))
                     for key in ("regret_per_member", "min_satisfaction", "questions", "rounds")}}
            for arm in ARMS}


def summarize(results):
    """Means per situation (with the pass verdict) and per situation and size."""
    summary = {}
    for situation in SITUATIONS:
        rows = [c for c in results if c["situation"] == situation]
        if not rows:
            continue
        means = _means(rows)
        group, separate, matched = (means[arm] for arm in ARMS)
        checks = {"questions": group["questions"] <= QUESTION_SHARE * separate["questions"],
                  "regret_vs_separate": group["regret_per_member"] - separate["regret_per_member"] <= REGRET_MARGIN,
                  "regret_vs_matched": group["regret_per_member"] < matched["regret_per_member"]}
        summary[situation] = {"cases": len(rows), **means, "checks": checks, "passed": all(checks.values()),
                              "by_size": {size: _means([c for c in rows if c["size"] == size])
                                          for size in SIZES if any(c["size"] == size for c in rows)}}
    return summary
