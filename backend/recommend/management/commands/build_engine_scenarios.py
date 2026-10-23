# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py build_engine_scenarios --date 2026-10-20 [--date ...] --output scenarios.json

Make the scenarios both engines and the human test play, on the given menus:
--counts users per situation (default in_menu:40, multiple:20, not_in_menu:20,
close_alternative:20), with certainty levels taken in turn. Each menu is loaded
as the app loads it (get_catalog: the feature version covering more dishes), and
its candidate list is copied into the file. All menus must have the same feature
version: similarities across versions mean nothing. See question_engines/benchmark/scenarios.py.
No LLM call.
"""

from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from menus.models import Food
from menus.services import get_catalog
from question_engines.benchmark import COUNTS, SITUATIONS, scenarios

DEFAULT_COUNTS = ",".join(f"{situation}:{count}" for situation, count in COUNTS.items())


def parse_counts(text) -> dict[str, int]:
    """"in_menu:40,multiple:20" -> {"in_menu": 40, "multiple": 20}."""
    counts = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        situation, _, count = part.partition(":")
        if situation not in SITUATIONS or not count.isdigit() or int(count) < 1:
            raise CommandError(f"--counts takes situation:count pairs from {', '.join(SITUATIONS)}: {part!r}")
        counts[situation] = int(count)
    if not counts:
        raise CommandError("--counts is empty.")
    return counts


def load_menus(dates, meals, write) -> dict:
    menus = {}
    for date in dates:
        for meal in meals:
            candidates, _, version = get_catalog(date, meal)
            if candidates:
                menus[scenarios.menu_id(date, meal)] = {"date": date.isoformat(), "meal": meal,
                                                        "feature_version": version, "candidates": candidates}
            else:
                write(f"{date} {meal}: 태깅된 후보가 없어 건너뜁니다.")
    if not menus:
        raise CommandError("후보가 있는 메뉴가 없습니다. run_daily_pipeline이나 loaddata를 먼저 하세요.")
    versions = {menu["feature_version"] for menu in menus.values()}
    if len(versions) > 1:
        listed = ", ".join(f"{key} {menu['feature_version']}" for key, menu in menus.items())
        raise CommandError(f"메뉴의 feature 버전이 섞여 있습니다 ({listed}). 같은 버전의 날짜만 주세요.")
    return menus


def build(dates, meals, counts, seed, write) -> dict:
    menus = load_menus(dates, meals, write)
    version = next(iter(menus.values()))["feature_version"]  # load_menus checked that they share it
    others = list(Food.objects.filter(is_food=True, feature_version=version).values("name", "features", "food_group"))
    try:
        return scenarios.build(menus, others, counts, seed)
    except ValueError as error:
        raise CommandError(str(error)) from error


class Command(BaseCommand):
    help = "Build the scenarios for the question engine benchmark."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)
        parser.add_argument("--date", type=datetime.date.fromisoformat, action="append",
                            help="a menu date; repeat for several (default: today in Asia/Seoul)")
        parser.add_argument("--meal", action="append", choices=("BR", "LU", "DN"),
                            help="repeat for several (default: LU)")
        parser.add_argument("--counts", default=DEFAULT_COUNTS, help=f"default: {DEFAULT_COUNTS}")
        parser.add_argument("--seed", type=int, default=0)

    def handle(self, *args, **options):
        counts = parse_counts(options["counts"])
        data = build(options["date"] or [timezone.localdate()], options["meal"] or ["LU"], counts,
                     options["seed"], lambda text: self.stdout.write(self.style.WARNING(text)))
        scenarios.save(options["output"], data)
        made = ", ".join(f"{s} {sum(x['situation'] == s for x in data['scenarios'])}" for s in counts)
        self.stdout.write(self.style.SUCCESS(f"메뉴 {len(data['menus'])}개, 시나리오 {made} -> {options['output']}"))
