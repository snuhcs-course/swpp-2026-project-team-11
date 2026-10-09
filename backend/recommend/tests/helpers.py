# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Shared pieces for the recommendation API tests."""
import datetime
import json

from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION
from menus.models import Food, MenuItem, Restaurant

DAY = "2026-09-29"
ANSWER_IDS = ("yes", "probably_yes", "any", "probably_no", "no", "unknown")
STATE_KEYS = {"session_id", "engine", "date", "meal", "candidate_count",
              "max_questions", "can_undo", "step"}


def post(client, path, body=None):
    return client.post(path, data=json.dumps(body or {}), content_type="application/json")


def add_food(name, group="", *, restaurant="Test hall", meal="LU", price=5000,
             day=DAY, display_name=None, **features):
    """One served dish. Unnamed features default to 0.5."""
    place, _ = Restaurant.objects.get_or_create(code=restaurant, defaults={"name": restaurant})
    food, _ = Food.objects.get_or_create(name=name, defaults={
        "display_name": display_name or name, "food_group": group, "is_food": True,
        "feature_version": FEATURE_VERSION,
        "features": {key: features.get(key, 0.5) for key in FEATURE_KEYS}})
    MenuItem.objects.create(date=datetime.date.fromisoformat(day), meal=meal, restaurant=place,
                            raw_name=name, food=food, price=price)
    return food


def check_state(test, state):
    """Assert the shape the Android client decodes (client/.../SessionState.kt)."""
    test.assertEqual(set(state), STATE_KEYS)
    test.assertIsInstance(state["session_id"], str)
    test.assertIn(state["engine"], ("decision_tree", "llm"))
    test.assertIsInstance(state["can_undo"], bool)
    test.assertIsInstance(state["candidate_count"], int)
    step = state["step"]
    test.assertIsInstance(step["question_count"], int)
    test.assertTrue(step["text"])
    kind = step["type"]
    if kind == "question":
        test.assertTrue(step["question_id"])
        test.assertEqual([option["id"] for option in step["options"]], list(ANSWER_IDS))
        test.assertTrue(all(option["label"] for option in step["options"]))
        if state["max_questions"] is not None:
            test.assertLess(step["question_count"], state["max_questions"])
    elif kind in ("guess", "recommendation"):
        test.assertEqual("guess_id" in step, kind == "guess")
        test.assertIn(step["target_kind"], ("food", "group"))
        food = step["food"]
        test.assertEqual(set(food), {"food_id", "name", "display_name", "food_group", "offers"})
        test.assertTrue(food["display_name"])
        test.assertTrue(food["offers"])
        for offer in food["offers"]:
            test.assertEqual(set(offer), {"restaurant", "meal", "price"})
            test.assertIn(offer["meal"], ("BR", "LU", "DN"))
            test.assertTrue(offer["price"] is None or isinstance(offer["price"], int))
        test.assertEqual("group" in step, step["target_kind"] == "group")
        if "group" in step:
            group = step["group"]
            test.assertEqual(set(group), {"group_id", "display_name", "members"})
            test.assertIn(food["food_id"], [member["food_id"] for member in group["members"]])
            test.assertTrue(all(set(member) == {"food_id", "display_name"} and member["display_name"]
                                for member in group["members"]))
    elif kind == "unavailable":
        test.assertIn(step["reason"], ("empty_candidates", "candidates_exhausted"))
    else:
        test.fail(f"Unexpected step type: {kind}")
