# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""SNU cafeteria menus from the Siksha public API (by Waffle Studio).

    GET https://siksha-api.wafflestudio.com/menus/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

No auth. The response is {"result": [{"date", "BR": [...], "LU": [...], "DN": [...]}]},
where each meal lists restaurants and each restaurant lists its menus.
We ask for a single day per run.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import requests

API_URL = "https://siksha-api.wafflestudio.com/menus/"
USER_AGENT = "Metchu/0.1 (SNU SWPP 2026 Team 11 student project)"
TIMEOUT_SECONDS = 10
MEALS = ("BR", "LU", "DN")


@dataclass(frozen=True)
class MenuRecord:
    date: datetime.date
    meal: str
    restaurant_code: str
    restaurant_name: str
    lat: float | None
    lng: float | None
    raw_name: str
    price: int | None
    no_meat: bool


def fetch_raw(date: datetime.date) -> dict:
    """Download one day of menus. Stub this in tests."""
    day = date.isoformat()
    response = requests.get(
        API_URL,
        params={"start_date": day, "end_date": day},
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def parse(payload: dict) -> list[MenuRecord]:
    """Flatten the API response into one record per (day, meal, restaurant, menu)."""
    records = []
    for day in payload.get("result") or []:
        date = datetime.date.fromisoformat(day["date"])
        for meal in MEALS:
            for restaurant in day.get(meal) or []:
                for menu in restaurant.get("menus") or []:
                    records.append(MenuRecord(
                        date=date,
                        meal=meal,
                        restaurant_code=restaurant["code"],
                        restaurant_name=restaurant["name_kr"],
                        lat=restaurant.get("lat"),
                        lng=restaurant.get("lng"),
                        raw_name=menu["name_kr"],
                        price=menu.get("price"),
                        no_meat="No meat" in (menu.get("etc") or []),
                    ))
    return records
