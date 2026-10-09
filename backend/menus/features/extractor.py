# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Tag dishes with feature probabilities using Gemini structured output.

`extract_batch()` takes the LLM as an argument so tests can pass a fake one and
run without an API key (same seam as `describe()` in the App-Integration lab).
"""

from __future__ import annotations

import os
import re

from pydantic import BaseModel, Field, create_model

from .prompt import SYSTEM_PROMPT, build_user_message
from .schema import FEATURES

MODEL = "gemini-3.5-flash"

# One float field per feature, generated from the schema so the two cannot drift.
FoodFeatures = create_model(
    "FoodFeatures",
    **{
        f.key: (float, Field(ge=0.0, le=1.0, description=f"{f.question} - {f.guide}"))
        for f in FEATURES
    },
)


class FoodAnnotation(BaseModel):
    input_name: str = Field(description="입력 메뉴 이름을 그대로 복사")
    is_food: bool = Field(description="한 끼 식사로 추천할 만한 메뉴인가")
    display_name: str = Field(description="15자 이내의 짧은 이름")
    food_group: str = Field(description="한국어 상위 분류 하나")
    features: FoodFeatures


class FoodBatch(BaseModel):
    items: list[FoodAnnotation]


def api_key_available() -> bool:
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))


def build_llm():
    """The real Gemini client. Replace this in tests."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    # Temperature is left unset: for Gemini 3 models langchain-google-genai keeps
    # Google's default, which Google recommends. The few-shot examples keep scores stable.
    return ChatGoogleGenerativeAI(model=MODEL, thinking_level="low").with_structured_output(FoodBatch)


def _key(name: str) -> str:
    """Loose match key: the model sometimes echoes "3. 육개장" or changes spacing."""
    return "".join(re.sub(r"^\s*\d+\.\s*", "", name).split())


def extract_batch(names: list[str], llm) -> dict[str, FoodAnnotation]:
    """Tag `names` in one call. Returns {name: annotation} for the names the model answered."""
    from langchain_core.messages import HumanMessage, SystemMessage

    batch = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=build_user_message(names)),
    ])
    wanted = {_key(name): name for name in names}
    found = {}
    for item in batch.items:
        name = wanted.get(_key(item.input_name))
        if name is not None:
            found[name] = item
    if len(names) == 1 and not found and len(batch.items) == 1:
        found[names[0]] = batch.items[0]  # a single answer can only be for the single name
    return found


def extract(names: list[str], llm, batch_size: int = 25, on_progress=None) -> tuple[dict, list]:
    """Tag all `names`, batch by batch, retrying misses one at a time.

    Returns ({name: annotation}, [names that still failed]).
    """
    results: dict[str, FoodAnnotation] = {}
    for start in range(0, len(names), batch_size):
        chunk = names[start:start + batch_size]
        try:
            results.update(extract_batch(chunk, llm))
        except Exception as error:  # invalid JSON, a value out of [0, 1], a network error...
            if on_progress:
                on_progress(f"  배치 실패, 하나씩 재시도: {type(error).__name__}: {error}"[:300])
        for name in chunk:
            if name in results:
                continue
            try:
                results.update(extract_batch([name], llm))
            except Exception as error:
                if on_progress:
                    on_progress(f"  실패: {name} ({type(error).__name__})")
        if on_progress:
            on_progress(f"{min(start + batch_size, len(names))}/{len(names)} 처리")
    failed = [name for name in names if name not in results]
    return results, failed
