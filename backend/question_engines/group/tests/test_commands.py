import io
import json
from pathlib import Path
import tempfile
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase

from question_engines.benchmark.tests.helpers import FakeUserLLM

RUN = ["benchmark_group", "--date", "2026-11-02", "--groups", "1"]


class GroupBenchmarkCommandTests(TestCase):
    fixtures = ["menus_2026-11-02"]

    def test_freezes_cases_first_then_plays_them_with_each_simulator(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            call_command(*RUN, "--dir", directory, stdout=io.StringIO())
            frozen = json.loads((folder / "cases.json").read_text())
            self.assertEqual(len(frozen["cases"]), 12)
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ["cases.json"])

            call_command(*RUN, "--dir", directory, stdout=io.StringIO())
            self.assertEqual(len(json.loads((folder / "oracle.json").read_text())["cases"]), 12)

            llm = FakeUserLLM(seed=1)
            with mock.patch("menus.management.commands.benchmark_group.build_llm", return_value=llm):
                call_command(*RUN, "--dir", directory, "--simulator", "llm", "--workers", "4", stdout=io.StringIO())
            report = json.loads((folder / "llm.json").read_text())
            cached = (folder / "answers.jsonl").read_text().splitlines()
            self.assertEqual(report["simulator_usage"]["calls"], len(llm.calls))
            self.assertEqual(len(cached), len(llm.calls))
            self.assertIn("simulator_prompt_id", report["config"])

    def test_refuses_other_menus_and_missing_ones(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "cases.json").write_text(json.dumps({"catalog": "other", "cases": []}))
            with self.assertRaisesMessage(CommandError, "differ from"):
                call_command(*RUN, "--dir", directory, stdout=io.StringIO())
            with self.assertRaisesMessage(CommandError, "No cafeteria LU menu"):
                call_command("benchmark_group", "--date", "2026-10-06", "--dir", directory, stdout=io.StringIO())
            with self.assertRaisesMessage(CommandError, "No general LU menu"):
                call_command("benchmark_group", "--source", "general", "--dir", directory, stdout=io.StringIO())
            with self.assertRaisesMessage(CommandError, "--date is required"):
                call_command("benchmark_group", "--dir", directory, stdout=io.StringIO())
