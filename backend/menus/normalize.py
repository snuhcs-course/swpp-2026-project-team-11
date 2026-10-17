"""Turn a raw cafeteria menu line into a dish name, or tell that it is not one.

Only the obvious, mechanical cleanup happens here. Splitting combo lines into
dishes and deciding whether a line is a real meal is done in menus/preprocess/.

`dish_key()` is the rule-based merge: two lines with the same key are the same
menu line ("눈꽃 치즈 돈까스" = "눈꽃치즈 돈까스", "육회 비빔밥(S)" = "육회 비빔밥(L)").
"""

from __future__ import annotations

import re

_WHOLE_TAG = re.compile(r"^<[^<>]*>$")        # <경성 돈카츠>, <TAKE-OUT>
_WHOLE_PAREN = re.compile(r"^\([^()]*\)$")    # ( Break time은 없습니다 )
_LEADING_TAG = re.compile(r"^<[^<>]*>\s*[:+]?\s*")   # <A코너>, <셀프코너>:, <뷔페>+
_TRAILING_TAG = re.compile(r"\s*\+?\s*<[^<>]*>$")    # ...+<뷔페 특성상 ... 양해 부탁드립니다>
# " : 5,200원 / ..." or " = 17,100원 (...)" - Siksha sometimes leaves the price in the name.
_PRICE_IN_NAME = re.compile(r"\s*[:=]\s*(\d{1,3}(?:[,.]\d{3})+|\d+)\s*원.*$")
_TRAILING_PUNCT = re.compile(r"[\s=:/+]+$")

# Markers that change the size, portion or serving but not the dish. Kept on purpose:
# variety markers such as (야채), (막국수), (진라면), and (추가) for add-ons.
_SAME_DISH_MARKERS = re.compile(
    r"\((?:S|M|L|R|大|中|小|소|중|대|뚝|밥포함|채식변경가능)\)"  # (S), (소), (밥포함), (뚝)
    r"|\(\d+p\)|\d+p$"                                          # 야채춘권(3p), 감자고로케 2P
    r"|\d+조각",                                                # 김말이 10조각
    re.IGNORECASE,
)


def is_noise(raw: str) -> bool:
    """True for lines that are clearly not a dish: blanks, notices and headers."""
    name = raw.strip()
    return (
        not name
        or name.startswith("※")
        or bool(_WHOLE_TAG.match(name))
        or bool(_WHOLE_PAREN.match(name))
    )


def clean_name(raw: str) -> tuple[str, int | None]:
    """Return (dish name, price written inside the name or None).

    Combo lines ("A, B, C" or "A+B+C") are kept whole; the LLM picks the main dish.
    """
    name = " ".join(raw.split())

    price = None
    match = _PRICE_IN_NAME.search(name)
    if match:
        price = int(re.sub(r"[,.]", "", match.group(1)))
        name = name[: match.start()]

    for pattern in (_LEADING_TAG, _TRAILING_TAG):
        stripped = pattern.sub("", name)
        if stripped:  # never strip a line down to nothing
            name = stripped

    return _TRAILING_PUNCT.sub("", name), price


KEY_MAX = 300  # MenuLine.key max_length; Postgres enforces it


def dish_key(name: str) -> str:
    """Key that is equal for lines differing only in spacing, size or portion markers."""
    key = _SAME_DISH_MARKERS.sub("", "".join(name.split()))
    return (key or "".join(name.split())).lower()[:KEY_MAX]
