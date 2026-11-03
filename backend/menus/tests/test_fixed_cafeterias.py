import datetime
import io
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from menus.models import MenuItem, Restaurant
from menus.normalize import dish_key
from menus.preprocess import overrides
from menus.sources import fixed_cafeterias, siksha
from menus.tests.utils import without_committed_rules

TUESDAY, SUNDAY = datetime.date(2026, 11, 3), datetime.date(2026, 11, 8)
CAFETERIA = {"name": "구시아푸드마켓", "lat": 37.45, "lng": 126.95, "since": "2026-11-03",
             "meals": ["LU", "DN"], "weekdays": [0, 1, 2, 3, 4, 5],
             "menus": [{"corner": "비비고고", "name": "장어비빔밥", "price": 8900},
                       {"name": "소금삼겹", "price": 3900}]}


@mock.patch("menus.sources.fixed_cafeterias.load", new=lambda: [CAFETERIA])
class RecordsTests(SimpleTestCase):
    def test_an_open_day_has_every_line_at_every_meal(self):
        records = fixed_cafeterias.records(TUESDAY)
        self.assertEqual([(r.meal, r.raw_name) for r in records],
                         [("LU", "장어비빔밥"), ("LU", "소금삼겹"), ("DN", "장어비빔밥"), ("DN", "소금삼겹")])
        eel = records[0]
        self.assertEqual((eel.restaurant_code, eel.restaurant_name, eel.price, eel.lat, eel.date),
                         ("구시아푸드마켓비비고고", "구시아푸드마켓>비비고고", 8900, 37.45, TUESDAY))
        self.assertEqual(records[1].restaurant_name, "구시아푸드마켓")

    def test_a_closed_weekday_and_a_day_before_the_board_have_none(self):
        self.assertEqual(fixed_cafeterias.records(SUNDAY), [])
        self.assertEqual(fixed_cafeterias.records(datetime.date(2026, 11, 2)), [])


class CommittedBoardTests(SimpleTestCase):
    def test_the_committed_boards_are_complete(self):
        for cafeteria in fixed_cafeterias.load():
            self.assertLessEqual(set(cafeteria["meals"]), set(siksha.MEALS))
            self.assertLessEqual(set(cafeteria["weekdays"]), set(range(7)))
            datetime.date.fromisoformat(cafeteria["since"])
            for menu in cafeteria["menus"]:
                self.assertTrue(menu["name"].strip())
                self.assertIsInstance(menu["price"], int)

    def test_a_set_with_a_plate_of_jeyuk_is_both_dishes_and_drinks_are_none(self):
        lines, _ = overrides.load_overrides()
        self.assertEqual(lines[dish_key("스팸마요 SET")], ["스팸마요덮밥", "제육볶음"])
        for drink in ("펩시콜라", "펩시콜라제로", "펩시 제로", "코카콜라 제로"):
            self.assertEqual(lines[dish_key(drink)], [], drink)


@without_committed_rules
@mock.patch("menus.management.commands.fetch_menus.api_key_available", new=lambda: False)
@mock.patch("menus.sources.fixed_cafeterias.load", new=lambda: [CAFETERIA])
@mock.patch("menus.sources.siksha.fetch_raw")
class FetchMenusTests(TestCase):
    def run_command(self, day):
        out = io.StringIO()
        call_command("fetch_menus", "--date", day.isoformat(), stdout=out)
        return out.getvalue()

    def test_the_board_is_stored_with_the_day_menu(self, fetch_raw):
        fetch_raw.return_value = {"result": [{"date": TUESDAY.isoformat(), "LU": [{
            "code": "학생회관식당", "name_kr": "학생회관식당", "lat": 37.45932, "lng": 126.95058,
            "menus": [{"name_kr": "육개장", "price": 3000}]}]}]}
        self.run_command(TUESDAY)
        eel = MenuItem.objects.get(meal="DN", raw_name="장어비빔밥")
        self.assertEqual((eel.date, eel.price, eel.restaurant.name, eel.restaurant.lat),
                         (TUESDAY, 8900, "구시아푸드마켓>비비고고", 37.45))
        self.assertEqual(MenuItem.objects.get(raw_name="육개장").restaurant.name, "학생회관식당")
        self.assertEqual(MenuItem.objects.count(), 1 + 4)
        self.assertEqual(Restaurant.objects.count(), 3)

    def test_nothing_is_stored_on_a_closed_day(self, fetch_raw):
        fetch_raw.return_value = {"result": [{"date": SUNDAY.isoformat()}]}
        self.assertIn("운영 메뉴 없음", self.run_command(SUNDAY))
        self.assertFalse(MenuItem.objects.exists())
