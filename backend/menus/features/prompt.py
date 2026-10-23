# AI-generated: written with Codex (OpenAI) and reviewed by the team.
"""The accepted food-name rubric, without recommendation questions."""
from __future__ import annotations
import json
from pathlib import Path
from .schema import LLM_FEATURE_KEYS, RUBRIC

PROMPT_VERSION = RUBRIC["prompt_version"]
_INSTRUCTIONS = Path(__file__).with_name("instructions.txt").read_text(encoding="utf-8").strip()
_RUBRIC = {feature["key"]: feature for feature in RUBRIC["features"]}

def build_system_prompt(feature_order=LLM_FEATURE_KEYS) -> str:
    """The rubric prompt with its features in `feature_order` (the stability benchmark shuffles it)."""
    if sorted(feature_order) != sorted(LLM_FEATURE_KEYS):
        raise ValueError("feature_order must list every LLM feature key once")
    blocks = [_INSTRUCTIONS, "출력 feature key 순서\n" + ", ".join(feature_order)]
    for number, key in enumerate(feature_order, 1):
        feature = _RUBRIC[key]
        blocks.append(
            f"\n{number}. {feature['label_en']} | {feature['label_ko']} | {feature['key']}\n"
            f"정의: {feature['definition']}\n구분 규칙:\n"
            + "\n".join("- " + rule for rule in feature["distinction_rules"])
            + "\n평균 판단: " + feature["mean_guidance"]
            + "\n표준편차 판단: " + feature["std_guidance"] + "\n"
        )
    return "\n".join(blocks)

SYSTEM_PROMPT = build_system_prompt()

def build_user_message(names: list[str]) -> str:
    return json.dumps({"items": [{"input_name": name} for name in names]}, ensure_ascii=False)
