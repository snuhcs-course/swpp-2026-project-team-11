"""Allergies are a hard rule: no session proposes a dish that may contain one."""
import datetime
import functools
from unittest import mock

from menus import services
from menus.allergens import ALLERGEN_VERSION
from menus.models import Food, MenuItem, Restaurant
from menus.menu_registry import register_menu_ids
from question_engines.llm import LLMEngine
from question_engines.llm.tests.helpers import FakeLLM, ask

from .helpers import DAY, add_food, post
from .test_edge_cases import SmallMenuTestCase


class AllergyTests(SmallMenuTestCase):
    def setUp(self):
        super().setUp()
        for name, tags in [("Beef noodles", ["beef", "wheat"]), ("Rice bowl", ["egg"])]:
            Food.objects.filter(name=name).update(allergens=tags, allergen_version=ALLERGEN_VERSION)
        # Chicken noodles has no tags yet.

    def catalog(self, *allergies):
        return services.get_catalog(datetime.date.fromisoformat(DAY), "LU", frozenset(allergies))

    def served(self, *allergies):
        return sorted(c["name"] for c in self.catalog(*allergies)[0])

    def test_only_dishes_known_to_be_free_of_every_allergy_are_served(self):
        self.assertEqual(self.served(), ["Beef noodles", "Chicken noodles", "Rice bowl"])
        self.assertEqual(self.served("egg"), ["Beef noodles"])
        self.assertEqual(self.served("milk"), ["Beef noodles", "Rice bowl"])
        self.assertEqual(self.served("egg", "wheat"), [])

    def test_tags_of_an_old_version_count_as_untagged(self):
        Food.objects.filter(name="Rice bowl").update(allergen_version="old")
        self.assertEqual(self.served("milk"), ["Beef noodles"])

    def test_a_combo_line_is_left_out_when_any_of_its_dishes_is_unsafe(self):
        for name, tags in [("Pork cutlet", ["pork"]), ("Curry udon", ["wheat"])]:
            add_food(name, price=7000)
            Food.objects.filter(name=name).update(allergens=tags, allergen_version=ALLERGEN_VERSION)
        MenuItem.objects.filter(food__name__in=["Pork cutlet", "Curry udon"]).update(raw_name="Pork cutlet curry udon")
        register_menu_ids("cafeteria", date=DAY)
        self.assertIn("Pork cutlet curry udon", self.served("egg"))
        self.assertNotIn("Pork cutlet curry udon", self.served("pork"))

        Food.objects.filter(name="Pork cutlet").update(allergen_version="")
        self.assertNotIn("Pork cutlet curry udon", self.served("egg"))  # an untagged dish in the line

        add_food("Curry udon", restaurant="Other hall", price=4500)
        [udon] = [c for c in self.catalog("egg")[0] if c["name"] == "Curry udon"]
        self.assertEqual([(o["restaurant"], o["price"]) for o in udon["offers"]], [("Other hall", 4500)])

    def test_the_session_counts_and_proposes_only_safe_dishes(self):
        state, url = self.start(allergies=["egg"])
        self.assertEqual(state["candidate_count"], 1)
        guess = self.call(url + "recommend-now/")
        self.assertEqual(guess["step"]["food"]["display_name"], "Beef noodles")
        self.assertEqual(self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"],
                                                       "accepted": False})["step"]["reason"],
                         "candidates_exhausted")

    def test_a_location_still_gives_distances_with_allergies(self):
        Restaurant.objects.filter(code="Test hall").update(lat=37.4593, lng=126.9506)
        state, url = self.start(allergies=["egg"], location={"lat": 37.4593, "lng": 126.9506})
        self.assertEqual(state["candidate_count"], 1)
        offers = self.call(url + "recommend-now/")["step"]["food"]["offers"]
        self.assertEqual([offer["distance_m"] for offer in offers], [0])

    def test_no_safe_dish_is_an_empty_menu(self):
        state, _ = self.start(allergies=["egg", "wheat"])
        self.assertEqual((state["candidate_count"], state["step"]["reason"]), (0, "empty_candidates"))

    def test_the_llm_engine_sees_only_safe_dishes(self):
        llm = FakeLLM(ask("Do you feel like noodles?", "Beef noodles"))
        with mock.patch("recommend.sessions.LLMEngine", functools.partial(LLMEngine, llm=llm)):
            state, _ = self.start(engine="llm", allergies=["milk"])
        self.assertEqual(state["candidate_count"], 2)
        prompt = llm.calls[0][-1].content
        self.assertIn("Rice bowl", prompt)
        self.assertNotIn("Chicken noodles", prompt)

    def test_empty_or_null_allergies_change_nothing(self):
        self.assertEqual(self.start(allergies=[])[0]["candidate_count"], 3)
        self.assertEqual(self.start(allergies=None)[0]["candidate_count"], 3)

    def test_allergies_must_be_a_list_of_known_keys(self):
        for allergies in ("egg", ["nuts"], [["egg"]], [{"key": "egg"}], {"egg": True}, 1):
            response = post(self.client, "/api/sessions/", {"date": DAY, "allergies": allergies})
            self.assertEqual(response.status_code, 400, allergies)
            self.assertEqual(response.json()["error"]["code"], "invalid_request")
