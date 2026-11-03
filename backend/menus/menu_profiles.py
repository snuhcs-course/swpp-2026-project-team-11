"""Identity and validation for externally authored menu profiles; no model calls."""
import hashlib
import json
import math
import re

from .features.schema import FEATURE_KEYS
from .normalize import clean_name

_PORTIONS = re.compile(r"\d+(?:[.,]\d+)?\s*(?:인분|인|kg|g|ml|리터|조각|개|servings?|people)(?![a-z])", re.I)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False).encode()).hexdigest()


def title(raw_name):
    return clean_name(raw_name)[0]


def offer_key(source, restaurant_code, raw_name, description=""):
    return digest(["offer-v1", source, restaurant_code, title(raw_name), " ".join(description.split())])


def description_digest(description):
    return digest(" ".join(description.split()))


def recipe_key(source, raw_name, description, components):
    return digest(["recipe-v1", source, title(raw_name), " ".join(description.split()),
                   sorted((food.name, food.is_set) for food in components)])


def equivalent_menu_key(name, description, components, means, deviations):
    """Conservative duplicate grouping, retaining recipe and explicit portion differences."""
    composition = ("components", tuple(sorted(set(components)))) if components else ("description", " ".join(description.split()))
    portions = sorted(re.sub(r"\s+", "", value.lower()) for value in _PORTIONS.findall(name+" "+description))
    return digest([name.casefold(), composition, portions, means, deviations])


def validate_features(features, deviations):
    if (not isinstance(features, dict) or not isinstance(deviations, dict)
            or set(features) != set(FEATURE_KEYS) or set(deviations) != set(FEATURE_KEYS)):
        raise ValueError("A menu profile must cover every current feature and std key")
    for key, mean in features.items():
        std = deviations[key]
        if (isinstance(mean, bool) or isinstance(std, bool)
                or not isinstance(mean, (int, float)) or not isinstance(std, (int, float))
                or not math.isfinite(mean) or not math.isfinite(std)
                or not 0 <= mean <= 1 or not 0 <= std <= .5
                or std * std > mean * (1 - mean) + 1e-12):
            raise ValueError(f"Invalid bounded feature moments for {key}")
