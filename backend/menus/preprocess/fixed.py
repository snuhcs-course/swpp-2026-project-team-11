# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Fixed-menu catalog: lines a cafeteria serves (almost) every day get one rule.

Some cafeterias sell from a fixed menu board (버거운버거, 공대간이식당, 220동식당,
75-1동 푸드코트), and some daily cafeterias always offer a few fixed items
(두레미담's order menu, 301동's 헬스팩). `build_fixed_menus` finds those lines in
the menu history, resolves each once, and writes fixed_menus.json. The file is
reviewed by a person and committed, so every database (each teammate's, the
shared Supabase one) treats a fixed line the same way, with no LLM call.
"""

from __future__ import annotations

import json
import pathlib
import statistics
from collections import defaultdict
from dataclasses import dataclass

from menus.normalize import clean_name, dish_key, is_noise

CATALOG_PATH = pathlib.Path(__file__).with_name("fixed_menus.json")

FIXED, MIXED, DAILY = "fixed", "mixed", "daily"


@dataclass(frozen=True)
class RestaurantHistory:
    code: str
    name: str
    kind: str                # FIXED, MIXED or DAILY
    open_days: int
    overlap: float           # median day-to-day Jaccard overlap of its menu lines
    fixed_lines: dict        # {dish_key: cleaned name} to put in the catalog


def classify(records, *, fixed_overlap: float = 0.9, min_ratio: float = 0.8,
             recent_days: int = 5, min_open_days: int = 3) -> list[RestaurantHistory]:
    """Find the fixed lines of each cafeteria in a menu history (siksha MenuRecords).

    - FIXED: the day-to-day overlap is at least `fixed_overlap`, i.e. a menu board.
      Every line of its last `recent_days` open days goes in, so a board that
      changed during the window is cataloged as it is now.
    - MIXED: a daily cafeteria with some lines on at least `min_ratio` of its open days.
    - DAILY: nothing is fixed.
    """
    days = defaultdict(lambda: defaultdict(dict))  # code -> date -> {key: name}
    names = {}
    for record in records:
        if is_noise(record.raw_name):
            continue
        name, _ = clean_name(record.raw_name)
        days[record.restaurant_code][record.date].setdefault(dish_key(name), name)
        names[record.restaurant_code] = record.restaurant_name

    result = []
    for code, by_day in sorted(days.items()):
        dates = sorted(by_day)
        overlaps = [len(by_day[a].keys() & by_day[b].keys()) / len(by_day[a].keys() | by_day[b].keys())
                    for a, b in zip(dates, dates[1:])]
        overlap = statistics.median(overlaps) if overlaps else 0.0
        if len(dates) < min_open_days:
            kind, lines = DAILY, {}
        elif overlap >= fixed_overlap:
            kind, lines = FIXED, {}
            for day in dates[-recent_days:]:
                for key, name in by_day[day].items():
                    lines.setdefault(key, name)
        else:
            seen = defaultdict(int)
            for day in dates:
                for key in by_day[day]:
                    seen[key] += 1
            lines = {key: next(by_day[d][key] for d in dates if key in by_day[d])
                     for key, count in seen.items() if count >= min_ratio * len(dates)}
            kind = MIXED if lines else DAILY
        result.append(RestaurantHistory(code, names[code], kind, len(dates), round(overlap, 2), lines))
    return result


def load_catalog(path: pathlib.Path | None = None) -> dict:
    """The committed catalog, or an empty one when the file does not exist."""
    path = path or CATALOG_PATH
    if not path.exists():
        return {"restaurants": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def catalog_lines(catalog: dict) -> dict[str, dict]:
    """{dish_key: {"name", "is_meal", "dishes"}} for every cataloged line."""
    lines = {}
    for restaurant in catalog.get("restaurants", {}).values():
        lines.update(restaurant.get("lines", {}))
    return lines


def new_lines_in_fixed_restaurants(records, catalog: dict) -> list[tuple[str, str]]:
    """(cafeteria, line) pairs served by a FIXED cafeteria but missing from the catalog.

    A fixed cafeteria showing new lines usually means its menu board changed and
    the catalog should be rebuilt with build_fixed_menus.
    """
    known = catalog_lines(catalog)
    fixed_codes = {code for code, r in catalog.get("restaurants", {}).items() if r.get("type") == FIXED}
    found = {}
    for record in records:
        if record.restaurant_code in fixed_codes and not is_noise(record.raw_name):
            name, _ = clean_name(record.raw_name)
            if dish_key(name) not in known:
                found[(record.restaurant_name, name)] = None
    return list(found)
