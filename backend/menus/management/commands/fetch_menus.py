"""python manage.py fetch_menus [--date YYYY-MM-DD] [--no-llm]

Fetch one day of SNU cafeteria menus (default: today in Seoul), resolve each menu
line to the dishes it stands for (menus/preprocess), and store one MenuItem per
dish. Re-running replaces that day's menu items, so it is safe to run as often
as needed.

Lines never seen before are resolved by Gemini (needs GOOGLE_API_KEY). Without a
key, or with --no-llm, each new line is stored as one dish, as before.
"""

from __future__ import annotations

import datetime
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from menus.models import Food, MenuItem, Restaurant
from menus.normalize import clean_name, dish_key, is_noise
from menus.features.extractor import api_key_available
from menus.preprocess import fixed, mapper
from menus.preprocess.mapper import NAME_MAX, Mapping, map_lines
from menus.sources import siksha


def menu_lines(records: list[siksha.MenuRecord]) -> dict[str, str]:
    """{dish_key: cleaned name} for the non-noise lines of `records`, first name wins."""
    lines: dict[str, str] = {}
    for record in records:
        if not is_noise(record.raw_name):
            name, _ = clean_name(record.raw_name)
            lines.setdefault(dish_key(name)[:NAME_MAX], name)
    return lines


@transaction.atomic
def store(date: datetime.date, records: list[siksha.MenuRecord],
          mappings: dict[str, Mapping]) -> Counter:
    """Replace the menu items of `date`: one MenuItem per (line, dish). Returns counts.

    Written with few queries on purpose: the shared database (Supabase) is remote,
    so the number of round trips decides how long a run takes.
    """
    stats = Counter()
    MenuItem.objects.filter(date=date).delete()

    kept = []
    for record in records:
        if is_noise(record.raw_name):
            stats["noise"] += 1
            continue
        name, price_in_name = clean_name(record.raw_name)
        kept.append((record, mappings[dish_key(name)[:NAME_MAX]], price_in_name))

    restaurants = {}
    for code, record in {r.restaurant_code: r for r, _, _ in kept}.items():
        restaurants[code], _ = Restaurant.objects.update_or_create(
            code=code,
            defaults={"name": record.restaurant_name, "lat": record.lat,
                      "lng": record.lng, "source": "siksha"},
        )

    dish_names = {dish[:NAME_MAX] for _, mapping, _ in kept for dish in mapping.dishes}
    foods = {food.name: food for food in Food.objects.filter(name__in=dish_names)}
    new_foods = Food.objects.bulk_create([Food(name=n) for n in sorted(dish_names - foods.keys())])
    foods.update({food.name: food for food in new_foods})
    stats["new_foods"] = len(new_foods)

    items, seen = [], set()
    for record, mapping, price_in_name in kept:
        if not mapping.is_meal:
            stats["not_meal"] += 1
            continue
        if len(mapping.dishes) > 1:
            stats["split_lines"] += 1
        for dish in mapping.dishes:
            unique = (record.meal, record.restaurant_code, record.raw_name, dish[:NAME_MAX])
            if unique in seen:  # Siksha occasionally repeats a line within a meal
                continue
            seen.add(unique)
            items.append(MenuItem(
                date=date, meal=record.meal, restaurant=restaurants[record.restaurant_code],
                raw_name=record.raw_name, food=foods[dish[:NAME_MAX]],
                price=price_in_name or record.price, no_meat=record.no_meat,
            ))
    MenuItem.objects.bulk_create(items)

    stats["menu_items"] = len(items)
    stats["restaurants"] = len(restaurants)
    return stats


class Command(BaseCommand):
    help = "Fetch one day of SNU cafeteria menus from Siksha and store them in the DB."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=datetime.date.fromisoformat, default=None,
                            help="YYYY-MM-DD (default: today in Asia/Seoul)")
        parser.add_argument("--no-llm", action="store_true",
                            help="do not call the LLM; new lines are stored as one dish each")

    def handle(self, *args, **options):
        date = options["date"] or timezone.localdate()
        records = [r for r in siksha.parse(siksha.fetch_days(date, date)) if r.date == date]
        if not records:
            self.stdout.write(f"{date}: 오늘 운영 메뉴 없음")
            return

        llm = None
        if not options["no_llm"]:
            if api_key_available():
                llm = mapper.build_llm()
            else:
                self.stdout.write("GOOGLE_API_KEY가 없어 새 메뉴 줄은 LLM 없이 한 덩어리로 저장합니다.")

        lines = menu_lines(records)
        mappings = map_lines(lines, llm, on_progress=self.stdout.write)
        stats = store(date, records, mappings)
        changed = fixed.new_lines_in_fixed_restaurants(records, fixed.load_catalog())
        if changed:
            sample = ", ".join(f"{cafeteria} {line}" for cafeteria, line in changed[:3])
            self.stdout.write(self.style.WARNING(
                f"고정 메뉴 식당에 목록에 없는 메뉴 {len(changed)}개 (예: {sample}) "
                f"-> 메뉴판이 바뀌었으면 build_fixed_menus로 목록을 갱신하세요."))
        foods = Food.objects.filter(menu_items__date=date).distinct().count()
        sources = Counter(m.source for m in mappings.values())
        self.stdout.write(self.style.SUCCESS(
            f"{date}: 식당 {stats['restaurants']} / 메뉴 {stats['menu_items']} / "
            f"음식 {foods} (신규 {stats['new_foods']}) / 노이즈 스킵 {stats['noise']} / "
            f"세트 나눔 {stats['split_lines']} / 식사 아님 {stats['not_meal']} / "
            f"메뉴 줄 {len(lines)} ({', '.join(f'{k} {v}' for k, v in sorted(sources.items()))})"
        ))
