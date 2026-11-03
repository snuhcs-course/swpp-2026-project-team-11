"""Versioned, short display labels for raw sales-menu names."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from menus import llm
from menus.features import extractor
from menus.normalize import clean_name

LABEL_VERSION = "l1"
SYSTEM_PROMPT = """메뉴판에 적힌 원래 표현을 유지하면서 앱에 표시할 짧고 대표적인 메뉴 이름을 작성한다.
input_name은 입력 그대로 복사한다. 각 입력에 하나씩 답한다. label은 보통 20자 안팎이다.
세트는 세트 이름만 남긴다: 한입치킨 세트 - 구성 및 가격 → 한입치킨 세트.
뷔페나 코너는 핵심 메뉴를 최대 두 개만 쓴다: 핫커리 & 치킨까스, 셀프라면.
홍보 문구, 이모지, 가격과 길게 나열된 반찬은 제거한다: [인기만점] 탕수육 소(2인) → 탕수육 소(2인).
음식 이름이나 크기를 지어내거나 다른 메뉴로 바꾸지 않는다.
"""


def needs_label(name: str) -> bool:
    base = clean_name(name)[0]
    return len(base) > 20 or any(not (c.isalnum() or c.isspace() or c in "()") for c in base)


class LabelAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_name: str = Field(description="입력 메뉴 이름을 그대로 복사")
    label: str = Field(min_length=1, max_length=100, description="짧은 대표 메뉴 이름")

    @field_validator("label")
    @classmethod
    def valid_label(cls, value):
        value = " ".join(value.split())
        if not value:
            raise ValueError("A display label must not be blank")
        return value


class LabelBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[LabelAnnotation]


def build_llm():
    return llm.build(LabelBatch)


def extract(names: list[str], model, batch_size: int = 25, on_progress=None):
    return extractor.extract(names, model, batch_size, on_progress,
                             system_prompt=SYSTEM_PROMPT, batch_model=LabelBatch)
