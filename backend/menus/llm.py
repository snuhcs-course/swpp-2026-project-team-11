# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""The chat model behind menu preprocessing and feature extraction.

    METCHU_MENU_MODEL   "<provider>:<model>", default DEFAULT
                        google: Gemini with GOOGLE_API_KEY (or GEMINI_API_KEY)
                        openai: OpenAI with OPENAI_API_KEY, e.g. openai:gpt-5.4-mini

The question engines choose their models elsewhere (question_engines/llm/config.py).
"""

from __future__ import annotations

import os

DEFAULT = "google:gemini-3.5-flash"
KEYS = {"google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"), "openai": ("OPENAI_API_KEY",)}


def configured() -> tuple[str, str]:
    """(provider, model) from METCHU_MENU_MODEL."""
    value = (os.environ.get("METCHU_MENU_MODEL") or DEFAULT).strip()
    provider, _, model = value.partition(":")
    if provider not in KEYS or not model:
        raise ValueError("METCHU_MENU_MODEL must look like google:gemini-3.5-flash "
                         f"or openai:gpt-5.4-mini: {value!r}")
    return provider, model


def model_id() -> str:
    """The configured model as "<provider>:<model>", as stored in Food.extraction_model."""
    return ":".join(configured())


def key_name() -> str:
    return KEYS[configured()[0]][0]


def api_key_available() -> bool:
    return any(os.environ.get(name) for name in KEYS[configured()[0]])


def build(schema):
    """The configured chat model, answering with `schema` (structured output)."""
    provider, model = configured()
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=model)
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(model=model, thinking_level="low")
    return llm.with_structured_output(schema)
