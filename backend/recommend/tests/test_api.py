import datetime
import json

from django.test import TestCase, override_settings

DAY = "2026-09-29"


class SessionApiTests(TestCase):
    fixtures = ["menus_2026-09-29"]

    def post(self, path, body=None):
        return self.client.post(path, data=json.dumps(body or {}), content_type="application/json")

    def start(self, **body):
        response = self.post("/api/sessions/", {"date": DAY, "meal": "LU", **body})
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_create_returns_first_question(self):
        state = self.start()
        self.assertEqual((state["engine"], state["date"], state["meal"]), ("decision_tree", DAY, "LU"))
        self.assertEqual(state["candidate_count"], 193)
        self.assertFalse(state["can_undo"])
        self.assertEqual(state["step"]["type"], "question")
        self.assertEqual(len(state["step"]["options"]), 6)

    def test_answer_then_undo_restores_the_question(self):
        state = self.start()
        url = f"/api/sessions/{state['session_id']}/"
        question_id = state["step"]["question_id"]
        after = self.post(url + "answer/", {"question_id": question_id, "answer_id": "yes"}).json()
        self.assertTrue(after["can_undo"])
        self.assertEqual(after["step"]["question_count"], 1)
        self.assertEqual(self.client.get(url).json(), after)
        undone = self.post(url + "undo/").json()
        self.assertEqual(undone["step"], state["step"])
        self.assertFalse(undone["can_undo"])

    def test_repeated_answer_is_stale_and_returns_current_state(self):
        state = self.start()
        url = f"/api/sessions/{state['session_id']}/"
        body = {"question_id": state["step"]["question_id"], "answer_id": "no"}
        current = self.post(url + "answer/", body).json()
        response = self.post(url + "answer/", body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "stale_step")
        self.assertEqual(response.json()["state"], current)

    def test_invalid_requests_are_400(self):
        state = self.start()
        url = f"/api/sessions/{state['session_id']}/"
        question_id = state["step"]["question_id"]
        for path, body in [
            ("answer/", {"question_id": question_id, "answer_id": "maybe"}),
            ("answer/", {"question_id": question_id}),
            ("feedback/", {"guess_id": "food:1", "accepted": "yes"}),
        ]:
            response = self.post(url + path, body)
            self.assertEqual(response.status_code, 400, body)
            self.assertEqual(response.json()["error"]["code"], "invalid_request")
        self.assertEqual(self.client.post(url + "answer/", data="[", content_type="application/json").status_code, 400)
        self.assertEqual(self.post("/api/sessions/", {"date": "tomorrow"}).status_code, 400)
        self.assertEqual(self.post("/api/sessions/", {"meal": "SNACK"}).status_code, 400)
        self.assertEqual(self.client.get(url + "undo/").status_code, 405)

    def test_unknown_session_is_404(self):
        self.assertEqual(self.client.get("/api/sessions/nope/").status_code, 404)
        response = self.post("/api/sessions/nope/undo/")
        self.assertEqual(response.json()["error"]["code"], "session_not_found")

    def test_recommend_now_reject_then_accept(self):
        state = self.start()
        url = f"/api/sessions/{state['session_id']}/"
        guess = self.post(url + "recommend-now/").json()
        self.assertEqual(guess["step"]["type"], "guess")
        # A second tap must not stack events: one undo still returns to the question.
        self.assertEqual(self.post(url + "recommend-now/").json(), guess)
        self.assertEqual(self.post(url + "undo/").json()["step"], state["step"])

        guess = self.post(url + "recommend-now/").json()["step"]
        rejected = self.post(url + "feedback/", {"guess_id": guess["guess_id"], "accepted": False}).json()
        self.assertIn(rejected["step"]["type"], {"question", "guess"})
        guess = self.post(url + "recommend-now/").json()["step"]
        final = self.post(url + "feedback/", {"guess_id": guess["guess_id"], "accepted": True}).json()
        self.assertEqual(final["step"]["type"], "recommendation")
        self.assertEqual(final["step"]["food"]["food_id"], guess["food"]["food_id"])
        self.assertTrue(final["step"]["food"]["offers"])
        # The session has ended; a late tap redraws rather than fails.
        self.assertEqual(self.post(url + "recommend-now/").json(), final)

    @override_settings(RECOMMEND_MAX_QUESTIONS=3)
    def test_question_cap_forces_a_guess_with_named_group_members(self):
        state = self.start()
        url = f"/api/sessions/{state['session_id']}/"
        self.assertEqual(state["max_questions"], 3)
        while state["step"]["type"] == "question":
            self.assertLess(state["step"]["question_count"], 3)
            state = self.post(url + "answer/", {"question_id": state["step"]["question_id"],
                                                 "answer_id": "any"}).json()
        step = state["step"]
        self.assertEqual(step["type"], "guess")
        if step["target_kind"] == "group":
            self.assertNotIn("food_ids", step["group"])
            members = step["group"]["members"]
            self.assertIn(step["food"]["food_id"], [m["food_id"] for m in members])
            self.assertTrue(all(m["display_name"] for m in members))

    def test_day_without_menu_is_unavailable(self):
        state = self.post("/api/sessions/", {"date": "2026-10-06"}).json()
        self.assertEqual(state["candidate_count"], 0)
        self.assertEqual(state["step"]["type"], "unavailable")
        self.assertEqual(state["step"]["reason"], "empty_candidates")
        url = f"/api/sessions/{state['session_id']}/"
        self.assertEqual(self.post(url + "recommend-now/").json()["step"]["type"], "unavailable")

    @override_settings(RECOMMEND_DEFAULT_DATE=datetime.date(2026, 9, 29))
    def test_default_date_setting_is_used_when_client_sends_none(self):
        state = self.post("/api/sessions/").json()
        self.assertEqual((state["date"], state["meal"]), (DAY, None))
        self.assertGreater(state["candidate_count"], 0)
