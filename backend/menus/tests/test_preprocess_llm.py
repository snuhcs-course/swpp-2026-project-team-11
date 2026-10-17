# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import datetime
import io
import re
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase

from menus.models import Food, MenuItem, MenuLine
from menus.normalize import dish_key
from menus.preprocess import mapper
from menus.preprocess.mapper import LineBatch, map_lines
from menus.tests.utils import without_committed_rules

DAY = datetime.date(2026, 10, 13)

ANSWERS = {
    "돈가스 카레우동": (True, ["돈까스", "카레우동"]),
    "즉석 마라탕": (True, ["마라탕"]),
    "마라탕": (True, ["마라탕"]),
    "공기밥": (False, []),
    "냉모밀": (True, ["냉모밀"]),
}


class FakeLLM:
    """Answers like the structured-output Gemini client, without a network call."""

    def __init__(self, answers=ANSWERS, fail=False, drop=()):
        self.answers, self.fail, self.drop = answers, fail, set(drop)
        self.calls = []

    def invoke(self, messages):
        text = messages[-1].content
        known = text.split("[기존 표준 이름]\n", 1)[1].split("\n", 1)[0]
        names = [re.sub(r"^\d+\.\s*", "", line) for line in text.split("개]\n", 1)[1].splitlines()]
        self.calls.append({"names": names, "known": known})
        if self.fail:
            raise ValueError("model returned invalid JSON")
        items = [{"input_name": n, "is_meal": self.answers[n][0], "dishes": self.answers[n][1]}
                 for n in names if n in self.answers and not (len(names) > 1 and n in self.drop)]
        return LineBatch.model_validate({"items": items})


def lines(*names):
    return {dish_key(n): n for n in names}


@without_committed_rules
class MapLinesWithLLMTests(TestCase):
    def test_combo_lines_are_split_and_cached(self):
        llm = FakeLLM()
        result = map_lines(lines("돈가스 카레우동", "공기밥"), llm)
        self.assertEqual(result[dish_key("돈가스 카레우동")].dishes, ("돈까스", "카레우동"))
        self.assertFalse(result[dish_key("공기밥")].is_meal)
        self.assertEqual(MenuLine.objects.get(key=dish_key("돈가스 카레우동")).source, "llm")

        again = FakeLLM()
        self.assertEqual(map_lines(lines("돈가스 카레우동"), again), {
            dish_key("돈가스 카레우동"): mapper.Mapping(True, ("돈까스", "카레우동"), "llm")})
        self.assertEqual(again.calls, [])  # answered from the cache

    def test_earlier_dish_names_are_offered_for_reuse(self):
        map_lines(lines("마라탕"), FakeLLM())
        llm = FakeLLM()
        map_lines(lines("즉석 마라탕"), llm)
        self.assertIn("마라탕", llm.calls[0]["known"])

    def test_later_batches_see_names_chosen_by_earlier_ones(self):
        llm = FakeLLM()
        mapper.resolve_with_llm(["마라탕", "즉석 마라탕"], llm, [], batch_size=1)
        self.assertEqual(llm.calls[0]["known"], "(아직 없음)")
        self.assertIn("마라탕", llm.calls[1]["known"])

    def test_a_line_missing_from_the_batch_is_retried_alone(self):
        llm = FakeLLM(drop=["공기밥"])
        result = map_lines(lines("돈가스 카레우동", "공기밥"), llm)
        self.assertEqual(llm.calls[1]["names"], ["공기밥"])
        self.assertEqual(result[dish_key("공기밥")].source, "llm")

    def test_llm_failure_falls_back_to_the_rule_and_is_retried_next_time(self):
        result = map_lines(lines("돈가스 카레우동"), FakeLLM(fail=True))
        self.assertEqual(result[dish_key("돈가스 카레우동")],
                         mapper.Mapping(True, ("돈가스 카레우동",), "rule"))
        self.assertEqual(MenuLine.objects.get().source, "rule")

        result = map_lines(lines("돈가스 카레우동"), FakeLLM())
        self.assertEqual(result[dish_key("돈가스 카레우동")].dishes, ("돈까스", "카레우동"))
        self.assertEqual(MenuLine.objects.get().source, "llm")

    def test_a_meal_without_a_nameable_main_is_its_own_dish(self):
        llm = FakeLLM(answers={"세미양식부페": (True, [])})
        result = map_lines(lines("세미양식부페"), llm)
        self.assertEqual(result[dish_key("세미양식부페")], mapper.Mapping(True, ("세미양식부페",), "llm"))

    def test_unusable_answers_fall_back_to_the_rule(self):
        llm = FakeLLM(answers={"냉모밀": (True, ["냉" * 60])})  # not a dish name
        result = map_lines(lines("냉모밀"), llm)
        self.assertEqual(result[dish_key("냉모밀")].source, "rule")


@without_committed_rules
class FetchMenusWithLLMTests(TestCase):
    PAYLOAD = {"result": [{"date": "2026-10-13", "LU": [
        {"code": "220동식당", "name_kr": "220동식당", "lat": None, "lng": None, "menus": [
            {"name_kr": "돈가스 카레우동", "price": 6500, "etc": []},
            {"name_kr": "공기밥", "price": 700, "etc": []},
            {"name_kr": "냉모밀", "price": 5900, "etc": []}]},
        {"code": "공대간이식당", "name_kr": "공대간이식당", "lat": None, "lng": None, "menus": [
            {"name_kr": "마라탕", "price": 7700, "etc": []}]},
        {"code": "751동4층푸드코트", "name_kr": "75-1동 4층 푸드코트", "lat": None, "lng": None, "menus": [
            {"name_kr": "즉석 마라탕", "price": 8500, "etc": []}]},
    ]}]}

    def run_command(self, llm, *args):
        out = io.StringIO()
        with mock.patch("menus.sources.siksha.fetch_raw", return_value=self.PAYLOAD), \
                mock.patch("menus.management.commands.fetch_menus.api_key_available", return_value=True), \
                mock.patch.object(mapper, "build_llm", return_value=llm):
            call_command("fetch_menus", "--date", DAY.isoformat(), *args, stdout=out)
        return out.getvalue()

    def test_splits_merges_and_drops_non_meals(self):
        output = self.run_command(FakeLLM())
        self.assertEqual(sorted(Food.objects.values_list("name", flat=True)),
                         ["냉모밀", "돈까스", "마라탕", "카레우동"])
        self.assertEqual(Food.objects.get(name="마라탕").menu_items.count(), 2)
        self.assertFalse(MenuItem.objects.filter(raw_name="공기밥").exists())
        self.assertIn("세트 나눔 1", output)
        self.assertIn("식사 아님 1", output)

    def test_no_llm_flag_keeps_lines_whole(self):
        llm = FakeLLM()
        self.run_command(llm, "--no-llm")
        self.assertEqual(llm.calls, [])
        self.assertTrue(Food.objects.filter(name="돈가스 카레우동").exists())

    def test_gemini_failures_fail_the_command_after_storing(self):
        with self.assertRaisesMessage(CommandError, "메뉴 줄 5개를 처리하지 못해"):
            self.run_command(FakeLLM(fail=True))
        self.assertTrue(Food.objects.filter(name="돈가스 카레우동").exists())  # stored as one dish

