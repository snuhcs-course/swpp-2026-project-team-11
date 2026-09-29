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
from .models import MenuItem

MEAL_ORDER = {"BR": 0, "LU": 1, "DN": 2}


def get_feature_schema() -> list[dict]:
    return [{"key": f.key, "question": f.question} for f in FEATURES]


def get_candidates(date: datetime.date | None = None, meal: str | None = None) -> list[dict]:
    """Dishes served on `date` (default: today in Seoul), optionally for one meal ("BR"/"LU"/"DN").

    Only real meals (is_food) tagged under the current FEATURE_VERSION are returned.
    """
    items = (
        MenuItem.objects
        .filter(date=date or timezone.localdate(),
                food__is_food=True, food__feature_version=FEATURE_VERSION)
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
        candidate["offers"].append(
            {"restaurant": item.restaurant.name, "meal": item.meal, "price": item.price})
    for candidate in candidates.values():
        candidate["offers"].sort(key=lambda offer: MEAL_ORDER[offer["meal"]])  # stable: keeps name order
    return list(candidates.values())
