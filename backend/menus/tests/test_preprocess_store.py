# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import datetime

from django.test import TestCase

from menus import services
from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION
from menus.management.commands.fetch_menus import menu_lines, store
from menus.models import Food, MenuItem, MenuLine
from menus.normalize import dish_key
from menus.preprocess.mapper import PREPROCESS_VERSION, map_lines
from menus.sources.siksha import MenuRecord
from menus.tests.utils import without_committed_rules

DAY = datetime.date(2026, 10, 13)


def record(raw_name, restaurant="220동식당", meal="LU", price=6500):
    return MenuRecord(date=DAY, meal=meal, restaurant_code=restaurant, restaurant_name=restaurant,
                      lat=None, lng=None, raw_name=raw_name, price=price, no_meat=False)


def run(records):
    lines = menu_lines(records)
    return store(DAY, records, map_lines(lines))


def seed_llm(name, dishes, is_meal=True, version=PREPROCESS_VERSION):
    MenuLine.objects.create(key=dish_key(name), name=name, dishes=dishes, is_meal=is_meal,
                            source=MenuLine.Source.LLM, version=version)


def tag(*names):
    Food.objects.filter(name__in=names).update(
        is_food=True, feature_version=FEATURE_VERSION, features={k: 0.5 for k in FEATURE_KEYS})


@without_committed_rules
class RuleMappingTests(TestCase):
    def test_without_an_llm_answer_each_line_is_one_dish(self):
        stats = run([record("육개장", "학생회관식당", price=3000), record("냉모밀")])
        self.assertEqual(stats["menu_items"], 2)
        self.assertEqual(set(Food.objects.values_list("name", flat=True)), {"육개장", "냉모밀"})
        self.assertEqual(set(MenuLine.objects.values_list("source", flat=True)), {"rule"})

    def test_spacing_and_size_variants_share_one_food(self):
        run([record("눈꽃 치즈 돈까스"), record("눈꽃치즈 돈까스", "75-1동 4층 푸드코트"),
             record("육회 비빔밥(S)", price=5900), record("육회 비빔밥(L)", price=7900)])
        self.assertEqual(Food.objects.count(), 2)
        self.assertEqual(MenuLine.objects.count(), 2)
        yukhoe = Food.objects.get(name="육회 비빔밥(S)")
        self.assertEqual(sorted(yukhoe.menu_items.values_list("price", flat=True)), [5900, 7900])

    def test_an_old_preprocess_version_is_not_trusted(self):
        seed_llm("돈가스 카레우동", ["돈까스", "카레우동"], version="v0")
        run([record("돈가스 카레우동")])
        self.assertEqual(list(Food.objects.values_list("name", flat=True)), ["돈가스 카레우동"])


@without_committed_rules
class CachedMappingTests(TestCase):
    def test_a_combo_line_is_stored_once_per_dish(self):
        seed_llm("돈가스 카레우동", ["돈까스", "카레우동"])
        stats = run([record("돈가스 카레우동")])
        self.assertEqual((stats["menu_items"], stats["split_lines"]), (2, 1))
        items = MenuItem.objects.filter(raw_name="돈가스 카레우동")
        self.assertEqual(sorted(i.food.name for i in items), ["돈까스", "카레우동"])

    def test_both_dishes_offer_the_combo_and_the_contract_is_unchanged(self):
        seed_llm("돈가스 카레우동", ["돈까스", "카레우동"])
        run([record("돈가스 카레우동"), record("마라탕", "공대간이식당", price=7700)])
        tag("돈까스", "카레우동", "마라탕")
        candidates = {c["name"]: c for c in services.get_candidates(DAY, "LU")}
        self.assertEqual(set(candidates), {"돈까스", "카레우동", "마라탕"})
        for name in ("돈까스", "카레우동"):
            self.assertEqual(candidates[name]["offers"],
                             [{"restaurant": "220동식당", "meal": "LU", "price": 6500}])
        for candidate in candidates.values():
            self.assertEqual(set(candidate),
                             {"food_id", "name", "display_name", "food_group", "features", "offers"})
            self.assertTrue(all(set(o) == {"restaurant", "meal", "price"} for o in candidate["offers"]))

    def test_a_merged_dish_lists_every_cafeteria(self):
        seed_llm("즉석 마라탕", ["마라탕"])
        seed_llm("마라탕", ["마라탕"])
        run([record("마라탕", "공대간이식당", price=7700),
             record("즉석 마라탕", "75-1동 4층 푸드코트", price=8500)])
        mala = Food.objects.get(name="마라탕")
        self.assertEqual(sorted(mala.menu_items.values_list("restaurant__name", flat=True)),
                         ["75-1동 4층 푸드코트", "공대간이식당"])

    def test_two_lines_of_one_cafeteria_merged_into_one_dish_offer_it_once(self):
        seed_llm("눈꽃치즈 돈까스", ["치즈돈까스"])
        seed_llm("치즈돈까스", ["치즈돈까스"])
        run([record("눈꽃치즈 돈까스", price=7900), record("치즈돈까스", price=7900),
             record("치즈돈까스", meal="DN", price=7900)])
        tag("치즈돈까스")
        [candidate] = services.get_candidates(DAY)
        self.assertEqual(candidate["offers"], [{"restaurant": "220동식당", "meal": "LU", "price": 7900},
                                               {"restaurant": "220동식당", "meal": "DN", "price": 7900}])

    def test_lines_that_are_not_meals_are_not_stored(self):
        seed_llm("공기밥", [], is_meal=False)
        stats = run([record("공기밥", price=700), record("냉모밀")])
        self.assertEqual((stats["not_meal"], stats["menu_items"]), (1, 1))
        self.assertFalse(MenuItem.objects.filter(raw_name="공기밥").exists())

    def test_rerun_is_idempotent(self):
        seed_llm("돈가스 카레우동", ["돈까스", "카레우동"])
        records = [record("돈가스 카레우동"), record("냉모밀")]
        run(records)
        before = (MenuItem.objects.count(), Food.objects.count(), MenuLine.objects.count())
        run(records)
        self.assertEqual((MenuItem.objects.count(), Food.objects.count(), MenuLine.objects.count()),
                         before)
