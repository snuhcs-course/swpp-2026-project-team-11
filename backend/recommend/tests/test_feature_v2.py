# AI-generated: written with Codex (OpenAI) and reviewed by the team.
import datetime
import functools
import io
import json
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from menus import services
from menus.features import extractor
from menus.features.schema import FEATURE_KEYS
from menus.models import Food, MenuItem, Restaurant
from menus.tests.test_extract_features import FakeLLM
from question_engines.decision_tree.contracts import FEATURE_PRESENTATION_V2
from question_engines.decision_tree import DecisionTreeEngine
from question_engines.llm import LLMEngine
from question_engines.llm.tests.helpers import FakeLLM as FakeQuestionLLM, ask
from recommend import sessions
from .helpers import check_state, post

DAY = datetime.date(2026, 10, 13)


class V2SessionTests(TestCase):
    def setUp(self):
        self.hall = Restaurant.objects.create(code="test", name="Test hall")
        self.foods = []
        for is_set in (False, True):
            food = Food.objects.create(name="돈까스", is_set=is_set, is_food=True)
            MenuItem.objects.create(date=DAY, meal="LU", restaurant=self.hall,
                                    raw_name="돈까스와 우동" if is_set else "돈까스", food=food, price=6000)
            self.foods.append(food)
        with mock.patch.object(extractor, "api_key_available", return_value=True), \
                mock.patch.object(extractor, "build_llm", return_value=FakeLLM()):
            call_command("extract_features", "--date", str(DAY), stdout=io.StringIO())

    def test_every_v2_feature_has_explicit_question_metadata(self):
        self.assertEqual(set(FEATURE_PRESENTATION_V2), set(FEATURE_KEYS))
        schema = services.get_feature_schema("v2")
        self.assertTrue(all(row["question_en"].endswith("?") for row in schema))
        questions = {r["key"]: r["question_en"] for r in schema}
        self.assertNotIn("stir", questions["grilled"])
        self.assertNotEqual(questions["large_portion"], questions["filling"])
        self.assertNotEqual(questions["oily"], questions["greasy"])

    def test_v2_cannot_silently_run_without_std(self):
        rows = services.get_candidates(DAY, feature_version="v2")
        with self.assertRaisesMessage(ValueError, "v2 requires std"):
            DecisionTreeEngine(rows, services.get_feature_schema("v2"))

    def test_set_variants_stay_distinct_and_variety_is_asked(self):
        response = post(self.client, "/api/sessions/", {"date": str(DAY), "meal": "LU"})
        self.assertEqual(response.status_code, 201)
        state = response.json()
        check_state(self, state)
        self.assertEqual(state["candidate_count"], 2)
        self.assertEqual(state["step"]["question_id"], "q:meal_variety")
        session = sessions.get(state["session_id"])
        before = session.engine.probabilities[self.foods[1].pk]
        url = f"/api/sessions/{state['session_id']}/"
        after = post(self.client, url + "answer/", {
            "question_id": "q:meal_variety", "answer_id": "yes"}).json()
        check_state(self, after)
        self.assertGreater(session.engine.probabilities[self.foods[1].pk], before)
        guess = post(self.client, url + "recommend-now/").json()
        check_state(self, guess)
        self.assertEqual(guess["step"]["food"]["food_id"], self.foods[1].pk)
        self.assertTrue(guess["step"]["food"]["display_name"].endswith(" (세트)"))

    def test_version_selection_is_scoped_to_meal_and_never_mixed(self):
        legacy = Food.objects.create(name="Legacy", is_food=True, feature_version="v1")
        for meal in ("LU", "DN"):
            MenuItem.objects.create(date=DAY, meal=meal, restaurant=self.hall,
                                    raw_name="Legacy", food=legacy)
        rows, schema, version = services.get_catalog(DAY, "LU")
        self.assertEqual(version, "v2")
        self.assertEqual(len(schema), 33)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(set(row["feature_std"]) == set(FEATURE_KEYS) for row in rows))
        rows, schema, version = services.get_catalog(DAY, "DN")
        self.assertEqual(version, "v1")
        self.assertEqual(len(schema), 23)
        self.assertEqual([r["food_id"] for r in rows], [legacy.pk])
        self.assertNotIn("feature_std", rows[0])

    def test_v2_demo_uses_same_catalog_and_replay_version(self):
        out = io.StringIO()
        call_command("demo_decision_tree", "--date", str(DAY), "--smoke", stdout=out)
        result = json.loads(out.getvalue())
        self.assertEqual(result["final_step"]["type"], "recommendation")
        self.assertIn(result["final_step"]["food"]["food_id"], [f.pk for f in self.foods])

    def test_llm_engine_receives_the_same_v2_names_without_feature_details(self):
        llm = FakeQuestionLLM(ask("Do you feel like fried food?", "돈까스"))
        with mock.patch("recommend.sessions.LLMEngine", functools.partial(LLMEngine, llm=llm)):
            response = post(self.client, "/api/sessions/",
                            {"date": str(DAY), "meal": "LU", "engine": "llm"})
        self.assertEqual(response.status_code, 201)
        check_state(self, response.json())
        self.assertEqual(response.json()["candidate_count"], 2)
        self.assertEqual(set(llm.offered_foods()), {"돈까스", "돈까스 (세트)"})
        self.assertNotIn("feature_std", llm.prompt())
