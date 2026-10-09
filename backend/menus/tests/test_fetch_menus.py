# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import datetime
import io
import json
import pathlib
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from menus.models import Food, MenuItem, Restaurant
from menus.sources import siksha

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "siksha_2026-09-29.json"
DAY = datetime.date(2026, 9, 29)


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class SikshaParseTests(SimpleTestCase):
    def test_parse_real_response(self):
        records = siksha.parse(load_fixture())
        self.assertEqual(len(records), 65)
        self.assertEqual({r.meal for r in records}, {"BR", "LU", "DN"})
        self.assertTrue(all(r.date == DAY for r in records))

        yukgaejang = next(r for r in records if r.raw_name == "육개장")
        self.assertEqual((yukgaejang.meal, yukgaejang.restaurant_code, yukgaejang.price),
                         ("LU", "학생회관식당", 3000))
        self.assertAlmostEqual(yukgaejang.lat, 37.45, places=1)

    def test_no_meat_tag(self):
        payload = {"result": [{"date": "2026-09-30", "LU": [{
            "code": "학생회관식당", "name_kr": "학생회관식당", "lat": None, "lng": None,
            "menus": [{"name_kr": "마파두부", "price": 3000, "etc": ["No meat"]}],
        }]}]}
        [record] = siksha.parse(payload)
        self.assertTrue(record.no_meat)

    def test_empty_day(self):
        self.assertEqual(siksha.parse({"count": 0, "result": []}), [])


@mock.patch("menus.sources.siksha.fetch_raw")
class FetchMenusCommandTests(TestCase):
    def run_command(self, *args) -> str:
        out = io.StringIO()
        call_command("fetch_menus", *args, stdout=out)
        return out.getvalue()

    def test_stores_one_day(self, fetch_raw):
        fetch_raw.return_value = load_fixture()
        output = self.run_command("--date", "2026-09-29")

        fetch_raw.assert_called_once_with(DAY)
        self.assertEqual(Restaurant.objects.count(), 6)
        self.assertEqual(MenuItem.objects.count(), 65 - 12)  # 12 header/notice lines
        self.assertEqual(Food.objects.count(), 27)
        self.assertIn("노이즈 스킵 12", output)

        burger = MenuItem.objects.get(meal="LU", raw_name="버거운치킨버거 : 5,200원 /")
        self.assertEqual((burger.food.name, burger.price), ("버거운치킨버거", 5200))
        # 220동 serves the same menu all day: one Food, three MenuItems.
        self.assertEqual(Food.objects.get(name="냉모밀").menu_items.count(), 3)

    def test_rerun_is_idempotent(self, fetch_raw):
        fetch_raw.return_value = load_fixture()
        self.run_command("--date", "2026-09-29")
        counts = (Restaurant.objects.count(), MenuItem.objects.count(), Food.objects.count())
        self.run_command("--date", "2026-09-29")
        self.assertEqual(
            (Restaurant.objects.count(), MenuItem.objects.count(), Food.objects.count()), counts)

    def test_rerun_drops_menus_that_were_removed(self, fetch_raw):
        payload = load_fixture()
        fetch_raw.return_value = payload
        self.run_command("--date", "2026-09-29")
        for restaurant in payload["result"][0]["LU"]:
            if restaurant["code"] == "학생회관식당":
                restaurant["menus"] = [m for m in restaurant["menus"] if m["name_kr"] != "육개장"]
        self.run_command("--date", "2026-09-29")
        self.assertFalse(MenuItem.objects.filter(raw_name="육개장").exists())

    def test_defaults_to_today_in_seoul(self, fetch_raw):
        fetch_raw.return_value = {"count": 0, "result": []}
        with mock.patch("django.utils.timezone.localdate", return_value=DAY):
            output = self.run_command()
        fetch_raw.assert_called_once_with(DAY)
        self.assertIn("오늘 운영 메뉴 없음", output)
        self.assertEqual(MenuItem.objects.count(), 0)
