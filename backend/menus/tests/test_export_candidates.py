# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import datetime
import io
import json
import pathlib
import tempfile

from django.core.management import call_command
from django.test import TestCase

from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION
from menus.models import Food, MenuItem, Restaurant

DAY = datetime.date(2026, 9, 29)


class ExportCandidatesTests(TestCase):
    def setUp(self):
        restaurant = Restaurant.objects.create(code="학생회관식당", name="학생회관식당")
        food = Food.objects.create(name="육개장", display_name="육개장", is_food=True,
                                   feature_version=FEATURE_VERSION,
                                   features={key: 0.5 for key in FEATURE_KEYS})
        MenuItem.objects.create(date=DAY, meal="LU", restaurant=restaurant,
                                raw_name="육개장", food=food, price=3000)

    def test_writes_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "candidates.json"
            out = io.StringIO()
            call_command("export_candidates", "--date", DAY.isoformat(), "--meal", "LU",
                         "--output", str(path), stdout=out)
            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertIn("후보 1개", out.getvalue())
        self.assertEqual((data["date"], data["meal"], data["feature_version"]),
                         ("2026-09-29", "LU", FEATURE_VERSION))
        self.assertEqual([f["key"] for f in data["features"]], list(FEATURE_KEYS))
        self.assertEqual([c["name"] for c in data["candidates"]], ["육개장"])

    def test_prints_json_without_output(self):
        out = io.StringIO()
        call_command("export_candidates", "--date", DAY.isoformat(), stdout=out)
        self.assertEqual(len(json.loads(out.getvalue())["candidates"]), 1)


class SeedFixtureTests(TestCase):
    """The committed snapshot teammates load instead of calling the LLM."""

    fixtures = ["menus_2026-09-29"]

    def test_snapshot_gives_a_full_candidate_set(self):
        from menus import services

        candidates = services.get_candidates(DAY, meal="LU")
        self.assertGreater(len(candidates), 100)
        for candidate in candidates:
            self.assertEqual(set(candidate["features"]), set(FEATURE_KEYS), candidate["name"])
