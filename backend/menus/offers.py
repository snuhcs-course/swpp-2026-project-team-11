"""Which offers of a full catalogue a catalogue read without an allergen keeps.

Equivalent menu lines merge into one candidate under the smallest line ID, and the
allergen filter drops lines before they merge (menus/services.py). A menu can
therefore come back from the filtered catalogue under another ID, so offers are
matched by the menu's title and features and the offer itself, not by ID.
"""
import json

from question_engines.group.engine import place

from .menu_profiles import title


def safe_offers(rows, safe_rows):
    """The (food ID, place) offers of `rows` that `safe_rows`, the same catalogue without an
    allergen, keeps. Raises ValueError when an offer cannot be traced to exactly one of them."""
    def keys(row):
        menu = json.dumps([title(row["name"]), row["features"], row["feature_std"]], ensure_ascii=False, sort_keys=True)
        return [(menu, json.dumps(offer, ensure_ascii=False, sort_keys=True)) for offer in row["offers"]]

    owners = {}
    for row in rows:
        for key, offer in zip(keys(row), row["offers"]):
            owners.setdefault(key, set()).add((row["food_id"], place(offer)))
    matched = [owners.get(key, set()) for row in safe_rows for key in keys(row)]
    if any(len(offers) != 1 for offers in matched):
        raise ValueError("An offer of the catalogue without the allergen matches no single offer of the full one")
    return set().union(*matched)
