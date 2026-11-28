"""price_level: only dishes priced inside the picked band reach the engine, in sessions and rooms."""
import json
from unittest import mock

from django.test import TestCase

from menus.allergens import ALLERGEN_VERSION
from menus.models import Restaurant, StoreMenu
from menus.personal import offers
from recommend import sessions
from recommend.prices import PRICE_BANDS, within_price

from .helpers import DAY, add_food, check_state, post

# (dish, restaurant, price, features)
MENUS = [
    ("Rice bowl", "North hall", 5000, {"spicy": .1, "rice": .9}),
    ("Kimbap", "North hall", 7999, {"spicy": .2, "rice": .8}),
    ("Pork cutlet", "South hall", 8000, {"fried": .9, "pork": .9}),
    ("Spicy stew", "South hall", 14999, {"spicy": .9, "soupy": .9}),
    ("Steak", "West hall", 15000, {"beef": .9, "grilled": .9}),
    ("Chef's special", "West hall", None, {"spicy": .5}),
]


def priced(*prices):
    return [{"food_id": i, "offers": [{"restaurant": "Hall", "price": price}]} for i, price in enumerate(prices)]


class WithinPriceTests(TestCase):
    def test_bands_include_their_lower_bound_and_exclude_their_upper_bound(self):
        prices = [0, 7999, 8000, 14999, 15000, 90000]
        kept = {level: [c["offers"][0]["price"] for c in within_price(priced(*prices), level)] for level in PRICE_BANDS}
        self.assertEqual(kept, {1: [0, 7999], 2: [8000, 14999], 3: [15000, 90000]})

    def test_unknown_prices_and_out_of_band_offers_are_dropped(self):
        candidate = {"food_id": 1, "offers": [{"restaurant": "A", "price": 6000}, {"restaurant": "B", "price": 9000},
                                              {"restaurant": "C", "price": None}]}
        kept = within_price([candidate, *priced(None)], 2)
        self.assertEqual([offer["restaurant"] for c in kept for offer in c["offers"]], ["B"])


class PriceFilterApiTests(TestCase):
    def setUp(self):
        for name, restaurant, price, features in MENUS:
            add_food(name, restaurant=restaurant, price=price, **features)

    def start(self, **body):
        response = post(self.client, "/api/sessions/", {"date": DAY, "meal": "LU", **body})
        self.assertEqual(response.status_code, 201, response.content)
        check_state(self, response.json())
        return response.json()

    def test_every_proposal_and_find_another_stays_in_the_band(self):
        state = self.start(price_level=2)
        self.assertEqual(state["candidate_count"], 2)
        path = f"/api/sessions/{state['session_id']}"
        state = post(self.client, f"{path}/recommend-now/").json()
        seen = []
        while state["step"]["type"] == "guess":
            food = state["step"]["food"]
            seen.append(food["name"])
            self.assertTrue(all(8000 <= offer["price"] < 15000 for offer in food["offers"]), food)
            state = post(self.client, f"{path}/feedback/", {"guess_id": state["step"]["guess_id"], "accepted": False}).json()
        self.assertCountEqual(seen, ["Pork cutlet", "Spicy stew"])
        self.assertEqual(state["step"]["type"], "unavailable")

    def test_the_restaurant_menu_lists_only_dishes_in_the_band(self):
        state = self.start(price_level=1)
        menu = self.client.get(f"/api/sessions/{state['session_id']}/menu/", {"restaurant": "North hall"}).json()
        self.assertEqual([dish["display_name"] for dish in menu["dishes"]], ["Kimbap", "Rice bowl"])
        self.assertEqual(sessions.get(state["session_id"]).menus.keys(), {"North hall"})

    def test_any_price_keeps_every_dish_including_unknown_prices(self):
        self.assertEqual(self.start()["candidate_count"], 6)
        self.assertEqual(self.start(price_level=None)["candidate_count"], 6)
        self.assertEqual(self.start(price_level=3)["candidate_count"], 1)

    def test_a_level_outside_one_to_three_is_rejected(self):
        for level in (0, 4, "2", True, 2.0):
            response = post(self.client, "/api/sessions/", {"date": DAY, "price_level": level})
            self.assertEqual(response.status_code, 400, level)
            self.assertIn("price_level", response.json()["error"]["message"])

    def test_a_room_proposes_only_restaurant_dishes_in_the_band(self):
        response = post(self.client, "/api/rooms/", {"name": "Jimin", "date": DAY, "meal": "LU", "price_level": 1})
        self.assertEqual(response.status_code, 201, response.content)
        code, host = response.json()["state"]["code"], response.json()["token"]
        post(self.client, "/api/rooms/join/", {"code": code, "name": "Seoyeon"})
        reply = self.client.post(f"/api/rooms/{code}/start/", data=json.dumps({}),
                                 content_type="application/json", HTTP_X_MEMBER_TOKEN=host)
        self.assertEqual(reply.status_code, 200, reply.content)
        # Only North hall has a dish in the band, so the room decides without a question.
        picks = reply.json()["picks"]
        self.assertEqual([pick["restaurant"] for pick in picks], ["North hall"])
        dishes = [m["food"] for m in picks[0]["menus"]] + picks[0]["others"]
        self.assertTrue({dish["display_name"] for dish in dishes} <= {"Kimbap", "Rice bowl"}, dishes)
        rejected = post(self.client, "/api/rooms/", {"name": "Jimin", "price_level": 0})
        self.assertEqual(rejected.status_code, 400)


class MergedOfferPriceTests(TestCase):
    """One merged store menu sold at several prices: only its offers in the band remain,
    for a session and for every member's allergy-filtered load in a room."""

    def setUp(self):
        patch = mock.patch.object(offers, "resolve", return_value="food_009")  # 김치찌개
        patch.start()
        self.addCleanup(patch.stop)
        lines = [("가게 A", 6000, []), ("가게 B", 9000, ["pork"]), ("가게 C", 12000, []), ("가게 D", 16000, [])]
        for i, (name, price, tags) in enumerate(lines):
            place = Restaurant.objects.create(code=f"MA000{i}", name=name, source="naver", lat=37.48 + i / 1000, lng=126.95)
            StoreMenu.objects.create(restaurant=place, raw_name="김치찌개", description=f"{name} 김치찌개",
                                     price=price, allergens=tags, allergen_version=ALLERGEN_VERSION)

    def test_a_session_keeps_only_the_offers_in_the_band(self):
        state = post(self.client, "/api/sessions/", {"area": "snu_station", "price_level": 2}).json()
        self.assertEqual(state["candidate_count"], 1)
        guess = post(self.client, f"/api/sessions/{state['session_id']}/recommend-now/").json()["step"]
        self.assertCountEqual([(o["restaurant"], o["price"]) for o in guess["food"]["offers"]],
                              [("가게 B", 9000), ("가게 C", 12000)])

    def test_an_allergic_member_in_a_room_sees_only_safe_offers_in_the_band(self):
        response = post(self.client, "/api/rooms/", {"name": "Jimin", "area": "snu_station", "price_level": 2})
        code, host = response.json()["state"]["code"], response.json()["token"]
        post(self.client, "/api/rooms/join/", {"code": code, "name": "Seoyeon", "allergies": ["pork"]})
        done = self.client.post(f"/api/rooms/{code}/start/", content_type="application/json",
                                HTTP_X_MEMBER_TOKEN=host).json()  # one menu: nothing to ask
        self.assertEqual([pick["restaurant"] for pick in done["picks"]], ["가게 C"])
