from unittest.mock import patch

from django.test import TestCase, override_settings

from menus.features.schema import FEATURE_KEYS
from menus.models import Food, Restaurant, StoreMenu
from question_engines.rl import RLEngine
from question_engines.rl.policy import FEATURE_KEYS as RL_KEYS, prepare
from .helpers import DAY, add_food, check_state, post


class RLSessions(TestCase):
    def test_general_rejection_undo_and_confirm_preserve_offers(self):
        store = Restaurant.objects.create(code="R1", name="Test restaurant", source="naver", lat=37.48, lng=126.95)
        for i in range(3):
            features = {k: float((j+i)%3 == 0) for j,k in enumerate(FEATURE_KEYS)}
            f = Food.objects.create(name=f"Test {i}", is_food=True, feature_version="v2",
                                    features=features, feature_std=dict.fromkeys(FEATURE_KEYS, 0.))
            StoreMenu.objects.create(food=f, restaurant=store, raw_name=f.name, price=7000+i)
        response = post(self.client, "/api/sessions/", {"source":"general", "engine":"rl", "meal":"LU", "language":"ko"})
        self.assertEqual(response.status_code, 201)
        state = response.json()
        self.assertEqual(state["engine"], "rl")
        url = "/api/sessions/"+state["session_id"]+"/"
        def action(name, body=None):
            response = post(self.client, url+name+"/", body)
            self.assertEqual(response.status_code, 200)
            value = response.json()
            check_state(self, value)
            return value["step"]
        question = state["step"]
        self.assertEqual(question["type"], "question")
        self.assertRegex(question["text"], "[가-힣]")
        self.assertEqual(question["options"][0]["label"], "좋아요")
        action("answer", {"question_id": question["question_id"], "answer_id": "yes"})
        first = action("recommend-now")
        self.assertEqual(first["text"], "이 메뉴가 당기나요?")
        with patch("recommend.reasons.default_llm", return_value=None):
            reason = self.client.get(url + "reason/")
        self.assertEqual(reason.status_code, 200)
        self.assertEqual(reason.json()["source"], "template")
        self.assertIn(first["food"]["display_name"], reason.json()["reason"])
        self.assertIn("골랐어요", reason.json()["reason"])
        original = first["food"]
        self.assertEqual(original["offers"][0]["restaurant"], store.name)
        self.assertEqual(original["offers"][0]["lat"], store.lat)
        decline = {"guess_id":first["guess_id"], "accepted":False}
        action("feedback", decline)
        self.assertEqual(action("undo"), first)
        action("feedback", decline)
        second = action("recommend-now")
        self.assertNotEqual(second["food"]["food_id"], original["food_id"])
        self.assertEqual(action("feedback", {"guess_id":second["guess_id"], "accepted":True})["food"], second["food"])
        self.assertEqual(action("undo"), second)

    @override_settings(RECOMMEND_DEFAULT_ENGINE="rl")
    def test_cafeteria_default_serves_only_dishes_with_current_features(self):
        empty = post(self.client, "/api/sessions/", {"date":DAY}).json()
        self.assertEqual(empty["engine"], "rl")
        self.assertEqual(empty["step"]["reason"], "empty_candidates")
        food = add_food("Daily menu")
        add_food("Untagged dish A")
        add_food("Untagged dish B")
        Food.objects.filter(name__startswith="Untagged").update(feature_version="v1")
        state = post(self.client, "/api/sessions/", {"date":DAY, "meal":"LU"}).json()
        check_state(self, state)
        self.assertEqual(state["candidate_count"], 1)
        self.assertEqual(state["step"]["food"]["food_id"], food.pk)
        dt = post(self.client, "/api/sessions/", {"date":DAY, "meal":"LU", "engine":"decision_tree"})
        self.assertEqual(dt.json()["candidate_count"], 1)

    def test_invalid_stored_v2_menu_is_withheld_without_breaking_the_session(self):
        food = add_food("Invalid v2 menu")
        food.feature_version = "v2"
        food.features = {"rice": 2.0}
        food.feature_std = {}
        food.save()
        result = post(self.client, "/api/sessions/", {"date": DAY, "engine": "rl"})
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json()["step"]["type"], "unavailable")

    def test_shares_only_numeric_state_and_can_undo_a_question(self):
        self.assertEqual(tuple(FEATURE_KEYS), RL_KEYS)
        rows = [{"food_id":i+1, "name":str(i), "features":{k:float((i >> (j%4))&1) for j,k in enumerate(RL_KEYS)}}
                for i in range(12)]
        engine = RLEngine(rows)
        renamed = RLEngine([{**r, "food_id":r["food_id"]+100, "name":"new"} for r in rows])
        self.assertIs(engine.world, renamed.world)
        first = engine.start()
        self.assertEqual(first["type"], "question")
        engine.answer(first["question_id"], "yes")
        self.assertEqual(engine.undo(), first)
        self.assertEqual(renamed.start(), first)
        self.assertIsNot(prepare([{**rows[0], "features":{}}]), prepare([{**rows[0], "features":{"rice":0}}]))
