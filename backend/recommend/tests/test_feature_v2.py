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
from question_engines.decision_tree.contracts import FEATURE_PRESENTATION
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
        self.assertEqual(set(FEATURE_PRESENTATION), set(FEATURE_KEYS))
        schema = services.get_feature_schema()
        self.assertTrue(all(row["question_en"].endswith("?") for row in schema))
        questions = {r["key"]: r["question_en"] for r in schema}
        self.assertNotIn("stir", questions["grilled"])
        self.assertNotEqual(questions["large_portion"], questions["filling"])
        self.assertNotEqual(questions["oily"], questions["greasy"])

    def test_dt_cannot_silently_run_without_std(self):
        rows = [{key: value for key, value in row.items() if key != "feature_std"}
                for row in services.get_candidates(DAY)]
        with self.assertRaisesMessage(ValueError, "the feature schema requires std"):
            DecisionTreeEngine(rows, services.get_feature_schema())

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

    def test_dishes_without_current_features_are_left_out_with_a_warning(self):
        untagged = Food.objects.create(name="Untagged", is_food=True, feature_version="v1",
                                       features={"spicy": 0.5})
        MenuItem.objects.create(date=DAY, meal="LU", restaurant=self.hall, raw_name="Untagged", food=untagged)
        with self.assertLogs("menus.services", level="WARNING") as cm:
            rows, schema = services.get_catalog(DAY, "LU")
        self.assertEqual(len(schema), 33)
        self.assertEqual([r["food_id"] for r in rows], [f.pk for f in self.foods])
        self.assertTrue(all(set(row["feature_std"]) == set(FEATURE_KEYS) for row in rows))
        self.assertIn("1 dishes without v2 features are not served", "\n".join(cm.output))

    def test_retagging_on_a_later_date_leaves_other_days_dishes_untagged(self):
        old_day = datetime.date(2026, 9, 29)
        later_day = datetime.date(2026, 10, 20)
        old_foods = [
            Food.objects.create(name=name, is_food=True, feature_version="v1",
                                features={"spicy": 0.5})
            for name in ("짬뽕", "짜장면", "볶음밥")
        ]
        for food in old_foods:
            MenuItem.objects.create(date=old_day, meal="LU", restaurant=self.hall,
                                    raw_name=food.name, food=food, price=5000)
        MenuItem.objects.create(date=later_day, meal="LU", restaurant=self.hall,
                                raw_name="짬뽕", food=old_foods[0], price=6000)
        with mock.patch.object(extractor, "api_key_available", return_value=True), \
                mock.patch.object(extractor, "build_llm", return_value=FakeLLM()):
            call_command("extract_features", "--date", str(later_day), stdout=io.StringIO())
        with self.assertLogs("menus.services", level="WARNING") as cm:
            rows, _ = services.get_catalog(old_day, "LU")
        self.assertEqual({r["name"] for r in rows}, {"짬뽕"})
        self.assertIn("2 dishes without v2 features", "\n".join(cm.output))

    def test_dt_policy_setting_and_diagnostics_expose_version_and_counts(self):
        session = sessions.create(DAY, "LU", "decision_tree")
        diag = session.engine.diagnostics()
        self.assertEqual(diag["policy"], "preference")
        self.assertEqual(diag["feature_version"], "v2")
        self.assertEqual(diag["candidate_count"], 2)
        with self.settings(RECOMMEND_DT_POLICY="greedy"):
            greedy_session = sessions.create(DAY, "LU", "decision_tree")
        self.assertEqual(greedy_session.engine.config.policy, "greedy")
        self.assertEqual(greedy_session.engine.diagnostics()["policy"], "greedy")

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
