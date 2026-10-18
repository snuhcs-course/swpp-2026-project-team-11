# AI-generated: written with Codex (OpenAI) and reviewed by the team.
"""Versioned food measurements. Questions belong to the consuming engines."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

FEATURE_VERSION = "v2"
RUBRIC = json.loads(Path(__file__).with_name("rubric.json").read_text(encoding="utf-8"))

@dataclass(frozen=True)
class Feature:
    key: str
    question: str
    guide: str
    llm_scored: bool = True

FEATURES = tuple(
    Feature(f["key"], f"Would you like {f['label_en'].lower()} food?", f["definition"])
    for f in RUBRIC["features"]
) + (Feature("meal_variety", "Would you like several dishes in one meal?",
             "Whether preprocessing split the original menu line into multiple dishes.", False),)
LLM_FEATURES = tuple(f for f in FEATURES if f.llm_scored)
FEATURE_KEYS = tuple(f.key for f in FEATURES)
LLM_FEATURE_KEYS = tuple(f.key for f in LLM_FEATURES)
