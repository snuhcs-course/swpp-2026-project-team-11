"""Paired synthetic comparison: group mode against separate sessions aggregated by Nash welfare.

Each member wants a target menu and answers through `respond` (a ResponseOracle, or the
LLM simulated user in the command). Their true satisfaction with a restaurant is the best
feature similarity to that target (1 - mean absolute difference, as in benchmark/metrics.py)
among its menus they can eat, and the true group score is sum_i log(EPSILON + that).
Every arm of a case gets the same answer for the same member and question. Results are
reported per situation, never averaged across them.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import random

import numpy as np

from question_engines.decision_tree.catalog import CandidateCatalog
from question_engines.decision_tree.engine import DecisionTreeEngine
from question_engines.decision_tree.evaluation import ResponseOracle
from .engine import GroupConfig, GroupEngine, PICKS, closest, features, fit, picks, restaurants

SITUATIONS = ("similar", "conflict", "restricted")
SIZES = (2, 4, 6, 8)
ARMS = ("group", "separate", "separate_matched", "most_menus")
ALLERGIES = ("pork", "wheat", "milk", "egg")  # one member of a restricted group has one of these
SEPARATE_LIMIT = 20  # questions per separate session, as in the engine benchmark
EPSILON = .05
# Pass criteria, per situation, fixed before the case sets they judge (README).
QUESTION_SHARE = .5  # group asks at most half the questions of separate sessions
REGRET_MARGIN = .02  # and loses at most .02 Nash welfare per member against them


def _similarity(x, rows):
    """Similarity of the menus at `rows` to every menu: (len(rows), F)."""
    return 1 - np.abs(x[rows][:, None] - x[None]).mean(-1)


def build_cases(catalog, safe, *, groups, seed):
    """`groups` cases per situation and size; `safe` maps each allergy to the food IDs without it.

    A restricted group's first member has one allergy that leaves at least one menu.
    """
    ids = [c.food_id for c in catalog.candidates]
    x = features(catalog)
    usable = sorted(key for key in safe if safe[key] & set(ids))
    rng = random.Random(seed)
    cases = []
    for situation in SITUATIONS:
        for size in SIZES:
            for _ in range(groups):
                chosen, allergy = [rng.randrange(len(ids))], None
                if situation == "similar":
                    order = np.argsort(-_similarity(x, chosen)[0], kind="stable")
                    neighbours = [int(j) for j in order if j != chosen[0]][:10]
                    chosen += rng.sample(neighbours, size - 1)
                elif situation == "conflict":
                    while len(chosen) < size:
                        closeness = _similarity(x, chosen).max(0)
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


def _separate(catalogs, catalog, members, ask, max_questions):
    """Each member's own preference session until it would propose a menu: (beliefs, questions)."""
    beliefs, asked = [], []
    for i, member in enumerate(members):
        engine = DecisionTreeEngine(catalogs[member["allergy"]], config={"max_questions": max(max_questions, 1)})
        step = engine.start()
        while step["type"] == "question" and engine.question_count < max_questions:
            step = engine.answer(step["question_id"], ask(i, step))
        probabilities = engine.probabilities
        beliefs.append([probabilities.get(c.food_id, 0.) for c in catalog.candidates])
        asked.append(engine.question_count)
    return np.array(beliefs), asked


def _outcome(names, truth, chosen, menu, questions, rounds):
    """The first pick decides the criteria; `picks` reports each against the truth."""
    nash = np.log(EPSILON + truth).sum(0)
    regret = (nash.max() - nash) / len(truth)
    r = chosen[0][1]
    return {"restaurant": names[r], "best": bool(nash[r] >= nash.max() - 1e-12), "regret_per_member": float(regret[r]),
            "min_satisfaction": float(truth[:, r].min()), "menu_satisfaction": menu,
            "picks": {kind: {"restaurant": names[p], "regret_per_member": float(regret[p]),
                             "mean_satisfaction": float(truth[:, p].mean()),
                             "min_satisfaction": float(truth[:, p].min())} for kind, p in chosen},
            "best_pick_regret_per_member": float(min(regret[p] for _, p in chosen)),
            "questions": questions, "rounds": rounds}


def compare(candidates, schema, safe, cases, respond, *, config=None, workers=1):
    config = config if isinstance(config, GroupConfig) else GroupConfig(**(config or {}))
    catalog = CandidateCatalog(candidates, schema)
    ids = [c.food_id for c in catalog.candidates]
    names, serves = restaurants(catalog)
    x = features(catalog)
    allergies = {m["allergy"] for case in cases for m in case["members"]} - {None}
    catalogs = {None: catalog} | {key: CandidateCatalog([c for c in candidates if c["food_id"] in safe[key]], schema)
                                  for key in allergies}

    def run(n, case):
        members = case["members"]
        excluded = [set(ids) - safe[m["allergy"]] if m["allergy"] else set() for m in members]
        allowed = np.array([[food_id not in banned for food_id in ids] for banned in excluded])
        similarity = _similarity(x, [ids.index(m["target"]) for m in members]) * allowed
        truth = np.array([np.where(serves, row, 0).max(1) for row in similarity])

        def ask(i, step):
            return respond(n, i, members[i]["target"], step)

        def told(r, beliefs):
            """Mean similarity to their targets of the menus each member would be told at r."""
            options = [np.flatnonzero(serves[r] & row) for row in allowed]
            return float(np.mean([similarity[i, closest(x, b, o)] if o.size else 0.
                                  for i, (b, o) in enumerate(zip(beliefs, options))]))

        fits = [fit(catalog, frozenset(banned)) for banned in excluded]
        group = GroupEngine(catalog, None, excluded, config=config)
        while not group.finished:
            for i, step in group.questions().items():
                group.answer(i, step["question_id"], ask(i, step))
        chosen = group.recommendation()["picks"]
        menu = float(np.mean([similarity[i, ids.index(m["food_id"])] if m else 0.
                              for i, m in enumerate(chosen[0]["menus"])]))
        result = dict(case, group=_outcome(names, truth, [(p["kind"], names.index(p["restaurant"])) for p in chosen],
                                           menu, sum(len(m.answers) for m in group.members), group.round))
        # Separate sessions as they stop by themselves, and capped at the group's round count.
        for arm, cap in (("separate", SEPARATE_LIMIT), ("separate_matched", group.round)):
            beliefs, asked = _separate(catalogs, catalog, members, ask, cap)
            chosen = picks(np.array([f @ b for f, b in zip(fits, beliefs)]))
            result[arm] = _outcome(names, truth, chosen, told(chosen[0][1], beliefs), sum(asked), max(asked))
        # Every menu equally likely to be the one wanted: the restaurants with the most menus
        # among those where every member can eat.
        chosen = picks(serves.mean(1) * (serves[None] & allowed[:, None]).any(-1))
        uniform = allowed / allowed.sum(1, keepdims=True)
        result["most_menus"] = _outcome(names, truth, chosen, told(chosen[0][1], uniform), 0, 0)
        return result

    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(run, range(len(cases)), cases))
    return {"config": {"epsilon": EPSILON, "group": asdict(config), "separate_limit": SEPARATE_LIMIT,
                       "safe_menus": {key: len(safe[key]) for key in sorted(safe)},
                       "menus": len(ids), "restaurants": len(names), "catalog": catalog.fingerprint},
            "summary": summarize(results), "cases": results}


def _means(rows):
    def mean(values):
        return float(np.mean(list(values)))

    return {arm: {"best_restaurant": mean(c[arm]["best"] for c in rows),
                  **{key: mean(c[arm][key] for c in rows)
                     for key in ("regret_per_member", "best_pick_regret_per_member", "min_satisfaction",
                                 "menu_satisfaction", "questions", "rounds")},
                  "picks": {kind: {"cases": len(given), **{key: mean(p[key] for p in given) for key in
                                                           ("regret_per_member", "mean_satisfaction", "min_satisfaction")}}
                            for kind in PICKS if (given := [c[arm]["picks"][kind] for c in rows if kind in c[arm]["picks"]])}}
            for arm in ARMS}


def summarize(results):
    """Means per situation (with the pass verdict) and per situation and size."""
    summary = {}
    for situation in SITUATIONS:
        rows = [c for c in results if c["situation"] == situation]
        if not rows:
            continue
        means = _means(rows)
        group, separate, matched, most = (means[arm]["regret_per_member"] for arm in ARMS)
        checks = {"questions": means["group"]["questions"] <= QUESTION_SHARE * means["separate"]["questions"],
                  "regret_vs_separate": group - separate <= REGRET_MARGIN,
                  "regret_vs_matched": group < matched,
                  "regret_vs_most_menus": group < most,
                  "menu_vs_most_menus": means["group"]["menu_satisfaction"] > means["most_menus"]["menu_satisfaction"]}
        summary[situation] = {"cases": len(rows), **means, "checks": checks, "passed": all(checks.values()),
                              "by_size": {size: _means([c for c in rows if c["size"] == size])
                                          for size in SIZES if any(c["size"] == size for c in rows)}}
    return summary
