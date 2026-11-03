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
    "oily": ("Do you feel like something oily?", "richness"),
    "greasy": ("Do you feel like something creamy, cheesy or buttery?", "richness"),
    "smoky": ("Do you feel like something with a smoky, charred flavor?", "taste"),
    "crispy": ("Do you feel like something crispy?", "texture"),
    "grilled": ("Do you feel like grilled food?", "preparation"),
    "stir_fried": ("Do you feel like stir-fried food?", "preparation"),
    "bread": ("Do you feel like a bread-based meal, like a burger or sandwich?", "starch"),
    "wheat": ("Do you feel like something made with flour, like noodles or dumplings?", "ingredient"),
    "fish": ("Do you feel like fish?", "protein"),
    "crustacean": ("Do you feel like shrimp or crab?", "protein"),
    "bivalve": ("Do you feel like clams or mussels?", "protein"),
    "cephalopod": ("Do you feel like squid or octopus?", "protein"),
    "large_portion": ("Do you feel like a large portion?", "portion"),
    "filling": ("Do you feel like a filling meal?", "satiety"),
    "western": ("Do you feel like Western food?", "cuisine"),
    "southeast_asian": ("Do you feel like Southeast Asian food?", "cuisine"),
    "indian": ("Do you feel like Indian food?", "cuisine"),
    # Food.is_set: a menu line that preprocessing split into several dishes.
    "meal_variety": ("Do you feel like a combo of two dishes?", "variety"),
}

# Two more phrasings of each v2 question, (English, Korean), in other sentence
# patterns: 1 "How about ... today?", 2 "In the mood for ...?". Each asks for one
# feature, positively, so "yes" still means "more of it".
PHRASINGS_V2 = {
    "spicy": (("How about something spicy today?", "오늘은 매콤한 음식 어때요?"),
              ("In the mood for some heat?", "얼큰하고 매운맛이 끌리나요?")),
    "sweet": (("How about something sweet today?", "오늘은 달달한 음식 어때요?"),
              ("In the mood for a sweet sauce or glaze?", "달콤한 양념이 끌리나요?")),
    "sour": (("How about something tangy today?", "오늘은 새콤한 음식 어때요?"),
             ("In the mood for something vinegary or tart?", "새콤달콤한 맛이 끌리나요?")),
    "oily": (("How about something oily today?", "오늘은 기름기 있는 음식 어때요?"),
             ("In the mood for something rich with oil?", "기름진 음식이 끌리나요?")),
    "greasy": (("How about something creamy or cheesy today?", "오늘은 크림이나 치즈가 들어간 음식 어때요?"),
               ("In the mood for something rich and buttery?", "고소하고 느끼한 맛이 끌리나요?")),
    "smoky": (("How about something with a smoky flavor today?", "오늘은 불맛 나는 음식 어때요?"),
              ("In the mood for something charcoal-grilled or wok-fired?", "불향 가득한 음식이 끌리나요?")),
    "crispy": (("How about something crispy today?", "오늘은 바삭한 음식 어때요?"),
               ("In the mood for something crunchy?", "바삭바삭한 식감이 끌리나요?")),
    "soupy": (("How about a dish with broth today?", "오늘은 국물 요리 어때요?"),
              ("In the mood for a soup or stew?", "국이나 찌개처럼 국물 있는 메뉴가 끌리나요?")),
    "hot": (("How about something served hot today?", "오늘은 따끈한 음식 어때요?"),
            ("In the mood for something piping hot?", "뜨끈한 음식이 끌리나요?")),
    "cold": (("How about something cold today?", "오늘은 시원하고 차가운 음식 어때요?"),
             ("In the mood for something chilled?", "차갑게 먹는 음식이 끌리나요?")),
    "fried": (("How about something fried today?", "오늘은 튀김 요리 어때요?"),
              ("In the mood for something deep-fried?", "튀긴 음식이 끌리나요?")),
    "grilled": (("How about something grilled today?", "오늘은 구이 요리 어때요?"),
                ("In the mood for something pan-seared or roasted?", "노릇하게 구운 음식이 끌리나요?")),
    "stir_fried": (("How about a stir-fry today?", "오늘은 볶음 요리 어때요?"),
                   ("In the mood for something wok-tossed?", "달달 볶은 요리가 끌리나요?")),
    "rice": (("How about a rice dish today?", "오늘은 밥 요리 어때요?"),
             ("In the mood for a rice bowl or fried rice?", "덮밥이나 볶음밥 같은 밥 메뉴가 끌리나요?")),
    "noodle": (("How about noodles today?", "오늘은 면 요리 어때요?"),
               ("In the mood for a bowl of noodles?", "국수나 파스타 같은 면 요리가 끌리나요?")),
    "bread": (("How about a burger or sandwich today?", "오늘은 버거나 샌드위치 어때요?"),
              ("In the mood for something on bread?", "빵으로 된 식사가 끌리나요?")),
    "wheat": (("How about something made with flour today?", "오늘은 밀가루 음식 어때요?"),
              ("In the mood for a flour-based dish?", "밀가루로 만든 음식이 끌리나요?")),
    "beef": (("How about beef today?", "오늘은 소고기 어때요?"),
             ("In the mood for a beef dish?", "소고기 요리가 끌리나요?")),
    "pork": (("How about pork today?", "오늘은 돼지고기 어때요?"),
             ("In the mood for a pork dish?", "돼지고기 요리가 끌리나요?")),
    "chicken": (("How about chicken today?", "오늘은 닭고기 어때요?"),
                ("In the mood for a chicken dish?", "닭고기 요리가 끌리나요?")),
    "fish": (("How about fish today?", "오늘은 생선 요리 어때요?"),
             ("In the mood for a fish dish?", "생선이 들어간 메뉴가 끌리나요?")),
    "crustacean": (("How about shrimp or crab today?", "오늘은 새우나 게 요리 어때요?"),
                   ("In the mood for shrimp or crab?", "새우나 게가 끌리나요?")),
    "bivalve": (("How about clams or mussels today?", "오늘은 조개 요리 어때요?"),
                ("In the mood for shellfish like clams?", "조개나 홍합이 끌리나요?")),
    "cephalopod": (("How about squid or octopus today?", "오늘은 오징어나 문어 요리 어때요?"),
                   ("In the mood for squid or baby octopus?", "오징어나 쭈꾸미가 끌리나요?")),
    "large_portion": (("How about a big portion today?", "오늘은 양 많은 메뉴 어때요?"),
                      ("In the mood for an extra-large serving?", "넉넉한 양이 끌리나요?")),
    "filling": (("How about a hearty meal today?", "오늘은 든든한 식사 어때요?"),
                ("In the mood for something that keeps you full?", "배부르게 먹는 식사가 끌리나요?")),
    "korean": (("How about Korean food today?", "오늘은 한식 어때요?"),
               ("In the mood for Korean food?", "한식이 끌리나요?")),
    "chinese": (("How about Chinese food today?", "오늘은 중식 어때요?"),
                ("In the mood for Chinese food?", "중국 요리가 끌리나요?")),
    "japanese": (("How about Japanese food today?", "오늘은 일식 어때요?"),
                 ("In the mood for Japanese food?", "일본 요리가 끌리나요?")),
    "western": (("How about Western food today?", "오늘은 양식 어때요?"),
                ("In the mood for Western food?", "양식이 끌리나요?")),
    "southeast_asian": (("How about Southeast Asian food today?", "오늘은 동남아 음식 어때요?"),
                        ("In the mood for Thai or Vietnamese food?", "쌀국수 같은 동남아 음식이 끌리나요?")),
    "indian": (("How about Indian food today?", "오늘은 인도 음식 어때요?"),
               ("In the mood for an Indian curry?", "인도 커리가 끌리나요?")),
    "meal_variety": (("How about a combo with two dishes today?", "오늘은 두 가지 메뉴가 같이 나오는 세트 어때요?"),
                     ("In the mood for a combo meal?", "세트 메뉴가 끌리나요?")),
}

# How broad a question is: the first two questions are tier 1, the next two at
# most tier 2. Keys not listed (v1 and custom schemas) are tier 2.
QUESTION_TIERS = {
    **dict.fromkeys(("korean", "chinese", "japanese", "western", "rice", "noodle", "soupy", "spicy"), 1),
    **dict.fromkeys(("crustacean", "bivalve", "cephalopod", "smoky", "sour", "wheat",
                     "large_portion", "meal_variety"), 3),
}

# Questions about the same thing, never asked back to back. Keys not listed are
# their own topic.
QUESTION_TOPICS = {
    **dict.fromkeys(("wheat", "bread", "noodle", "bread_flour"), "flour"),
    **dict.fromkeys(("fish", "crustacean", "bivalve", "cephalopod", "seafood"), "seafood"),
    **dict.fromkeys(("beef", "pork", "chicken", "meatless"), "meat"),
    **dict.fromkeys(("korean", "chinese", "japanese", "western", "southeast_asian", "indian",
                     "western_asian"), "cuisine"),
    **dict.fromkeys(("fried", "crispy", "grilled", "stir_fried", "smoky"), "cooking"),
    **dict.fromkeys(("oily", "greasy"), "richness"),
    **dict.fromkeys(("hot", "cold", "soupy"), "temperature"),
    **dict.fromkeys(("spicy", "sweet", "sour", "sour_fresh"), "taste"),
    **dict.fromkeys(("large_portion", "filling", "heavy", "light_healthy"), "amount"),
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
    "Do you feel like something sour?": "새콤한 맛이 당기나요?",
    "Do you feel like something oily?": "기름기 있는 음식이 당기나요?",
    "Do you feel like something creamy, cheesy or buttery?": "크림이나 치즈처럼 고소하고 느끼한 음식이 당기나요?",
    "Do you feel like something with a smoky, charred flavor?": "불맛 나는 음식이 당기나요?",
    "Do you feel like something crispy?": "바삭한 음식이 당기나요?",
    "Do you feel like grilled food?": "구운 음식이 당기나요?",
    "Do you feel like stir-fried food?": "볶은 음식이 당기나요?",
    "Do you feel like a bread-based meal, like a burger or sandwich?": "버거나 샌드위치처럼 빵으로 된 식사가 당기나요?",
    "Do you feel like something made with flour, like noodles or dumplings?": "면이나 만두처럼 밀가루로 만든 음식이 당기나요?",
    "Do you feel like fish?": "생선 요리가 당기나요?",
    "Do you feel like shrimp or crab?": "새우나 게 요리가 당기나요?",
    "Do you feel like clams or mussels?": "조개나 홍합이 들어간 음식이 당기나요?",
    "Do you feel like squid or octopus?": "오징어나 문어가 당기나요?",
    "Do you feel like a large portion?": "양이 많은 음식이 당기나요?",
    "Do you feel like a filling meal?": "든든한 식사가 당기나요?",
    "Do you feel like Western food?": "양식이 당기나요?",
    "Do you feel like Southeast Asian food?": "동남아 음식이 당기나요?",
    "Do you feel like Indian food?": "인도 음식이 당기나요?",
    "Do you feel like a combo of two dishes?": "두 가지 메뉴가 같이 나오는 세트가 당기나요?",
}


def translate(text, language):
    """`text` in `language`; a text with no Korean entry, such as a custom schema question, stays English."""
    return KOREAN.get(text, text) if language == "ko" else text


def question_text(key, text, language, phrasing=0):
    """Question `text` about feature `key` in `language`, in phrasing 0 (`text`), 1 or 2.

    Only a v2 question keeps its other phrasings: a v1 or custom question with the
    same key may mean something else, so it is always shown as `text`.
    """
    variants = PHRASINGS_V2.get(key) if FEATURE_PRESENTATION_V2.get(key, ("",))[0] == text else None
    if not phrasing or not variants:
        return translate(text, language)
    english, korean = variants[(phrasing - 1) % len(variants)]
    return korean if language == "ko" else english


def question_tier(key):
    return QUESTION_TIERS.get(key, 2)


def question_topic(key):
    return QUESTION_TOPICS.get(key, key)


def answer_options(language):
    return [{"id": option["id"], "label": translate(option["label"], language)} for option in ANSWER_OPTIONS]
