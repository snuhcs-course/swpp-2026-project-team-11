# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Scenarios: what the user wants, on which menu. Built once and shared by both
engines and the human test, so every engine faces the same users.

    {"version": 2, "seed": 0,
     "menus": {"2026-10-20/LU": {"date", "meal", "feature_version", "candidates": [get_catalog() rows]}},
     "scenarios": [{"id": "in_menu-001", "situation": "in_menu", "certainty": "high",
                    "menu": "2026-10-20/LU",
                    "targets": [{"name", "features", "food_group", "matches": [food_id], "match_names",
                                 "close": [display names]}]}]}

The candidate lists are frozen in the file, so a later menu fetch cannot change a
scenario. A target's `matches` are the candidates that satisfy it: the menu
itself and its kinds (돈까스 -> 치즈돈까스), found by name containment after
ignoring spacing and size markers.

- in_menu:           one target served that day
- multiple:          two or three served targets with no candidate in common
- not_in_menu:       one tagged dish from another day that no candidate satisfies
- close_alternative: one served target with another served dish whose features differ
                     by at most CLOSE_GAP on average (`close`), so no question tells
                     them apart (양념치킨 next to 매운양념치킨); only the target is accepted.
                     A dish's set and single version are the same dish, not alternatives.

A user (the wanted menus) is repeated within a situation only when new ones run out.
"""

from __future__ import annotations

import json
import pathlib
import random

import numpy as np

from menus.normalize import dish_key

from . import CERTAINTY

CLOSE_GAP = 0.05  # the feature benchmark's collision gap (P12)


def menu_id(date, meal) -> str:
    return f"{date}/{meal}"


def _keys(candidate) -> set[str]:
    return {dish_key(candidate["name"]), dish_key(candidate["display_name"])}


def matches(name: str, candidates) -> list[int]:
    """Food IDs of the candidates that are `name` or a kind of it."""
    wanted = dish_key(name)
    return sorted(c["food_id"] for c in candidates if any(wanted and wanted in key for key in _keys(c)))


def is_wanted(scenario, food_id, group=None) -> bool:
    """Whether a proposal (a dish, or a group of dishes) is a wanted menu or a kind of one."""
    ids = {i for target in scenario["targets"] for i in target["matches"]}
    return set(group) <= ids if group else food_id in ids


def target(name, features, food_group, candidates) -> dict:
    ids = matches(name, candidates)
    by_id = {c["food_id"]: c for c in candidates}
    return {"name": name, "features": features, "food_group": food_group, "matches": ids,
            "match_names": sorted({by_id[i]["display_name"] for i in ids})}


def _choices(candidates) -> list[dict]:
    """One candidate per display name: the engines show dishes by that name."""
    seen = {}
    for candidate in sorted(candidates, key=lambda c: c["food_id"]):
        seen.setdefault(candidate["display_name"], candidate)
    return list(seen.values())


def gap(a: dict, b: dict) -> float:
    """Mean absolute difference of two feature dicts over their shared keys."""
    keys = sorted(a.keys() & b.keys())
    return float(np.abs(np.array([a[k] for k in keys]) - np.array([b[k] for k in keys])).mean()) if keys else 1.0


def build(menus: dict, others: list[dict], counts: dict, seed: int = 0) -> dict:
    """`menus` is {menu id: {"date", "meal", "feature_version", "candidates"}}; `others` are
    tagged dishes of other days ({"name", "features", "food_group"}), the not-served targets;
    `counts` is {situation: number of scenarios}."""
    rng = random.Random(seed)
    ids = sorted(menus)
    scenarios = []
    for situation, count in counts.items():
        made, seen = 0, set()
        for attempt in range(count * 20):
            if made == count:
                break
            key = ids[attempt % len(ids)]
            targets = _targets(situation, menus[key]["candidates"], others, rng)
            if targets is None:
                continue
            user = (key, tuple(sorted(t["name"] for t in targets)))
            if user in seen and attempt < count * 10:
                continue
            seen.add(user)
            made += 1
            scenarios.append({"id": f"{situation}-{made:03d}", "situation": situation,
                              "certainty": CERTAINTY[(made - 1) % len(CERTAINTY)], "menu": key,
                              "targets": targets})
        if made < count:
            raise ValueError(f"Only {made} {situation} scenarios could be made; add menus or lower the count.")
    return {"version": 2, "seed": seed, "menus": menus, "scenarios": scenarios}


def _targets(situation, candidates, others, rng):
    choices = _choices(candidates)
    if not choices:
        return None
    if situation == "in_menu":
        pick = rng.choice(choices)
        return [target(pick["display_name"], pick["features"], pick["food_group"], candidates)]
    if situation == "not_in_menu":
        pool = [dish for dish in others if not matches(dish["name"], candidates)]
        if not pool:
            return None
        pick = rng.choice(pool)
        return [target(pick["name"], pick["features"], pick.get("food_group", ""), candidates)]
    if situation == "close_alternative":
        pairs = []
        for pick in choices:
            made = target(pick["display_name"], pick["features"], pick["food_group"], candidates)
            close = sorted(other["display_name"] for other in choices if other["food_id"] not in made["matches"]
                           and other["name"] != pick["name"] and gap(pick["features"], other["features"]) <= CLOSE_GAP)
            if close:
                pairs.append(made | {"close": close})
        return [rng.choice(pairs)] if pairs else None
    count = rng.choice((2, 3))
    picks, used = [], set()
    for pick in rng.sample(choices, len(choices)):
        made = target(pick["display_name"], pick["features"], pick["food_group"], candidates)
        if used.isdisjoint(made["matches"]) and pick["food_group"] not in {p["food_group"] for p in picks}:
            picks.append(made)
            used.update(made["matches"])
        if len(picks) == count:
            return picks
    return None


def save(path, data) -> None:
    pathlib.Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load(path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
