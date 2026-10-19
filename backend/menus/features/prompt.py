# AI-generated: written with Codex (OpenAI) and reviewed by the team.
"""The accepted food-name rubric, without recommendation questions."""
from __future__ import annotations
import json
from pathlib import Path
from .schema import LLM_FEATURE_KEYS, RUBRIC

PROMPT_VERSION = RUBRIC["prompt_version"]
_blocks = [
    Path(__file__).with_name("instructions.txt").read_text(encoding="utf-8").strip(),
    "출력 feature key 순서\n" + ", ".join(LLM_FEATURE_KEYS),
]
for number, feature in enumerate(RUBRIC["features"], 1):
    _blocks.append(
        f"\n{number}. {feature['label_en']} | {feature['label_ko']} | {feature['key']}\n"
        f"정의: {feature['definition']}\n구분 규칙:\n"
        + "\n".join("- " + rule for rule in feature["distinction_rules"])
        + "\n평균 판단: " + feature["mean_guidance"]
        + "\n표준편차 판단: " + feature["std_guidance"] + "\n"
    )
SYSTEM_PROMPT = "\n".join(_blocks)

def build_user_message(names: list[str]) -> str:
    return json.dumps({"items": [{"input_name": name} for name in names]}, ensure_ascii=False)
