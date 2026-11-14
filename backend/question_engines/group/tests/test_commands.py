import io
import json
from pathlib import Path
import tempfile
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase
import pytest

from menus.management.commands.benchmark_group import _safe_offers
from question_engines.benchmark.tests.helpers import FakeUserLLM

RUN = ["benchmark_group", "--date", "2026-11-02", "--groups", "1"]


class GroupBenchmarkCommandTests(TestCase):
    fixtures = ["menus_2026-11-02"]

    def test_freezes_cases_first_then_plays_them_with_each_simulator(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            call_command(*RUN, "--dir", directory, stdout=io.StringIO())
            frozen = json.loads((folder / "cases.json").read_text(encoding="utf-8"))
            self.assertEqual(len(frozen["cases"]), 12)
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ["cases.json"])

            call_command(*RUN, "--dir", directory, stdout=io.StringIO())
            self.assertEqual(len(json.loads((folder / "oracle.json").read_text(encoding="utf-8"))["cases"]), 12)

            llm = FakeUserLLM(seed=1)
            with mock.patch("menus.management.commands.benchmark_group.build_llm", return_value=llm):
                call_command(*RUN, "--dir", directory, "--simulator", "llm", "--workers", "4", stdout=io.StringIO())
            report = json.loads((folder / "llm.json").read_text(encoding="utf-8"))
            cached = (folder / "answers.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(report["simulator_usage"]["calls"], len(llm.calls))
            self.assertEqual(len(cached), len(llm.calls))
            self.assertIn("simulator_prompt_id", report["config"])

    def test_refuses_other_menus_and_missing_ones(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "cases.json").write_text(json.dumps({"catalog": "other", "cases": []}), encoding="utf-8")
            with self.assertRaisesMessage(CommandError, "메뉴와 지금 메뉴가 다릅니다"):
                call_command(*RUN, "--dir", directory, stdout=io.StringIO())
            with self.assertRaisesMessage(CommandError, "cafeteria LU 메뉴가 없습니다"):
                call_command("benchmark_group", "--date", "2026-10-06", "--dir", directory, stdout=io.StringIO())
            with self.assertRaisesMessage(CommandError, "general LU 메뉴가 없습니다"):
                call_command("benchmark_group", "--source", "general", "--dir", directory, stdout=io.StringIO())
            with self.assertRaisesMessage(CommandError, "--date가 필요합니다"):
                call_command("benchmark_group", "--dir", directory, stdout=io.StringIO())

    def test_refuses_changed_allergy_restrictions(self):
        with tempfile.TemporaryDirectory() as directory:
            call_command(*RUN, "--dir", directory, stdout=io.StringIO())
            frozen = Path(directory) / "cases.json"
            data = json.loads(frozen.read_text(encoding="utf-8"))
            frozen.write_text(json.dumps(data | {"restrictions": "other"}), encoding="utf-8")
            with self.assertRaisesMessage(CommandError, "알레르기 제한"):
                call_command(*RUN, "--dir", directory, stdout=io.StringIO())


def test_safe_offers_keep_each_restaurant_apart_and_follow_the_full_catalogs_ids():
    def row(food_id, name, *places):
        return {"food_id": food_id, "name": name, "features": {"spicy": .5}, "feature_std": {"spicy": .1},
                "offers": [{"restaurant": p, "meal": "LU", "price": 5000, "lat": 37., "lng": 127.} for p in places]}

    full = [row(1, "국밥", "A", "B"), row(2, "국수", "A")]
    safe = [row(5, "국밥", "B")]  # merged again without the allergen, under another ID
    assert _safe_offers(full, safe) == {(1, ("B", 37., 127.))}
    with pytest.raises(CommandError):
        _safe_offers(full, [row(5, "비빔밥", "B")])  # the command reports what menus/offers.py raises
    with pytest.raises(CommandError):
        _safe_offers(full + [row(3, "국밥", "B")], safe)  # two menus look alike at B
