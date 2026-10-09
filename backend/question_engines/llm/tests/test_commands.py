# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import datetime
import io
import json
from pathlib import Path
import tempfile
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase

from menus.services import get_candidates

from .. import engine as llm_engine
from .helpers import FakeLLM, ask, recommend


class DemoCommandTests(TestCase):
    fixtures = ["menus_2026-09-29"]

    def setUp(self):
        rows = get_candidates(datetime.date(2026, 9, 29), "LU")
        self.first, self.second = rows[0]["display_name"], rows[1]["display_name"]

    def run_demo(self, llm, *args, answers=()):
        stream = io.StringIO()
        with mock.patch.object(llm_engine, "build_llm", return_value=llm), \
                mock.patch.dict("os.environ", {"GOOGLE_API_KEY": "k"}), \
                mock.patch("builtins.input", side_effect=list(answers)):
            call_command("demo_llm_engine", "--date", "2026-09-29", *args, stdout=stream)
        return stream.getvalue()

    def test_smoke_exports_replayable_snapshot_and_real_offers(self):
        llm = FakeLLM(ask("Do you feel like noodles?", food=self.first), recommend(self.first),
                      recommend(self.second))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "session.json"
            self.run_demo(llm, "--smoke", "--output", str(output))
            result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual([e["action"] for e in result["events"]],
                         ["start", "answer", "recommend_now", "reject", "recommend_now", "accept"])
        final = result["events"][-1]["step"]
        self.assertEqual((final["type"], final["food"]["display_name"]), ("recommendation", self.second))
        self.assertTrue(final["food"]["offers"])
        self.assertEqual(result["snapshot"]["version"], 1)
        self.assertEqual(result["diagnostics"]["question_count"], 1)
        self.assertEqual(len(llm.calls), 3)  # recommend_now on a shown guess makes no call

    def test_interactive_session_with_undo(self):
        llm = FakeLLM(ask("Do you feel like noodles?", food=self.first), recommend(self.second),
                      recommend(self.first))
        output = self.run_demo(llm, answers=["9", "1", "u", "2", "y"])
        self.assertIn("Choose one of the displayed options.", output)
        self.assertIn(f"Recommended meal: {self.first}", output)
        self.assertIn("Questions: 1", output)
        self.assertEqual(len(llm.calls), 3)  # undo restores the question; answering it again asks the LLM

    def test_missing_key_is_a_command_error(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesMessage(CommandError, "GOOGLE_API_KEY"):
                call_command("demo_llm_engine", "--date", "2026-09-29", stdout=io.StringIO())
