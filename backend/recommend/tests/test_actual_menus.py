"""Original sales menus, with RMS composition instead of standalone component proposals."""

import datetime
import math
from types import SimpleNamespace
from django.test import TestCase
from menus.models import Food, MenuItem, Restaurant, StoreMenu
from menus.features.schema import FEATURE_KEYS
from menus.allergens import ALLERGEN_VERSION
from menus import services
from .helpers import post, check_state

DAY = datetime.date(2026, 11, 3)


class OriginalMenuTests(TestCase):
    def setUp(self):
        self.place = Restaurant.objects.create(code="hall", name="Test hall", lat=37.46, lng=126.95)

    def food(self, name, value):
        return Food.objects.create(
            name=name,
            is_food=True,
            is_set=True,
            feature_version="v2",
            features={k: value for k in FEATURE_KEYS},
            feature_std=dict.fromkeys(FEATURE_KEYS, 0.1),
            allergens=[],
            allergen_version=ALLERGEN_VERSION,
        )

    def menu(self, raw, parts, price=12000, place=None, source="cafeteria"):
        for f in parts:
            fields = dict(restaurant=place or self.place, raw_name=raw, food=f, price=price)
            if source == "general":
                StoreMenu.objects.create(**fields, allergens=[], allergen_version=ALLERGEN_VERSION)
            else:
                MenuItem.objects.create(**fields, date=DAY, meal="LU")

    def test_rms_returns_original_menu_and_exact_singleton(self):
        a, b = self.food("삼겹살", 0.8), self.food("떡볶이", 0.2)
        self.menu("삼겹살+떡볶이", [a, b])
        self.menu("단품 삼겹살", [a], 10000)
        rows, _ = services.get_catalog(DAY, "LU")
        by_name = {r["name"]: r for r in rows}
        combo = by_name["삼겹살+떡볶이"]
        self.assertEqual(set(by_name), {"삼겹살+떡볶이", "단품 삼겹살"})
        self.assertAlmostEqual(combo["features"]["pork"], math.sqrt(0.34))
        self.assertEqual(combo["offers"][0]["price"], 12000)
        self.assertEqual(by_name["단품 삼겹살"]["features"], a.features)
        self.assertEqual(by_name["단품 삼겹살"]["feature_std"], a.feature_std)
        for r in rows:
            self.assertTrue(
                all(
                    s * s <= r["features"][k] * (1 - r["features"][k]) + 1e-12
                    for k, s in r["feature_std"].items()
                )
            )

    def test_three_components_and_repeated_database_rows_do_not_change_weights(self):
        parts = [self.food("a", 0.8), self.food("b", 0.2), self.food("c", 0.5)]
        self.menu("Three mains", parts)
        first = services.get_catalog(DAY, "LU")[0]
        other = Restaurant.objects.create(code="other", name="Second hall")
        self.menu("Three mains", parts, place=other, price=15000)
        [menu], _ = services.get_catalog(DAY, "LU")
        self.assertEqual(menu["features"], first[0]["features"])
        self.assertAlmostEqual(menu["features"]["spicy"], math.sqrt((0.8**2 + 0.2**2 + 0.5**2) / 3))
        self.assertEqual(len(menu["offers"]), 2)

    def test_a_missing_component_hides_the_whole_menu_for_both_sources(self):
        a, b = self.food("a", 0.8), self.food("b", 0.2)
        self.menu("Set", [a, b])
        self.menu("Set", [a, b], source="general")
        b.feature_version = ""
        b.save()
        self.assertFalse(services.get_catalog(DAY, "LU")[0])
        self.assertFalse(services.get_store_catalog("LU")[0])

    def test_refusal_and_undo_operate_on_actual_menu_for_dt_and_rl(self):
        a, b = self.food("a", 0.8), self.food("b", 0.2)
        self.menu("Original set", [a, b])
        self.menu("Another real menu", [a], price=8000)
        for engine in ("rl", "decision_tree"):
            with self.subTest(engine=engine):
                r = post(
                    self.client,
                    "/api/sessions/",
                    {"date": str(DAY), "meal": "LU", "engine": engine, "language": "ko"},
                )
                self.assertEqual(r.status_code, 201)
                state = r.json()
                self.assertEqual(state["candidate_count"], 2)
                url = "/api/sessions/" + state["session_id"] + "/"
                guess = post(self.client, url + "recommend-now/").json()
                check_state(self, guess)
                original = guess["step"]
                post(self.client, url + "feedback/", {"guess_id": original["guess_id"], "accepted": False})
                restored = post(self.client, url + "undo/").json()["step"]
                self.assertEqual(restored, original)
                post(self.client, url + "feedback/", {"guess_id": original["guess_id"], "accepted": False})
                next_menu = post(self.client, url + "recommend-now/").json()["step"]
                self.assertNotEqual(next_menu["food"]["display_name"], original["food"]["display_name"])
                self.assertIn(original["food"]["display_name"], {"Original set", "Another real menu"})

    def test_equal_set_names_with_different_components_remain_distinct(self):
        a, b, c = self.food("a", 0.8), self.food("b", 0.2), self.food("c", 0.5)
        other = Restaurant.objects.create(code="shop2", name="Other restaurant")
        self.menu("A세트", [a, b], source="general")
        self.menu("A세트", [a, c], source="general", place=other, price=17000)
        menus, _ = services.get_store_catalog("LU")
        self.assertEqual(len(menus), 2)
        self.assertNotEqual(menus[0]["food_id"], menus[1]["food_id"])
        self.assertEqual({m["offers"][0]["price"] for m in menus}, {12000, 17000})

    def test_llm_can_select_same_named_sets_independently_without_changing_shown_name(self):
        from question_engines.llm import LLMEngine
        from question_engines.llm.tests.helpers import FakeLLM, recommend

        a, b, c = self.food("a", 0.8), self.food("b", 0.2), self.food("c", 0.5)
        other = Restaurant.objects.create(code="shop2", name="Other restaurant")
        self.menu("A세트", [a, b], source="general")
        self.menu("A세트", [a, c], source="general", place=other, price=17000)
        candidates, _ = services.get_store_catalog("LU")
        fake = FakeLLM()
        e = LLMEngine(candidates, llm=fake)
        labels = list(e.choices)
        fake.replies.extend([recommend(labels[0]), recommend(labels[1])])
        first = e.start()
        second = e.feedback(first["guess_id"], False)
        self.assertEqual(first["food"]["display_name"], "A세트")
        self.assertEqual(second["food"]["display_name"], "A세트")
        self.assertNotEqual(first["guess_id"], second["guess_id"])
        self.assertNotEqual(first["food"]["offers"], second["food"]["offers"])

    def test_rms_is_bounded_and_singleton_preserves_the_complete_vector(self):
        import random

        rng = random.Random(731)
        for n in (1, 2, 3, 8):
            parts = []
            for i in range(n):
                mean = rng.random()
                std = min(0.5, (mean * (1 - mean)) ** 0.5) * rng.random()
                parts.append(SimpleNamespace(features={"spicy": mean}, feature_std={"spicy": std}))
            means, stds = services.rms_components(parts)
            self.assertGreaterEqual(means["spicy"], 0)
            self.assertLessEqual(means["spicy"], 1)
            self.assertLessEqual(stds["spicy"] ** 2, means["spicy"] * (1 - means["spicy"]) + 1e-12)
            if n == 1:
                self.assertEqual((means, stds), (parts[0].features, parts[0].feature_std))

    def test_original_title_keeps_dish_identity_but_cleans_source_decoration(self):
        a = self.food("pork", 0.8)
        original = "  [A] 삼겹살 + 떡볶이  "
        self.menu(original, [a])
        for engine in ("rl", "decision_tree"):
            r = post(self.client, "/api/sessions/", {"date": str(DAY), "meal": "LU", "engine": engine})
            self.assertEqual(r.status_code, 201)
            self.assertEqual(r.json()["step"]["food"]["display_name"], "[A] 삼겹살 + 떡볶이")

    def test_prices_and_source_notices_do_not_reach_the_title(self):
        self.menu("<A코너>삼겹살+떡볶이 : 12,000원 /", [self.food("pork", .8)])
        [menu], _ = services.get_catalog(DAY, "LU")
        self.assertEqual(menu["display_name"], "삼겹살+떡볶이")

    def test_one_invalid_component_does_not_break_other_menus(self):
        good, broken = self.food("good", .8), self.food("broken", .2)
        broken.features = {"pork": 2.0}
        broken.save()
        self.menu("Valid meal", [good])
        self.menu("Invalid meal", [broken])
        with self.assertLogs("menus.services", level="WARNING"):
            rows, _ = services.get_catalog(DAY, "LU")
        self.assertEqual([r["name"] for r in rows], ["Valid meal"])

    def test_registry_id_survives_source_row_replacement_and_date_and_price_changes(self):
        food = self.food("pork", .8)
        self.menu("Pork set", [food], price=10000)
        original = services.get_catalog(DAY, "LU")[0][0]["food_id"]
        MenuItem.objects.all().delete()
        MenuItem.objects.create(date=DAY + datetime.timedelta(days=1), meal="DN",
                                restaurant=self.place, raw_name="Pork set", food=food, price=13000)
        new = services.get_catalog(DAY + datetime.timedelta(days=1), "DN")[0][0]
        self.assertEqual(new["food_id"], original)
        self.menu("Pork set", [food], source="general")
        self.assertNotEqual(services.get_store_catalog("LU")[0][0]["food_id"], original)
