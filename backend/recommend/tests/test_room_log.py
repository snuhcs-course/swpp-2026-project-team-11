"""Room records in the interaction log: one per change of state, counts instead of names and answers."""
import json
import tempfile
from pathlib import Path
from unittest import mock

from django.test import override_settings

from recommend import interaction_log, rooms

from .test_rooms import RoomTestCase


class RoomLogTestCase(RoomTestCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "private"
        settings = override_settings(INTERACTION_LOG_DIR=str(self.root))
        settings.enable()
        self.addCleanup(settings.disable)

    def text(self):
        return "".join(path.read_text(encoding="utf8") for path in sorted(self.root.glob("interactions-*.jsonl")))

    def events(self):
        return [json.loads(line) for line in self.text().splitlines()]

    def answer(self, code, token, state, answer_id="yes"):
        return self.call(code, "answer", token, {"question_id": state["question"]["question_id"], "answer_id": answer_id})


class RoomLogTests(RoomLogTestCase):
    def test_a_room_is_logged_once_per_change_without_names_codes_or_tokens(self):
        code, host, _ = self.create(round_seconds=10)
        guest = self.join(code, "Seoyeon")["token"]
        state = self.call(code, "start", host)
        self.clock.now += 4
        self.answer(code, host, state)
        self.clock.now += 6  # the guest stays silent until the round's time is up
        state = self.state(code, guest)
        lines = len(self.events())
        for _ in range(100):
            self.state(code, host)
        self.assertEqual(len(self.events()), lines, "polling writes nothing")
        if state["status"] == "asking":
            state = self.call(code, "recommend-now", host)
        found = state["more"]
        if found:
            self.call(code, "another", host)
        self.call(code, "vote", guest, {"pick": 0, "agree": True})
        self.clock.now += 30
        self.call(code, "decide", host, {"pick": 0})
        self.call(code, "leave", guest, status=204)
        self.call(code, "leave", host, status=204)

        events = self.events()
        names = [e["event"] for e in events]
        self.assertEqual(names[:4], ["create", "join", "start", "round"])
        self.assertEqual(names[-4:], ["decide", "leave", "leave", "end"])
        self.assertEqual(names.count("result"), 1)
        self.assertEqual(len({e["room"] for e in events}), 1)
        self.assertTrue(all(e["record"] == "room" and e["outcome"] == "ok" and e["round_seconds"] == 10 for e in events))
        self.assertEqual((events[1]["member"], events[1]["members"]), (1, 2))
        self.assertEqual((events[2]["allergic_members"], events[2]["waited_s"]), (0, 0.0))
        self.assertGreater(events[2]["candidate_count"], 0)
        first_round = events[3]
        self.assertEqual((first_round["round"], first_round["answered"], first_round["timeout"], first_round["left"]),
                         (1, 1, 1, 0))
        self.assertEqual((first_round["answer_s"], first_round["round_s"]), (4.0, 10.0))
        decide = events[-4]
        self.assertEqual((decide["pick"], decide["batch"], decide["votes"], decide["deciding_s"]), (0, 0, 1, 30.0))
        self.assertEqual(decide["finds"], 1 if found else 0)
        self.assertEqual([e["was_host"] for e in events[-3:-1]], [False, True])
        self.assertEqual((events[-1]["reason"], events[-1]["decided"], events[-1]["members"]), ("all_left", True, 0))
        text = self.text()
        for secret in (code, host, guest, "Jimin", "Seoyeon"):
            self.assertNotIn(f'"{secret}"', text)
        self.assertTrue(all(len(line.encode()) < 600 for line in text.splitlines()))

    def test_who_left_mid_round_counts_as_left_and_an_empty_room_logs_no_more_rounds(self):
        code, host, (guest,), state = self.started()
        self.call(code, "leave", guest, status=204)
        after = self.answer(code, host, state)
        self.call(code, "leave", host, status=204)
        events = self.events()
        rounds = [e for e in events if e["event"] == "round"]
        self.assertEqual((rounds[0]["answered"], rounds[0]["timeout"], rounds[0]["left"]), (1, 0, 1))
        last_leave = max(i for i, e in enumerate(events) if e["event"] == "leave")
        self.assertEqual([e["event"] for e in events[last_leave:]], ["leave", "end"])
        self.assertEqual(events[last_leave]["status"], after["status"])
        self.assertIs(events[-1]["decided"], False)

    def test_the_host_stopping_early_is_a_result_of_its_own_kind(self):
        code, host, _, _ = self.started()
        self.clock.now += 3
        self.call(code, "recommend-now", host)
        result = next(e for e in self.events() if e["event"] == "result")
        self.assertEqual((result["how"], result["round"], result["asking_s"]), ("recommend_now", 0, 3.0))
        self.assertGreaterEqual(result["picks"], 1)

    def test_refused_starts_and_joins_are_logged_with_their_reason(self):
        code, host, _ = self.create()
        self.call(code, "start", host, status=409)
        for i in range(7):
            self.join(code, f"Friend {i}")
        self.join(code, "Late", status=409)
        self.call(code, "start", host)
        self.join(code, "Later", status=409)
        refused = [(e["event"], e["outcome"]) for e in self.events() if e["outcome"] != "ok"]
        self.assertEqual(refused, [("start", "too_few_members"), ("join", "room_full"), ("join", "room_started")])

    def test_a_pushed_out_room_ends_as_evicted(self):
        # Without the rooms earlier tests left, which would be pushed out too.
        with mock.patch.object(rooms, "MAX_ROOMS", 1), mock.patch.dict(rooms._rooms, clear=True):
            self.create()
            self.create()
        ends = [e for e in self.events() if e["event"] == "end"]
        self.assertEqual([(e["reason"], e["decided"]) for e in ends], [("evicted", False)])

    def test_disabled_writes_nothing_and_a_failing_disk_fails_no_request(self):
        with override_settings(INTERACTION_LOG_DIR=""):
            self.started()
        self.assertFalse(self.root.exists())
        with mock.patch.object(interaction_log.os, "open", side_effect=OSError("unavailable")):
            with self.assertLogs("recommend.interaction_log", level="WARNING"):
                code, host, _, _ = self.started()
                self.assertEqual(self.call(code, "recommend-now", host)["status"], "done")
