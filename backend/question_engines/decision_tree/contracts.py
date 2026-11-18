"""Presentation metadata in English and Korean, and stable, JSON-compatible answer IDs."""
from enum import Enum


class Answer(str, Enum):
    YES = "yes"
    PROBABLY_YES = "probably_yes"
    ANY = "any"
    PROBABLY_NO = "probably_no"
    NO = "no"
    UNKNOWN = "unknown"


ANSWER_OPTIONS = (
    {"id": Answer.YES.value, "label": "Yes, sounds good"},
    {"id": Answer.PROBABLY_YES.value, "label": "Probably yes"},
    {"id": Answer.ANY.value, "label": "Doesn't matter"},
    {"id": Answer.PROBABLY_NO.value, "label": "Probably not"},
    {"id": Answer.NO.value, "label": "No"},
    {"id": Answer.UNKNOWN.value, "label": "Not sure"},
)

LANGUAGES = ("en", "ko")
GUESS_TEXT = "Is this what you feel like eating?"
RECOMMENDATION_TEXT = "Enjoy your meal."
UNAVAILABLE_TEXT = "No available meal matches this session. Try starting again."

# These are translations/presentation metadata, not inference rules. The
# team's feature keys and meanings remain the source of truth.
# Questions use the same versioned definitions as all catalogue producers.
import json
from pathlib import Path
RUBRIC = json.loads(Path(__file__).parents[1].joinpath("feature_schema.json").read_text(encoding="utf-8"))
FEATURE_PRESENTATION = {f["key"]: (f["question"], f["family"]) for f in RUBRIC["features"]}

# The Korean of every fixed English text above, keyed by the English.
KOREAN = {
    "Yes, sounds good": "좋아요",
    "Probably yes": "아마 그래요",
    "Doesn't matter": "상관없어요",
    "Probably not": "별로예요",
    "No": "아니에요",
    "Not sure": "잘 모르겠어요",
    GUESS_TEXT: "이 메뉴가 당기나요?",
    RECOMMENDATION_TEXT: "맛있게 드세요.",
    UNAVAILABLE_TEXT: "조건에 맞는 메뉴가 없어요. 다시 시작해 주세요.",

}
KOREAN.update({f["question"]: f["question_ko"] for f in RUBRIC["features"]})


def translate(text, language):
    """`text` in `language`; a text with no Korean entry, such as a custom schema question, stays English."""
    return KOREAN.get(text, text) if language == "ko" else text


def answer_options(language):
    return [{"id": option["id"], "label": translate(option["label"], language)} for option in ANSWER_OPTIONS]
