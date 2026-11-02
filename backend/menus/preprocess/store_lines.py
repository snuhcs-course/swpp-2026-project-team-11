"""Menu lines of the restaurants near the stations -> dishes.

    entries(stores)              -> every menu line, after the free rules
    distinct_lines(entries)      -> {cache key: StoreLine}, the lines to resolve
    map_store_lines(lines, llm)  -> {cache key: Mapping}

Naver menu boards mix dishes with banners ("🔥 중식은 불향이 반입니다 🔥"), drinks and
add-ons. Rules drop the obvious ones for free: notices (is_store_notice) and drinks
(is_drink), in every kind of restaurant, bars included. The LLM resolves the rest with
the cafeteria's dish rules (store_prompt.py), so a dish has one name and one Food in
both modes.

Answers are cached in MenuLine under "store:" keys and STORE_VERSION, apart from the
cafeteria lines. A key holds everything the LLM sees: the name (by dish_key), the
restaurant's category and the description, so "김치찌개" with the same category and
description is resolved once for all restaurants. A vague line such as "A세트" or
"점심특선" is also keyed by its restaurant.

Sources, first match wins: overrides.json "lines" (matched by the dish_key of the
line's ref, so a correction of "A세트 @홍콩반점" stays with that restaurant), the cache, the LLM, then the rule fallback (the whole line is one dish, and a vague
line none). The fallback is not cached, so a later run asks the LLM again.
overrides.json "dishes" renames dishes in every answer.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace

from menus.models import MenuLine
from menus.normalize import KEY_MAX, clean_name, dish_key
from menus.sources.naver_stores import StoreRecord

from . import fixed, overrides
from .mapper import NAME_MAX, Mapping, _loose, known_dishes, resolve_with_llm
from .store_prompt import DESCRIPTION_MAX, STORE_SYSTEM_PROMPT, build_store_message

STORE_VERSION = "store-v1"
# sha256(STORE_SYSTEM_PROMPT)[:12] for this version. A prompt change bumps STORE_VERSION,
# so cached answers from the old prompt are resolved again, and updates this;
# test_store_lines checks the pair.
STORE_PROMPT_SHA256 = "7503632404bf"
KNOWN_LIMIT = 300  # dish names offered to the LLM per batch

# Emoji, dingbats, arrows, shapes and stars used to decorate menu boards.
_DECORATION = re.compile("[•※←-⇿⌀-⏿■-➿⬀-⯿"
                         "️‍\U0001f000-\U0001faff]")
_PROMO_TAG = re.compile(r"[\[(【<]\s*(?:best|new|hot|추천|인기|강추|신메뉴|대표|시그니처|베스트|사장님\s*추천)\s*[\])】>]",
                        re.IGNORECASE)
_PROMO_WORD = re.compile(r"^(?:BEST|NEW|HOT)\s+|\s+(?:BEST|NEW|HOT)$")
_LETTER = re.compile(r"[가-힣A-Za-z]")
_SENTENCE_END = re.compile(r"(?:니다|세요|해요|어요|아요|에요|예요)[.!~\s]*$")
NOTICE_WORDS = ("주차", "영업시간", "예약", "배달", "포장", "리뷰", "이벤트", "공지", "안내", "원산지", "휴무", "문의")

_PARENS = re.compile(r"\([^()]*\)")
_COMBO = re.compile(r"[&+,/]|세트|셋트")
_AMOUNT = re.compile(r"\d+(?:\.\d+)?\s*(?:ml|cc|l|병|잔|캔)?|피처|pitcher|병|잔|캔")
_DRINK_MODIFIER = re.compile(r"(?:후레쉬|후레시|프레시|fresh|오리지널|original|이즈백|제로|zero|라이트|light)$")
DRINK_SUFFIXES = ("소주", "맥주", "막걸리", "동동주", "하이볼", "와인", "사케", "칵테일", "위스키", "고량주",
                  "콜라", "사이다", "음료", "음료수", "에이드", "주스", "쥬스", "아메리카노", "라떼", "탄산수",
                  "생수", "식혜")
# Names that are drinks only on their own: "돈카스" is not a "카스" beer.
DRINK_NAMES = {"참이슬", "처음처럼", "진로", "새로", "카스", "테라", "켈리", "클라우드", "하이네켄", "칭따오",
               "아사히", "삿포로", "기린", "버드와이저", "코로나", "기네스", "호가든", "청하", "백세주", "매화수",
               "산사춘", "이과두주", "복분자주", "매실주", "청주", "양주", "보드카", "데킬라", "진토닉", "환타",
               "스프라이트", "펩시", "밀키스", "웰치스", "데미소다", "토닉워터", "우롱차", "녹차", "커피", "우유"}

# Words that say how a menu is sold, not what it is: "A세트", "2인 점심특선", "Premium Set".
_VAGUE_WORDS = re.compile(r"세트|셋트|정식|특선|코스|메뉴|런치|디너|점심|저녁|스페셜|오늘의|추천|기본|베스트|"
                          r"커플|가족|패밀리|혼밥|실속|알뜰|든든|\d+\s*인분?|\d|"
                          r"(?<![a-z])(?:set|menu|course|tasting|lunch|dinner|special|best|basic|premium|"
                          r"signature|vip|combo|[a-z])(?![a-z])")


def clean_store_name(raw: str) -> tuple[str, int | None]:
    """(menu name without decorations and promo tags, price written in the name or None)."""
    name = _PROMO_TAG.sub(" ", _DECORATION.sub(" ", raw))
    return clean_name(_PROMO_WORD.sub("", " ".join(name.split())))


def is_store_notice(raw: str, name: str, price: int | None) -> bool:
    """True for banners and notices: no letters, or no price and framed, sentence-like or a notice word."""
    if not _LETTER.search(name):
        return True
    if price is not None:
        return False
    # Banners and section headers are framed ("■□세트 메뉴□■"); a dish is at most marked ("★모둠회").
    raw = raw.strip()
    framed = bool(_DECORATION.match(raw)) and bool(_DECORATION.match(raw[-1]))
    # A notice word in parentheses is a note on a dish: "한우등심(예약시 주문가능)".
    outside = _PARENS.sub("", name)
    return (framed or bool(_SENTENCE_END.search(name)) or "!" in name
            or len(name) > 30 or any(word in outside for word in NOTICE_WORDS))


def is_drink(name: str) -> bool:
    """True when the name is only a drink ("생맥주 500cc", "참이슬 후레쉬"), not a dish with one ("맥주 수육")."""
    name = _PARENS.sub("", name.lower())
    if _COMBO.search(name):
        return False  # "해물파전&막걸리" is a set with a dish; the LLM decides
    key = _DRINK_MODIFIER.sub("", re.sub(r"[^가-힣a-z]", "", _AMOUNT.sub("", name)))
    return bool(key) and (key in DRINK_NAMES or key.endswith(DRINK_SUFFIXES))


def is_vague(name: str) -> bool:
    """True when the name alone does not tell the dish ("A세트", "점심특선", "2인 커플세트").

    A name without such words is a dish however short ("죽", "Carbonara").
    """
    lowered = name.lower()
    rest = _VAGUE_WORDS.sub("", lowered)
    return rest != lowered and len(_LETTER.findall(rest)) < 2


def allergen_text(raw_name: str, description: str) -> str:
    """What the allergen model reads for a menu line: the whole line, sides included."""
    name, _ = clean_store_name(raw_name)
    return f"{name} ({description[:DESCRIPTION_MAX]})" if description else name


def line_key(store_code: str, name: str, category: str = "", description: str = "") -> str:
    """Equal for lines the LLM sees alike: the same dish_key, category and description."""
    context = hashlib.sha256(f"{category}\n{description[:DESCRIPTION_MAX]}".encode("utf-8")).hexdigest()[:10]
    scope = f"{store_code}:" if is_vague(name) else ""
    return f"store:{scope}{context}:{dish_key(name)}"[:KEY_MAX]


@dataclass(frozen=True)
class Entry:
    """One menu line of one restaurant, after the free rules."""

    store: StoreRecord
    raw_name: str
    name: str
    price: int | None
    description: str  # whitespace collapsed
    dropped: str  # "notice" or "drink" when a rule dropped the line
    key: str      # cache key of a line that was kept


@dataclass(frozen=True)
class StoreLine:
    ref: str          # the name, or "A세트 @홍콩반점" for a vague line; overrides.json "lines" use it
    label: str        # the ref made unique within a run: what the LLM sees and copies back
    name: str
    category: str
    description: str


def entries(stores: list[StoreRecord]) -> list[Entry]:
    result = []
    for store in stores:
        for menu in store.menus:
            name, price_in_name = clean_store_name(menu.name)
            price = menu.price if menu.price is not None else price_in_name
            description = " ".join(menu.description.split())
            dropped = "notice" if is_store_notice(menu.name, name, price) else "drink" if is_drink(name) else ""
            result.append(Entry(store, menu.name, name, price, description, dropped,
                                "" if dropped else line_key(store.code, name, store.category, description)))
    return result


def distinct_lines(entries: list[Entry]) -> dict[str, StoreLine]:
    """One StoreLine per cache key; a vague line is referred to with its restaurant ("A세트 @홍콩반점").

    Lines of one name with another category or description get labels "떡볶이 #2", ...
    Labels differ as the LLM's answers are matched (_loose), so "떡 볶이" is "떡 볶이 #2" too.
    """
    lines, labels = {}, set()
    for entry in entries:
        if entry.dropped or entry.key in lines:
            continue
        ref = f"{entry.name} @{entry.store.name}" if is_vague(entry.name) else entry.name
        label, n = ref, 2
        while _loose(label) in labels:
            label, n = f"{ref} #{n}", n + 1
        labels.add(_loose(label))
        lines[entry.key] = StoreLine(ref, label, entry.name, entry.store.category, entry.description)
    return lines


def known_answers(lines: dict[str, StoreLine]) -> dict[str, Mapping]:
    """Answers available without the LLM: overrides.json "lines", then the cache."""
    line_overrides, _ = overrides.load_overrides()
    found = {}
    for key, line in lines.items():
        dishes = line_overrides.get(dish_key(line.ref))
        if dishes is not None:
            found[key] = Mapping(bool(dishes), tuple(dishes), "override")
    cached = MenuLine.objects.filter(key__in=[key for key in lines if key not in found],
                                     source=MenuLine.Source.LLM, version=STORE_VERSION)
    for row in cached:
        found[row.key] = Mapping(row.is_meal, tuple(row.dishes), row.source)
    return found


def _grams(text: str) -> set[str]:
    text = "".join(text.split())
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _offered_names(lines_by_label: dict[str, StoreLine]):
    """known for resolve_with_llm: the canonical names sharing two letters with the batch's lines."""
    catalog = fixed.catalog_lines(fixed.load_catalog())
    line_overrides, renames = overrides.load_overrides()
    extra = {dish for dishes in line_overrides.values() for dish in dishes} | set(renames.values())
    extra |= {dish for dishes in MenuLine.objects.filter(source=MenuLine.Source.LLM, version=STORE_VERSION)
              .values_list("dishes", flat=True) for dish in dishes}
    base = known_dishes(catalog, extra)
    grams = {}

    def offered(labels: list[str], chosen: list[str]) -> list[str]:
        wanted = set().union(*(_grams(lines_by_label[label].name) for label in labels))
        scored = []
        for name in dict.fromkeys([*base, *chosen]):
            overlap = len(grams.setdefault(name, _grams(name)) & wanted)
            if overlap:
                scored.append((-overlap, name))
        return sorted(name for _, name in sorted(scored)[:KNOWN_LIMIT])

    return offered


def map_store_lines(lines: dict[str, StoreLine], llm=None, on_progress=None,
                    batch_size: int = 25) -> dict[str, Mapping]:
    """Return a Mapping for every key of `lines` (see the module docstring for the order)."""
    result = known_answers(lines)
    pending = {line.label: (key, line) for key, line in lines.items() if key not in result}
    if llm is not None and pending:
        by_label = {label: line for label, (_, line) in pending.items()}
        message = lambda labels, known: build_store_message([by_label[label] for label in labels], known)
        answers = resolve_with_llm(list(pending), llm, _offered_names(by_label), batch_size, on_progress,
                                   prompt=(STORE_SYSTEM_PROMPT, message), line_as_dish=False)
        rows = []
        for label, (is_meal, dishes) in answers.items():
            key, line = pending[label]
            result[key] = Mapping(is_meal, dishes, MenuLine.Source.LLM)
            rows.append(MenuLine(key=key, name=line.name[:NAME_MAX], is_meal=is_meal, dishes=list(dishes),
                                 source=MenuLine.Source.LLM, version=STORE_VERSION))
        MenuLine.objects.bulk_create(rows, batch_size=1000, update_conflicts=True, unique_fields=["key"],
                                     update_fields=["name", "is_meal", "dishes", "source", "version"])
    for key, line in lines.items():
        # Without an answer "A세트" names no dish; any other line is one dish, as it reads.
        dishes = () if is_vague(line.name) else (line.name[:NAME_MAX],)
        result.setdefault(key, Mapping(True, dishes, MenuLine.Source.RULE))
    _, renames = overrides.load_overrides()
    if renames:
        result = {key: replace(m, dishes=overrides.rename(m.dishes, renames)) for key, m in result.items()}
    return result
