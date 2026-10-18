"""What the question engines read from the menu DB.

    get_feature_schema()          -> [{"key", "question"}, ...]
    get_candidates(date, meal)    -> today's dishes with their features

MVP2 (LLM engine) only needs each candidate's name; MVP1 (information-gain engine)
uses `features` as P(yes | food) for each question in the schema.
"""

from __future__ import annotations

import datetime

from django.utils import timezone

from .features.schema import FEATURE_VERSION, FEATURES
from .features.legacy_schema import FEATURES as LEGACY_FEATURES
from .models import MenuItem

MEAL_ORDER = {"BR": 0, "LU": 1, "DN": 2}


def get_feature_schema(feature_version: str = "v1") -> list[dict]:
    if feature_version not in ("v1", FEATURE_VERSION):
        raise ValueError(f"Unsupported feature version: {feature_version}")
    features = LEGACY_FEATURES if feature_version == "v1" else FEATURES
    return [{"key": f.key, "question": f.question} for f in features]


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
