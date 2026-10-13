# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import csv
import datetime
import io
import json
import pathlib
import tempfile
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from menus.normalize import dish_key
from menus.preprocess import overrides
from menus.preprocess.mapper import map_lines
from menus.tests.test_preprocess_llm import FakeLLM
from menus.tests.utils import without_committed_rules

DAY = datetime.date(2026, 10, 13)
PAYLOAD = {"result": [{"date": "2026-10-13", "LU": [
    {"code": "220동식당", "name_kr": "220동식당", "lat": None, "lng": None, "menus": [
        {"name_kr": "돈가스 카레우동", "price": 6500, "etc": []},
        {"name_kr": "공기밥", "price": 700, "etc": []}]},
    {"code": "공대간이식당", "name_kr": "공대간이식당", "lat": None, "lng": None, "menus": [
        {"name_kr": "마라탕", "price": 7700, "etc": []}]},
    {"code": "751동4층푸드코트", "name_kr": "75-1동 4층 푸드코트", "lat": None, "lng": None, "menus": [
        {"name_kr": "즉석 마라탕", "price": 8500, "etc": []}]},
]}]}
ANSWERS = {"돈가스 카레우동": (True, ["돈까스", "카레우동"]), "공기밥": (False, []),
           "마라탕": (True, ["마라탕"]), "즉석 마라탕": (True, ["즉석마라탕"])}  # a missed merge


def write_overrides(data):
    tmp = tempfile.TemporaryDirectory()
    path = pathlib.Path(tmp.name) / "overrides.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return tmp, mock.patch.object(overrides, "OVERRIDES_PATH", path)


@without_committed_rules
class OverridesTests(TestCase):
    def test_a_line_override_beats_the_llm(self):
        tmp, patch = write_overrides({"lines": {"돈가스 카레우동": ["돈까스"]}})
        with tmp, patch:
            llm = FakeLLM(ANSWERS)
            result = map_lines({dish_key("돈가스 카레우동"): "돈가스 카레우동"}, llm)
        self.assertEqual(result[dish_key("돈가스 카레우동")].dishes, ("돈까스",))
        self.assertEqual(result[dish_key("돈가스 카레우동")].source, "override")
        self.assertEqual(llm.calls, [])

    def test_an_empty_line_override_means_not_a_meal(self):
        tmp, patch = write_overrides({"lines": {"공기밥": []}})
        with tmp, patch:
            result = map_lines({dish_key("공기밥"): "공기밥"})
        self.assertFalse(result[dish_key("공기밥")].is_meal)

    def test_a_dish_override_merges_names_in_every_answer(self):
        tmp, patch = write_overrides({"dishes": {"즉석 마라탕": "마라탕"}})
        with tmp, patch:
            result = map_lines({dish_key("즉석 마라탕"): "즉석 마라탕", dish_key("마라탕"): "마라탕"},
                               FakeLLM(ANSWERS))
        self.assertEqual({m.dishes for m in result.values()}, {("마라탕",)})


@without_committed_rules
class ExportReviewTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        (self.dir / "day.json").write_text(json.dumps(PAYLOAD, ensure_ascii=False), encoding="utf-8")
        # The day was processed earlier: answers are in the MenuLine cache.
        lines = {dish_key(n): n for n in ANSWERS}
        map_lines(lines, FakeLLM(ANSWERS))

    def export(self):
        out, path = io.StringIO(), self.dir / "review.csv"
        call_command("export_preprocess_review", "--date", DAY.isoformat(),
                     "--from-json", str(self.dir / "day.json"), "--output", str(path), stdout=out)
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.reader(f)), out.getvalue()

    def test_rows_for_splits_non_meals_and_possible_missed_merges(self):
        rows, output = self.export()
        self.assertEqual(rows[0], ["type", "cafeteria", "line", "dishes", "source", "ok (Y/N)", "correction"])
        by_type = {row[0]: row for row in rows[1:]}
        self.assertEqual(by_type["split"][2:4], ["돈가스 카레우동", "돈까스 | 카레우동"])
        self.assertEqual(by_type["not_meal"][2], "공기밥")
        self.assertEqual(by_type["maybe_same"][2:4], ["즉석마라탕", "마라탕"])
        self.assertNotIn("merge", by_type)
        self.assertIn("합칠 후보 1", output)

    def test_after_the_override_the_dishes_show_up_as_a_merge(self):
        tmp, patch = write_overrides({"dishes": {"즉석마라탕": "마라탕"}})
        with tmp, patch:
            rows, _ = self.export()
        merge = next(row for row in rows if row[0] == "merge")
        self.assertEqual(merge[1:4], ["75-1동 4층 푸드코트, 공대간이식당", "마라탕 / 즉석 마라탕", "마라탕"])
        self.assertFalse(any(row[0] == "maybe_same" for row in rows))
