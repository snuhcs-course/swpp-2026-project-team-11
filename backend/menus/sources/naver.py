"""Restaurant menus from Naver Place's public mobile pages (unofficial, no login).

    GET https://m.place.naver.com/restaurant/list?query=...&x=<lng>&y=<lat>
    GET https://m.place.naver.com/restaurant/<place id>/menu/list

Naver has no official API that returns menus, so we read the pages a signed-out
visitor sees. Each page embeds its data as `window.__APOLLO_STATE__ = {...}`.
The list page renders only its first page (about ten places near x, y and a list
of places open now); `start` and `display` in the URL are ignored. Naver answers
non-browser user agents with 429, so we send a mobile browser's. A change to the
pages breaks parsing; `apollo_state` then raises ValueError.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import requests

from recommend.distance import distance_m

BASE_URL = "https://m.place.naver.com/restaurant"
USER_AGENT = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
              "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
TIMEOUT_SECONDS = 10
STATE_START = re.compile(r"window\.__APOLLO_STATE__\s*=\s*")
PRICE = re.compile(r"([\d,]+)원")
NOT_NAME = re.compile(r"[^0-9a-z가-힣]")
MATCH_MAX_M = 150


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    category: str
    lat: float | None
    lng: float | None
    road_address: str


@dataclass(frozen=True)
class Menu:
    place_id: str
    name: str
    price: int | None
    description: str
    is_set: bool


def _get(url: str, params: dict | None = None) -> str:
    response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT},
                            timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    response.encoding = "utf-8"  # the pages send no charset, and requests would assume Latin-1
    return response.text


def fetch_list_html(query: str, lat: float, lng: float) -> str:
    """Download the place list for a search near (lat, lng). Stub this in tests."""
    return _get(f"{BASE_URL}/list", {"query": query, "x": lng, "y": lat})


def fetch_menu_html(place_id: str) -> str:
    """Download one place's menu page. Stub this in tests."""
    return _get(f"{BASE_URL}/{place_id}/menu/list")


def apollo_state(html: str) -> dict:
    match = STATE_START.search(html)
    if not match:
        raise ValueError("__APOLLO_STATE__ not found; the Naver Place page may have changed")
    state, _ = json.JSONDecoder().raw_decode(html, match.end())
    return state


def parse_places(state: dict) -> list[Place]:
    """Every place the list page holds, once each, in page order."""
    places = {}
    for item in state.values():
        if item.get("__typename") == "PlaceListBusinessesItem" and item["id"] not in places:
            places[item["id"]] = Place(
                id=item["id"],
                name=item["name"],
                category=item.get("category") or "",
                lat=float(item["y"]) if item.get("y") else None,
                lng=float(item["x"]) if item.get("x") else None,
                road_address=item.get("roadAddress") or "",
            )
    return list(places.values())


def parse_price(text: str | None) -> int | None:
    """9000 for "9,000원"; None for "변동", "시가" or a range."""
    match = PRICE.fullmatch(text or "")
    return int(match.group(1).replace(",", "")) if match else None


def parse_menus(place_id: str, state: dict) -> list[Menu]:
    """The menu items a place lists as text; a menu shown only as photos gives none."""
    return [
        Menu(
            place_id=place_id,
            name=item["name"],
            price=parse_price((item.get("price") or {}).get("displayText")),
            description=item.get("description") or "",
            is_set=bool(item.get("isSetMenu")),
        )
        for item in state.values() if item.get("__typename") == "PlaceMenuItem"
    ]


def search_places(query: str, lat: float, lng: float) -> list[Place]:
    return parse_places(apollo_state(fetch_list_html(query, lat, lng)))


def name_key(name: str) -> str:
    return NOT_NAME.sub("", name.lower())


def match_place(name: str, lat: float, lng: float, places: list[Place]) -> Place | None:
    """The nearest place within MATCH_MAX_M of (lat, lng) whose name contains `name`."""
    key = name_key(name)
    near = [(distance_m(lat, lng, p.lat, p.lng), p) for p in places
            if p.lat is not None and p.lng is not None and key and key in name_key(p.name)]
    near = [(meters, p) for meters, p in near if meters <= MATCH_MAX_M]
    return min(near, key=lambda pair: pair[0])[1] if near else None


def find_place(name: str, branch: str, lat: float, lng: float) -> Place | None:
    """The Naver place of a shop known by name, branch and location, if Naver lists it."""
    return match_place(name, lat, lng, search_places(f"{name} {branch}".strip(), lat, lng))


def fetch_menus(place_id: str) -> list[Menu]:
    return parse_menus(place_id, apollo_state(fetch_menu_html(place_id)))
