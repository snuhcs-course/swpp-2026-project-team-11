# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Gemini settings for the LLM engine, read from the environment.

    GOOGLE_API_KEY (or GEMINI_API_KEY)   required; manage.py loads it from the repo-root .env
    METCHU_LLM_MODEL                     optional, default DEFAULT_MODEL
    METCHU_LLM_TIMEOUT                   optional, seconds per LLM call, default DEFAULT_TIMEOUT_S;
                                         Gemini rejects deadlines under MIN_TIMEOUT_S

The key is only handed to the Gemini client; it is kept out of repr() and logs.
"""
from dataclasses import dataclass, field
import logging
import os

DEFAULT_MODEL = "gemini-3.5-flash-lite"  # fast, and its free-tier quota is separate from 3.5-flash
MIN_TIMEOUT_S = 10.0  # "Manually set deadline ... is too short. Minimum allowed deadline is 10s."
DEFAULT_TIMEOUT_S = MIN_TIMEOUT_S


class LLMConfigError(RuntimeError):
    """The engine cannot reach Gemini: no API key, or a malformed setting."""


@dataclass(frozen=True)
class GeminiSettings:
    api_key: str = field(repr=False)
    model: str = DEFAULT_MODEL
    timeout_s: float = DEFAULT_TIMEOUT_S

    @classmethod
    def from_env(cls, environ=None):
        environ = os.environ if environ is None else environ
        api_key = (environ.get("GOOGLE_API_KEY") or environ.get("GEMINI_API_KEY") or "").strip()
        if not api_key:
            raise LLMConfigError("GOOGLE_API_KEY is not set. Put it in the repo-root .env file.")
        raw_timeout = environ.get("METCHU_LLM_TIMEOUT") or str(DEFAULT_TIMEOUT_S)
        try:
            timeout_s = float(raw_timeout)
        except ValueError:
            timeout_s = 0.0
        if not MIN_TIMEOUT_S <= timeout_s < float("inf"):
            raise LLMConfigError(f"METCHU_LLM_TIMEOUT must be at least {MIN_TIMEOUT_S:g} seconds, "
                                 f"Gemini's minimum deadline: {raw_timeout!r}")
        return cls(api_key=api_key, model=environ.get("METCHU_LLM_MODEL") or DEFAULT_MODEL, timeout_s=timeout_s)


def _drop_afc_notice(record):
    return not record.getMessage().startswith("Direct use of automatic function calling")


def build_llm(settings):
    """The real Gemini chat model. Replace this in tests."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    # google-genai warns about automatic function calling on the first call unless a
    # request disables it, which langchain-google-genai 4.4 cannot do. The engine
    # sends no tools, so that warning is noise; every other SDK warning still shows.
    afc_logger = logging.getLogger("google_genai.models")
    if _drop_afc_notice not in afc_logger.filters:
        afc_logger.addFilter(_drop_afc_notice)

    # max_retries=1 means a single request: the engine retries and falls back itself,
    # so one slow call cannot stall a session for the client's default six attempts.
    return ChatGoogleGenerativeAI(model=settings.model, api_key=settings.api_key,
                                  timeout=settings.timeout_s, max_retries=1, thinking_level="low")
