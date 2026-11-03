import json
from pathlib import Path

from ..catalog import CandidateCatalog


def october_menu():
    """(rows, schema) of the 2026-10-13 lunch fixture: 146 dishes with all 33 v2 features."""
    data = json.loads((Path(__file__).parent / "fixtures/lunch_20261013.json").read_text(encoding="utf-8"))
    rows = [{"food_id": i, "name": name, "display_name": label,
             "features": dict(zip(data["keys"], means)), "feature_std": dict(zip(data["keys"], stds))}
            for i, name, label, means, stds in data["foods"]]
    return rows, [{"key": key} for key in data["keys"]]


def candidate(food_id, name, group, beef, soupy):
    return {"food_id": food_id, "name": name, "display_name": name,
            "food_group": group, "features": {"beef": beef, "soupy": soupy},
            "offers": [{"restaurant": "Test hall", "meal": "LU", "price": 5000}]}


def small_catalog():
    return CandidateCatalog([
        candidate(1, "Beef noodles", "Noodles", .9, .9),
        candidate(2, "Chicken noodles", "Noodles", .1, .9),
        candidate(3, "Rice bowl", "Rice", .1, .1),
    ], [{"key": "beef"}, {"key": "soupy"}])
