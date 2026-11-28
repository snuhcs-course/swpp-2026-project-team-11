import datetime
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase, override_settings

from recommend import interaction_log
from .helpers import post

DAY = "2026-11-02"


class InteractionLogTests(TestCase):
    fixtures = ["menus_v3_contract"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private"
        self.settings = override_settings(INTERACTION_LOG_DIR=str(self.root))
        self.settings.enable()
        self.addCleanup(self.settings.disable)

    def events(self):
        files = list(self.root.glob("interactions-*.jsonl"))
        return [json.loads(line) for f in files for line in f.read_text(encoding="utf8").splitlines()]

    def start(self, **extra):
        response = post(self.client, "/api/sessions/", {"date": DAY, "meal": "LU", "engine": "rl"} | extra)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_records_session_and_each_successful_action_in_order(self):
        state = self.start()
        api_session = state["session_id"]
        url = f"/api/sessions/{api_session}/"
        q = state["step"]
        state = post(self.client, url + "answer/", {"question_id": q["question_id"], "answer_id": "yes"}).json()
        state = post(self.client, url + "recommend-now/").json()
        self.assertEqual(state["step"]["type"], "guess")
        state = post(self.client, url + "feedback/", {"guess_id": state["step"]["guess_id"], "accepted": False}).json()
        post(self.client, url + "undo/")
        events = self.events()
        self.assertEqual([e["event"] for e in events], ["start", "answer", "recommend_now", "feedback", "undo"])
        self.assertEqual(len({e["session"] for e in events}), 1)
        self.assertNotEqual(events[0]["session"], api_session)
        self.assertEqual(events[0]["menu_date"], DAY)
        self.assertEqual(events[0]["after"]["question_id"], q["question_id"])
        self.assertEqual(events[1]["answer_id"], "yes")
        self.assertEqual(events[1]["before"]["question_id"], q["question_id"])
        self.assertEqual(events[2]["after"]["type"], "guess")
        self.assertTrue(events[2]["after"]["display_name"])
        self.assertTrue(events[2]["after"]["restaurants"])
        self.assertIs(events[3]["accepted"], False)
        self.assertTrue(all(e["engine"] == "rl" and e["outcome"] == "ok" for e in events))
        self.assertTrue(all("allergies" not in e for e in events[1:]))

    def test_area_and_allergies_are_logged_without_api_session_token(self):
        response = self.client.post("/api/sessions/", data=json.dumps({
            "date": DAY, "meal": "LU", "engine": "decision_tree", "areas": ["nakseongdae", "campus"],
            "price_levels": [2, 1], "allergies": ["egg"]}), content_type="application/json",
            HTTP_X_FORWARDED_FOR="203.0.113.88", HTTP_USER_AGENT="device-secret-marker")
        self.assertEqual(response.status_code, 201)
        state = response.json()
        text = next(self.root.glob("*.jsonl")).read_text(encoding="utf8")
        self.assertNotIn(state["session_id"], text)
        self.assertNotIn("203.0.113.88", text)
        self.assertNotIn("device-secret-marker", text)
        event = self.events()[0]
        self.assertEqual(event["allergies"], ["egg"])
        self.assertEqual(event["version"], 3)
        self.assertEqual(event["areas"], ["campus", "nakseongdae"])
        self.assertEqual(event["price_levels"], [1, 2])
        self.assertGreaterEqual(event["candidates_before_area"], event["candidate_count"])
        self.assertTrue({"location", "location_available", "source", "distance_scope", "area", "price_level"}.isdisjoint(event))

    def test_invalid_and_stale_events_never_store_untrusted_body(self):
        state = self.start()
        url = f"/api/sessions/{state['session_id']}/answer/"
        self.assertEqual(post(self.client, url, {"question_id": "secret-user-value", "answer_id": "secret-answer"}).status_code, 409)
        event = self.events()[-1]
        self.assertEqual(event["outcome"], "stale_step")
        self.assertNotIn("secret-user-value", json.dumps(event))
        self.assertNotIn("secret-answer", json.dumps(event))

    def test_logging_failure_does_not_break_a_session(self):
        with mock.patch.object(interaction_log.os, "open", side_effect=OSError("unavailable")):
            with self.assertLogs("recommend.interaction_log", level="WARNING"):
                self.start()

    def test_disabled_does_not_create_a_log(self):
        with override_settings(INTERACTION_LOG_DIR=""):
            state = self.start()
            response = post(self.client, f"/api/sessions/{state['session_id']}/event/", {"event": "home"})
        self.assertEqual(response.status_code, 204)
        self.assertFalse(self.root.exists())

    def test_app_events_are_logged_on_the_step_on_screen_and_change_nothing(self):
        state = self.start(engine="decision_tree")
        url = f"/api/sessions/{state['session_id']}/"
        for body in ({"event": "home"}, {"event": "resume"}, {"event": "directions", "restaurant": "학생회관식당"},
                     {"event": "bookmark", "restaurant": "학생회관식당"}, {"event": "background"}):
            self.assertEqual(post(self.client, url + "event/", body).status_code, 204, body)
        self.assertEqual(self.client.get(url).json(), state)
        events = self.events()[1:]
        self.assertEqual([e["event"] for e in events], ["home", "resume", "directions", "bookmark", "background"])
        self.assertTrue(all(e["before"]["question_id"] == state["step"]["question_id"] and e["after"] is None
                            for e in events))
        self.assertEqual([e.get("restaurant") for e in events], [None, None, "학생회관식당", "학생회관식당", None])

    def test_an_unknown_app_event_is_refused_and_not_logged(self):
        state = self.start(engine="decision_tree")
        url = f"/api/sessions/{state['session_id']}/event/"
        for body in ({}, {"event": "quit"}, {"event": "directions", "restaurant": ""},
                     {"event": "directions", "restaurant": "x" * 101}, {"event": "bookmark", "restaurant": 3}):
            response = post(self.client, url, body)
            self.assertEqual(response.status_code, 400, body)
            self.assertEqual(response.json()["error"]["code"], "invalid_request")
        self.assertEqual(post(self.client, "/api/sessions/no-such-session/event/", {"event": "home"}).status_code, 404)
        self.assertEqual([e["event"] for e in self.events()], ["start"])

    def test_opening_a_menu_is_logged_with_its_restaurant(self):
        state = self.start(engine="decision_tree")
        response = self.client.get(f"/api/sessions/{state['session_id']}/menu/", {"restaurant": "학생회관식당"})
        self.assertEqual(response.status_code, 200)
        event = self.events()[-1]
        self.assertEqual((event["event"], event["restaurant"]), ("menu", "학생회관식당"))
        self.assertEqual(event["before"]["question_id"], state["step"]["question_id"])

    def test_retention_deletes_only_expired_log_files(self):
        self.root.mkdir()
        for name in ("interactions-2026-10-01.jsonl", "interactions-2026-10-05.jsonl",
                     "interactions-2026-11-03.jsonl", "other-2026-01-01.jsonl", "interactions-bad.jsonl"):
            (self.root / name).write_text("{}\n")
        interaction_log.prune(self.root, datetime.date(2026, 11, 3))
        self.assertFalse((self.root / "interactions-2026-10-01.jsonl").exists())
        self.assertTrue((self.root / "interactions-2026-10-05.jsonl").exists())
        self.assertTrue((self.root / "interactions-2026-11-03.jsonl").exists())
        self.assertTrue((self.root / "other-2026-01-01.jsonl").exists())
        self.assertTrue((self.root / "interactions-bad.jsonl").exists())

    def test_concurrent_requests_do_not_interleave_json(self):
        session = SimpleNamespace(interaction_id="independent-id", engine_name="rl", meal="LU", date=datetime.date(2026, 11, 2), areas=("campus",),
                                  price_levels=(1, 2, 3), candidates_before_area=12, candidate_count=3)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: interaction_log.record(session, "answer", answer_id="yes"), range(50)))
        events = self.events()
        self.assertEqual(len(events), 50)
        self.assertTrue(all(e["answer_id"] == "yes" for e in events))
