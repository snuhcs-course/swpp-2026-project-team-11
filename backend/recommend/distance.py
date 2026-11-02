"""How far each cafeteria is from the user, and the optional distance cutoff.

Distances are straight lines on the map (haversine), in whole meters, computed
from the location the phone sends when a session starts. No map API is called.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((phi2 - phi1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return round(2 * EARTH_RADIUS_M * math.asin(math.sqrt(a)))


def with_distances(candidates: list[dict], location: tuple[float, float] | None,
                   max_distance_m: int | None = None) -> list[dict]:
    """Adds `distance_m` (null when unknown) to every offer and returns the candidates.

    With `max_distance_m`, offers known to be farther are dropped, and so are
    candidates left without an offer. An offer of unknown distance is kept.
    """
    located = []
    for candidate in candidates:
        for offer in candidate["offers"]:
            known = location is not None and offer["lat"] is not None and offer["lng"] is not None
            offer["distance_m"] = distance_m(*location, offer["lat"], offer["lng"]) if known else None
        if max_distance_m is not None:
            candidate["offers"] = [offer for offer in candidate["offers"]
                                   if offer["distance_m"] is None or offer["distance_m"] <= max_distance_m]
            if not candidate["offers"]:
                continue
        located.append(candidate)
    return located
