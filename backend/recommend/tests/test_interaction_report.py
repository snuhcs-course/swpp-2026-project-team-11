"""The numbers `manage.py interaction_report` prints, from a small hand-made log."""
import datetime
import io
import json
import tempfile
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from recommend import interaction_report

T0 = datetime.datetime(2026, 11, 30, 3, 0, tzinfo=datetime.timezone.utc)
NOW = T0 + datetime.timedelta(hours=2)


def q(k, qid=None):
    return {"type": "question", "question_count": k, "question_id": qid or f"q:{k}"}


def guess(k):
    return {"type": "guess", "question_count": k, "food_id": 7, "display_name": "Dish", "restaurants": ["Hall"]}


def at(minutes):
    return (T0 + datetime.timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def solo(session, *events):
    """(minute, event, before, after, extra) rows as the server writes them."""
    return [{"version": 3, "timestamp": at(m), "session": session, "event": event, "outcome": "ok",
             "before": before, "after": after, **extra} for m, event, before, after, extra in events]


def answers(session, upto, start=0.0, step=0.5):
    """Start, then `upto` answers, each showing the next question."""
    rows = [(start, "start", None, q(0, "q:first"), {"allergies": ["egg"]})]
    for k in range(upto):
        rows.append((start + step * (k + 1), "answer", q(k, "q:first" if k == 0 else None), q(k + 1), {"answer_id": "yes"}))
    return solo(session, *rows)


def room(room_id, *events):
    return [{"record": "room", "version": 1, "timestamp": at(m), "room": room_id, "event": event, "outcome": "ok",
             "round_seconds": 15, **fields} for m, event, fields in events]


def log():
    left_at_seven = answers("s1", 6)  # six answers, then gone on the seventh question
    accepted = answers("s2", 1) + solo("s2", (1.5, "answer", q(1), guess(2), {}),
                                       (2.0, "directions", guess(2), None, {"restaurant": "Hall"}))
    home = answers("s3", 0) + solo("s3", (0.2, "home", q(0, "q:first"), None, {}))
    still_open = answers("s4", 1, start=110)
    decided = room("r1", (0, "create", {"status": "lobby", "round": 0}), (1, "join", {"status": "lobby", "round": 0}),
                   (2, "start", {"status": "asking", "round": 0, "waited_s": 120.0}),
                   (2.5, "round", {"status": "asking", "round": 1, "answered": 2, "timeout": 0, "left": 0}),
                   (3, "round", {"status": "asking", "round": 2, "answered": 1, "timeout": 1, "left": 0}),
                   (3, "result", {"status": "done", "round": 2, "how": "engine", "asking_s": 60.0}),
                   (5, "decide", {"status": "done", "round": 2, "deciding_s": 120.0, "finds": 1, "votes": 2,
                                  "members": 2}),
                   (6, "leave", {"status": "done", "round": 2, "was_host": False}),
                   (6, "end", {"status": "done", "round": 2, "reason": "all_left"}))
    gone_mid_round = room("r2", (0, "create", {"status": "lobby", "round": 0}),
                          (1, "start", {"status": "asking", "round": 0}),
                          (1.5, "round", {"status": "asking", "round": 1, "answered": 1, "timeout": 1, "left": 0}),
                          (2, "leave", {"status": "asking", "round": 1, "was_host": False}),
                          (2, "leave", {"status": "asking", "round": 1, "was_host": True}),
                          (2, "end", {"status": "done", "round": 3, "reason": "all_left"}))
    lobby = room("r3", (0, "create", {"status": "lobby", "round": 0}),
                 (1, "leave", {"status": "lobby", "round": 0, "was_host": True}),
                 (1, "end", {"status": "lobby", "round": 0, "reason": "all_left"}))
    return left_at_seven + accepted + home + still_open + decided + gone_mid_round + lobby


class ReportTests(SimpleTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        lines = [json.dumps(e) for e in log()] + ["not json", "{}"]
        (self.root / "interactions-2026-11-30.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (self.root / "interactions-2026-11-01.jsonl").write_text(json.dumps(answers("old", 3)[0]) + "\n", encoding="utf-8")

    def report(self, full=False):
        events = interaction_report.read(self.root, datetime.date(2026, 11, 2))
        return interaction_report.report(events, NOW, full=full)

    def row(self, text, first, section="SOLO SESSIONS"):
        """The cells of the first table row in `section` that starts with `first`."""
        lines = text.split(section, 1)[1].splitlines()
        return next(line.split() for line in lines if line.split()[:1] == [str(first)])

    def test_where_solo_sessions_end(self):
        text = self.report()
        self.assertIn("SOLO SESSIONS: 3 ended, 1 still open", text)
        self.assertEqual(self.row(text, 0), ["0", "3", "1", "33%", "100%"])  # the one who went home
        self.assertEqual(self.row(text, 1), ["1", "2", "0", "0%", "67%"])
        self.assertEqual(self.row(text, 6), ["6", "1", "1", "100%", "33%"])  # six answers, gone on the seventh
        self.assertEqual(self.row(text, "q:first"), ["q:first", "3", "1", "33%"])
        self.assertIn("1 of 3 (33%); median 2.0 questions and 90.0 s to the first", text)
        self.assertIn("1 of 2 (50%); 100% of those that reached a proposal", text)

    def test_how_rooms_end(self):
        text = self.report()
        self.assertIn("GROUP ROOMS: 3 closed, 0 still open", text)
        self.assertIn("1 of 2 started (50%); 2 of 3 created rooms started", text)
        self.assertIn("undecided rooms ended at: lobby 1, round 2 1", text)
        self.assertEqual(self.row(text, 1, "2. Timed-out"), ["1", "2", "4", "1", "25%"])
        self.assertEqual(self.row(text, 2, "2. Timed-out"), ["2", "1", "2", "1", "50%"])
        self.assertIn("start to result 1.0, result to decision 2.0", text)

    def test_the_full_report_adds_the_rest_and_nothing_personal(self):
        short, full = self.report(), self.report(full=True)
        self.assertNotIn("How sessions ended", short)
        self.assertIn("How sessions ended: no signal 1, accepted 1, home 1", full)
        self.assertIn("Lobby wait (create to start): 2.0 min", full)
        self.assertIn("Leaves by stage: asking 2, done 1, lobby 1; hosts who left: 2", full)
        self.assertIn("Finds before deciding: median 1.0", full)
        for private in ("egg", "Hall"):
            self.assertNotIn(private, full)

    def test_older_files_and_broken_lines_are_skipped(self):
        events = interaction_report.read(self.root, datetime.date(2026, 11, 2))
        self.assertNotIn("old", {e.get("session") for e in events})
        self.assertEqual(len(events), len(log()))
        self.assertEqual(len(interaction_report.read(self.root)), len(log()) + 1)

    def test_the_command_reads_the_given_directory(self):
        out = io.StringIO()
        call_command("interaction_report", dir=self.root, since=datetime.date(2026, 11, 2), stdout=out)
        self.assertIn("SOLO SESSIONS", out.getvalue())
        with self.assertRaises(CommandError):
            call_command("interaction_report", dir=self.root / "missing", stdout=io.StringIO())
