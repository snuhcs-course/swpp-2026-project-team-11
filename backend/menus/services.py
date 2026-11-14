"""What the question engines read from the menu DB.

    get_catalog(date, meal, allergies) -> matching candidates, schema
    get_store_catalog(meal, allergies) -> the same for the restaurants near the stations
    get_feature_schema()         -> current schema

These readers perform SELECTs only; source writers and imports prepare IDs.
Session candidates are actual sales menus. Source prices/notices are removed
from their titles. Imported whole-menu profiles take precedence over RMS mains.

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
from django.db.models import Q
from django.utils import timezone

from .allergens import ALLERGEN_VERSION
from .features.schema import FEATURE_VERSION, FEATURES
from .models import Food, MenuItem, MenuLabel, SalesMenu, StoreMenu
from .labels import LABEL_VERSION, needs_label
from .normalize import clean_name
from .menu_profiles import description_digest, equivalent_menu_key, offer_key, recipe_key, title, validate_features

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
    restaurant_code: str


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
                        item.food.allergen_version if item.food_id else "", place.code))
    menus = _menu_lines(records, foods, allergies)
    version = FEATURE_VERSION
    rows = _menu_candidates(menus, _dish_groups(foods), source="cafeteria")
    logger.info("%s %s: serving %d recommendations from %d source menus with feature_version=%s",
        date, meal or "ALL", len(rows), len(menus), version)
    return rows, get_feature_schema()


def _menu_lines(records, foods, allergies):
    """A line can never lose a component due to tags or a partial feature rollout."""
    grouped = defaultdict(list)
    for row in records:
        grouped[(row.restaurant_id, row.meal, row.raw_name, row.description, row.price)].append(row)
    menus = []
    for rows in grouped.values():
        if allergies and any(row.allergen_version != ALLERGEN_VERSION or not allergies.isdisjoint(row.allergens) for row in rows):
            continue
        complete = all(row.food_id in foods and foods[row.food_id].is_food is True for row in rows)
        parts = {row.food_id: foods[row.food_id] for row in rows if row.food_id in foods}
        versions = {f.feature_version for f in parts.values()}
        version = versions.pop() if complete and len(versions) == 1 else None
        menus.append((rows, list(parts.values()), version))
    return menus


def rms_components(components):
    """Singleton identity; RMS means and conservative RMS recipe-spread proxy."""
    if not components or any(not isinstance(f.features, dict) or
                             not isinstance(f.feature_std, dict) for f in components):
        raise ValueError("A menu requires keyed features for every main dish")
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
    if len(components) == 1:
        return dict(components[0].features), dict(components[0].feature_std)
    def rms(rows):
        return {key: math.sqrt(math.fsum(row[key] ** 2 for row in rows) / len(rows)) for key in means[0]}
    values = rms(means)
    deviations = rms([f.feature_std for f in components])
    return values, deviations


def _dish_groups(foods: dict) -> dict[int, str]:
    """Each dish's group; a set dish has none of its own, so it takes its single variant's."""
    singles = dict(Food.objects.filter(name__in={f.name for f in foods.values() if not f.food_group}, is_set=False)
                   .exclude(food_group="").values_list("name", "food_group"))
    return {pk: f.food_group or singles.get(f.name, "") for pk, f in foods.items()}


def _menu_candidates(menus, groups, *, source):
    """Imported whole-menu profiles take precedence; otherwise compose complete mains.

    The durable registry is separate from replaceable source rows. Profile keys
    are restaurant-scoped; equal computed recipes can still share several offers.
    """
    keys = {offer_key(source, rows[0].restaurant_code, rows[0].raw_name, rows[0].description)
            for rows, _, _ in menus}
    keys.update(recipe_key(source, rows[0].raw_name, rows[0].description, parts)
                for rows, parts, _ in menus)
    codes = {rows[0].restaurant_code for rows, _, _ in menus}
    profiles = {p.key: p for p in SalesMenu.objects.filter(
        Q(key__in=keys) | (Q(source=source, restaurant_code__in=codes) & ~Q(feature_version="")))}
    annotated_titles = {(p.restaurant_code, p.name) for p in profiles.values() if p.feature_version}
    names = list({rows[0].raw_name for rows, _, _ in menus if needs_label(rows[0].raw_name)})
    labels = {}
    for start in range(0, len(names), 500):
        labels.update(MenuLabel.objects.filter(name__in=names[start:start + 500], version=LABEL_VERSION)
                      .values_list("name", "label"))
    combined = {}
    for rows, parts, current in menus:
        row = rows[0]
        profile = profiles.get(offer_key(source, row.restaurant_code, row.raw_name, row.description))
        annotated = profile is not None and bool(profile.feature_version)
        try:
            if annotated:
                if (profile.feature_version != FEATURE_VERSION
                        or profile.description_sha256 != description_digest(row.description)):
                    logger.warning("Withholding changed/stale menu profile: %s %s", row.restaurant_code, row.raw_name)
                    continue
                values, deviations = dict(profile.features), dict(profile.feature_std)
                identity = profile.key
            else:
                if (row.restaurant_code, title(row.raw_name)) in annotated_titles:
                    logger.warning("Withholding changed menu description: %s %s", row.restaurant_code, row.raw_name)
                    continue
                if current != FEATURE_VERSION:
                    logger.warning("Withholding untagged/partial menu: %s %s", row.restaurant_code, row.raw_name)
                    continue
                values, deviations = rms_components(parts)
                identity = recipe_key(source, row.raw_name, row.description, parts)
            validate_features(values, deviations)
        except (ValueError, TypeError, KeyError) as error:
            logger.warning("Withholding invalid menu profile: %s %s (%s)", row.restaurant_code, row.raw_name, error)
            continue
        registered = profiles.get(identity)
        if registered is None:
            logger.warning("Unregistered menu; run register_menu_ids: %s %s", row.restaurant_code, row.raw_name)
            continue
        components = profile.annotation_metadata.get("components") if annotated else None
        if not isinstance(components, list) or not components or not all(isinstance(c, str) for c in components):
            components = [part.name for part in parts]
        equivalent = equivalent_menu_key(title(row.raw_name), row.description, components, values, deviations)
        if equivalent not in combined:
            candidate = {"food_id": registered.pk, "name": row.raw_name, "display_name": labels.get(row.raw_name) or clean_name(row.raw_name)[0],
                         "food_group": parts[0].food_group if len(parts) == 1 else "",
                         "food_groups": sorted({groups[f.pk] for f in parts} - {""}),
                         "menu_profile": "rms-v1", "features": values, "feature_std": deviations, "offers": []}
            combined[equivalent] = candidate
        candidate = combined[equivalent]
        candidate["food_id"] = min(candidate["food_id"], registered.pk)
        candidate["food_groups"] = sorted(set(candidate["food_groups"]) | {groups[f.pk] for f in parts} - {""})
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


_store_menus = None  # (read at, rows, foods, dish groups, catalogues) of _read_store_menus


def _read_store_menus() -> tuple[list[tuple], dict, dict, dict]:
    """Cache complete sales lines, including untagged components, and the catalogues built from them."""
    global _store_menus
    now = time.monotonic()
    if _store_menus is None or now - _store_menus[0] >= settings.RECOMMEND_STORE_MENU_CACHE_S:
        rows = list(StoreMenu.objects.order_by("pk").values_list(
            "pk", "restaurant_id", "restaurant__name", "restaurant__lat", "restaurant__lng",
            "raw_name", "description", "price", "food_id", "allergens", "allergen_version", "restaurant__code"))
        foods = Food.objects.filter(pk__in=StoreMenu.objects.values("food_id")).in_bulk()
        _store_menus = (now, rows, foods, _dish_groups(foods), {})
    return _store_menus[1:]


def get_store_catalog(meal: str | None = None,
                      allergies: frozenset[str] = frozenset()) -> tuple[list, list]:
    """One original restaurant menu with RMS features, never its separate dishes.

    Building the catalogue takes about a second for thousands of menus, so it is kept with
    the cached lines for each meal and allergy set. Each call gets its own offers to change.
    """
    rows, foods, groups, catalogues = _read_store_menus()
    meal = meal or current_meal()
    if (meal, allergies) not in catalogues:
        records = [SalesLine(*row[:5], meal, *row[5:]) for row in rows]
        catalogues[meal, allergies] = _menu_candidates(_menu_lines(records, foods, allergies), groups, source="general")
    candidates = [{**c, "offers": [dict(offer) for offer in c["offers"]]} for c in catalogues[meal, allergies]]
    return candidates, get_feature_schema()
