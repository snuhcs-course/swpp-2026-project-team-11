# AI-generated: written with OpenAI Codex and reviewed by the team.
import io
import json
from pathlib import Path
import tempfile

from django.core.management import call_command, CommandError
from django.test import TestCase


class CommandIntegrationTests(TestCase):
    fixtures = ["menus_2026-09-29"]

    def test_smoke_exports_replayable_snapshot_and_real_offers(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "session.json"
            stream = io.StringIO()
            call_command("demo_decision_tree", "--date", "2026-09-29", "--smoke", "--output", str(output), stdout=stream)
            result = json.loads(output.read_text())
        self.assertEqual(result["events"][-1]["step"]["type"], "recommendation")
        self.assertEqual([x["action"] for x in result["events"]], ["start", "answer", "recommend_now", "reject", "recommend_now", "accept"])
        self.assertEqual(result["snapshot"]["version"], 1)
        self.assertTrue(result["events"][-1]["step"]["food"]["offers"])

    def test_empty_date_is_explicit_in_demo_and_benchmark(self):
        stream = io.StringIO()
        call_command("demo_decision_tree", "--date", "2026-10-06", "--smoke", stdout=stream)
        self.assertEqual(json.loads(stream.getvalue())["final_step"]["reason"], "empty_candidates")
        with self.assertRaisesMessage(CommandError, "No candidates"):
            call_command("benchmark_decision_tree", "--date", "2026-10-06", "--trials", "1", stdout=io.StringIO())
