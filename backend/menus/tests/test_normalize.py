from django.test import SimpleTestCase

from menus.normalize import clean_name, dish_key, is_noise


class IsNoiseTests(SimpleTestCase):
    def test_headers_and_notices_are_noise(self):
        for raw in ["<경성 돈카츠>", "< 바비든든>", "<TAKE-OUT>", "( Break time은 없습니다 )",
                    "※ 운영시간 : 11:00~14:00", "   ",
                    "< 위 메뉴외에도 다양한 메뉴가 준비되어 있습니다>"]:
            self.assertTrue(is_noise(raw), raw)

    def test_dishes_are_not_noise(self):
        for raw in ["육개장", "<A코너>베테랑칼국수, 미니열무보리비빔밥, 옥수수야채전",
                    "(뚝)어묵매운탕&계란찜", "순두부찌개(밥포함)"]:
            self.assertFalse(is_noise(raw), raw)


class CleanNameTests(SimpleTestCase):
    def test_plain_name_is_unchanged(self):
        self.assertEqual(clean_name("  쇠고기  육개장 "), ("쇠고기 육개장", None))

    def test_corner_tags_are_stripped(self):
        self.assertEqual(clean_name("<A코너>베테랑칼국수, 미니열무보리비빔밥")[0],
                         "베테랑칼국수, 미니열무보리비빔밥")
        self.assertEqual(clean_name("<셀프코너>: 잡곡밥+육짬뽕탕+통삼겹동파육")[0],
                         "잡곡밥+육짬뽕탕+통삼겹동파육")
        self.assertEqual(clean_name("<뷔페>+차돌박이된장찌개+연근조림")[0],
                         "차돌박이된장찌개+연근조림")

    def test_trailing_notice_is_stripped(self):
        raw = "<+세미뷔페>+알감자조림+후식+<뷔페 특성상 메뉴의 조기품절+가능성이 있으니 양해 부탁드립니다>"
        self.assertEqual(clean_name(raw)[0], "알감자조림+후식")

    def test_price_inside_name_is_extracted(self):
        self.assertEqual(clean_name("버거운치킨버거 : 5,200원 /"), ("버거운치킨버거", 5200))
        self.assertEqual(clean_name("쉬림프치즈베이크 : 5.900원 /"), ("쉬림프치즈베이크", 5900))
        self.assertEqual(clean_name("케이준순살강정(소) : 5,000원 / (중)"), ("케이준순살강정(소)", 5000))
        self.assertEqual(
            clean_name("한입치킨 세트 - 버거운치킨버거 + 음료 1잔 = 17,100원 (순살변경 + )"),
            ("한입치킨 세트 - 버거운치킨버거 + 음료 1잔", 17100),
        )

    def test_dangling_equals_is_stripped(self):
        self.assertEqual(clean_name("한입떡말이 세트 - 눈꽃치즈떡볶이 + 김말이 10조각 ="),
                         ("한입떡말이 세트 - 눈꽃치즈떡볶이 + 김말이 10조각", None))


class DishKeyTests(SimpleTestCase):
    """Real names from 2026-09-28 ~ 10-13 that are the same menu line."""

    def test_spacing_variants_share_a_key(self):
        self.assertEqual(dish_key("눈꽃 치즈 돈까스"), dish_key("눈꽃치즈 돈까스"))
        self.assertEqual(dish_key("치킨 마요 덮밥"), dish_key("치킨마요덮밥"))

    def test_size_portion_and_serving_markers_are_ignored(self):
        for variant, base in [
            ("육회 비빔밥(S)", "육회 비빔밥"), ("육회 비빔밥(L)", "육회 비빔밥"),
            ("케이준순살강정(소)", "케이준순살강정"), ("치킨탕수육 (大)", "치킨탕수육"),
            ("순두부찌개(밥포함)", "순두부찌개"), ("갈릭슈림프샐러드(채식변경가능)", "갈릭슈림프샐러드"),
            ("(뚝)어묵매운탕&계란찜", "어묵매운탕&계란찜"), ("야채춘권(3p)", "야채춘권"),
            ("옥수수 감자고로케 2P", "옥수수 감자고로케"), ("김말이 10조각", "김말이"),
            ("참치마요(R)+제육한접시 세트", "참치마요+제육한접시 세트"),
        ]:
            self.assertEqual(dish_key(variant), dish_key(base), variant)

    def test_variety_markers_and_different_dishes_stay_apart(self):
        self.assertNotEqual(dish_key("키친101 비빔밥(야채)"), dish_key("키친101 비빔밥"))
        self.assertNotEqual(dish_key("물냉면"), dish_key("비빔냉면"))
        self.assertNotEqual(dish_key("핫치킨버거"), dish_key("통새우버거"))

    def test_key_is_never_empty(self):
        self.assertEqual(dish_key("(소)"), "(소)")
