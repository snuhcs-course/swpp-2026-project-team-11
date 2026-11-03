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
FEATURE_PRESENTATION = {
    "spicy": ("Do you feel like something spicy?", "taste"),
    "sweet": ("Do you feel like something sweet?", "taste"),
    "sour_fresh": ("Do you feel like something tangy or refreshing?", "taste"),
    "greasy": ("Do you feel like something rich and oily?", "richness"),
    "soupy": ("Do you feel like something with broth?", "format"),
    "hot": ("Do you feel like something served hot?", "temperature"),
    "cold": ("Do you feel like something cold?", "temperature"),
    "fried": ("Do you feel like something fried?", "preparation"),
    "grilled": ("Do you feel like grilled or stir-fried food?", "preparation"),
    "rice": ("Do you feel like a rice dish?", "starch"),
    "noodle": ("Do you feel like noodles?", "starch"),
    "bread_flour": ("Do you feel like bread or flour-based food, other than noodles?", "starch"),
    "beef": ("Do you feel like beef?", "protein"),
    "pork": ("Do you feel like pork?", "protein"),
    "chicken": ("Do you feel like chicken?", "protein"),
    "seafood": ("Do you feel like fish or seafood?", "protein"),
    "meatless": ("Do you feel like something without meat?", "protein"),
    "heavy": ("Do you feel like a hearty, filling meal?", "weight"),
    "light_healthy": ("Do you feel like something light and healthy?", "weight"),
    "korean": ("Do you feel like Korean food?", "cuisine"),
    "chinese": ("Do you feel like Chinese food?", "cuisine"),
    "japanese": ("Do you feel like Japanese food?", "cuisine"),
    "western_asian": ("Do you feel like Western or Southeast Asian food?", "cuisine"),
}

# The old keys and their meanings remain available for v1 snapshots.
FEATURE_PRESENTATION_V2 = {
    key: value for key, value in FEATURE_PRESENTATION.items()
    if key not in {"sour_fresh", "bread_flour", "seafood", "meatless",
                   "heavy", "light_healthy", "western_asian"}
} | {
    "sour": ("Do you feel like something sour?", "taste"),
    "oily": ("Do you feel like food with a noticeable oily texture?", "richness"),
    "greasy": ("Do you feel like something rich and heavy on the palate?", "richness"),
    "smoky": ("Do you feel like something with a smoky flavor?", "taste"),
    "crispy": ("Do you feel like something crispy?", "texture"),
    "grilled": ("Do you feel like grilled food?", "preparation"),
    "stir_fried": ("Do you feel like stir-fried food?", "preparation"),
    "bread": ("Do you feel like a bread-based meal?", "starch"),
    "wheat": ("Do you feel like food made with wheat?", "ingredient"),
    "fish": ("Do you feel like fish?", "protein"),
    "crustacean": ("Do you feel like shrimp, crab or other crustaceans?", "protein"),
    "bivalve": ("Do you feel like clams, mussels or other bivalve shellfish?", "protein"),
    "cephalopod": ("Do you feel like squid or octopus?", "protein"),
    "large_portion": ("Do you feel like a large portion?", "portion"),
    "filling": ("Do you feel like a filling meal?", "satiety"),
    "western": ("Do you feel like Western food?", "cuisine"),
    "southeast_asian": ("Do you feel like Southeast Asian food?", "cuisine"),
    "indian": ("Do you feel like Indian food?", "cuisine"),
    "meal_variety": ("Do you feel like several dishes in one meal?", "variety"),
}

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
    "Do you feel like something spicy?": "매운 음식이 당기나요?",
    "Do you feel like something sweet?": "단 음식이 당기나요?",
    "Do you feel like something tangy or refreshing?": "새콤하거나 상큼한 음식이 당기나요?",
    "Do you feel like something rich and oily?": "기름지고 진한 음식이 당기나요?",
    "Do you feel like something with broth?": "국물 있는 음식이 당기나요?",
    "Do you feel like something served hot?": "따뜻한 음식이 당기나요?",
    "Do you feel like something cold?": "차가운 음식이 당기나요?",
    "Do you feel like something fried?": "튀긴 음식이 당기나요?",
    "Do you feel like grilled or stir-fried food?": "굽거나 볶은 음식이 당기나요?",
    "Do you feel like a rice dish?": "밥 요리가 당기나요?",
    "Do you feel like noodles?": "면 요리가 당기나요?",
    "Do you feel like bread or flour-based food, other than noodles?": "면 말고 빵이나 밀가루 음식이 당기나요?",
    "Do you feel like beef?": "소고기가 당기나요?",
    "Do you feel like pork?": "돼지고기가 당기나요?",
    "Do you feel like chicken?": "닭고기가 당기나요?",
    "Do you feel like fish or seafood?": "생선이나 해산물이 당기나요?",
    "Do you feel like something without meat?": "고기 없는 음식이 당기나요?",
    "Do you feel like a hearty, filling meal?": "든든하고 배부른 식사가 당기나요?",
    "Do you feel like something light and healthy?": "가볍고 건강한 음식이 당기나요?",
    "Do you feel like Korean food?": "한식이 당기나요?",
    "Do you feel like Chinese food?": "중식이 당기나요?",
    "Do you feel like Japanese food?": "일식이 당기나요?",
    "Do you feel like Western or Southeast Asian food?": "양식이나 동남아 음식이 당기나요?",
    "Do you feel like something sour?": "신 음식이 당기나요?",
    "Do you feel like food with a noticeable oily texture?": "기름진 식감의 음식이 당기나요?",
    "Do you feel like something rich and heavy on the palate?": "맛이 진하고 묵직한 음식이 당기나요?",
    "Do you feel like something with a smoky flavor?": "불향이나 훈연향이 나는 음식이 당기나요?",
    "Do you feel like something crispy?": "바삭한 음식이 당기나요?",
    "Do you feel like grilled food?": "구운 음식이 당기나요?",
    "Do you feel like stir-fried food?": "볶은 음식이 당기나요?",
    "Do you feel like a bread-based meal?": "빵으로 된 식사가 당기나요?",
    "Do you feel like food made with wheat?": "밀가루 음식이 당기나요?",
    "Do you feel like fish?": "생선이 당기나요?",
    "Do you feel like shrimp, crab or other crustaceans?": "새우나 게 같은 갑각류가 당기나요?",
    "Do you feel like clams, mussels or other bivalve shellfish?": "조개나 홍합 같은 조개류가 당기나요?",
    "Do you feel like squid or octopus?": "오징어나 문어가 당기나요?",
    "Do you feel like a large portion?": "양이 많은 음식이 당기나요?",
    "Do you feel like a filling meal?": "배부른 식사가 당기나요?",
    "Do you feel like Western food?": "양식이 당기나요?",
    "Do you feel like Southeast Asian food?": "동남아 음식이 당기나요?",
    "Do you feel like Indian food?": "인도 음식이 당기나요?",
    "Do you feel like several dishes in one meal?": "여러 요리를 함께 먹는 식사가 당기나요?",
}


def translate(text, language):
    """`text` in `language`; a text with no Korean entry, such as a custom schema question, stays English."""
    return KOREAN.get(text, text) if language == "ko" else text


def answer_options(language):
    return [{"id": option["id"], "label": translate(option["label"], language)} for option in ANSWER_OPTIONS]
