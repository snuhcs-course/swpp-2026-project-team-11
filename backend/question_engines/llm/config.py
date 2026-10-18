"""OpenRouter settings for the LLM engine, read from the environment.

    OPENROUTER_API_KEY                   required; manage.py loads it from the repo-root .env
    METCHU_LLM_MODEL                     optional, an OpenRouter model ID, default DEFAULT_MODEL
    METCHU_LLM_TIMEOUT                   optional, seconds per LLM call, default DEFAULT_TIMEOUT_S

The key is only handed to the OpenRouter client; it is kept out of repr() and logs.
"""
from dataclasses import dataclass, field
import math
import os

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-3.5-flash-lite"  # fast and cheap; the prompt is tuned on it
DEFAULT_TIMEOUT_S = 10.0


class LLMConfigError(RuntimeError):
    """The engine cannot reach the LLM: no API key, or a malformed setting."""


@dataclass(frozen=True)
class LLMSettings:
    api_key: str = field(repr=False)
    model: str = DEFAULT_MODEL
    timeout_s: float = DEFAULT_TIMEOUT_S

    @classmethod
    def from_env(cls, environ=None):
        environ = os.environ if environ is None else environ
        api_key = (environ.get("OPENROUTER_API_KEY") or "").strip()
        if not api_key:
            raise LLMConfigError("OPENROUTER_API_KEY is not set. Put it in the repo-root .env file.")
        raw_timeout = environ.get("METCHU_LLM_TIMEOUT") or str(DEFAULT_TIMEOUT_S)
        try:
            timeout_s = float(raw_timeout)
        except ValueError:
            timeout_s = 0.0
        if not 0 < timeout_s < math.inf:
            raise LLMConfigError(f"METCHU_LLM_TIMEOUT must be a positive number of seconds: {raw_timeout!r}")
        return cls(api_key=api_key, model=environ.get("METCHU_LLM_MODEL") or DEFAULT_MODEL, timeout_s=timeout_s)


def build_llm(settings):
    """The real chat model, through OpenRouter's OpenAI-compatible API. Replace this in tests."""
    from langchain_openai import ChatOpenAI

    # max_retries=0 means a single request: the engine retries and falls back itself.
    # require_parameters routes only to providers that honour the JSON schema, so the
    # food enum is enforced. Low reasoning effort keeps a step at about a second.
    return ChatOpenAI(model=settings.model, api_key=settings.api_key, base_url=OPENROUTER_BASE_URL,
                      timeout=settings.timeout_s, max_retries=0,
                      extra_body={"provider": {"require_parameters": True}, "reasoning": {"effort": "low"}})
