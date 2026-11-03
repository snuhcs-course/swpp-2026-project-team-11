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


def record(raw_name, restaurant="220동식당", meal="LU", price=6500, lat=None, lng=None):
    return MenuRecord(date=DAY, meal=meal, restaurant_code=restaurant, restaurant_name=restaurant,
                      lat=lat, lng=lng, raw_name=raw_name, price=price, no_meat=False)


def run(records):
    lines = menu_lines(records)
    return store(DAY, records, map_lines(lines))


def seed_llm(name, dishes, is_meal=True, version=PREPROCESS_VERSION):
    MenuLine.objects.create(key=dish_key(name), name=name, dishes=dishes, is_meal=is_meal,
                            source=MenuLine.Source.LLM, version=version)


def tag(*names):
    for food in Food.objects.filter(name__in=names):
        food.is_food = True
        food.feature_version = FEATURE_VERSION
        food.features = {k: .5 for k in FEATURE_KEYS} | {"meal_variety": float(food.is_set)}
        food.feature_std = {k: .1 for k in FEATURE_KEYS} | {"meal_variety": 0.}
        food.save()


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

    def test_component_rows_produce_one_original_combo_candidate(self):
        seed_llm("돈가스 카레우동", ["돈까스", "카레우동"])
        run([record("돈가스 카레우동"), record("마라탕", "공대간이식당", price=7700)])
        tag("돈까스", "카레우동", "마라탕")
        candidates = {c["name"]: c for c in services.get_catalog(DAY, "LU")[0]}
        self.assertEqual(set(candidates), {"돈가스 카레우동", "마라탕"})
        self.assertEqual(candidates["돈가스 카레우동"]["offers"],
                         [{"restaurant": "220동식당", "meal": "LU", "price": 6500, "lat": None, "lng": None}])
        self.assertEqual(candidates["돈가스 카레우동"]["menu_profile"], "rms-v1")

    def test_a_merged_dish_lists_every_cafeteria(self):
        seed_llm("즉석 마라탕", ["마라탕"])
        seed_llm("마라탕", ["마라탕"])
        run([record("마라탕", "공대간이식당", price=7700),
             record("즉석 마라탕", "75-1동 4층 푸드코트", price=8500)])
        mala = Food.objects.get(name="마라탕")
        self.assertEqual(sorted(mala.menu_items.values_list("restaurant__name", flat=True)),
                         ["75-1동 4층 푸드코트", "공대간이식당"])

    def test_offers_carry_the_cafeteria_coordinates(self):
        run([record("마라탕", "공대간이식당", price=7700, lat=37.45727, lng=126.95079),
             record("마라탕", "220동식당")])
        tag("마라탕")
        [mala] = services.get_catalog(DAY, "LU")[0]
        self.assertEqual({o["restaurant"]: (o["lat"], o["lng"]) for o in mala["offers"]},
                         {"공대간이식당": (37.45727, 126.95079), "220동식당": (None, None)})

    def test_original_menu_variants_keep_their_own_offers(self):
        seed_llm("눈꽃치즈 돈까스", ["치즈돈까스"])
        seed_llm("치즈돈까스", ["치즈돈까스"])
        run([record("눈꽃치즈 돈까스", price=7900), record("치즈돈까스", price=7900),
             record("치즈돈까스", meal="DN", price=7900)])
        tag("치즈돈까스")
        candidates, _ = services.get_catalog(DAY)
        by_name = {c["name"]: c for c in candidates}
        self.assertEqual(set(by_name), {"눈꽃치즈 돈까스", "치즈돈까스"})
        self.assertEqual([o["meal"] for o in by_name["눈꽃치즈 돈까스"]["offers"]], ["LU"])
        self.assertEqual([o["meal"] for o in by_name["치즈돈까스"]["offers"]], ["LU", "DN"])

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
