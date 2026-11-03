"""What the question engines read from the menu DB.

    get_catalog(date, meal, allergies) -> candidates, feature schema
    get_store_catalog(meal, allergies) -> the same for the restaurants near the stations
    get_feature_schema()          -> feature schema

Session candidates are actual sales menus, named exactly as the restaurant lists
them. Preprocessing's main-dish vectors are RMS-composed for each whole menu; a menu
is served only when every main dish has current (FEATURE_VERSION) features.

`allergies` (menus/allergens.py keys) is a hard rule: a menu line is never offered when
one of its dishes is tagged with one of them or has no current allergen tags. A combo
line ("돈가스 카레우동") is bought whole, so this covers every dish it lists.

`food_group` is a single-dish menu's group; `food_groups` lists the groups of every dish
a menu holds, a set dish taking that of its single variant (the same name), so a
session can ban a group with the sets that contain it.
"""

from __future__ import annotations

import datetime
import logging
import math
from collections import defaultdict
from typing import NamedTuple
import time

from django.conf import settings
from django.utils import timezone

from .allergens import ALLERGEN_VERSION
from .features.schema import FEATURE_VERSION, FEATURES
from .models import Food, MenuItem, StoreMenu

logger = logging.getLogger(__name__)
MEAL_ORDER = {"BR": 0, "LU": 1, "DN": 2}


class SalesLine(NamedTuple):
    id: int
    restaurant_id: int
    restaurant: str
    lat: float | None
    lng: float | None
    meal: str
    raw_name: str
    description: str
    price: int | None
    food_id: int | None
    allergens: list
    allergen_version: str


def get_feature_schema() -> list[dict]:
    from question_engines.decision_tree.contracts import FEATURE_PRESENTATION
    return [{"key": f.key, "question": FEATURE_PRESENTATION[f.key][0],
             "question_en": FEATURE_PRESENTATION[f.key][0],
             "family": FEATURE_PRESENTATION[f.key][1]} for f in FEATURES]


def get_catalog(date: datetime.date | None = None, meal: str | None = None,
                allergies: frozenset[str] = frozenset()) -> tuple[list, list]:
    """Recommend the original purchasable menu, with RMS component features."""
    date = date or timezone.localdate()
    items = MenuItem.objects.filter(date=date).select_related("food", "restaurant")
    if meal:
        items = items.filter(meal=meal)
    records = []
    foods = {}
    for item in items.order_by("id"):
        if item.food_id:
            foods[item.food_id] = item.food
        place = item.restaurant
        records.append(SalesLine(item.pk, place.pk, place.name, place.lat, place.lng, item.meal,
                        item.raw_name, "", item.price, item.food_id,
                        item.food.allergens if item.food_id else [],
                        item.food.allergen_version if item.food_id else ""))
    menus = _menu_lines(records, foods, allergies)
    rows = _menu_candidates(menus, _dish_groups(foods))
    log = logger.warning if len(rows) < len(menus) else logger.info
    log("%s %s: serving %d/%d actual menus with feature_version=%s",
        date, meal or "ALL", len(rows), len(menus), FEATURE_VERSION)
    return rows, get_feature_schema()


def _menu_lines(records, foods, allergies):
    """A line can never lose a component due to tags or a partial feature rollout."""
    grouped = defaultdict(list)
    for row in records:
        grouped[(row.restaurant_id, row.meal, row.raw_name, row.description, row.price)].append(row)
    menus = []
    for rows in grouped.values():
        if any(not row.food_id or row.food_id not in foods or foods[row.food_id].is_food is not True for row in rows):
            continue
        if allergies and any(row.allergen_version != ALLERGEN_VERSION or not allergies.isdisjoint(row.allergens) for row in rows):
            continue
        parts = {row.food_id: foods[row.food_id] for row in rows}
        versions = {f.feature_version for f in parts.values()}
        version = versions.pop() if len(versions) == 1 else None
        menus.append((rows, list(parts.values()), version))
    return menus


def rms_components(components):
    """Singleton identity; RMS means and conservative RMS recipe-spread proxy."""
    if not components or any(not isinstance(f.features, dict) or
                             not isinstance(f.feature_std, dict) for f in components):
        raise ValueError("A menu requires keyed features for every main dish")
    if len(components) == 1:
        f = components[0]
        return dict(f.features), dict(f.feature_std)
    means = [f.features for f in components]
    if any(set(row) != set(means[0]) for row in means):
        raise ValueError("All components of a menu must have the same feature keys")
    for food in components:
        if set(food.feature_std) != set(means[0]):
            raise ValueError("Component spread must cover its feature keys")
        for key, value in food.features.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Invalid component feature mean")
            std = food.feature_std[key]
            if (isinstance(std, bool) or not isinstance(std, (int, float)) or not math.isfinite(std)
                    or not 0 <= std <= .5 or std * std > value * (1-value) + 1e-12):
                raise ValueError("Invalid component recipe spread")
    def rms(rows):
        return {key: math.sqrt(math.fsum(row[key] ** 2 for row in rows) / len(rows)) for key in means[0]}
    return rms(means), rms([f.feature_std for f in components])


def _dish_groups(foods: dict) -> dict[int, str]:
    """Each dish's group; a set dish has none of its own, so it takes its single variant's."""
    singles = dict(Food.objects.filter(name__in={f.name for f in foods.values() if not f.food_group}, is_set=False)
                   .exclude(food_group="").values_list("name", "food_group"))
    return {pk: f.food_group or singles.get(f.name, "") for pk, f in foods.items()}


def _menu_candidates(menus, groups):
    combined = {}
    for rows, parts, version in menus:
        if version != FEATURE_VERSION:
            continue
        row = rows[0]
        identity = (row.raw_name, row.description, tuple(sorted(f.pk for f in parts)))
        if identity not in combined:
            values, deviations = rms_components(parts)
            candidate = {"food_id": min(r.id for r in rows), "name": row.raw_name, "display_name": row.raw_name,
                         "food_group": parts[0].food_group if len(parts) == 1 else "",
                         "food_groups": sorted({groups[f.pk] for f in parts} - {""}),
                         "menu_profile": "rms-v1", "features": values, "feature_std": deviations, "offers": []}
            combined[identity] = candidate
        candidate = combined[identity]
        candidate["food_id"] = min(candidate["food_id"], *(r.id for r in rows))
        offer = {"restaurant": row.restaurant, "meal": row.meal, "price": row.price, "lat": row.lat, "lng": row.lng}
        if offer not in candidate["offers"]:
            candidate["offers"].append(offer)
    for candidate in combined.values():
        candidate["offers"].sort(key=lambda o: (MEAL_ORDER[o["meal"]], o["restaurant"]))
    return sorted(combined.values(), key=lambda c: c["food_id"])


def current_meal(now: datetime.datetime | None = None) -> str:
    """The meal at this hour in Seoul: BR before 10:00, LU before 16:00, DN after."""
    hour = timezone.localtime(now).hour
    return "BR" if hour < 10 else "LU" if hour < 16 else "DN"


_store_menus = None  # (read at, rows, foods, dish groups) of _read_store_menus


def _read_store_menus() -> tuple[list[tuple], dict, dict]:
    """Cache complete sales lines, including untagged components."""
    global _store_menus
    now = time.monotonic()
    if _store_menus is None or now - _store_menus[0] >= settings.RECOMMEND_STORE_MENU_CACHE_S:
        rows = list(StoreMenu.objects.order_by("pk").values_list(
            "pk", "restaurant_id", "restaurant__name", "restaurant__lat", "restaurant__lng",
            "raw_name", "description", "price", "food_id", "allergens", "allergen_version"))
        foods = Food.objects.filter(pk__in=StoreMenu.objects.values("food_id")).in_bulk()
        _store_menus = (now, rows, foods, _dish_groups(foods))
    return _store_menus[1:]


def get_store_catalog(meal: str | None = None,
                      allergies: frozenset[str] = frozenset()) -> tuple[list, list]:
    """One original restaurant menu with RMS features, never its separate dishes."""
    rows, foods, groups = _read_store_menus()
    meal = meal or current_meal()
    records = [SalesLine(*row[:5], meal, *row[5:]) for row in rows]
    menus = _menu_lines(records, foods, allergies)
    return _menu_candidates(menus, groups), get_feature_schema()
