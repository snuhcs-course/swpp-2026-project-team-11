# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Turn a raw cafeteria menu line into a dish name, or tell that it is not one.

Only the obvious, mechanical cleanup happens here. Whether a line is a real meal
(vs. a drink, an add-on like 공기밥, or an upcharge note) is left to the LLM in
features/, which sees the cleaned name and sets Food.is_food.
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
