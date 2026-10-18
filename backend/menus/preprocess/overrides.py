# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Human corrections from reviewing preprocessing results (overrides.json).

    {"lines":  {"돈가스 카레우동": ["돈까스", "카레우동"], "공기밥": []},
     "dishes": {"즉석마라탕": "마라탕"}}

- lines: a cleaned menu line -> its dishes ([] = not a meal). Beats every other source.
- dishes: a dish name -> the name it should be merged into. Applied to every answer.

Keys are matched by normalize.dish_key, so spacing and size markers do not matter.
"""

from __future__ import annotations

import json
import pathlib

from menus.normalize import dish_key

OVERRIDES_PATH = pathlib.Path(__file__).with_name("overrides.json")


def load_overrides(path: pathlib.Path | None = None) -> tuple[dict, dict]:
    """({line key: [dishes]}, {dish key: merged name}); empty when the file is missing."""
    path = path or OVERRIDES_PATH
    if not path.exists():
        return {}, {}
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = {dish_key(line): list(dishes) for line, dishes in data.get("lines", {}).items()}
    dishes = {dish_key(name): target for name, target in data.get("dishes", {}).items()}
    return lines, dishes


def rename(dishes: tuple[str, ...], renames: dict) -> tuple[str, ...]:
    """Apply dish merges, keeping order and dropping duplicates they create."""
    return tuple(dict.fromkeys(renames.get(dish_key(d), d) for d in dishes))
