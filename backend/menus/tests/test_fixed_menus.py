# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import csv
import datetime
import io
import json
import pathlib
import tempfile
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from menus.normalize import dish_key
from menus.preprocess import fixed, mapper
from menus.preprocess.mapper import map_lines
from menus.sources import siksha
from menus.tests.test_preprocess_llm import FakeLLM

START = datetime.date(2026, 10, 5)


def day(n):
    return START + datetime.timedelta(days=n)


def payload(menus_by_day):
    """{day index: {cafeteria: [menu names]}} -> a Siksha-shaped payload (lunch only)."""
    result = []
    for n, cafeterias in sorted(menus_by_day.items()):
        result.append({"date": day(n).isoformat(), "LU": [
            {"code": code, "name_kr": code, "lat": None, "lng": None,
             "menus": [{"name_kr": m, "price": 5000, "etc": []} for m in menus]}
            for code, menus in cafeterias.items()]})
    return {"result": result}


BURGER = ["핫치킨버거", "통새우버거", "탄산음료"]
HISTORY = {n: {
    "버거운버거": BURGER,                                     # same board every day
    "두레미담": ["고등어 소금구이", f"셀프코너 메뉴 {n}"],       # one fixed order item
    "학생회관식당": [f"오늘의 메뉴 {n}"],                       # changes every day
    "220동식당": ["직화구이 쌀국수"] if n < 3 else ["직화쌀국수"],  # board changed on day 3
} for n in range(6)}


class ClassifyTests(SimpleTestCase):
    def setUp(self):
        records = siksha.parse(payload(HISTORY))
        self.by_code = {h.code: h for h in fixed.classify(records, recent_days=3)}

    def test_restaurant_kinds(self):
        self.assertEqual({c: h.kind for c, h in self.by_code.items()}, {
            "버거운버거": fixed.FIXED, "두레미담": fixed.MIXED,
            "학생회관식당": fixed.DAILY, "220동식당": fixed.FIXED})

    def test_fixed_lines(self):
        self.assertEqual(set(self.by_code["버거운버거"].fixed_lines.values()), set(BURGER))
        self.assertEqual(list(self.by_code["두레미담"].fixed_lines.values()), ["고등어 소금구이"])
        self.assertEqual(self.by_code["학생회관식당"].fixed_lines, {})

    def test_a_changed_board_is_cataloged_as_it_is_now(self):
        self.assertEqual(list(self.by_code["220동식당"].fixed_lines.values()), ["직화쌀국수"])


ANSWERS = {"핫치킨버거": (True, ["핫치킨버거"]), "통새우버거": (True, ["통새우버거"]),
           "탄산음료": (False, []), "고등어 소금구이": (True, ["고등어구이"]),
           "직화쌀국수": (True, ["쌀국수"])}


class BuildFixedMenusTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.history = self.tmp / "history.json"
        self.history.write_text(json.dumps(payload(HISTORY), ensure_ascii=False), encoding="utf-8")
        self.catalog = self.tmp / "fixed_menus.json"

    def build(self, llm, *args):
        out = io.StringIO()
        with mock.patch("menus.management.commands.build_fixed_menus.api_key_available",
                        return_value=llm is not None), \
                mock.patch.object(mapper, "build_llm", return_value=llm):
            call_command("build_fixed_menus", "--from-json", str(self.history),
                         "--output", str(self.catalog), "--recent-days", "3", *args, stdout=out)
        return out.getvalue()

    def test_writes_a_catalog_and_a_review_csv(self):
        review = self.tmp / "review.csv"
        self.build(FakeLLM(ANSWERS), "--review", str(review))
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        burger = catalog["restaurants"]["버거운버거"]
        self.assertEqual(burger["type"], "fixed")
        self.assertEqual(burger["lines"][dish_key("탄산음료")],
                         {"name": "탄산음료", "is_meal": False, "dishes": [], "source": "llm"})
        self.assertEqual(catalog["restaurants"]["두레미담"]["lines"][dish_key("고등어 소금구이")]["dishes"],
                         ["고등어구이"])
        self.assertNotIn("학생회관식당", catalog["restaurants"])

        with open(review, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0][-2:], ["ok (Y/N)", "correction"])
        self.assertEqual(len(rows), 1 + 5)

    def test_a_rebuild_keeps_hand_corrections(self):
        self.build(FakeLLM(ANSWERS))
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        key = dish_key("고등어 소금구이")
        catalog["restaurants"]["두레미담"]["lines"][key]["dishes"] = ["고등어소금구이"]
        self.catalog.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")

        llm = FakeLLM(ANSWERS)
        self.build(llm)
        rebuilt = json.loads(self.catalog.read_text(encoding="utf-8"))
        self.assertEqual(rebuilt["restaurants"]["두레미담"]["lines"][key]["dishes"], ["고등어소금구이"])
        self.assertEqual(llm.calls, [])  # nothing new to resolve

    def test_without_an_llm_nothing_is_cataloged_as_a_guess(self):
        output = self.build(None)
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        self.assertEqual(sum(len(r["lines"]) for r in catalog["restaurants"].values()), 0)
        self.assertIn("넣지 않은 줄 5개", output)


class CatalogAtRunTimeTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = pathlib.Path(tmp.name) / "fixed_menus.json"
        self.path.write_text(json.dumps({"restaurants": {"버거운버거": {"type": "fixed", "lines": {
            dish_key("핫치킨버거"): {"name": "핫치킨버거", "is_meal": True, "dishes": ["핫치킨버거"]},
            dish_key("탄산음료"): {"name": "탄산음료", "is_meal": False, "dishes": []},
        }}}}, ensure_ascii=False), encoding="utf-8")
        patcher = mock.patch.object(fixed, "CATALOG_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cataloged_lines_never_reach_the_llm(self):
        llm = FakeLLM(ANSWERS)
        result = map_lines({dish_key("핫치킨버거"): "핫치킨버거", dish_key("탄산음료"): "탄산음료"}, llm)
        self.assertEqual({k: m.source for k, m in result.items()}, {
            dish_key("핫치킨버거"): "fixed", dish_key("탄산음료"): "fixed"})
        self.assertFalse(result[dish_key("탄산음료")].is_meal)
        self.assertEqual(llm.calls, [])

    def test_fetch_menus_warns_when_a_fixed_board_shows_new_lines(self):
        out = io.StringIO()
        day_payload = payload({0: {"버거운버거": ["핫치킨버거", "불고기버거"]}})
        with mock.patch("menus.sources.siksha.fetch_raw", return_value=day_payload), \
                mock.patch("menus.management.commands.fetch_menus.api_key_available", return_value=False):
            call_command("fetch_menus", "--date", day(0).isoformat(), stdout=out)
        self.assertIn("목록에 없는 메뉴 1개", out.getvalue())
        self.assertIn("불고기버거", out.getvalue())
