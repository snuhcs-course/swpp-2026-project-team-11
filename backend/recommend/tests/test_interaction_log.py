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
    fixtures = ["menus_2026-11-02"]

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
        self.assertTrue(all(e["engine"] == "rl" and e["outcome"] == "ok" and e["test"] is False for e in events))
        self.assertTrue(all("allergies" not in e and "location" not in e for e in events[1:]))

    def test_location_and_allergies_are_logged_without_api_session_token(self):
        location = {"lat": 37.481247, "lng": 126.952739}
        response = self.client.post("/api/sessions/", data=json.dumps({
            "date": DAY, "meal": "LU", "engine": "rl", "source": "all", "distance_scope": "near",
            "location": location, "allergies": ["egg"]}), content_type="application/json",
            HTTP_X_FORWARDED_FOR="203.0.113.88", HTTP_USER_AGENT="device-secret-marker")
        self.assertEqual(response.status_code, 201)
        state = response.json()
        text = next(self.root.glob("*.jsonl")).read_text(encoding="utf8")
        self.assertNotIn(state["session_id"], text)
        self.assertNotIn("203.0.113.88", text)
        self.assertNotIn("device-secret-marker", text)
        event = self.events()[0]
        self.assertEqual(event["allergies"], ["egg"])
        self.assertEqual(event["location"], location)
        self.assertIs(event["location_available"], True)
        self.assertEqual(event["source"], "all")
        self.assertEqual(event["distance_scope"], "near")
        self.assertGreaterEqual(event["candidates_before_distance"], event["candidate_count"])

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

    def test_synthetic_marker_follows_the_session(self):
        response = self.client.post("/api/sessions/", data=json.dumps({"date": DAY, "meal": "LU", "engine": "rl"}),
                                    content_type="application/json", HTTP_X_METCHU_TEST="1")
        self.assertEqual(response.status_code, 201)
        state = response.json()
        post(self.client, f"/api/sessions/{state['session_id']}/recommend-now/")
        self.assertTrue(all(e["test"] is True for e in self.events()))

    def test_disabled_does_not_create_a_log(self):
        with override_settings(INTERACTION_LOG_DIR=""):
            self.start()
        self.assertFalse(self.root.exists())

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
        session = SimpleNamespace(interaction_id="independent-id", engine_name="rl", meal="LU", date=datetime.date(2026, 11, 2), source="all", interaction_test=False,
                                  distance_scope="near", location_available=True,
                                  candidates_before_distance=12, candidate_count=3)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: interaction_log.record(session, "answer", answer_id="yes"), range(50)))
        events = self.events()
        self.assertEqual(len(events), 50)
        self.assertTrue(all(e["answer_id"] == "yes" for e in events))
