"""What the question engines read from the menu DB.

    get_catalog(date, meal)       -> matching candidates, schema, version
    get_feature_schema("v1")      -> legacy schema
    get_candidates(date, meal)    -> legacy candidate shape

MVP2 only needs names. MVP1 receives v2 feature intensity means and recipe std,
or v1 scores when a dated meal has no v2 candidates.
"""

from __future__ import annotations

import datetime
import logging

from django.utils import timezone

from .features.schema import FEATURE_VERSION, FEATURES
from .features.legacy_schema import FEATURES as LEGACY_FEATURES
from .models import MenuItem

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


def get_catalog(date: datetime.date | None = None, meal: str | None = None) -> tuple[list, list, str]:
    """Load matching candidates/schema: choose whichever version covers more candidates on the date/meal.

    Never mix measurements with different meanings in one session; when coverage is partial,
    log a warning with the served vs. total candidate counts.
    """
    date = date or timezone.localdate()
    items = MenuItem.objects.filter(date=date, food__is_food=True)
    if meal:
        items = items.filter(meal=meal)
    total = items.values("food_id").distinct().count()
    v2_count = items.filter(food__feature_version=FEATURE_VERSION).values("food_id").distinct().count()
    version = FEATURE_VERSION if total > 0 and v2_count >= total - v2_count else "v1"
    candidates = get_candidates(date, meal, feature_version=version, include_std=(version == FEATURE_VERSION))
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


def get_candidates(date: datetime.date | None = None, meal: str | None = None, *,
                   feature_version: str = "v1", include_std: bool = False) -> list[dict]:
    """Dishes served on `date` (default: today in Seoul), optionally for one meal ("BR"/"LU"/"DN").

    Version selection is explicit during the staged extractor/DT rollout.
    """
    get_feature_schema(feature_version)  # reject unsupported versions
    items = (
        MenuItem.objects
        .filter(date=date or timezone.localdate(),
                food__is_food=True, food__feature_version=feature_version)
        .select_related("food", "restaurant")
        .order_by("food__name", "restaurant__name")
    )
    if meal:
        items = items.filter(meal=meal)

    candidates: dict[int, dict] = {}
    for item in items:
        food = item.food
        candidate = candidates.setdefault(food.id, {
            "food_id": food.id,
            "name": food.name,
            "display_name": food.display_name or food.name,
            "food_group": food.food_group,
            "features": food.features,
            "offers": [],
        })
        if include_std and feature_version == FEATURE_VERSION:
            candidate["feature_std"] = food.feature_std
        offer = {"restaurant": item.restaurant.name, "meal": item.meal, "price": item.price}
        # Two lines of one cafeteria can become the same dish ("눈꽃치즈 돈까스" and
        # "치즈돈까스"); list that cafeteria, meal and price once.
        if offer not in candidate["offers"]:
            candidate["offers"].append(offer)
    for candidate in candidates.values():
        candidate["offers"].sort(key=lambda offer: MEAL_ORDER[offer["meal"]])  # stable: keeps name order
    return list(candidates.values())
