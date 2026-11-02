"""What the question engines read from the menu DB.

    get_catalog(date, meal, allergies) -> matching candidates, schema, version
    get_store_catalog(meal, allergies) -> the same for the restaurants near the stations
    get_feature_schema("v1")      -> legacy schema
    get_candidates(date, meal)    -> legacy candidate shape

MVP2 only needs names. MVP1 receives v2 feature intensity means and recipe std,
or v1 scores when a dated meal has no v2 candidates.

`allergies` (menus/allergens.py keys) is a hard rule: a menu line is never offered when
one of its dishes is tagged with one of them or has no current allergen tags. A combo
line ("돈가스 카레우동") is bought whole, so this covers every dish it lists.
"""

from __future__ import annotations

import datetime
import logging
import time

from django.conf import settings
from django.utils import timezone

from .allergens import ALLERGEN_VERSION
from .features.schema import FEATURE_VERSION, FEATURES
from .features.legacy_schema import FEATURES as LEGACY_FEATURES
from .models import Food, MenuItem, StoreMenu

logger = logging.getLogger(__name__)
MEAL_ORDER = {"BR": 0, "LU": 1, "DN": 2}


def get_feature_schema(feature_version: str = "v1") -> list[dict]:
    if feature_version not in ("v1", FEATURE_VERSION):
        raise ValueError(f"Unsupported feature version: {feature_version}")
    if feature_version == "v1":
        return [{"key": f.key, "question": f.question} for f in LEGACY_FEATURES]
    from question_engines.decision_tree.contracts import FEATURE_PRESENTATION_V2
    return [{"key": f.key, "question": FEATURE_PRESENTATION_V2[f.key][0],
             "question_en": FEATURE_PRESENTATION_V2[f.key][0],
             "family": FEATURE_PRESENTATION_V2[f.key][1]} for f in FEATURES]


def get_catalog(date: datetime.date | None = None, meal: str | None = None,
                allergies: frozenset[str] = frozenset(), *, prefer_v2: bool = False) -> tuple[list, list, str]:
    """Use the majority version unless a v2 engine requests available v2 dishes.

    Never mix measurements with different meanings in one session; when coverage is partial,
    log a warning with the served vs. total candidate counts.
    """
    date = date or timezone.localdate()
    items = MenuItem.objects.filter(date=date, food__is_food=True)
    if meal:
        items = items.filter(meal=meal)
    # The version is chosen among the dishes the user can be offered.
    unsafe = _unsafe_lines(date, allergies)
    versions = {food: feature_version for food, feature_version, *line in items.values_list(
                    "food_id", "food__feature_version", "meal", "restaurant_id", "raw_name")
                if tuple(line) not in unsafe}
    total = len(versions)
    v2_count = sum(feature_version == FEATURE_VERSION for feature_version in versions.values())
    version = FEATURE_VERSION if v2_count and (prefer_v2 or v2_count >= total - v2_count) else "v1"
    candidates = get_candidates(date, meal, feature_version=version,
                                include_std=(version == FEATURE_VERSION), allergies=allergies)
    if len(candidates) != total:
        logger.warning(
            "%s %s: serving %d/%d candidates with feature_version=%s (%d v2 candidates present)",
            date, meal or "ALL", len(candidates), total, version, v2_count,
        )
    else:
        logger.info(
            "%s %s: serving %d/%d candidates with feature_version=%s",
            date, meal or "ALL", len(candidates), total, version,
        )
    return candidates, get_feature_schema(version), version


def _unsafe_lines(date: datetime.date, allergies: frozenset[str]) -> set[tuple]:
    """The (meal, restaurant, menu line) of `date` that cannot be offered with `allergies`."""
    if not allergies:
        return set()
    rows = MenuItem.objects.filter(date=date).values_list(
        "meal", "restaurant_id", "raw_name", "food__allergens", "food__allergen_version")
    return {(meal, restaurant, line) for meal, restaurant, line, tags, version in rows
            if version != ALLERGEN_VERSION or not allergies.isdisjoint(tags)}


def get_candidates(date: datetime.date | None = None, meal: str | None = None, *,
                   feature_version: str = "v1", include_std: bool = False,
                   allergies: frozenset[str] = frozenset()) -> list[dict]:
    """Dishes served on `date` (default: today in Seoul), optionally for one meal ("BR"/"LU"/"DN").

    Version selection is explicit during the staged extractor/DT rollout.
    """
    get_feature_schema(feature_version)  # reject unsupported versions
    date = date or timezone.localdate()
    unsafe = _unsafe_lines(date, allergies)
    items = (
        MenuItem.objects
        .filter(date=date, food__is_food=True, food__feature_version=feature_version)
        .select_related("food", "restaurant")
        .order_by("food__name", "restaurant__name")
    )
    if meal:
        items = items.filter(meal=meal)

    candidates: dict[int, dict] = {}
    for item in items:
        if (item.meal, item.restaurant_id, item.raw_name) in unsafe:
            continue
        if item.food_id not in candidates:
            candidates[item.food_id] = _candidate(item.food, include_std and feature_version == FEATURE_VERSION)
        candidate = candidates[item.food_id]
        restaurant = item.restaurant
        offer = {"restaurant": restaurant.name, "meal": item.meal, "price": item.price,
                 "lat": restaurant.lat, "lng": restaurant.lng}
        # Two lines of one cafeteria can become the same dish ("눈꽃치즈 돈까스" and
        # "치즈돈까스"); list that cafeteria, meal and price once.
        if offer not in candidate["offers"]:
            candidate["offers"].append(offer)
    for candidate in candidates.values():
        candidate["offers"].sort(key=lambda offer: MEAL_ORDER[offer["meal"]])  # stable: keeps name order
    return list(candidates.values())


def _candidate(food, include_std: bool) -> dict:
    candidate = {
        "food_id": food.id,
        "name": food.name,
        "display_name": food.display_name or food.name,
        "food_group": food.food_group,
        "features": food.features,
        "offers": [],
    }
    if include_std:
        candidate["feature_std"] = food.feature_std
    return candidate


def current_meal(now: datetime.datetime | None = None) -> str:
    """The meal at this hour in Seoul: BR before 10:00, LU before 16:00, DN after."""
    hour = timezone.localtime(now).hour
    return "BR" if hour < 10 else "LU" if hour < 16 else "DN"


_store_menus = None  # (read at, rows, foods) of _read_store_menus


def _read_store_menus() -> tuple[list[tuple], dict]:
    """(menu rows, {food id: v2-tagged Food}) of the restaurants, read again after
    RECOMMEND_STORE_MENU_CACHE_S seconds: they change only when a crawl is imported."""
    global _store_menus
    now = time.monotonic()
    if _store_menus is None or now - _store_menus[0] >= settings.RECOMMEND_STORE_MENU_CACHE_S:
        rows = list(StoreMenu.objects.filter(food__is_food=True).order_by("food__name", "restaurant__name")
                    .values_list("food_id", "restaurant__name", "restaurant__lat", "restaurant__lng", "price",
                                 "allergens", "allergen_version"))
        foods = Food.objects.filter(pk__in=StoreMenu.objects.values("food_id"),
                                    feature_version=FEATURE_VERSION).in_bulk()
        _store_menus = (now, rows, foods)
    return _store_menus[1], _store_menus[2]


def get_store_catalog(meal: str | None = None,
                      allergies: frozenset[str] = frozenset()) -> tuple[list, list, str]:
    """The dishes of the restaurants near the stations (StoreMenu), as get_catalog returns them.

    Only v2-tagged dishes are served. A menu board is not split into meals, so each offer
    carries the session's meal (else the current one) and keeps the cafeteria offer shape.
    With `allergies`, a menu line is left out unless its own tags (the whole line, sides
    included: StoreMenu.allergens) are current and free of them.
    """
    rows, foods = _read_store_menus()
    meal = meal or current_meal()
    candidates: dict[int, dict] = {}
    offered, untagged = set(), set()
    for food_id, restaurant, lat, lng, price, tags, allergen_version in rows:
        if allergies and (allergen_version != ALLERGEN_VERSION or not allergies.isdisjoint(tags)):
            continue
        if food_id not in foods:
            untagged.add(food_id)
            continue
        if (food_id, restaurant, price, lat, lng) in offered:
            continue
        offered.add((food_id, restaurant, price, lat, lng))
        if food_id not in candidates:
            candidates[food_id] = _candidate(foods[food_id], include_std=True)
        candidates[food_id]["offers"].append(
            {"restaurant": restaurant, "meal": meal, "price": price, "lat": lat, "lng": lng})
    if untagged:
        logger.warning("restaurants: %d dishes without %s features are not served; run extract_features --stores",
                       len(untagged), FEATURE_VERSION)
    return list(candidates.values()), get_feature_schema(FEATURE_VERSION), FEATURE_VERSION
