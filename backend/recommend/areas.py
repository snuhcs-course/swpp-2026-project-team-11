"""The places a user can pick to eat at, instead of sending the phone's location.

    "campus"      the day's SNU cafeteria menu
    "snu_station" restaurants near 서울대입구역
    "nakseongdae" restaurants near 낙성대역
    "all"         all of them

A station's area is the circle fetch_naver_menus crawled around it. Distances are
straight lines on the map (haversine), in whole meters; no map API is called.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000
AREAS = ("campus", "snu_station", "nakseongdae", "all")
SOURCES = {"campus": "cafeteria", "snu_station": "general", "nakseongdae": "general", "all": "all"}
STATIONS = {  # area: (station, lat, lng, radius in meters)
    "snu_station": ("서울대입구역", 37.481247, 126.952739, 600),
    "nakseongdae": ("낙성대역", 37.476930, 126.963693, 500),
}


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((phi2 - phi1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return round(2 * EARTH_RADIUS_M * math.asin(math.sqrt(a)))


def near_station(candidates: list[dict], area: str) -> list[dict]:
    """Keeps the offers inside the station's area, and the candidates left with one."""
    _, lat, lng, radius = STATIONS[area]
    kept = []
    for candidate in candidates:
        candidate["offers"] = [offer for offer in candidate["offers"]
                               if offer["lat"] is not None and offer["lng"] is not None
                               and distance_m(lat, lng, offer["lat"], offer["lng"]) <= radius]
        if candidate["offers"]:
            kept.append(candidate)
    return kept
