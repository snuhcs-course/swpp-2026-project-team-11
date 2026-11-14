"""python manage.py export_feature_review (--date 2026-11-02 | --stores | --workbook FILE.xlsx) [--n 50]
       --raters 구본재,김신서,이민규,이승호 --output-dir DIR [--overlap 0] [--seed 0]

Write the human review of the extracted features (menus/features/benchmark/review.py):
<source>_<rater>.xlsx per rater, and <source>_assignment.csv saying who reviews which
dish. --n dishes are sampled (all without it), half of them hard (review.signals), each
stratum's groups in proportion to their dishes, and split between the raters (--overlap
of them to every rater, none by default). No LLM call; the database is only read.
  --date D         the dishes served on that day (cafeteria), grouped by cafeteria
  --stores         the dishes on the menu boards of the restaurants near the stations
                   (general menus), grouped by restaurant category
  --workbook FILE  the same from the team's per-dish export (sheet "일반 음식": one row per
                   menu, its linked dish in "구성 음식(원본 연결)"), for the dishes the
                   database here does not have
"""

from __future__ import annotations

import csv
import datetime
import pathlib
import re
from collections import Counter, defaultdict

import openpyxl
from django.core.management.base import BaseCommand, CommandError

from menus.features.benchmark import review
from menus.features.schema import FEATURE_VERSION
from menus.models import Food, MenuItem, StoreMenu

SERVED_SHOWN = 3
STORE_SHEET = "일반 음식"


def _per_store(text) -> dict[int, str]:
    """'1, 2: a\\n3: b' -> {1: 'a', 2: 'a', 3: 'b'}"""
    out = {}
    for line in (text or "").split("\n"):
        numbers, _, value = line.partition(": ")
        for number in numbers.split(","):
            if value and number.strip().isdigit():
                out[int(number)] = value
    return out


def workbook_dishes(path) -> dict[str, dict]:
    """The export's menus with v2 features, grouped into dishes: one per linked dish and feature values."""
    book = openpyxl.load_workbook(path, read_only=True)
    try:  # a read-only book keeps its file open (locked on Windows) until closed
        rows = iter(list(book[STORE_SHEET].iter_rows(values_only=True)))
    finally:
        book.close()
    header = next(row for row in rows if row[0] == "후보 ID")
    column = {name: index for index, name in enumerate(header) if name}
    fields = {"mean": " 평균", "std": " 표준편차"}
    values = {field: {re.search(r"\((\w+)\)", name)[1]: index for name, index in column.items()
                      if name.endswith(suffix)} for field, suffix in fields.items()}
    menus = defaultdict(list)
    for row in rows:
        if row[0] is None or row[column["feature 버전"]] != FEATURE_VERSION:
            continue
        features = {field: {key: row[index] for key, index in keys.items()} for field, keys in values.items()}
        dish = (row[column["구성 음식(원본 연결)"]], tuple(sorted(features["mean"].items())),
                tuple(sorted(features["std"].items())))
        menus[dish].append((row, features))
    dishes = {}
    for (name, _, _), listed in menus.items():
        listed.sort(key=lambda item: item[0][0])
        row, features = listed[0]
        served, kinds, models = [], Counter(), Counter()
        for menu, _ in listed:
            stores = dict((int(m[1]), m[2]) for m in re.finditer(r"^(\d+)\. (.+)$", menu[column["식당 목록"]] or "", re.M))
            notes = _per_store(menu[column["식당별 원본 설명"]])
            for number, store in sorted(stores.items()):
                note = f" ({notes[number][:40]})" if notes.get(number) else ""
                served.append(f"{store}: {menu[column['원본 메뉴명']]}{note}")
            kinds.update(_per_store(menu[column["식당별 유형"]]).values())
            models.update(_per_store(menu[column["특성 추출 모델"]]).values())
        dishes[str(row[0])] = {
            "id": row[0], "name": name, "food_group": row[column["음식 분류"]] or "",
            "is_set": (features["mean"].get("meal_variety") or 0) >= 0.5,
            "served": list(dict.fromkeys(served))[:SERVED_SHOWN],
            "features": features["mean"], "feature_std": features["std"],
            "model": models.most_common(1)[0][0] if models else "",
            "group": min(kinds, key=lambda kind: (-kinds[kind], kind)) if kinds else ""}
    return dishes


class Command(BaseCommand):
    help = "Write per-rater workbooks for judging the extracted features of a day's or the restaurants' dishes."

    def add_arguments(self, parser):
        where = parser.add_mutually_exclusive_group(required=True)
        where.add_argument("--date", type=datetime.date.fromisoformat)
        where.add_argument("--stores", action="store_true")
        where.add_argument("--workbook")
        parser.add_argument("--n", type=int, help="dishes to sample; all without it")
        parser.add_argument("--raters", required=True, help="comma-separated names")
        parser.add_argument("--output-dir", required=True)
        parser.add_argument("--overlap", type=int, default=review.OVERLAP, help="dishes every rater reviews")
        parser.add_argument("--seed", type=int, default=0)

    def handle(self, *args, **options):
        raters = [name.strip() for name in options["raters"].split(",") if name.strip()]
        if not raters or len(set(raters)) != len(raters):
            raise CommandError("--raters에 서로 다른 이름을 쉼표로 적으세요.")
        if options["workbook"]:
            kind, source = "general", "general"
            try:
                dishes = workbook_dishes(options["workbook"])
            except (OSError, KeyError, StopIteration) as error:
                raise CommandError(f"{options['workbook']}: '{STORE_SHEET}' 시트를 읽지 못했습니다 ({error!r}).") from error
        else:
            kind, source, dishes = self._database(options["date"])
        if not dishes:
            raise CommandError("현재 feature가 있는 음식이 없습니다.")
        for pk, found in review.signals(dishes).items():
            dishes[pk]["signals"] = found
        strata = {pk: review.stratum(dish["signals"]) for pk, dish in dishes.items()}
        population = Counter(strata.values())
        ids = list(dishes)
        if options["n"]:
            ids = review.oversample(ids, strata, lambda pk: dishes[pk]["group"], options["n"], options["seed"])
        overlap = min(options["overlap"], len(ids))
        assignment = review.assign(ids, raters, overlap, options["seed"], strata.get)
        output = pathlib.Path(options["output_dir"])
        output.mkdir(parents=True, exist_ok=True)
        for rater, mine in assignment.items():
            review.write(output / f"{kind}_{rater}.xlsx", rater, source, [dishes[pk] for pk in mine], population)
        with open(output / f"{kind}_assignment.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "name", "set", "group", "stratum", "signals", "raters"])
            for pk in sorted(ids, key=lambda pk: (dishes[pk]["name"], str(pk))):
                writer.writerow([dishes[pk]["id"], dishes[pk]["name"], "세트" if dishes[pk]["is_set"] else "",
                                 dishes[pk]["group"], strata[pk], ", ".join(dishes[pk]["signals"]),
                                 ", ".join(r for r, mine in assignment.items() if pk in mine)])
        each = ", ".join(f"{rater} {len(mine)}" for rater, mine in assignment.items())
        hard = sum(strata[pk] == review.STRATA[0] for pk in ids)
        self.stdout.write(self.style.SUCCESS(f"{source}: 음식 {len(dishes)}개 중 {len(ids)}개 (어려운 음식 "
                                             f"{population[review.STRATA[0]]}개 중 {hard}개, 공통 {overlap}개), "
                                             f"검토자별 {each} -> {output}"))

    def _database(self, date):
        foods = Food.objects.filter(is_food=True, feature_version=FEATURE_VERSION)
        served, group = defaultdict(list), {}
        if date:
            kind, source = "cafeteria", f"cafeteria {date}"
            lines = MenuItem.objects.filter(date=date, food__in=foods).order_by("meal", "restaurant__name")
            for item in lines.values("food_id", "restaurant__name", "raw_name"):
                served[item["food_id"]].append(f"{item['restaurant__name']}: {item['raw_name']}")
                group.setdefault(item["food_id"], item["restaurant__name"])
        else:
            kind, source = "general", "general"
            lines = StoreMenu.objects.filter(food__in=foods).order_by("restaurant__name", "id")
            for item in lines.values("food_id", "restaurant__name", "restaurant__category", "raw_name", "description"):
                note = f" ({item['description'][:40]})" if item["description"] else ""
                served[item["food_id"]].append(f"{item['restaurant__name']}: {item['raw_name']}{note}")
                group.setdefault(item["food_id"], item["restaurant__category"])
        dishes = {food.pk: {"id": food.pk, "name": food.name, "food_group": food.food_group, "is_set": food.is_set,
                            "served": list(dict.fromkeys(served[food.pk]))[:SERVED_SHOWN],
                            "features": food.features, "feature_std": food.feature_std,
                            "model": food.extraction_model, "group": group.get(food.pk, "")}
                  for food in foods.filter(pk__in=served)}
        return kind, source, dishes
