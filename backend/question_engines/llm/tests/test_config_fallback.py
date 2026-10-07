import logging
import random
from unittest import mock

from django.test import SimpleTestCase

from .. import engine as llm_engine
from ..config import DEFAULT_MODEL, DEFAULT_TIMEOUT_S, MIN_TIMEOUT_S, GeminiSettings, LLMConfigError, build_llm
from ..engine import InvalidTurn, LLMEngine, failure_reason
from ..prompt import FALLBACK_QUESTIONS
from .helpers import CANDIDATES, FakeLLM, ask, check_step, recommend

BROTH = "Do you feel like something with broth?"


class GeminiSettingsTests(SimpleTestCase):
    def test_reads_key_and_defaults(self):
        settings = GeminiSettings.from_env({"GOOGLE_API_KEY": "secret-key"})
        self.assertEqual((settings.api_key, settings.model, settings.timeout_s),
                         ("secret-key", DEFAULT_MODEL, DEFAULT_TIMEOUT_S))
        self.assertNotIn("secret-key", repr(settings))

    def test_gemini_api_key_and_overrides(self):
        settings = GeminiSettings.from_env({"GEMINI_API_KEY": "k", "METCHU_LLM_MODEL": "gemini-x",
                                            "METCHU_LLM_TIMEOUT": "12.5"})
        self.assertEqual((settings.api_key, settings.model, settings.timeout_s), ("k", "gemini-x", 12.5))

    def test_missing_key_is_a_clear_error(self):
        for environ in [{}, {"GOOGLE_API_KEY": "  "}]:
            with self.assertRaisesMessage(LLMConfigError, "GOOGLE_API_KEY"):
                GeminiSettings.from_env(environ)

    def test_bad_timeout_is_a_clear_error(self):
        for timeout in ["abc", "0", "-1", "8", "9.9", "inf", "nan"]:
            with self.assertRaisesMessage(LLMConfigError, "METCHU_LLM_TIMEOUT"):
                GeminiSettings.from_env({"GOOGLE_API_KEY": "k", "METCHU_LLM_TIMEOUT": timeout})

    def test_client_gets_the_timeout_and_makes_one_request(self):
        llm = build_llm(GeminiSettings(api_key="k", timeout_s=12.0))
        self.assertEqual((llm.timeout, llm.max_retries), (12.0, 1))

    def test_default_timeout_is_accepted_by_gemini(self):
        self.assertGreaterEqual(DEFAULT_TIMEOUT_S, MIN_TIMEOUT_S)
        self.assertEqual(GeminiSettings.from_env({"GOOGLE_API_KEY": "k", "METCHU_LLM_TIMEOUT": "10"}).timeout_s, 10)

    def test_only_the_afc_notice_is_silenced(self):
        build_llm(GeminiSettings(api_key="k"))
        build_llm(GeminiSettings(api_key="k"))
        sdk_logger = logging.getLogger("google_genai.models")
        with self.assertLogs(sdk_logger, "WARNING") as logs:
            sdk_logger.warning("Direct use of automatic function calling (AFC) in Models.generate_content")
            sdk_logger.warning("something else")
        self.assertEqual(logs.output, ["WARNING:google_genai.models:something else"])
        self.assertEqual(len(sdk_logger.filters), 1)

    def test_engine_builds_gemini_from_the_environment(self):
        with mock.patch.dict("os.environ", {"GOOGLE_API_KEY": "k"}, clear=True), \
                mock.patch.object(llm_engine, "build_llm", return_value="gemini") as build:
            engine = LLMEngine(CANDIDATES)
        self.assertEqual(engine.llm, "gemini")
        self.assertEqual(build.call_args.args[0].api_key, "k")

    def test_engine_without_key_fails_fast(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(LLMConfigError):
                LLMEngine(CANDIDATES)


class FallbackTests(SimpleTestCase):
    def setUp(self):
        patcher = mock.patch.object(llm_engine.logger, "warning")
        self.log_warning = patcher.start()
        self.addCleanup(patcher.stop)

    def engine(self, *replies, **config):
        self.llm = FakeLLM(*replies)
        return LLMEngine(CANDIDATES, llm=self.llm, config=config, rng=random.Random(0))

    def last_call(self, engine):
        return engine.diagnostics()["llm_calls"][-1]

    def test_invalid_turn_is_retried(self):
        engine = self.engine(ask(" "), ask(BROTH))
        self.assertEqual(engine.start()["text"], BROTH)
        self.assertEqual(self.last_call(engine)["attempts"], 2)
        self.assertIsNone(self.last_call(engine)["fallback"])

    def test_timeout_falls_back_to_a_fixed_question(self):
        engine = self.engine(TimeoutError(), TimeoutError())
        step = engine.start()
        check_step(self, step)
        self.assertEqual(step["text"], FALLBACK_QUESTIONS[0])
        self.assertEqual(self.last_call(engine)["fallback"], "timeout")
        self.assertEqual(engine.diagnostics()["fallback_count"], 1)
        self.assertEqual(self.log_warning.call_count, 2)  # one line per failed attempt

    def test_network_error(self):
        engine = self.engine(ConnectionError(), ConnectionError())
        engine.start()
        self.assertEqual(self.last_call(engine)["fallback"], "error")

    def test_food_outside_the_list_is_invalid_output(self):
        engine = self.engine(recommend("짜장면"), recommend("짜장면"))
        engine.start()
        self.assertEqual(self.last_call(engine)["fallback"], "invalid_output")

    def test_fallback_skips_questions_already_asked(self):
        engine = self.engine(ask(FALLBACK_QUESTIONS[0].lower()), TimeoutError(), TimeoutError())
        step = engine.answer(engine.start()["question_id"], "yes")
        self.assertEqual(step["text"], FALLBACK_QUESTIONS[1])

    def test_no_question_left_falls_back_to_a_random_guess(self):
        engine = self.engine(ask(BROTH), TimeoutError(), TimeoutError(), max_questions=1)
        step = engine.answer(engine.start()["question_id"], "yes")
        check_step(self, step)
        self.assertEqual(step["type"], "guess")
        self.assertIn(step["food"]["food_id"], [c["food_id"] for c in CANDIDATES])

    def test_recommend_now_falls_back_to_a_guess(self):
        engine = self.engine(ask(BROTH), ValueError(), ValueError())
        engine.start()
        self.assertEqual(engine.recommend_now()["type"], "guess")

    def test_fallback_guess_never_offers_a_rejected_menu(self):
        for seed in range(10):
            llm = FakeLLM(ask(BROTH), recommend("물냉면"), ValueError(), ValueError())
            engine = LLMEngine(CANDIDATES, llm=llm, config={"max_questions": 1}, rng=random.Random(seed))
            step = engine.answer(engine.start()["question_id"], "no")
            step = engine.feedback(step["guess_id"], False)
            self.assertEqual(step["type"], "guess")
            self.assertNotEqual(step["food"]["display_name"], "물냉면")

    def test_failure_reason(self):
        class ReadTimeout(Exception):  # what httpx raises when Gemini is too slow
            pass

        self.assertEqual(failure_reason(ReadTimeout()), "timeout")
        self.assertEqual(failure_reason(InvalidTurn()), "invalid_output")
        self.assertEqual(failure_reason(RuntimeError()), "error")
