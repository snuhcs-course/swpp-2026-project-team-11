import io
import json
import pathlib
import tempfile
from unittest import mock

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from menus.management.commands import fetch_naver_menus
from menus.sources import naver
from menus.tests.test_stores_source import store_row, write_stores


def page(state: dict) -> str:
    """A page shaped like Naver Place's: the state is assigned in an inline script."""
    return ("<html><script>window.__PLACE_STATE__ = {};\n"
            f"window.__APOLLO_STATE__ = {json.dumps(state, ensure_ascii=False)};\n"
            "window.__OTHER__ = {};</script></html>")


def place_item(place_id, name, **fields):
    return {"__typename": "PlaceListBusinessesItem", "id": place_id, "name": name,
            "category": "우동,소바", "x": "126.9516050", "y": "37.4820226",
            "roadAddress": "봉천로 466 101호", **fields}


def menu_item(item_id, name, price_text="9,000원", **fields):
    return {"__typename": "PlaceMenuItem", "id": item_id, "name": name,
            "price": {"__typename": "PlaceMenuPrice", "priceType": "fixed", "displayText": price_text},
            "description": "", "isSetMenu": False, **fields}


LIST_STATE = {
    "ROOT_QUERY": {"__typename": "Query"},
    "PlaceListBusinessesItem:1:1": place_item("1", "코시 서울대입구점"),
    "RestaurantAdSummary:9": {"__typename": "RestaurantAdSummary", "id": "9", "name": "광고"},
    "PlaceListBusinessesItem:2:2": place_item("2", "샤로수길 국밥", category="국밥", x=None, y=None),
    "PlaceListBusinessesItem:1:other": place_item("1", "코시 서울대입구점"),
    "PlaceListBusinessesItem:3:3": place_item("3", "봉천동 중국집", x="126.95", y="37.46"),
    "PlaceListBusinessesItem:4:4": place_item("4", "낙성대 분식", x="126.9640", y="37.4772"),
}
MENU_STATE = {
    "PlaceMenuItem:a": menu_item("a", "사누키면 붓카케우동", description="간장 냉우동"),
    "PlaceMenuItem:b": menu_item("b", "붓카케우동정식", "14,000원", isSetMenu=True),
    "PlaceMenuItem:c": menu_item("c", "모둠회", "변동"),
    "PlaceMenuItem:d": menu_item("d", "음료", price=None),
    "PlaceMenuCategory:recommend": {"__typename": "PlaceMenuCategory", "itemIds": ["a"]},
}


class ApolloStateTests(SimpleTestCase):
    def test_reads_the_state_up_to_its_end(self):
        state = {"PlaceMenuItem:a": menu_item("a", "우동", description="};\n 끝")}
        self.assertEqual(naver.apollo_state(page(state)), state)

    def test_raises_when_the_page_has_no_state(self):
        with self.assertRaises(ValueError):
            naver.apollo_state("<html>429 Too Many Requests</html>")


class ParseTests(SimpleTestCase):
    def test_places_once_each_without_ads(self):
        places = naver.parse_places(LIST_STATE)
        self.assertEqual([p.id for p in places], ["1", "2", "3", "4"])
        self.assertEqual(places[0], naver.Place(
            id="1", name="코시 서울대입구점", category="우동,소바",
            lat=37.4820226, lng=126.951605, road_address="봉천로 466 101호"))
        self.assertEqual((places[1].lat, places[1].lng), (None, None))

    def test_menus(self):
        menus = naver.parse_menus("1", MENU_STATE)
        self.assertEqual([(m.name, m.price, m.is_set) for m in menus], [
            ("사누키면 붓카케우동", 9000, False), ("붓카케우동정식", 14000, True),
            ("모둠회", None, False), ("음료", None, False)])
        self.assertEqual(menus[0].description, "간장 냉우동")
        self.assertTrue(all(m.place_id == "1" for m in menus))

    def test_price(self):
        self.assertEqual(naver.parse_price("12,500원"), 12500)
        for text in ("변동", "9,000~12,000원", "", None):
            self.assertIsNone(naver.parse_price(text))


def html_response(state: dict) -> requests.Response:
    """A UTF-8 page whose Content-Type names no charset, as Naver's do."""
    response = requests.Response()
    response.status_code = 200
    response._content = page(state).encode("utf-8")
    response.headers["Content-Type"] = "text/html"
    response.encoding = requests.utils.get_encoding_from_headers(response.headers)
    return response


class FetchTests(SimpleTestCase):
    def test_list_request_sends_query_and_coordinates(self):
        with mock.patch.object(naver.requests, "get", return_value=html_response(LIST_STATE)) as get:
            places = naver.search_places("서울대입구역 맛집", 37.4812, 126.9526)
        self.assertEqual(places[0].name, "코시 서울대입구점")
        self.assertEqual(get.call_args.args[0], "https://m.place.naver.com/restaurant/list")
        self.assertEqual(get.call_args.kwargs["params"],
                         {"query": "서울대입구역 맛집", "x": 126.9526, "y": 37.4812})

    def test_menu_page_is_read_as_utf8(self):
        with mock.patch.object(naver.requests, "get", return_value=html_response(MENU_STATE)):
            menu = naver.fetch_menus("1")[1]
        self.assertEqual((menu.name, menu.price), ("붓카케우동정식", 14000))


def place(place_id, name, lat, lng):
    return naver.Place(id=place_id, name=name, category="", lat=lat, lng=lng, road_address="")


class MatchTests(SimpleTestCase):
    def test_nearest_place_whose_name_contains_the_shop_name(self):
        places = [place("far", "코시 본점", 37.4830, 126.9516),  # about 110 m
                  place("near", "코시 서울대입구점", 37.4821, 126.9516),
                  place("other", "우동집", 37.4820, 126.9516),
                  place("unknown", "코시", None, None)]
        self.assertEqual(naver.match_place("코시", 37.4820, 126.9516, places).id, "near")

    def test_name_is_compared_without_spaces_case_or_symbols(self):
        self.assertIsNotNone(naver.match_place("BBQ(서울대점)", 37.48, 126.95,
                                               [place("1", "bbq 서울대점", 37.48, 126.95)]))

    def test_none_when_the_only_match_is_too_far(self):
        self.assertIsNone(naver.match_place("코시", 37.4820, 126.9516,
                                            [place("1", "코시", 37.4840, 126.9516)]))  # about 220 m

    def test_find_place_searches_name_and_branch_near_the_shop(self):
        with mock.patch.object(naver, "fetch_list_html", return_value=page(LIST_STATE)) as list_html:
            found = naver.find_place("코시", "서울대입구점", 37.4820226, 126.951605)
        self.assertEqual(found.id, "1")
        list_html.assert_called_once_with("코시 서울대입구점", 37.4820226, 126.951605)


SHOPS = [
    store_row("1", "코시", "서울대입구점", 37.4820226, 126.951605),
    store_row("2", "코시", "", 37.4820226, 126.951605),  # the same shop listed twice
    store_row("3", "낙성대 분식", "", 37.4772, 126.9640),
    store_row("4", "없는집", "", 37.4815, 126.9530),
    store_row("5", "스타벅스", "", 37.4815, 126.9530, sub_code="I21201"),  # café
    store_row("6", "봉천동 중국집", "", 37.46, 126.95),  # outside both radii
]


@mock.patch.object(fetch_naver_menus.time, "sleep")
class CommandTests(SimpleTestCase):
    def run_command(self, list_html=(page(LIST_STATE),) * 4, menu_html=(page(MENU_STATE),) * 2):
        tmp = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        write_stores(tmp / "stores.csv", SHOPS)
        output = tmp / "naver.json"
        out = io.StringIO()
        self.list_html = self.enterContext(
            mock.patch.object(naver, "fetch_list_html", side_effect=list(list_html)))
        self.menu_html = self.enterContext(
            mock.patch.object(naver, "fetch_menu_html", side_effect=list(menu_html)))
        try:
            call_command("fetch_naver_menus", "--stores", str(tmp / "stores.csv"),
                         "--output", str(output), stdout=out)
        finally:
            self.out = out.getvalue()
            self.saved = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None

    def test_saves_each_shop_in_radius_with_its_naver_menu(self, sleep):
        self.run_command()
        stores = self.saved["stores"]
        self.assertEqual([(s["id"], s["status"]) for s in stores], [
            ("1", "matched"), ("2", "matched"), ("3", "matched"), ("4", "not_found")])
        self.assertEqual(self.saved["counts"],
                         {"in_radius": 4, "matched": 3, "not_found": 1, "failed": 0})
        self.assertEqual(self.saved["areas"]["서울대입구역"]["radius_m"], 600)
        self.assertEqual(self.saved["stores_file"], "stores.csv")

        koshi = stores[0]
        self.assertEqual(list(koshi["distances_m"]), ["서울대입구역"])
        self.assertEqual((koshi["name"], koshi["branch"], koshi["subcategory"]),
                         ("코시", "서울대입구점", "국/탕/찌개류"))
        self.assertEqual((koshi["naver"]["id"], koshi["naver"]["distance_m"]), ("1", 0))
        self.assertEqual(koshi["menus"][1], {
            "name": "붓카케우동정식", "price": 14000, "description": "", "is_set": True})
        self.assertEqual(stores[1]["menus"], koshi["menus"])
        self.assertEqual(list(stores[2]["distances_m"]), ["낙성대역"])
        self.assertEqual((stores[3]["naver"], stores[3]["menus"]), (None, []))

        self.assertEqual([c.args[0] for c in self.menu_html.call_args_list], ["1", "4"])
        self.assertEqual(sleep.call_count, 4 + 2)
        self.assertIn("음식점 4/4 / 찾음 3 / 못 찾음 1 / 실패 0 / 메뉴 12", self.out)

    def test_a_failed_shop_is_kept_as_failed(self, sleep):
        self.run_command(list_html=[requests.HTTPError("429")] + [page(LIST_STATE)] * 3)
        self.assertEqual([s["status"] for s in self.saved["stores"]],
                         ["failed", "matched", "matched", "not_found"])
        self.assertIn("코시 서울대입구점 (1): 실패: 429", self.out)

    @mock.patch.object(fetch_naver_menus, "MAX_CONSECUTIVE_FAILURES", 2)
    def test_stops_after_failures_in_a_row_and_keeps_what_it_has(self, sleep):
        with self.assertRaisesMessage(CommandError, "2번 연속 실패"):
            self.run_command(list_html=[requests.HTTPError("429")] * 4)
        self.assertEqual(len(self.saved["stores"]), 2)
        self.assertEqual(self.saved["counts"],
                         {"in_radius": 4, "matched": 0, "not_found": 0, "failed": 2})
