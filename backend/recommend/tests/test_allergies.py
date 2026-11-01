"""Allergies are a hard rule: no session proposes a dish that may contain one."""
import datetime
import functools
from unittest import mock

from menus import services
from menus.allergens import ALLERGEN_VERSION
from menus.models import Food
from question_engines.llm import LLMEngine
from question_engines.llm.tests.helpers import FakeLLM, ask

from .helpers import DAY, post
from .test_edge_cases import SmallMenuTestCase


class AllergyTests(SmallMenuTestCase):
    def setUp(self):
        super().setUp()
        for name, tags in [("Beef noodles", ["beef", "wheat"]), ("Rice bowl", ["egg"])]:
            Food.objects.filter(name=name).update(allergens=tags, allergen_version=ALLERGEN_VERSION)
        # Chicken noodles has no tags yet.

    def served(self, *allergies):
        candidates, _, _ = services.get_catalog(datetime.date.fromisoformat(DAY), "LU", frozenset(allergies))
        return sorted(c["name"] for c in candidates)

    def test_only_dishes_known_to_be_free_of_every_allergy_are_served(self):
        self.assertEqual(self.served(), ["Beef noodles", "Chicken noodles", "Rice bowl"])
        self.assertEqual(self.served("egg"), ["Beef noodles"])
        self.assertEqual(self.served("milk"), ["Beef noodles", "Rice bowl"])
        self.assertEqual(self.served("egg", "wheat"), [])

    def test_tags_of_an_old_version_count_as_untagged(self):
        Food.objects.filter(name="Rice bowl").update(allergen_version="old")
        self.assertEqual(self.served("milk"), ["Beef noodles"])

    def test_the_session_counts_and_proposes_only_safe_dishes(self):
        state, url = self.start(allergies=["egg"])
        self.assertEqual(state["candidate_count"], 1)
        guess = self.call(url + "recommend-now/")
        self.assertEqual(guess["step"]["food"]["display_name"], "Beef noodles")
        self.assertEqual(self.call(url + "feedback/", {"guess_id": guess["step"]["guess_id"],
                                                       "accepted": False})["step"]["reason"],
                         "candidates_exhausted")

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
