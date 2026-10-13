# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Resolve menu lines to dishes.

    map_lines({dish_key: cleaned name}) -> {dish_key: Mapping}

Sources, first match wins:
  1. MenuLine cache from an earlier run (LLM answers under PREPROCESS_VERSION)
  2. rule fallback: the whole line is one dish, named as it was first seen
"""

from __future__ import annotations

from dataclasses import dataclass

from menus.models import MenuLine

PREPROCESS_VERSION = "v1"
NAME_MAX = 300  # MenuLine.name / Food.name max_length; Postgres enforces it


@dataclass(frozen=True)
class Mapping:
    is_meal: bool
    dishes: tuple[str, ...]  # canonical dish names, empty when not a meal
    source: str              # where the answer came from: "llm", "rule", ...


def map_lines(lines: dict[str, str]) -> dict[str, Mapping]:
    """Return a Mapping for every key of `lines` ({dish_key: cleaned name})."""
    cached = {line.key: line for line in MenuLine.objects.filter(key__in=lines)}
    result: dict[str, Mapping] = {}

    for key, line in cached.items():
        if line.source == MenuLine.Source.LLM and line.version == PREPROCESS_VERSION:
            result[key] = Mapping(line.is_meal, tuple(line.dishes), line.source)

    new_rule_lines = []
    for key, name in lines.items():
        if key in result:
            continue
        # Keep the name first seen, so spacing variants keep pointing at one Food.
        first_name = cached[key].name if key in cached else name[:NAME_MAX]
        result[key] = Mapping(True, (first_name,), MenuLine.Source.RULE)
        if key not in cached:
            new_rule_lines.append(MenuLine(key=key, name=first_name, dishes=[first_name],
                                           source=MenuLine.Source.RULE))
    MenuLine.objects.bulk_create(new_rule_lines, ignore_conflicts=True)
    return result
