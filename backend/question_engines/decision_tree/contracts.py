# AI-generated: written with OpenAI Codex and reviewed by the team.
"""English presentation metadata and stable, JSON-compatible answer IDs."""
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
