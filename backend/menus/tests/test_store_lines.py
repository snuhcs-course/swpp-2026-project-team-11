import hashlib
import json
import pathlib
import tempfile
from unittest import mock

from django.test import SimpleTestCase, TestCase

from menus.models import MenuLine
from menus.preprocess import mapper, store_lines
from menus.preprocess.mapper import Mapping
from menus.preprocess.store_lines import (
    clean_store_name, distinct_lines, entries, is_drink, is_store_notice, is_vague, line_key, map_store_lines,
)
from menus.preprocess.store_prompt import STORE_SYSTEM_PROMPT
from menus.sources.naver_stores import StoreMenuLine, StoreRecord
from menus.tests.utils import FakeStoreLLM, without_committed_rules

BANNERS = ["🔥 중식은 불향이 반입니다 🔥", "🍜 혼밥부터 가족 외식까지 🍜", "🚇역에서 2분 주차는 2시간🚗"]


def store(code, name, *menus, category="중식당"):
    return StoreRecord(code, name, category, 37.48, 126.95, "", "", 1,
                       tuple(StoreMenuLine(menu, price, description) for menu, price, description in menus))


def key(code, name, description=""):
    return line_key(code, name, "중식당", description)


def kept(name, price):
    cleaned, _ = clean_store_name(name)
    return not is_store_notice(name, cleaned, price) and not is_drink(cleaned)


class RuleTests(SimpleTestCase):
    def test_banners_without_a_price_are_notices(self):
        for banner in BANNERS:
            with self.subTest(banner):
                self.assertTrue(is_store_notice(banner, clean_store_name(banner)[0], None))
        self.assertTrue(is_store_notice("★★★", "", 1000))  # nothing left to name a dish
        self.assertTrue(is_store_notice("■□■□세트 메뉴□■□■", "세트 메뉴", None))  # a section header

    def test_dishes_are_kept_with_or_without_a_price(self):
        self.assertTrue(kept("모둠회(대)", None))  # "변동": a price that is not one number
        self.assertTrue(kept("★모둠회", None))  # "시가": marked, not framed
        self.assertTrue(kept("🔥불닭볶음면", None))
        self.assertTrue(kept("🍜 짬뽕", 8000))
        self.assertTrue(kept("한우등심(예약시 주문가능)", None))
        self.assertFalse(kept("주차 2시간 무료", None))
        self.assertEqual(clean_store_name("🍜 짬뽕")[0], "짬뽕")

    def test_promo_tags_are_removed(self):
        self.assertEqual(clean_store_name("[BEST] 김치찌개")[0], "김치찌개")
        self.assertEqual(clean_store_name("BEST 차돌짬뽕")[0], "차돌짬뽕")
        self.assertEqual(clean_store_name("(추천) 마라샹궈 NEW")[0], "마라샹궈")

    def test_drinks_are_dropped_but_not_dishes_named_after_one(self):
        for name in ["소주", "생맥주 500cc", "참이슬 후레쉬", "카스 1병", "콜라 1.25L", "레몬 하이볼", "제로콜라"]:
            with self.subTest(name):
                self.assertTrue(is_drink(name))
        for name in ["맥주 수육", "돈카스", "해물파전&막걸리", "닭볶음탕", "잔치국수"]:
            with self.subTest(name):
                self.assertFalse(is_drink(name))

    def test_vague_names_are_resolved_per_restaurant(self):
        for name in ["A세트", "점심특선", "2인 커플세트", "2인세트", "Premium Set", "VIP 특선", "혼밥 Set"]:
            self.assertTrue(is_vague(name), name)
        for name in ["탕수육세트", "Carbonara", "AMERICAN CHEESE SET", "죽", "회", "LA갈비"]:
            self.assertFalse(is_vague(name), name)
        self.assertNotEqual(key("MA1", "A세트"), key("MA2", "A세트"))
        self.assertEqual(key("MA1", "짜장 면"), key("MA2", "짜장면"))

    def test_the_key_holds_everything_the_llm_sees(self):
        self.assertNotEqual(key("MA1", "치킨세트", "후라이드+콜라"), key("MA2", "치킨세트", "양념+감자튀김"))
        self.assertNotEqual(key("MA1", "A세트", "짜장면+탕수육"), key("MA1", "A세트", "짬뽕+탕수육"))
        self.assertNotEqual(line_key("MA1", "떡볶이", "분식"), line_key("MA1", "떡볶이", "요리주점"))
        self.assertEqual(key("MA1", "짜장면", "x" * 60 + "a"), key("MA1", "짜장면", "x" * 60 + "b"))  # unseen tail

    def test_a_line_is_sent_once_and_a_vague_one_carries_its_restaurant(self):
        found = entries([
            store("MA1", "홍콩반점", ("짜장면", 7000, ""), ("A세트", 20000, "짜장면+탕수육"), ("소주", 5000, ""),
                  ("짬뽕", 8000, "")),
            store("MA2", "북경", ("짜장 면", 6500, ""), ("A세트", 22000, "짬뽕+탕수육"), ("짬뽕", 8000, "해물  가득")),
        ])
        self.assertEqual([e.dropped for e in found], ["", "", "drink", "", "", "", ""])
        lines = distinct_lines(found)
        self.assertEqual(sorted(line.label for line in lines.values()),
                         ["A세트 @북경", "A세트 @홍콩반점", "짜장면", "짬뽕", "짬뽕 #2"])
        self.assertEqual(lines[key("MA2", "짬뽕", "해물 가득")].description, "해물 가득")

    def test_labels_differ_as_the_answers_are_matched(self):
        lines = distinct_lines(entries([store("MA1", "분식집", ("떡볶이", 4000, "")),
                                        store("MA2", "포차", ("떡 볶이", 9000, "치즈 추가"))]))
        self.assertEqual(sorted(line.label for line in lines.values()), ["떡 볶이 #2", "떡볶이"])


class PromptVersionTests(SimpleTestCase):
    def test_a_prompt_change_comes_with_a_version_bump(self):
        digest = hashlib.sha256(STORE_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
        self.assertEqual(digest, store_lines.STORE_PROMPT_SHA256,
                         "The restaurant prompt changed: bump STORE_VERSION and update STORE_PROMPT_SHA256.")


@without_committed_rules
class MapStoreLinesTests(TestCase):
    ANSWERS = {"짜장면": (True, ["짜장면"]), "A세트 @홍콩반점": (True, ["짜장면", "탕수육"]),
               "점심특선 @한솥": (True, []), "꿔바로우": (True, ["꿔바로우"])}

    def lines(self, *menus):
        """menus: (code, restaurant, line) or (code, restaurant, line, description)."""
        return distinct_lines(entries([store(code, name, (menu, 7000, rest[0] if rest else ""))
                                       for code, name, menu, *rest in menus]))

    def test_answers_are_cached_apart_from_the_cafeteria_lines(self):
        lines = self.lines(("MA1", "홍콩반점", "짜장면"), ("MA1", "홍콩반점", "A세트"), ("MA2", "북경", "꿔바로우"))
        llm = FakeStoreLLM(self.ANSWERS)
        result = map_store_lines(lines, llm)
        self.assertEqual(result[key("MA1", "A세트")], Mapping(True, ("짜장면", "탕수육"), "llm"))
        self.assertEqual(set(MenuLine.objects.values_list("version", flat=True)), {store_lines.STORE_VERSION})
        self.assertNotIn("꿔바로우", mapper.known_dishes())  # the daily cafeteria prompt is unchanged

        again = FakeStoreLLM(self.ANSWERS)
        self.assertEqual(map_store_lines(lines, again), result)
        self.assertEqual(again.calls, [])

    def test_a_vague_line_without_a_nameable_dish_stores_none(self):
        result = map_store_lines(self.lines(("MA3", "한솥", "점심특선")), FakeStoreLLM(self.ANSWERS))
        self.assertEqual(result[key("MA3", "점심특선")], Mapping(True, (), "llm"))

    def test_a_changed_description_is_asked_again(self):
        map_store_lines(self.lines(("MA1", "홍콩반점", "A세트", "짜장면+탕수육")),
                        FakeStoreLLM({"A세트 @홍콩반점": (True, ["짜장면", "탕수육"])}))
        llm = FakeStoreLLM({"A세트 @홍콩반점": (True, ["짬뽕", "탕수육"])})
        result = map_store_lines(self.lines(("MA1", "홍콩반점", "A세트", "짬뽕+탕수육")), llm)
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(result[key("MA1", "A세트", "짬뽕+탕수육")].dishes, ("짬뽕", "탕수육"))

    def test_without_an_answer_a_line_is_one_dish_and_a_vague_one_none(self):
        lines = self.lines(("MA1", "홍콩반점", "짜장면"), ("MA1", "홍콩반점", "A세트"))
        result = map_store_lines(lines, FakeStoreLLM(self.ANSWERS, fail=True))
        self.assertEqual(result[key("MA1", "짜장면")], Mapping(True, ("짜장면",), "rule"))
        self.assertEqual(result[key("MA1", "A세트")], Mapping(True, (), "rule"))
        self.assertFalse(MenuLine.objects.exists())  # asked again next time

    def test_names_offered_for_reuse_share_letters_with_the_batch(self):
        MenuLine.objects.create(key="짜장면", name="짜장면", dishes=["짜장면"], source="llm",
                                version=mapper.PREPROCESS_VERSION)
        MenuLine.objects.create(key="김치찌개", name="김치찌개", dishes=["김치찌개"], source="llm",
                                version=mapper.PREPROCESS_VERSION)
        llm = FakeStoreLLM({"간짜장": (True, ["간짜장"])})
        map_store_lines(self.lines(("MA1", "홍콩반점", "간짜장")), llm)
        self.assertEqual(llm.calls[0]["known"], "짜장면")

    def test_overrides_name_one_restaurant_for_a_vague_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "overrides.json"
            path.write_text(json.dumps({"lines": {"A세트 @홍콩반점": ["짬뽕"]}, "dishes": {"자장면": "짜장면"}},
                                       ensure_ascii=False), encoding="utf-8")
            lines = self.lines(("MA1", "홍콩반점", "A세트"), ("MA2", "북경", "A세트"), ("MA2", "북경", "자장면"))
            llm = FakeStoreLLM({"A세트 @북경": (True, ["탕수육"]), "자장면": (True, ["자장면"])})
            with mock.patch("menus.preprocess.overrides.OVERRIDES_PATH", new=path):
                result = map_store_lines(lines, llm)
        self.assertEqual(result[key("MA1", "A세트")], Mapping(True, ("짬뽕",), "override"))
        self.assertEqual(result[key("MA2", "A세트")].dishes, ("탕수육",))
        self.assertEqual(result[key("MA2", "자장면")].dishes, ("짜장면",))
