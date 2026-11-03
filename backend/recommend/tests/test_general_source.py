"""source=general: sessions over the restaurants near the stations (menus.StoreMenu)."""
import datetime
import zoneinfo
from unittest import mock

from django.test import TestCase, override_settings

from menus import services
from menus.allergens import ALLERGEN_VERSION
from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION
from menus.models import Food, MenuItem, Restaurant, StoreMenu

from .helpers import check_state, post

SEOUL_NAT_UNIV_STATION = {"lat": 37.481247, "lng": 126.952739}


def tagged_food(name, spicy):
    """A v2-tagged dish with no allergens; spicy varies so the decision tree has something to ask."""
    features = {key: 0.5 for key in FEATURE_KEYS} | {"spicy": spicy, "meal_variety": 0.0}
    return Food.objects.create(name=name, is_food=True, features=features,
                               feature_std={key: 0.1 for key in FEATURE_KEYS} | {"meal_variety": 0.0},
                               feature_version=FEATURE_VERSION, allergen_version=ALLERGEN_VERSION)


class GeneralSourceTests(TestCase):
    def setUp(self):
        hongkong = Restaurant.objects.create(code="MA0001", name="홍콩반점 낙성대점", source="naver",
                                             lat=37.47692, lng=126.96361)
        beijing = Restaurant.objects.create(code="MA0002", name="북경 서울대입구점", source="naver",
                                            lat=37.48101, lng=126.95302)
        jjajang, jjamppong, kimchi = tagged_food("짜장면", 0.1), tagged_food("짬뽕", 0.9), tagged_food("김치찌개", 0.6)
        # Allergens are tagged per menu line: the 김치찌개 set also serves 계란말이.
        for restaurant, food, line, price, tags in [
                (hongkong, jjajang, "짜장면", 7000, ["wheat"]), (beijing, jjajang, "짜장면", 6500, ["wheat"]),
                (hongkong, jjamppong, "짬뽕", 8000, ["wheat"]), (beijing, kimchi, "김치찌개", 8000, []),
                (hongkong, kimchi, "김치찌개+계란말이", 11000, ["egg"])]:
            StoreMenu.objects.create(restaurant=restaurant, raw_name=line, food=food, price=price,
                                     allergens=tags, allergen_version=ALLERGEN_VERSION)
        hall = Restaurant.objects.create(code="학생회관식당", name="학생회관식당")
        MenuItem.objects.create(date=datetime.date(2026, 11, 2), meal="LU", restaurant=hall,
                                raw_name="돈까스", food=tagged_food("돈까스", 0.2))

    def start(self, **body):
        response = post(self.client, "/api/sessions/", {"source": "general"} | body)
        self.assertEqual(response.status_code, 201, response.content)
        state = response.json()
        check_state(self, state)
        return state

    def proposal(self, state):
        state = post(self.client, f"/api/sessions/{state['session_id']}/recommend-now/").json()
        check_state(self, state)
        return state["step"]["food"]

    def test_serves_the_restaurant_dishes_with_their_offers(self):
        state = self.start(meal="DN")
        self.assertEqual(state["candidate_count"], 4)  # four real menus, not the cafeteria's 돈까스
        self.assertEqual(state["engine"], "decision_tree")
        food = self.proposal(state)
        self.assertIn(food["name"], {"짜장면", "짬뽕", "김치찌개"})
        self.assertTrue(all(offer["meal"] == "DN" for offer in food["offers"]))
        StoreMenu.objects.create(restaurant=Restaurant.objects.get(code="MA0001"), raw_name="옛날짜장",
                                 food=Food.objects.get(name="짜장면"), price=7000)  # same offer, listed once
        candidates, _ = services.get_store_catalog("LU")
        jjajang = next(c for c in candidates if c["name"] == "짜장면")
        self.assertEqual([(o["restaurant"], o["price"], o["meal"]) for o in jjajang["offers"]],
                         [("북경 서울대입구점", 6500, "LU"), ("홍콩반점 낙성대점", 7000, "LU")])

    def test_without_a_meal_offers_carry_the_current_one(self):
        with mock.patch.object(services, "current_meal", return_value="DN"):
            food = self.proposal(self.start())
        self.assertTrue(all(offer["meal"] == "DN" for offer in food["offers"]))
        seoul = zoneinfo.ZoneInfo("Asia/Seoul")
        for hour, minute, meal in [(9, 59, "BR"), (10, 0, "LU"), (15, 59, "LU"), (16, 0, "DN")]:
            self.assertEqual(services.current_meal(datetime.datetime(2026, 11, 2, hour, minute, tzinfo=seoul)), meal)

    @override_settings(RECOMMEND_STORE_MENU_CACHE_S=300)
    def test_the_menus_are_read_once_per_cache_period(self):
        services._store_menus = None
        self.addCleanup(setattr, services, "_store_menus", None)
        services.get_store_catalog("LU")
        with mock.patch.object(StoreMenu.objects, "order_by", side_effect=AssertionError("Source cache miss")):
            self.assertEqual(len(services.get_store_catalog("LU")[0]), 4)

    def test_location_adds_distances(self):
        food = self.proposal(self.start(location=SEOUL_NAT_UNIV_STATION))
        self.assertTrue(all(isinstance(offer["distance_m"], int) for offer in food["offers"]))

    def test_allergies_leave_out_unsafe_dishes(self):
        self.assertEqual(self.start(allergies=["wheat"])["candidate_count"], 2)

    def test_a_safe_dish_is_left_out_where_its_set_serves_an_allergen(self):
        def kimchi_offers(*allergies):
            candidates, _ = services.get_store_catalog(allergies=frozenset(allergies))
            return [o["restaurant"] for c in candidates if c["name"].startswith("김치찌개") for o in c["offers"]]

        self.assertEqual(kimchi_offers(), ["북경 서울대입구점", "홍콩반점 낙성대점"])
        self.assertEqual(kimchi_offers("egg"), ["북경 서울대입구점"])  # the dish itself has no egg

    def test_an_untagged_line_is_left_out_only_with_allergies(self):
        StoreMenu.objects.filter(raw_name="김치찌개").update(allergen_version="")
        self.assertEqual(self.start()["candidate_count"], 4)
        self.assertEqual(self.start(allergies=["egg"])["candidate_count"], 2)

    def test_dishes_without_v2_features_are_not_served(self):
        Food.objects.filter(name="김치찌개").update(feature_version="")
        self.assertEqual(sorted(c["name"] for c in services.get_store_catalog()[0]), ["짜장면", "짬뽕"])

    @override_settings(RECOMMEND_DEFAULT_ENGINE="llm")
    def test_runs_the_decision_tree_whatever_the_default_engine(self):
        self.assertEqual(self.start()["engine"], "decision_tree")

    def test_the_llm_engine_and_unknown_sources_are_rejected(self):
        for body in ({"source": "general", "engine": "llm"}, {"source": "delivery"}):
            response = post(self.client, "/api/sessions/", body)
            self.assertEqual(response.status_code, 400, body)
            self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_without_a_source_the_session_is_the_cafeteria_menu(self):
        response = post(self.client, "/api/sessions/", {"date": "2026-11-02", "meal": "LU"})
        self.assertEqual(response.json()["candidate_count"], 1)
