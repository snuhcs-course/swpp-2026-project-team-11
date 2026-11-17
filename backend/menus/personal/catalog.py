"""Reviewed frozen dish profiles; operational sales mappings live in the DB."""
import csv
from functools import lru_cache
from pathlib import Path
from menus.features.schema import FEATURES, MODEL_LABELS
ASSETS = Path(__file__).parents[2] / "question_engines/rl/assets"

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
