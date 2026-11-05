"""python manage.py export_feature_review (--date 2026-11-02 | --stores [--n 100])
       --raters 구본재,김신서,이민규,이승호 --output-dir DIR [--overlap 10] [--seed 0]

Write the human review of the extracted features (menus/features/benchmark/review.py):
<source>_<rater>.xlsx per rater, and <source>_assignment.csv saying who reviews which
dish. --overlap dishes go to every rater, the rest are split. No LLM call; the
database is only read.
  --date D    every dish served on that day (cafeteria): the shared snapshot's day
  --stores    --n dishes on the menu boards of the restaurants near the stations
              (general menus), spread over the restaurants' categories
"""

from __future__ import annotations

import csv
import datetime
import pathlib
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError

from menus.features.benchmark import review, runs
from menus.features.schema import FEATURE_VERSION
from menus.models import Food, MenuItem, StoreMenu

SERVED_SHOWN = 3


class Command(BaseCommand):
    help = "Write per-rater workbooks for judging the extracted features of a day's or the restaurants' dishes."

    def add_arguments(self, parser):
        where = parser.add_mutually_exclusive_group(required=True)
        where.add_argument("--date", type=datetime.date.fromisoformat)
        where.add_argument("--stores", action="store_true")
        parser.add_argument("--n", type=int, default=100, help="--stores: dishes to sample")
        parser.add_argument("--raters", required=True, help="comma-separated names")
        parser.add_argument("--output-dir", required=True)
        parser.add_argument("--overlap", type=int, default=review.OVERLAP, help="dishes every rater reviews")
        parser.add_argument("--seed", type=int, default=0)

    def handle(self, *args, **options):
        raters = [name.strip() for name in options["raters"].split(",") if name.strip()]
        if not raters or len(set(raters)) != len(raters):
            raise CommandError("--raters에 서로 다른 이름을 쉼표로 적으세요.")
        foods = Food.objects.filter(is_food=True, feature_version=FEATURE_VERSION)
        served, group = defaultdict(list), {}
        if options["date"]:
            kind, source = "cafeteria", f"cafeteria {options['date']}"
            lines = MenuItem.objects.filter(date=options["date"], food__in=foods).order_by("meal", "restaurant__name")
            for item in lines.values("food_id", "restaurant__name", "raw_name"):
                served[item["food_id"]].append(f"{item['restaurant__name']}: {item['raw_name']}")
        else:
            kind, source = "general", "general"
            lines = StoreMenu.objects.filter(food__in=foods).order_by("restaurant__name", "id")
            for item in lines.values("food_id", "restaurant__name", "restaurant__category", "raw_name", "description"):
                note = f" ({item['description'][:40]})" if item["description"] else ""
                served[item["food_id"]].append(f"{item['restaurant__name']}: {item['raw_name']}{note}")
                group.setdefault(item["food_id"], item["restaurant__category"])
        dishes = {food.pk: {"name": food.name, "food_group": food.food_group, "is_set": food.is_set,
                              "served": list(dict.fromkeys(served[food.pk]))[:SERVED_SHOWN],
                              "features": food.features, "feature_std": food.feature_std,
                              "model": food.extraction_model, "group": group.get(food.pk, "")}
                  for food in foods.filter(pk__in=served)}
        if not dishes:
            raise CommandError("현재 feature가 있는 음식이 없습니다.")
        ids = list(dishes)
        if options["stores"]:
            ids = runs.stratified_sample(ids, lambda pk: dishes[pk]["group"], options["n"], options["seed"])
        overlap = min(options["overlap"], len(ids))
        assignment = review.assign(ids, raters, overlap, options["seed"])
        output = pathlib.Path(options["output_dir"])
        output.mkdir(parents=True, exist_ok=True)
        for rater, mine in assignment.items():
            review.write(output / f"{kind}_{rater}.xlsx", rater, source, [dishes[pk] for pk in mine])
        with open(output / f"{kind}_assignment.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "set", "raters"])
            for pk in sorted(ids, key=lambda pk: dishes[pk]["name"]):
                writer.writerow([dishes[pk]["name"], "세트" if dishes[pk]["is_set"] else "",
                                 ", ".join(r for r, mine in assignment.items() if pk in mine)])
        each = ", ".join(f"{rater} {len(mine)}" for rater, mine in assignment.items())
        self.stdout.write(self.style.SUCCESS(f"{source}: 음식 {len(ids)}개 (공통 {overlap}개), 검토자별 {each} -> {output}"))
