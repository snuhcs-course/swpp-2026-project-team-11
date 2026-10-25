# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""The chat model behind menu preprocessing and feature extraction.

    METCHU_MENU_MODEL   "<provider>:<model>", default DEFAULT
                        google: Gemini with GOOGLE_API_KEY (or GEMINI_API_KEY)
                        openai: OpenAI with OPENAI_API_KEY, e.g. openai:gpt-5.4-mini

ModelSetting reads any such variable; the engine benchmark's simulated user uses
one too (question_engines/benchmark/simulator.py). The question engines choose
their models elsewhere (question_engines/llm/config.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT = "google:gemini-3.5-flash"
KEYS = {"google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"), "openai": ("OPENAI_API_KEY",)}


@dataclass(frozen=True)
class ModelSetting:
    variable: str
    default: str

    def configured(self) -> tuple[str, str]:
        """(provider, model) from the variable."""
        value = (os.environ.get(self.variable) or self.default).strip()
        provider, _, model = value.partition(":")
        if provider not in KEYS or not model:
            raise ValueError(f"{self.variable} must look like google:gemini-3.5-flash "
                             f"or openai:gpt-5.4-mini: {value!r}")
        return provider, model

    def model_id(self) -> str:
        """The configured model as "<provider>:<model>", as stored in Food.extraction_model."""
        return ":".join(self.configured())

    def key_name(self) -> str:
        return KEYS[self.configured()[0]][0]

    def api_key_available(self) -> bool:
        return any(os.environ.get(name) for name in KEYS[self.configured()[0]])

    def chat(self):
        """The configured chat model."""
        provider, model = self.configured()
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(model=model)
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, thinking_level="low")


MENU = ModelSetting("METCHU_MENU_MODEL", DEFAULT)
configured, model_id, key_name, api_key_available = (MENU.configured, MENU.model_id, MENU.key_name,
                                                     MENU.api_key_available)


def build(schema):
    """The menu model, answering with `schema` (structured output)."""
    return MENU.chat().with_structured_output(schema)
