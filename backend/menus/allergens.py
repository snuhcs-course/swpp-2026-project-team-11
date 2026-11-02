"""The 19 allergens Korean food labels must declare, tagged from dish names.

    ALLERGEN_KEYS                 what POST /api/sessions/ accepts as "allergies"
    extract(names, llm)           -> ({name: AllergenAnnotation}, failed names)

A dish is tagged with every allergen its usual recipe may contain, sauces, broths
and batters included, so that a hard filter errs towards excluding it. Changing
the list or the prompt bumps ALLERGEN_VERSION, which re-tags every food; the
client offers the same keys (client/.../data/model/Allergen.kt).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from menus import llm
from menus.features import extractor

ALLERGEN_VERSION = "a1"
ALLERGENS = {
    "egg": "알류(가금류의 알)",
    "milk": "우유",
    "buckwheat": "메밀",
    "peanut": "땅콩",
    "soybean": "대두",
    "wheat": "밀",
    "mackerel": "고등어",
    "crab": "게",
    "shrimp": "새우",
    "pork": "돼지고기",
    "peach": "복숭아",
    "tomato": "토마토",
    "sulfite": "아황산류",
    "walnut": "호두",
    "chicken": "닭고기",
    "beef": "쇠고기",
    "squid": "오징어",
    "shellfish": "조개류(굴, 전복, 홍합 포함)",
    "pine_nut": "잣",
}
ALLERGEN_KEYS = tuple(ALLERGENS)

SYSTEM_PROMPT = "\n".join([
    "한국 대학 구내식당의 메뉴 이름을 보고, 그 요리에 들어갈 수 있는 알레르기 유발물질을 표시한다.",
    "통상적인 조리법에 들어갈 가능성이 조금이라도 있으면 그 key를 넣는다. 양념, 소스, 육수, 튀김옷, "
    "빵가루와 가공품(간장, 된장, 고추장, 마요네즈, 버터, 햄, 소시지, 어묵, 면 등)의 원료도 포함한다.",
    "이 표시는 알레르기가 있는 사용자에게서 메뉴를 빼는 데 쓰인다. 들어가지 않는다고 확신할 때만 뺀다.",
    "input_name은 입력 그대로 복사하고, 입력된 메뉴마다 한 번씩 답한다.",
    "",
    "알레르기 유발물질 key",
    *(f"- {key}: {label}" for key, label in ALLERGENS.items()),
])


class AllergenAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_name: str = Field(description="입력 메뉴 이름을 그대로 복사")
    allergens: list[Literal[ALLERGEN_KEYS]]

    def keys(self) -> list[str]:
        """The tagged keys once each, in ALLERGEN_KEYS order."""
        return [key for key in ALLERGEN_KEYS if key in self.allergens]


class AllergenBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[AllergenAnnotation]


def build_llm():
    """The configured model (menus/llm.py). Replace this in tests."""
    return llm.build(AllergenBatch)


def extract(names: list[str], model, batch_size: int = 25, on_progress=None) -> tuple[dict, list]:
    return extractor.extract(names, model, batch_size, on_progress,
                             system_prompt=SYSTEM_PROMPT, batch_model=AllergenBatch)
