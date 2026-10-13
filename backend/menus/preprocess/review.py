# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""CSV files for a person to review preprocessing results in Excel."""

from __future__ import annotations

import csv
import pathlib
from collections import defaultdict

from menus.normalize import clean_name, dish_key, is_noise

REVIEW_COLUMNS = ["ok (Y/N)", "correction"]  # filled in by the reviewer

# Words that do not make a different dish. Two dishes whose names differ only by one
# of these (즉석마라탕 / 마라탕) are flagged as a possibly missed merge; names that
# differ by an ingredient or flavor (돼지김치찌개 / 김치찌개) are different on purpose.
SAME_DISH_WORDS = {"즉석", "특", "왕", "수제", "옛날", "더블", "미니", "1인", "점보", "빅"}


def write_csv(path: str | pathlib.Path, header: list[str], rows: list[list]) -> None:
    """UTF-8 with a BOM, so Excel opens Korean text correctly by double-click."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header + REVIEW_COLUMNS)
        for row in rows:
            writer.writerow(list(row) + [""] * len(REVIEW_COLUMNS))


def review_rows(records, mappings) -> list[list]:
    """Rows for a person to check, as [type, cafeterias, line(s), dishes, source].

    - split: a line resolved into two or more dishes
    - not_meal: a line judged not to be a meal (drinks, add-ons, notices)
    - merge: two or more different lines resolved into the same dish
    - maybe_same: two dishes whose names differ only by a word such as 즉석 or 왕
      (마라탕 / 즉석마라탕), i.e. a merge that may have been missed
    """
    lines = {}
    for record in records:
        if is_noise(record.raw_name):
            continue
        name, _ = clean_name(record.raw_name)
        entry = lines.setdefault(dish_key(name), {"name": name, "cafeterias": set()})
        entry["cafeterias"].add(record.restaurant_name)

    rows, by_dish = [], defaultdict(list)
    for key, entry in sorted(lines.items(), key=lambda kv: kv[1]["name"]):
        mapping, cafeterias = mappings[key], ", ".join(sorted(entry["cafeterias"]))
        if not mapping.is_meal:
            rows.append(["not_meal", cafeterias, entry["name"], "", mapping.source])
        elif len(mapping.dishes) > 1:
            rows.append(["split", cafeterias, entry["name"], " | ".join(mapping.dishes), mapping.source])
        for dish in mapping.dishes:
            by_dish[dish].append((entry, mapping))

    for dish, served in sorted(by_dish.items()):
        if len(served) > 1:
            rows.append(["merge", ", ".join(sorted({c for e, _ in served for c in e["cafeterias"]})),
                         " / ".join(e["name"] for e, _ in served), dish,
                         ", ".join(sorted({m.source for _, m in served}))])

    keys = {dish: dish_key(dish) for dish in by_dish}
    for short, short_key in sorted(keys.items()):
        for long, long_key in sorted(keys.items()):
            if short_key != long_key and short_key in long_key                     and long_key.replace(short_key, "", 1) in SAME_DISH_WORDS:
                rows.append(["maybe_same", "", long, short, ""])
    return rows
