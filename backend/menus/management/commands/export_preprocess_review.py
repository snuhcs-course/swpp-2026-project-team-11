# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py export_preprocess_review [--date YYYY-MM-DD] --output review.csv

Write the day's preprocessing results (default: today in Seoul) as a CSV for a
person to check in Excel: split combos, merged dishes, non-meals, and possible
missed merges. Mark wrong rows "N" and write the fix in "correction"; fixes go
into menus/preprocess/overrides.json (or fixed_menus.json for fixed menus).

No LLM is called: lines are resolved from overrides, the fixed catalog and the
cache, so run fetch_menus (or run_daily_pipeline) first.
"""

from __future__ import annotations

import datetime
import json
import pathlib
from collections import Counter

from django.core.management.base import BaseCommand
from django.utils import timezone

from menus.management.commands.fetch_menus import menu_lines
from menus.preprocess.mapper import map_lines
from menus.preprocess.review import review_rows, write_csv
from menus.sources import siksha

HEADER = ["type", "cafeteria", "line", "dishes", "source"]


def export_review(records, path) -> Counter:
    """Write the review CSV for `records` and return counts by row type."""
    mappings = map_lines(menu_lines(records))
    rows = review_rows(records, mappings)
    write_csv(path, HEADER, rows)
    return Counter(row[0] for row in rows)


class Command(BaseCommand):
    help = "Export a day's preprocessing results as a CSV for human review."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=datetime.date.fromisoformat, default=None)
        parser.add_argument("--from-json", default=None,
                            help="read a saved Siksha payload instead of downloading")
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        date = options["date"] or timezone.localdate()
        if options["from_json"]:
            payload = json.loads(pathlib.Path(options["from_json"]).read_text(encoding="utf-8"))
        else:
            payload = siksha.fetch_raw(date)
        records = [r for r in siksha.parse(payload) if r.date == date]
        counts = export_review(records, options["output"])
        self.stdout.write(self.style.SUCCESS(
            f"{date}: 검토 행 {sum(counts.values())}개 "
            f"(나뉨 {counts['split']}, 합쳐짐 {counts['merge']}, 식사 아님 {counts['not_meal']}, "
            f"합칠 후보 {counts['maybe_same']}) -> {options['output']}"))
