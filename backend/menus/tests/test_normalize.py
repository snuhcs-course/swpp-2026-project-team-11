from django.test import SimpleTestCase

from menus.normalize import clean_name, is_noise


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
