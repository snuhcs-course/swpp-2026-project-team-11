# AI-generated: written with Codex (OpenAI) and reviewed by the team.
"""Extract bounded feature moments from preprocessed dish names."""
from __future__ import annotations
import math
import os
from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator
from .prompt import SYSTEM_PROMPT, build_user_message
from .schema import LLM_FEATURES

MODEL = "gemini-3.5-flash"

class FeatureStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mean: float = Field(ge=0, le=1)
    std: float = Field(ge=0, le=0.5)

    @field_validator("mean", "std", mode="before")
    @classmethod
    def finite_number(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Expected a finite number")
        if abs(value - round(value, 2)) > 1e-9:
            raise ValueError("Use at most two decimal places")
        return value

    @model_validator(mode="after")
    def bounded_variance(self):
        if self.std ** 2 > self.mean * (1 - self.mean) + 1e-12:
            raise ValueError("Variance exceeds the bound for a measurement in [0, 1]")
        return self

FoodFeatures = create_model(
    "FoodFeatures", __config__=ConfigDict(extra="forbid"),
    **{f.key: (FeatureStats, Field(description=f.guide)) for f in LLM_FEATURES},
)

class FoodAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_name: str = Field(description="입력 메뉴 이름을 그대로 복사")
    features: FoodFeatures

class FoodBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[FoodAnnotation]

def api_key_available() -> bool:
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))

def build_llm():
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=MODEL, thinking_level="low").with_structured_output(FoodBatch)

def extract_batch(names: list[str], llm) -> dict[str, FoodAnnotation]:
    from langchain_core.messages import HumanMessage, SystemMessage
    batch = FoodBatch.model_validate(llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=build_user_message(names)),
    ]))
    wanted = set(names)
    found, duplicates = {}, set()
    for item in batch.items:
        if item.input_name in wanted:
            if item.input_name in found:
                duplicates.add(item.input_name)
            found[item.input_name] = item
    return {name: item for name, item in found.items() if name not in duplicates}

def extract(names: list[str], llm, batch_size: int = 25, on_progress=None) -> tuple[dict, list]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    names = list(dict.fromkeys(names))
    results = {}
    for start in range(0, len(names), batch_size):
        chunk = names[start:start + batch_size]
        try:
            results.update(extract_batch(chunk, llm))
        except Exception as error:
            if on_progress:
                on_progress(f"배치 실패, 하나씩 재시도: {type(error).__name__}")
        for name in chunk:
            if name in results:
                continue
            try:
                results.update(extract_batch([name], llm))
            except Exception as error:
                if on_progress:
                    on_progress(f"실패: {name} ({type(error).__name__})")
        if on_progress:
            on_progress(f"{min(start + batch_size, len(names))}/{len(names)} 처리")
    return results, [name for name in names if name not in results]
