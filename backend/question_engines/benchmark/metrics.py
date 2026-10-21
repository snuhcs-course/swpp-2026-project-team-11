# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Per-session metrics, from a results row and its scenario. No LLM call.

- success:         the final menu is a wanted menu or a kind of one. Undefined (None)
                   when the wanted menu is not served: there, use similarity with a
                   threshold chosen from the distributions in the report.
- similarity:      1 - mean absolute feature difference between the final menu and the
                   closest wanted menu (1 = same features). Recorded in every situation.
- best_similarity: the closest any candidate came; regret = best - similarity
- rank:            share of candidates less similar than the final menu (1 = the closest)
- baselines, for first pick (not defined when the wanted menu is not served):
    random_pick:      the chance that a dish picked at random is accepted
    no_question_pick: the engine's "recommend now" before any question was accepted

A session without a final menu (gave up, unavailable, error) has no similarity and
is not a success. A wanted menu without features (a person asked for a dish that
was never tagged) gives no similarity either.
"""

from __future__ import annotations

import numpy as np

from .scenarios import is_wanted


def vector(features, keys) -> np.ndarray:
    return np.array([float(features.get(key, 0.5)) for key in keys])


def similarity(a: dict, b: dict, keys) -> float:
    return float(1 - np.abs(vector(a, keys) - vector(b, keys)).mean())


class MenuIndex:
    """Candidates of every scenario menu, by menu id and food id."""

    def __init__(self, scenario_data):
        menus = scenario_data["menus"]
        self.foods = {key: {c["food_id"]: c for c in menu["candidates"]} for key, menu in menus.items()}
        first = next(iter(menus.values()))["candidates"]
        self.keys = sorted(first[0]["features"]) if first else []

    def closeness(self, scenario, food) -> float | None:
        values = [similarity(food["features"], target["features"], self.keys)
                  for target in scenario["targets"] if target.get("features")]
        return max(values) if values else None


def session(record, scenario, index: MenuIndex) -> dict:
    foods = index.foods[scenario["menu"]]
    row = {key: record.get(key) for key in ("scenario", "situation", "certainty", "engine", "repeat", "outcome",
                                            "first_guess_accepted", "first_guess_exact", "questions", "guesses",
                                            "engine_ms")}
    row["interactions"] = (record.get("questions") or 0) + (record.get("guesses") or 0)
    llm = record.get("llm") or {}
    row.update({"llm_calls": llm.get("calls", 0), "input_tokens": llm.get("input_tokens", 0),
                "output_tokens": llm.get("output_tokens", 0), "cost_usd": llm.get("cost_usd", 0.0),
                "fallback": llm.get("fallbacks", 0) > 0})
    row.update(baselines(record, scenario, foods))
    closeness = {food_id: index.closeness(scenario, food) for food_id, food in foods.items()}
    known = [value for value in closeness.values() if value is not None]
    best = max(known) if known else None
    final = foods.get(record.get("final_food_id"))
    served = scenario["situation"] != "not_in_menu"
    sim = closeness[final["food_id"]] if final else None
    row.update(success=(final is not None and is_wanted(scenario, final["food_id"])) if served else None,
               similarity=_round(sim), best_similarity=_round(best),
               regret=_round(best - sim) if sim is not None else None,
               rank=round(sum(other < sim for other in known) / max(len(known) - 1, 1), 4) if sim is not None else None)
    return row


def baselines(record, scenario, foods) -> dict:
    if scenario["situation"] == "not_in_menu":
        return {"random_pick": None, "no_question_pick": None}
    names = {food["display_name"] for food in foods.values()}
    wanted = {name for target in scenario["targets"] for name in target["match_names"]}
    first = (record.get("anytime") or {}).get("0")
    return {"random_pick": round(len(names & wanted) / len(names), 4) if names else None,
            "no_question_pick": is_wanted(scenario, first["food_id"], first.get("group")) if first else None}


def _where(record, number) -> dict:
    where = {key: record.get(key) for key in ("scenario", "situation", "certainty", "engine", "repeat")}
    return where | {"step": number}


def questions(record) -> list[dict]:
    """Every question of a session: the answer the engine got and the simulated user's raw one."""
    return [_where(record, number) | {"question": step["question"], "answer": step["answer"],
                                      "raw": step.get("raw"), "blurred": step.get("blurred")}
            for number, step in enumerate(record.get("trace", []), start=1) if "question" in step]


def proposals(record, scenario, index: MenuIndex) -> list[dict]:
    """Every proposal of a session: what it was, whether it was a wanted menu by the rule, the
    verdict and how it was reached, and its similarity to the closest wanted menu."""
    foods = index.foods[scenario["menu"]]
    rows = []
    for number, step in enumerate(record.get("trace", []), start=1):
        if "proposal" in step:
            food = foods.get(step["proposal"])
            rows.append(_where(record, number) | {
                "food_id": step["proposal"], "label": step["label"], "group_size": len(step["group"] or []) or None,
                "wanted": is_wanted(scenario, step["proposal"], step["group"]), "accepted": step["accepted"],
                "judged_by": step.get("judged_by"),
                "similarity": _round(index.closeness(scenario, food)) if food else None})
    return rows


def anytime(record, scenario, index: MenuIndex) -> list[dict]:
    """The "recommend now" proposals taken at fixed question counts."""
    foods = index.foods[scenario["menu"]]
    rows = []
    for k, proposal in (record.get("anytime") or {}).items():
        food = foods.get((proposal or {}).get("food_id"))
        rows.append({"situation": scenario["situation"], "engine": record["engine"], "k": int(k),
                     "success": is_wanted(scenario, food["food_id"], proposal.get("group")) if food and
                     scenario["situation"] != "not_in_menu" else None,
                     "similarity": _round(index.closeness(scenario, food)) if food else None})
    return rows


def _round(value):
    return None if value is None else round(value, 4)
