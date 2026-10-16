import random
from unittest import mock

from django.test import SimpleTestCase

from .. import engine as llm_engine
from ..config import DEFAULT_MODEL, DEFAULT_TIMEOUT_S, OPENROUTER_BASE_URL, LLMConfigError, LLMSettings, build_llm
from ..engine import InvalidTurn, LLMEngine, failure_reason
from ..prompt import FALLBACK_QUESTIONS
from .helpers import CANDIDATES, USAGE, FakeLLM, ask, check_step, recommend

BROTH = "Do you feel like something with broth?"


class LLMSettingsTests(SimpleTestCase):
    def test_reads_key_and_defaults(self):
        settings = LLMSettings.from_env({"OPENROUTER_API_KEY": "secret-key"})
        self.assertEqual((settings.api_key, settings.model, settings.timeout_s),
                         ("secret-key", DEFAULT_MODEL, DEFAULT_TIMEOUT_S))
        self.assertNotIn("secret-key", repr(settings))

    def test_overrides(self):
        settings = LLMSettings.from_env({"OPENROUTER_API_KEY": "k", "METCHU_LLM_MODEL": "openai/gpt-x",
                                         "METCHU_LLM_TIMEOUT": "6.5"})
        self.assertEqual((settings.api_key, settings.model, settings.timeout_s), ("k", "openai/gpt-x", 6.5))

    def test_missing_key_is_a_clear_error(self):
        for environ in [{}, {"OPENROUTER_API_KEY": "  "}, {"GOOGLE_API_KEY": "gemini-only"}]:
            with self.assertRaisesMessage(LLMConfigError, "OPENROUTER_API_KEY"):
                LLMSettings.from_env(environ)

    def test_bad_timeout_is_a_clear_error(self):
        for timeout in ["abc", "0", "-1", "inf", "nan"]:
            with self.assertRaisesMessage(LLMConfigError, "METCHU_LLM_TIMEOUT"):
                LLMSettings.from_env({"OPENROUTER_API_KEY": "k", "METCHU_LLM_TIMEOUT": timeout})

    def test_client_talks_to_openrouter_once_per_call(self):
        llm = build_llm(LLMSettings(api_key="k", model="google/x", timeout_s=6.0))
        self.assertEqual((llm.model_name, llm.openai_api_base, llm.request_timeout, llm.max_retries),
                         ("google/x", OPENROUTER_BASE_URL, 6.0, 0))
        self.assertEqual(llm.extra_body["provider"], {"require_parameters": True})

    def test_engine_builds_the_client_from_the_environment(self):
        with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "k"}, clear=True), \
                mock.patch.object(llm_engine, "build_llm", return_value="client") as build:
            engine = LLMEngine(CANDIDATES)
        self.assertEqual(engine.llm, "client")
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

    def test_usage_and_cost_are_recorded_per_call(self):
        engine = self.engine(ask(" "), ask(BROTH), TimeoutError(), TimeoutError())
        engine.answer(engine.start()["question_id"], "yes")
        first, second = engine.diagnostics()["llm_calls"]
        self.assertEqual((first["input_tokens"], first["output_tokens"]),
                         (2 * USAGE["input_tokens"], 2 * USAGE["output_tokens"]))  # the invalid attempt was paid for too
        self.assertAlmostEqual(first["cost_usd"], 2 * USAGE["cost_usd"])
        self.assertEqual((second["input_tokens"], second["cost_usd"]), (0, 0.0))  # no response, nothing billed
        self.assertEqual(engine.diagnostics()["llm_tokens"], 2 * (USAGE["input_tokens"] + USAGE["output_tokens"]))
        self.assertAlmostEqual(engine.diagnostics()["llm_cost_usd"], 2 * USAGE["cost_usd"])
