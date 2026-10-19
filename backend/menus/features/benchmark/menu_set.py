# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""The dishes to benchmark, split by how they reach the app.

- invariant: dishes of the fixed-menu catalog (preprocess/fixed_menus.json). They
  come back every day, so they can be tagged once, checked by a person and kept.
- variant: dishes from lines that change from day to day. They are the reason the
  features are tagged by an LLM at all, so the benchmark reports them apart.

build() walks a menu history of many past days the way fetch_menus does: every
line is resolved by menus/preprocess (catalog, cache, then the LLM), and the
dishes of lines outside the catalog become the variant set. A dish that is also
on a fixed board counts as invariant, because its features can be kept.

    {"built_from": ["2026-09-15", "2026-10-13"], "days": 21,
     "invariant": [{"name": "핫치킨버거", "restaurants": ["버거운버거"]}],
     "variant": [{"name": "마라탕", "days": 3, "dates": [...], "restaurants": [...],
                  "lines": ["즉석 마라탕"], "source": "llm"}]}
"""

from __future__ import annotations

import json
import math
import pathlib
from collections import defaultdict

from menus.models import MenuLine
from menus.normalize import clean_name, dish_key, is_noise
from menus.preprocess import fixed, overrides
from menus.preprocess.mapper import NAME_MAX, PREPROCESS_VERSION

INVARIANT, VARIANT = "invariant", "variant"
LINES_SHOWN = 3


def line_key(raw_name: str) -> tuple[str, str]:
    """(menu line key, cleaned name), the same key fetch_menus and the mapper use."""
    name, _ = clean_name(raw_name)
    return dish_key(name)[:NAME_MAX], name


def catalog_dishes(catalog=None) -> set[str]:
    """Every dish name the fixed-menu catalog resolves to."""
    lines = fixed.catalog_lines(catalog if catalog is not None else fixed.load_catalog())
    return {dish for entry in lines.values() for dish in entry["dishes"]}


def segment(name: str, invariant_names) -> str:
    return INVARIANT if name in invariant_names else VARIANT


def lines_to_resolve(lines: dict[str, str], catalog=None) -> int:
    """How many lines the preprocessing LLM would be asked about (no override, catalog or cache)."""
    line_overrides, _ = overrides.load_overrides()
    known = set(line_overrides) | set(fixed.catalog_lines(catalog if catalog is not None else fixed.load_catalog()))
    cached = set(MenuLine.objects.filter(key__in=list(lines), source=MenuLine.Source.LLM,
                                         version=PREPROCESS_VERSION).values_list("key", flat=True))
    return sum(1 for key in lines if key not in known and key not in cached)


def preprocessing_calls(n_lines: int, batch_size: int = 25) -> int:
    return math.ceil(n_lines / batch_size)


def build(records, mappings, catalog=None) -> dict:
    """The menu set of a history: `records` are siksha MenuRecords, `mappings` the
    mapper's {line key: Mapping} for their lines."""
    catalog_keys = set(fixed.catalog_lines(catalog if catalog is not None else fixed.load_catalog()))
    invariant = defaultdict(set)
    variant = defaultdict(lambda: {"dates": set(), "restaurants": set(), "lines": [], "sources": set()})
    for record in records:
        if is_noise(record.raw_name):
            continue
        key, name = line_key(record.raw_name)
        mapping = mappings[key]
        if not mapping.is_meal:
            continue
        for dish in mapping.dishes:
            if key in catalog_keys:
                invariant[dish].add(record.restaurant_name)
                continue
            entry = variant[dish]
            entry["dates"].add(record.date.isoformat())
            entry["restaurants"].add(record.restaurant_name)
            entry["sources"].add(mapping.source)
            if name not in entry["lines"]:
                entry["lines"].append(name)

    dates = sorted({record.date.isoformat() for record in records})
    return {
        "built_from": [dates[0], dates[-1]] if dates else [],
        "days": len(dates),
        "preprocess_version": PREPROCESS_VERSION,
        "invariant": [{"name": dish, "restaurants": sorted(places)} for dish, places in sorted(invariant.items())],
        "variant": [{"name": dish, "days": len(entry["dates"]), "dates": sorted(entry["dates"]),
                     "restaurants": sorted(entry["restaurants"]), "lines": entry["lines"][:LINES_SHOWN],
                     "source": "rule" if entry["sources"] == {"rule"} else "llm" if "llm" in entry["sources"]
                     else sorted(entry["sources"])[0]}
                    for dish, entry in sorted(variant.items()) if dish not in invariant],
    }


def save(path, menu_set) -> None:
    pathlib.Path(path).write_text(json.dumps(menu_set, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load(path) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
