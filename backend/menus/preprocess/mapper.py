# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Resolve menu lines to dishes.

    map_lines({dish_key: cleaned name}, llm) -> {dish_key: Mapping}

Sources, first match wins:
  1. overrides.json "lines": a person's correction for that line
  2. fixed_menus.json: reviewed rules for lines a cafeteria serves every day
  3. MenuLine cache from an earlier run (LLM answers under PREPROCESS_VERSION)
  4. the LLM, for lines never resolved before (answers are cached in MenuLine)
  5. rule fallback: the whole line is one dish, named as it was first seen.
     Used without an API key or when the LLM fails; a later run retries the LLM.
Finally overrides.json "dishes" merges dish names in every answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from pydantic import BaseModel, Field

from menus.models import MenuLine

from . import fixed, overrides
from .prompt import SYSTEM_PROMPT, build_user_message

PREPROCESS_VERSION = "v1"
MODEL = "gemini-3.5-flash"
NAME_MAX = 300   # MenuLine.name / Food.name max_length; Postgres enforces it
DISH_MAX = 50    # a canonical dish name is short; longer means the model misbehaved


@dataclass(frozen=True)
class Mapping:
    is_meal: bool
    dishes: tuple[str, ...]  # canonical dish names, empty when not a meal
    source: str              # where the answer came from: "llm", "rule", ...


class LineDishes(BaseModel):
    input_name: str = Field(description="입력 메뉴 줄을 그대로 복사")
    is_meal: bool = Field(description="한 끼 식사로 고를 수 있는 메뉴인가")
    dishes: list[str] = Field(max_length=3, description="메인 요리 표준 이름 (식사가 아니면 빈 목록)")


class LineBatch(BaseModel):
    items: list[LineDishes]


def build_llm():
    """The real Gemini client. Replace this in tests."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model=MODEL, thinking_level="low").with_structured_output(LineBatch)


def _loose(name: str) -> str:
    """Match key for echoed names: the model sometimes adds "3. " or changes spacing."""
    return "".join(re.sub(r"^\s*\d+\.\s*", "", name).split())


def _valid(item: LineDishes) -> tuple[bool, tuple[str, ...]] | None:
    """Clean one answer, or None when it is unusable (then the rule fallback applies)."""
    dishes = tuple(dict.fromkeys(d.strip() for d in item.dishes if d.strip()))
    if item.is_meal and not dishes:
        return None
    if any(len(d) > DISH_MAX for d in dishes):
        return None
    return (True, dishes) if item.is_meal else (False, ())


def _ask(llm, names: list[str], known: list[str]) -> dict[str, tuple[bool, tuple[str, ...]]]:
    from langchain_core.messages import HumanMessage, SystemMessage

    batch = llm.invoke([SystemMessage(content=SYSTEM_PROMPT),
                        HumanMessage(content=build_user_message(names, known))])
    wanted = {_loose(name): name for name in names}
    found = {}
    for item in batch.items:
        name = wanted.get(_loose(item.input_name))
        if name is None and len(names) == 1 and len(batch.items) == 1:
            name = names[0]  # a single answer can only be for the single line
        answer = _valid(item) if name else None
        if answer is not None:
            found[name] = answer
    return found


def resolve_with_llm(names: list[str], llm, known: list[str], batch_size: int = 25,
                     on_progress=None) -> dict[str, tuple[bool, tuple[str, ...]]]:
    """Ask the LLM batch by batch, retrying misses one by one.

    Batches run in order and every new dish name is added to `known`, so later
    batches reuse the names earlier ones chose.
    """
    known = list(known)
    results: dict[str, tuple[bool, tuple[str, ...]]] = {}
    for start in range(0, len(names), batch_size):
        chunk = names[start:start + batch_size]
        try:
            results.update(_ask(llm, chunk, known))
        except Exception as error:  # invalid JSON, a network error, a quota error...
            if on_progress:
                on_progress(f"  배치 실패, 하나씩 재시도: {type(error).__name__}"[:200])
        for name in chunk:
            if name not in results:
                try:
                    results.update(_ask(llm, [name], known))
                except Exception as error:
                    if on_progress:
                        on_progress(f"  실패: {name} ({type(error).__name__})")
        for name in chunk:
            for dish in results.get(name, (True, ()))[1]:
                if dish not in known:
                    known.append(dish)
        if on_progress:
            on_progress(f"  메뉴 줄 {min(start + batch_size, len(names))}/{len(names)} 처리")
    return results


def known_dishes(catalog_entries: dict | None = None, extra=()) -> list[str]:
    """Canonical dish names chosen so far (cache, fixed catalog, overrides), for the LLM to reuse."""
    names = {dish for entry in (catalog_entries or {}).values() for dish in entry["dishes"]}
    names.update(extra)
    for dishes in MenuLine.objects.filter(source=MenuLine.Source.LLM,
                                          version=PREPROCESS_VERSION).values_list("dishes", flat=True):
        names.update(dishes)
    return sorted(names)


def map_lines(lines: dict[str, str], llm=None, on_progress=None,
              use_catalog: bool = True) -> dict[str, Mapping]:
    """Return a Mapping for every key of `lines` ({dish_key: cleaned name}).

    use_catalog=False skips fixed_menus.json; build_fixed_menus uses it to resolve
    lines for a new catalog.
    """
    line_overrides, renames = overrides.load_overrides()
    catalog = fixed.catalog_lines(fixed.load_catalog()) if use_catalog else {}
    result: dict[str, Mapping] = {}
    for key in lines:
        if key in line_overrides:
            dishes = tuple(line_overrides[key])
            result[key] = Mapping(bool(dishes), dishes, "override")
        elif key in catalog:
            result[key] = Mapping(catalog[key]["is_meal"], tuple(catalog[key]["dishes"]), "fixed")

    cached = {line.key: line for line in MenuLine.objects.filter(key__in=lines)}
    for key, line in cached.items():
        if key in result:
            continue
        if line.source == MenuLine.Source.LLM and line.version == PREPROCESS_VERSION:
            result[key] = Mapping(line.is_meal, tuple(line.dishes), line.source)

    pending = {key: name for key, name in lines.items() if key not in result}
    if llm is not None and pending:
        extra = {d for dishes in line_overrides.values() for d in dishes} | set(renames.values())
        answers = resolve_with_llm(list(pending.values()), llm, known_dishes(catalog, extra),
                                   on_progress=on_progress)
        rows = []
        for key, name in pending.items():
            if name in answers:
                is_meal, dishes = answers[name]
                result[key] = Mapping(is_meal, dishes, MenuLine.Source.LLM)
                rows.append(MenuLine(key=key, name=cached[key].name if key in cached else name[:NAME_MAX],
                                     is_meal=is_meal, dishes=list(dishes),
                                     source=MenuLine.Source.LLM, version=PREPROCESS_VERSION))
        MenuLine.objects.bulk_create(rows, update_conflicts=True, unique_fields=["key"],
                                     update_fields=["is_meal", "dishes", "source", "version"])

    new_rule_lines = []
    for key, name in lines.items():
        if key in result:
            continue
        # Keep the name first seen, so spacing variants keep pointing at one Food.
        first_name = cached[key].name if key in cached else name[:NAME_MAX]
        result[key] = Mapping(True, (first_name,), MenuLine.Source.RULE)
        if key not in cached:
            new_rule_lines.append(MenuLine(key=key, name=first_name, dishes=[first_name],
                                           source=MenuLine.Source.RULE))
    MenuLine.objects.bulk_create(new_rule_lines, ignore_conflicts=True)
    if renames:
        result = {key: replace(m, dishes=overrides.rename(m.dishes, renames)) for key, m in result.items()}
    return result
