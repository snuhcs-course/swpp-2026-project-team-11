"""Restaurants near the stations and their Naver Place menus, from a crawl file.

The crawl takes the stores of the 소상공인시장진흥공단 상가(상권)정보 within a radius of
each station, matches each to a Naver Place and saves its menu board:

    {"fetched_at", "areas", "counts", "stores": [
        {"id", "name", "branch", "category", "subcategory", "lat", "lng", "road_address",
         "status": "matched" | "not_found" | "failed",
         "naver": {"id", "name", "category", "lat", "lng", "road_address", "distance_m"} | null,
         "menus": [{"name", "price", "description", "is_set"}]}]}

`incomplete` tells whether a file is a whole crawl: the collector can stop early or
fail on some stores, and those stores must not lose the menus of an earlier import.
`parse` keeps the matched stores that have a menu and serve meals. Cafes, bakeries
and dessert shops are left out; bars stay, and their drinks are dropped line by line
(menus/preprocess/store_lines.py). The crawl is not daily: import_stores loads a new
file whenever the stores are crawled again.
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter
from dataclasses import dataclass

# 상가정보 업종: 중분류 "비알코올" is cafes. Names are matched as substrings of the
# 상가정보 소분류 or of the Naver category ("카페,디저트", "베이커리", "떡,한과").
NOT_MEAL_CATEGORY = "비알코올"
NOT_MEAL_SUBCATEGORY_WORDS = ("카페", "디저트", "제과", "빵", "도넛", "아이스크림", "빙수", "떡/한과")
NOT_MEAL_NAVER_WORDS = ("카페", "디저트", "베이커리", "제과", "빵", "도넛", "아이스크림", "빙수", "한과")


@dataclass(frozen=True)
class StoreMenuLine:
    name: str
    price: int | None
    description: str


@dataclass(frozen=True)
class StoreRecord:
    code: str            # 상가업소번호
    name: str
    category: str        # Naver category, else the 상가정보 소분류
    lat: float | None
    lng: float | None
    address: str
    place_id: str
    match_distance_m: int | None  # between the 상가정보 and the Naver location
    menus: tuple[StoreMenuLine, ...]


def read(path: str | pathlib.Path) -> dict:
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("stores"), list):
        raise ValueError('expected {"stores": [...]} at the top level')
    for i, store in enumerate(data["stores"]):
        if not isinstance(store, dict) or not store.get("id") or "status" not in store:
            raise ValueError(f"stores[{i}] needs an id and a status")
        if not isinstance(store.get("menus") or [], list):
            raise ValueError(f"stores[{i}].menus must be a list")
    return data


def serves_meals(store: dict) -> bool:
    naver = store.get("naver") or {}
    subcategory, naver_category = store.get("subcategory") or "", naver.get("category") or ""
    return not (store.get("category") == NOT_MEAL_CATEGORY
                or any(word in subcategory for word in NOT_MEAL_SUBCATEGORY_WORDS)
                or any(word in naver_category for word in NOT_MEAL_NAVER_WORDS))


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _price(value) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _record(store: dict) -> StoreRecord:
    naver = store["naver"] or {}
    lat, lng = _number(naver.get("lat")), _number(naver.get("lng"))
    if lat is None or lng is None:
        lat, lng = _number(store.get("lat")), _number(store.get("lng"))
    name = naver.get("name") or " ".join(filter(None, (store.get("name"), store.get("branch"))))
    return StoreRecord(
        code=str(store["id"]),
        name=name[:100],
        category=(naver.get("category") or store.get("subcategory") or "")[:50],
        lat=lat,
        lng=lng,
        address=(store.get("road_address") or naver.get("road_address") or "")[:200],
        place_id=str(naver.get("id") or "")[:30],
        match_distance_m=_number(naver.get("distance_m")),
        menus=tuple(StoreMenuLine(str(menu.get("name") or ""), _price(menu.get("price")),
                                  str(menu.get("description") or ""))
                    for menu in store["menus"] if isinstance(menu, dict)),
    )


def incomplete(data: dict) -> list[str]:
    """Why `data` is not a whole crawl (empty when it is): failed stores, or missing ones."""
    problems = []
    failed = sum(store["status"] == "failed" for store in data["stores"])
    if failed:
        problems.append(f"실패한 가게 {failed}곳")
    expected = (data.get("counts") or {}).get("in_radius")
    if isinstance(expected, int) and expected != len(data["stores"]):
        problems.append(f"파일의 가게 {len(data['stores'])}곳이 counts.in_radius {expected}곳과 다름")
    return problems


def settled_codes(data: dict) -> set[str]:
    """The stores this crawl has an answer for (not failed): their earlier menus may be replaced."""
    return {str(store["id"]) for store in data["stores"] if store["status"] != "failed"}


def parse(data: dict) -> tuple[list[StoreRecord], Counter]:
    """(stores to import, why the other stores were skipped)."""
    stores, skipped, places = [], Counter(), set()
    for store in data["stores"]:
        if store["status"] == "failed":
            skipped["failed"] += 1
        elif store["status"] != "matched" or not store.get("naver"):
            skipped["not_matched"] += 1
        elif not store.get("menus"):
            skipped["no_menu"] += 1
        elif not serves_meals(store):
            skipped["cafe_or_bakery"] += 1
        elif store["naver"].get("id") and store["naver"]["id"] in places:
            skipped["same_place"] += 1  # two 상가정보 rows matched to one Naver place
        else:
            places.add(store["naver"].get("id"))
            stores.append(_record(store))
    return stores, skipped
