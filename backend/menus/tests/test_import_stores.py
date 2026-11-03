import csv
import datetime
import io
import json
import pathlib
import tempfile
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from menus import allergens, llm
from menus.allergens import ALLERGEN_VERSION
from menus.features import extractor
from menus.models import Food, MenuItem, MenuLine, Restaurant, StoreMenu
from menus.preprocess import mapper
from menus.sources import naver_stores
from menus.tests.test_extract_allergens import FakeLLM as FakeAllergenLLM
from menus.tests.test_extract_features import FakeLLM as FakeFeatureLLM
from menus.tests.utils import FakeStoreLLM, without_committed_rules

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "stores_sample.json"
ANSWERS = {
    "짜장면": (True, ["짜장면"]),
    "A세트 @홍콩반점 낙성대점": (True, ["짜장면", "탕수육"]),
    "탕수육(소)": (True, ["탕수육"]),
    "차돌짬뽕": (True, ["차돌짬뽕"]),
    "A세트 @북경 서울대입구점": (True, ["짬뽕", "탕수육"]),
    "닭볶음탕": (True, ["닭볶음탕"]),
    "마른안주": (False, []),
    "모둠회(대)": (True, ["모둠회"]),
    "공깃밥": (False, []),
}


class LoaderTests(SimpleTestCase):
    def test_keeps_matched_restaurants_that_serve_meals(self):
        stores, skipped = naver_stores.parse(naver_stores.read(FIXTURE))
        self.assertEqual([s.code for s in stores], ["MA0001", "MA0002", "MA0003", "MA0007"])  # the bar stays
        self.assertEqual(skipped, {"cafe_or_bakery": 2, "not_matched": 1})
        hongkong = stores[0]
        self.assertEqual((hongkong.name, hongkong.category, hongkong.place_id, hongkong.lat),
                         ("홍콩반점 낙성대점", "중식당", "1001", 37.47692))
        self.assertEqual(hongkong.address, "서울특별시 관악구 남부순환로 1900")
        self.assertIsNone(stores[3].menus[0].price)  # 모둠회: "변동"

    def test_a_bakery_filed_under_snacks_is_left_out_by_its_naver_category(self):
        data = naver_stores.read(FIXTURE)
        bakery = next(s for s in data["stores"] if s["id"] == "MA0005")
        self.assertEqual(bakery["category"], "기타 간이")
        self.assertFalse(naver_stores.serves_meals(bakery))

    def test_two_rows_matched_to_one_place_are_imported_once(self):
        data = naver_stores.read(FIXTURE)
        data["stores"].append(dict(data["stores"][0], id="MA0099"))
        stores, skipped = naver_stores.parse(data)
        self.assertNotIn("MA0099", [s.code for s in stores])
        self.assertEqual(skipped["same_place"], 1)

    def test_a_file_of_another_shape_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "bad.json"
            for data in ({"stores": "x"}, {"stores": [{"status": "matched"}]}):
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    naver_stores.read(path)


@without_committed_rules
class ImportStoresTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = pathlib.Path(folder.name)

    def run_command(self, model=None, *args, path=FIXTURE):
        model = model or FakeStoreLLM(ANSWERS)
        out = io.StringIO()
        with mock.patch.object(llm, "api_key_available", return_value=True), \
                mock.patch.object(mapper, "build_llm", return_value=model):
            call_command("import_stores", "--file", str(path), *args, stdout=out)
        return model, out.getvalue()

    def write(self, data, name="next.json"):
        path = self.folder / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def menu(self, code):
        return sorted((m.raw_name, m.food.name, m.food.is_set)
                      for m in StoreMenu.objects.filter(restaurant__code=code).select_related("food"))

    def test_imports_restaurants_and_one_menu_row_per_dish(self):
        model, out = self.run_command()
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(len(model.calls[0]["rows"]), 9)  # each distinct line once; drinks and notices never
        self.assertIn("규칙 제외: 공지 3, 술·음료 3", out)

        restaurant = Restaurant.objects.get(code="MA0001")
        self.assertEqual((restaurant.name, restaurant.source, restaurant.category, restaurant.place_id),
                         ("홍콩반점 낙성대점", "naver", "중식당", "1001"))
        self.assertEqual(self.menu("MA0001"), [
            ("A세트", "짜장면", True), ("A세트", "탕수육", True),
            ("짜장면", "짜장면", False), ("탕수육(소)", "탕수육", False)])
        self.assertEqual(self.menu("MA0003"), [("닭볶음탕", "닭볶음탕", False)])  # no drinks, no 마른안주
        self.assertEqual(self.menu("MA0007"), [("모둠회(대)", "모둠회", False)])
        self.assertFalse(Restaurant.objects.filter(code__in=["MA0004", "MA0005", "MA0006"]).exists())
        jjajang = Food.objects.get(name="짜장면", is_set=False)
        self.assertEqual(jjajang.store_menus.count(), 2)  # 홍콩반점 and 북경

    def test_a_new_file_replaces_the_menus_and_reuses_cached_answers(self):
        self.run_command()
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["stores"] = [s for s in data["stores"] if s["id"] != "MA0001"]
        data["counts"]["in_radius"] = len(data["stores"])  # the store left the area
        model, _ = self.run_command(path=self.write(data))
        self.assertEqual(model.calls, [])
        self.assertEqual(self.menu("MA0001"), [])
        self.assertTrue(StoreMenu.objects.filter(restaurant__code="MA0002").exists())

    def test_a_new_file_updates_the_restaurants(self):
        self.run_command()
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        naver = next(s for s in data["stores"] if s["id"] == "MA0001")["naver"]
        naver.update(name="홍콩반점0410 낙성대점", category="중국집", id="2002")
        self.run_command(FakeStoreLLM(ANSWERS | {"A세트 @홍콩반점0410 낙성대점": (True, ["짜장면", "탕수육"])}),
                         path=self.write(data))
        restaurant = Restaurant.objects.get(code="MA0001")
        self.assertEqual((restaurant.name, restaurant.category, restaurant.place_id),
                         ("홍콩반점0410 낙성대점", "중국집", "2002"))

    def test_a_line_listed_twice_keeps_the_dishes_of_both(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        menus = next(s for s in data["stores"] if s["id"] == "MA0001")["menus"]
        menus += [{"name": "정식", "price": 9000, "description": "김치찌개", "is_set": False},
                  {"name": "정식", "price": 12000, "description": "김치찌개+제육볶음", "is_set": False}]
        self.run_command(FakeStoreLLM(ANSWERS | {"정식 @홍콩반점 낙성대점": (True, ["김치찌개"]),
                                                 "정식 @홍콩반점 낙성대점 #2": (True, ["김치찌개", "제육볶음"])}),
                         path=self.write(data))
        self.assertEqual([row for row in self.menu("MA0001") if row[0] == "정식"], [
            ("정식", "김치찌개", False), ("정식", "김치찌개", True), ("정식", "제육볶음", True)])

    def test_a_partial_crawl_is_refused_and_can_keep_the_earlier_menus(self):
        self.run_command()
        before = self.menu("MA0002")
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        failed = next(s for s in data["stores"] if s["id"] == "MA0002")
        failed.update(status="failed", naver=None, menus=[])
        data["stores"] = [s for s in data["stores"] if s["id"] != "MA0007"]  # the collector stopped early
        path = self.write(data)
        with self.assertRaisesMessage(CommandError, "실패한 가게 1곳"):
            self.run_command(path=path)
        self.assertEqual(self.menu("MA0002"), before)

        model, out = self.run_command(None, "--allow-partial", path=path)
        self.assertIn("완전하지 않은 크롤 파일", out)
        self.assertEqual(self.menu("MA0002"), before)  # failed: kept
        self.assertEqual(self.menu("MA0007"), [("모둠회(대)", "모둠회", False)])  # missing: kept
        self.assertTrue(self.menu("MA0001"))  # answered again: replaced

    def test_line_allergens_carry_over_to_the_same_line(self):
        self.run_command()
        StoreMenu.objects.filter(raw_name="짜장면").update(allergens=["wheat"], allergen_version=ALLERGEN_VERSION)
        StoreMenu.objects.filter(raw_name="A세트").update(allergens=["wheat"], allergen_version=ALLERGEN_VERSION)
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        next(s for s in data["stores"] if s["id"] == "MA0002")["menus"][2]["description"] = "짬뽕+군만두"
        self.run_command(FakeStoreLLM(ANSWERS | {"A세트 @북경 서울대입구점": (True, ["짬뽕"])}),
                         path=self.write(data))
        tags = {(m.restaurant.code, m.raw_name, m.description): (m.allergens, m.allergen_version)
                for m in StoreMenu.objects.select_related("restaurant")}
        self.assertEqual(tags[("MA0002", "짜장면", "")], (["wheat"], ALLERGEN_VERSION))
        self.assertEqual(tags[("MA0001", "A세트", "짜장면+탕수육(소)+군만두")], (["wheat"], ALLERGEN_VERSION))
        self.assertEqual(tags[("MA0002", "A세트", "짬뽕+군만두")], ([], ""))  # a new line: tagged again

    def test_limit_replaces_only_the_restaurants_it_imports(self):
        self.run_command()
        self.run_command(None, "--limit", "1")
        self.assertTrue(StoreMenu.objects.filter(restaurant__code="MA0007").exists())

    def test_the_cafeteria_menu_and_cache_are_untouched(self):
        hall = Restaurant.objects.create(code="220동식당", name="220동식당")
        food = Food.objects.create(name="짜장면", is_food=True)
        MenuItem.objects.create(date=datetime.date(2026, 11, 2), meal="LU", restaurant=hall,
                                raw_name="짜장면", food=food)
        MenuLine.objects.create(key="짜장면", name="짜장면", dishes=["짜장면"], source="llm", version="v1")
        self.run_command()
        self.assertEqual(MenuItem.objects.get().food, food)
        self.assertEqual(Food.objects.get(name="짜장면", is_set=False), food)  # shared with the restaurants
        self.assertEqual(MenuLine.objects.get(key="짜장면").version, "v1")
        self.assertEqual(Restaurant.objects.get(code="220동식당").source, "siksha")

    def test_dry_run_calls_and_writes_nothing(self):
        with mock.patch.object(mapper, "build_llm", side_effect=AssertionError("no LLM in a dry run")):
            out = io.StringIO()
            call_command("import_stores", "--file", str(FIXTURE), "--dry-run", stdout=out)
        out = out.getvalue()
        self.assertIn("제외 비알코올/카페 1", out)
        self.assertIn("제외한 가게의 네이버 카테고리: 카페,디저트 1, 베이커리 1", out)
        self.assertIn("규칙으로 뺀 술·음료 3종", out)
        self.assertIn("LLM에 보낼 줄 9개", out)
        self.assertFalse(Restaurant.objects.exists())
        self.assertFalse(MenuLine.objects.exists())

    def test_review_csv_lists_rule_drops_and_the_llm_answers(self):
        path = self.folder / "review.csv"
        self.run_command(None, "--review", str(path))
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        kinds = {}
        for row in rows:
            kinds.setdefault(row["type"], []).append(row["line"])
        self.assertEqual(sorted(kinds["rule_notice"]), ["역에서 2분 주차는 2시간", "중식은 불향이 반입니다",
                                                       "혼밥부터 가족 외식까지"])
        self.assertEqual(sorted(kinds["rule_drink"]), ["생맥주 500cc", "소주", "콜라 1.25L"])
        self.assertEqual(sorted(kinds["not_meal"]), ["공깃밥", "마른안주"])
        self.assertEqual(sorted(kinds["split"]), ["A세트 @북경 서울대입구점", "A세트 @홍콩반점 낙성대점"])

    def test_llm_failures_fail_the_command_after_storing(self):
        with self.assertRaisesMessage(CommandError, "메뉴 줄 9개를 처리하지 못해"):
            self.run_command(FakeStoreLLM(ANSWERS, fail=True))
        self.assertTrue(StoreMenu.objects.filter(food__name="짜장면").exists())  # stored as it reads
        self.assertFalse(StoreMenu.objects.filter(raw_name="A세트").exists())  # a vague line names no dish

    def test_a_file_that_cannot_be_read_is_a_clear_error(self):
        with self.assertRaisesMessage(CommandError, "크롤 파일을 읽지 못했습니다"):
            self.run_command(path=self.folder / "missing.json")


@without_committed_rules
class RunStorePipelineTests(TestCase):
    def test_imports_tags_and_counts_the_candidates(self):
        out = io.StringIO()
        with mock.patch.object(llm, "api_key_available", return_value=True), \
                mock.patch.object(extractor, "api_key_available", return_value=True), \
                mock.patch.object(mapper, "build_llm", return_value=FakeStoreLLM(ANSWERS)), \
                mock.patch.object(extractor, "build_llm", return_value=FakeFeatureLLM()), \
                mock.patch.object(allergens, "build_llm", return_value=FakeAllergenLLM()):
            call_command("run_store_pipeline", "--file", str(FIXTURE), stdout=out)
        # 짜장면 and 탕수육 alone and in a set, 차돌짬뽕, 짬뽕 (set), 닭볶음탕, 모둠회
        self.assertIn("일반 식당 추천 후보: 7", out.getvalue())
        self.assertFalse(StoreMenu.objects.filter(allergen_version="").exists())

    def test_a_failed_import_stops_before_tagging(self):
        with mock.patch.object(llm, "api_key_available", return_value=True), \
                mock.patch.object(mapper, "build_llm", return_value=FakeStoreLLM(ANSWERS, fail=True)), \
                mock.patch.object(extractor, "build_llm", side_effect=AssertionError("no tagging")), \
                mock.patch.object(allergens, "build_llm", side_effect=AssertionError("no tagging")):
            with self.assertRaisesMessage(CommandError, "태깅은 건너뜁니다"):
                call_command("run_store_pipeline", "--file", str(FIXTURE), stdout=io.StringIO())
