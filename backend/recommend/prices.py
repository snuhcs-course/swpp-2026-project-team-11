"""The price range filter: the user picks a level, one to three ₩ signs, on the start screen.

Each level is a band of offer prices in won, lower bound included and upper bound excluded.
The phone's price guide (client strings `price_guide_*`) shows the same bands.
"""

from __future__ import annotations

PRICE_BANDS = {1: (0, 8_000), 2: (8_000, 15_000), 3: (15_000, None)}


def within_price(candidates: list[dict], level: int) -> list[dict]:
    """Keeps only the offers priced inside the level's band, and the candidates left with one.
    An offer of unknown price is dropped: it cannot be shown to fit."""
    low, high = PRICE_BANDS[level]
    kept = []
    for candidate in candidates:
        candidate["offers"] = [offer for offer in candidate["offers"] if offer["price"] is not None
                               and low <= offer["price"] and (high is None or offer["price"] < high)]
        if candidate["offers"]:
            kept.append(candidate)
    return kept
