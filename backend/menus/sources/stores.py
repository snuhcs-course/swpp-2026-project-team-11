"""Food shops from 소상공인시장진흥공단 상가(상권)정보, a quarterly CSV per province.

Download the zip from data.go.kr and unzip the province's CSV (서울: about 300 MB,
UTF-8, one row per shop with WGS84 경도/위도). We keep food shops (대분류 I2) other
than cafés, bakeries, rice-cake shops and ice cream.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass

FOOD = "I2"
CAFE_LIKE = {"I21201", "I21001", "I21002", "I21008"}  # 카페, 빵/도넛, 떡/한과, 아이스크림/빙수


@dataclass(frozen=True)
class Store:
    id: str  # 상가업소번호
    name: str
    branch: str
    category: str  # 중분류, e.g. 한식
    subcategory: str  # 소분류, e.g. 국/탕/찌개류
    lat: float
    lng: float
    road_address: str
    floor: str


def read_food_stores(path) -> Iterator[Store]:
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["상권업종대분류코드"] != FOOD or row["상권업종소분류코드"] in CAFE_LIKE:
                continue
            yield Store(
                id=row["상가업소번호"],
                name=row["상호명"].strip(),
                branch=row["지점명"].strip(),
                category=row["상권업종중분류명"].strip(),
                subcategory=row["상권업종소분류명"].strip(),
                lat=float(row["위도"]),
                lng=float(row["경도"]),
                road_address=row["도로명주소"],
                floor=row["층정보"],
            )
