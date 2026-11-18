"""One versioned 53-feature schema shared by ingestion, DT and personal RL."""
import json
from dataclasses import dataclass
from pathlib import Path

FEATURE_VERSION = "v3"
RUBRIC = json.loads((Path(__file__).parents[2] / "question_engines" / "feature_schema.json").read_text())
@dataclass(frozen=True)
class Feature:
    key: str
    question: str
    guide: str
    llm_scored: bool = True
FEATURES = tuple(Feature(f["key"], f["question"], f["definition"]) for f in RUBRIC["features"])
FEATURE_KEYS = tuple(f.key for f in FEATURES)
LLM_FEATURES = FEATURES
LLM_FEATURE_KEYS = FEATURE_KEYS
MODEL_LABELS = tuple(f["label_ko"] for f in RUBRIC["features"])
