"""Reviewed canonical dishes and versioned sales-name mappings; no model calls."""
import csv
from functools import lru_cache
from pathlib import Path
import re
from menus.features.schema import FEATURES, MODEL_LABELS
ASSETS = Path(__file__).parents[2] / "question_engines/rl/assets"

def format_key(name):
    return re.sub(r"[\s_]+", "", re.sub(r"\[[^\]]*\]", "", name))

@lru_cache(maxsize=1)
def canonical_foods():
    with (ASSETS / "foods.csv").open(encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    result = {}
    for row in rows:
        key = row["food_id"]
        means, stds = {}, {}
        for feature, label in zip(FEATURES, MODEL_LABELS):
            known = row[label+"_mask"] == "1"
            means[feature.key] = float(row[label+"_mean"]) if known else None
            stds[feature.key] = float(row[label+"_std"]) if known else None
        result[key] = {"canonical_id":key, "food_id":1_000_000_000+int(key.split("_")[1]),
                       "name":row["name"], "display_name":row["name"], "food_group":row["name"],
                       "food_groups":[row["name"]], "features":means, "feature_std":stds,
                       "menu_profile":"rms-v1"}
    return result

@lru_cache(maxsize=1)
def mappings():
    names = {row["name"]:key for key,row in canonical_foods().items()}
    exact, formatted = {}, {}
    with Path(__file__).with_name("menu_mapping.csv").open(encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            owner, title = row["식당명"], row["기존 음식명"]
            value = names.get(row["정규화 음식명"])
            key = owner, title
            if key in exact and exact[key] != value:
                raise ValueError("Conflicting exact menu mapping")
            exact[key] = value
            formatted.setdefault((owner,format_key(title)),set()).add(value)
    return exact, formatted

def resolve(restaurant, raw_name):
    exact, formatted = mappings()
    if (restaurant, raw_name) in exact:
        return exact[restaurant, raw_name]
    matches = formatted.get((restaurant,format_key(raw_name)),set())
    return next(iter(matches)) if len(matches)==1 else None
