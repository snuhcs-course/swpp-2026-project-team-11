# AI-generated: written with OpenAI Codex and reviewed by the team.
import datetime

from django.test import TestCase

from menus.services import get_candidates, get_feature_schema
from .. import DecisionTreeEngine


class CafeteriaIntegrationTests(TestCase):
    fixtures = ["menus_2026-09-29"]

    def test_real_lunch_candidates_can_be_used_without_api_key(self):
        rows = get_candidates(datetime.date(2026, 9, 29), "LU")
        self.assertEqual(len(rows), 193)
        schema = get_feature_schema()
        engine = DecisionTreeEngine(rows, schema, context={"date": "2026-09-29", "meal": "LU"})
        step = engine.start()
        self.assertIn(step["type"], {"question", "guess"})
        if step["type"] == "question":
            self.assertTrue(step["text"].isascii())
        result = engine.recommend_now()
        original = next(c for c in rows if c["food_id"] == result["food"]["food_id"])
        self.assertEqual(result["food"]["offers"], original["offers"])
        final = engine.feedback(result["guess_id"], True)
        self.assertEqual(final["type"], "recommendation")
        self.assertEqual(final["food"]["food_id"], original["food_id"])

    def test_no_menu_for_current_date_is_explicit(self):
        engine = DecisionTreeEngine(get_candidates(datetime.date(2026, 10, 6)), get_feature_schema())
        self.assertEqual(engine.start()["reason"], "empty_candidates")

    def test_changed_meal_context_rejects_snapshot(self):
        rows = get_candidates(datetime.date(2026, 9, 29), "LU")
        schema = get_feature_schema()
        e = DecisionTreeEngine(rows, schema, config={"policy": "greedy"}, context={"date": "2026-09-29", "meal": "LU"})
        snap = e.snapshot()
        with self.assertRaises(ValueError):
            DecisionTreeEngine.from_snapshot(rows, schema, snap, context={"date": "2026-09-29", "meal": "DN"})
