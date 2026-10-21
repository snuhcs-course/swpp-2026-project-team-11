# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import datetime
import io
import os
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from menus import llm
from menus.features import extractor
from menus.models import Food, MenuItem, Restaurant
from menus.tests.test_extract_features import FakeLLM

NO_KEYS = {"METCHU_MENU_MODEL": "", "GOOGLE_API_KEY": "", "GEMINI_API_KEY": "", "OPENAI_API_KEY": ""}


class MenuModelTests(SimpleTestCase):
    def env(self, **values):
        patcher = mock.patch.dict(os.environ, NO_KEYS | values)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_is_gemini_with_the_google_key(self):
        self.env()
        self.assertEqual(llm.configured(), ("google", "gemini-3.5-flash"))
        self.assertEqual(llm.key_name(), "GOOGLE_API_KEY")
        self.assertFalse(llm.api_key_available())
        self.env(GEMINI_API_KEY="key")
        self.assertTrue(llm.api_key_available())

    def test_openai_model_needs_the_openai_key(self):
        self.env(METCHU_MENU_MODEL="openai:gpt-5.4-mini", GOOGLE_API_KEY="key")
        self.assertEqual(llm.model_id(), "openai:gpt-5.4-mini")
        self.assertEqual(llm.key_name(), "OPENAI_API_KEY")
        self.assertFalse(llm.api_key_available())
        self.env(METCHU_MENU_MODEL="openai:gpt-5.4-mini", OPENAI_API_KEY="key")
        self.assertTrue(llm.api_key_available())

    def test_malformed_setting_is_refused(self):
        for value in ("gpt-5.4-mini", "anthropic:claude", "openai:"):
            self.env(METCHU_MENU_MODEL=value)
            with self.assertRaisesMessage(ValueError, "METCHU_MENU_MODEL"):
                llm.configured()

    def test_openai_client_uses_the_configured_model(self):
        self.env(METCHU_MENU_MODEL="openai:gpt-5.4-mini", OPENAI_API_KEY="key")
        structured = extractor.build_llm()  # builds the client; no network call
        self.assertEqual(structured.first.model_name, "gpt-5.4-mini")


class ExtractionRecordsTheModelTests(TestCase):
    def setUp(self):
        hall = Restaurant.objects.create(code="hall", name="학생회관식당")
        food = Food.objects.create(name="육개장", is_food=True)
        MenuItem.objects.create(date=datetime.date(2026, 10, 20), meal="LU", restaurant=hall,
                                raw_name="육개장", food=food, price=5000)

    def run_command(self, **env):
        with mock.patch.dict(os.environ, NO_KEYS | env), \
                mock.patch.object(extractor, "build_llm", return_value=FakeLLM()):
            call_command("extract_features", "--date", "2026-10-20", stdout=io.StringIO())

    def test_the_configured_model_is_stored(self):
        self.run_command(METCHU_MENU_MODEL="openai:gpt-5.4-mini", OPENAI_API_KEY="key")
        self.assertEqual(Food.objects.get(name="육개장").extraction_model, "openai:gpt-5.4-mini")

    def test_missing_key_names_the_configured_provider(self):
        with self.assertRaisesMessage(CommandError, "OPENAI_API_KEY"):
            self.run_command(METCHU_MENU_MODEL="openai:gpt-5.4-mini", GOOGLE_API_KEY="key")
