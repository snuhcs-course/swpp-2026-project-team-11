# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py fetch_menus [--date YYYY-MM-DD]

Fetch one day of SNU cafeteria menus (default: today in Seoul) and store them.
Re-running replaces that day's menu items, so it is safe to run as often as needed.
"""

from __future__ import annotations

import datetime
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from menus.models import Food, MenuItem, Restaurant
from menus.normalize import clean_name, is_noise
from menus.sources import siksha


@transaction.atomic
def store(date: datetime.date, records: list[siksha.MenuRecord]) -> Counter:
    """Replace the menu items of `date` with `records`. Returns counts for the log."""
    stats = Counter()
    restaurants: dict[str, Restaurant] = {}
    MenuItem.objects.filter(date=date).delete()

    for record in records:
        if is_noise(record.raw_name):
            stats["noise"] += 1
            continue
        name, price_in_name = clean_name(record.raw_name)

        restaurant = restaurants.get(record.restaurant_code)
        if restaurant is None:
            restaurant, _ = Restaurant.objects.update_or_create(
                code=record.restaurant_code,
                defaults={"name": record.restaurant_name, "lat": record.lat,
                          "lng": record.lng, "source": "siksha"},
            )
            restaurants[record.restaurant_code] = restaurant

        food, created = Food.objects.get_or_create(name=name)
        stats["new_foods"] += created
        _, created = MenuItem.objects.get_or_create(
            date=date, meal=record.meal, restaurant=restaurant, raw_name=record.raw_name,
            defaults={"food": food, "price": price_in_name or record.price,
                      "no_meat": record.no_meat},
        )
        stats["menu_items"] += created

    stats["restaurants"] = len(restaurants)
    return stats


class Command(BaseCommand):
    help = "Fetch one day of SNU cafeteria menus from Siksha and store them in the DB."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=datetime.date.fromisoformat, default=None,
                            help="YYYY-MM-DD (default: today in Asia/Seoul)")

    def handle(self, *args, **options):
        date = options["date"] or timezone.localdate()
        records = [r for r in siksha.parse(siksha.fetch_raw(date)) if r.date == date]
        if not records:
            self.stdout.write(f"{date}: 오늘 운영 메뉴 없음")
            return

        stats = store(date, records)
        foods = Food.objects.filter(menu_items__date=date).distinct().count()
        self.stdout.write(self.style.SUCCESS(
            f"{date}: 식당 {stats['restaurants']} / 메뉴 {stats['menu_items']} / "
            f"음식 {foods} (신규 {stats['new_foods']}) / 노이즈 스킵 {stats['noise']}"
        ))
