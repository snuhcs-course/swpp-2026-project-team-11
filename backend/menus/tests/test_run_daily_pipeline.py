# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import io
import pathlib
import tempfile
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase

from menus.features import extractor
from menus.features.schema import FEATURE_VERSION
from menus.models import Food
from menus.preprocess import mapper
from menus.tests.test_extract_features import FakeLLM as FakeTagger
from menus.tests.test_preprocess_llm import FakeLLM as FakeMapper
from menus.tests.test_preprocess_review import ANSWERS, DAY, PAYLOAD
from menus.tests.utils import without_committed_rules


@without_committed_rules
class RunDailyPipelineTests(TestCase):
    def run_pipeline(self, *args, key=True, tagger=None):
        out = io.StringIO()
        with mock.patch("menus.sources.siksha.fetch_raw", return_value=PAYLOAD), \
                mock.patch("menus.management.commands.run_daily_pipeline.api_key_available", return_value=key), \
                mock.patch("menus.management.commands.fetch_menus.api_key_available", return_value=key), \
                mock.patch.object(extractor, "api_key_available", return_value=key), \
                mock.patch.object(mapper, "build_llm", return_value=FakeMapper(ANSWERS)), \
                mock.patch.object(extractor, "build_llm", return_value=tagger or FakeTagger()):
            call_command("run_daily_pipeline", "--date", DAY.isoformat(), *args, stdout=out)
        return out.getvalue()

    def test_fetches_preprocesses_tags_and_reports_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = pathlib.Path(tmp) / "review.csv"
            output = self.run_pipeline("--review", str(review))
            self.assertTrue(review.exists())
        self.assertEqual(sorted(Food.objects.values_list("name", flat=True)),
                         ["돈까스", "마라탕", "즉석마라탕", "카레우동"])
        self.assertFalse(Food.objects.exclude(feature_version=FEATURE_VERSION).exists())
        self.assertIn("점심 4", output)
        self.assertIn("[3/3]", output)

    def test_a_failing_step_fails_the_run_after_every_step_ran(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = pathlib.Path(tmp) / "review.csv"
            with self.assertRaisesMessage(CommandError, "extract_features: 특징을 뽑지 못한 음식 1개"):
                self.run_pipeline("--review", str(review), tagger=FakeTagger(always_fail=["카레우동"]))
            self.assertTrue(review.exists())
        self.assertEqual(Food.objects.get(name="카레우동").feature_version, "")
        self.assertEqual(Food.objects.get(name="돈까스").feature_version, FEATURE_VERSION)

    def test_requires_an_api_key(self):
        with self.assertRaisesMessage(CommandError, "GOOGLE_API_KEY"):
            self.run_pipeline(key=False)
