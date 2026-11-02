"""python manage.py fetch_naver_menus --stores PATH --output PATH

For every food shop of 상가(상권)정보 (menus/sources/stores.py) within a station's
radius in AREAS, find its Naver Place by name near the shop and fetch that place's
menu (menus/sources/naver.py), then write all shops to a JSON snapshot. Nothing goes
into the DB. One search per shop and one menu request per Naver place found, a
second apart: about 2000 requests, 40 minutes, for the ~1100 shops around
서울대입구역 and 낙성대역. After MAX_CONSECUTIVE_FAILURES failed requests in a row
(Naver is likely blocking us) it writes what it has and stops with an error.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import time
from collections import Counter

import requests
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from menus.sources import naver
from menus.sources.stores import read_food_stores
from recommend.distance import distance_m

AREAS = {  # name: (lat, lng, radius in meters)
    "서울대입구역": (37.481247, 126.952739, 600),
    "낙성대역": (37.476930, 126.963693, 500),
}
REQUEST_INTERVAL_SECONDS = 1
MAX_CONSECUTIVE_FAILURES = 5
PROGRESS_EVERY = 100


def area_distances(lat: float, lng: float) -> dict[str, int]:
    """Meters to each station whose radius covers (lat, lng)."""
    distances = {area: distance_m(a_lat, a_lng, lat, lng) for area, (a_lat, a_lng, _) in AREAS.items()}
    return {area: m for area, m in distances.items() if m <= AREAS[area][2]}


def menu_json(menus: list[naver.Menu]) -> list[dict]:
    return [{k: v for k, v in dataclasses.asdict(m).items() if k != "place_id"} for m in menus]


class Command(BaseCommand):
    help = "Save the Naver Place menus of the food shops near 서울대입구역 and 낙성대역 to JSON."

    def add_arguments(self, parser):
        parser.add_argument("--stores", type=pathlib.Path, required=True,
                            help="상가(상권)정보 CSV of 서울, e.g. 소상공인시장진흥공단_상가(상권)정보_서울_202609.csv")
        parser.add_argument("--output", type=pathlib.Path, required=True)

    def handle(self, *args, **options):
        shops = [(store, distances) for store in read_food_stores(options["stores"])
                 if (distances := area_distances(store.lat, store.lng))]
        self.stdout.write(f"반경 안 음식점 {len(shops)}곳 (카페류 제외), 네이버에서 찾습니다.")

        menus_by_place: dict[str, list[naver.Menu]] = {}
        entries, failures_in_a_row = [], 0
        for store, distances in shops:
            entry = {**dataclasses.asdict(store), "distances_m": distances,
                     "status": "not_found", "naver": None, "menus": []}
            try:
                time.sleep(REQUEST_INTERVAL_SECONDS)
                place = naver.find_place(store.name, store.branch, store.lat, store.lng)
                if place and place.id not in menus_by_place:
                    time.sleep(REQUEST_INTERVAL_SECONDS)
                    menus_by_place[place.id] = naver.fetch_menus(place.id)
            except (requests.RequestException, ValueError) as error:
                failures_in_a_row += 1
                entry["status"] = "failed"
                self.stdout.write(self.style.WARNING(f"{store.name} {store.branch} ({store.id}): 실패: {error}"))
            else:
                failures_in_a_row = 0
                if place:
                    entry.update(status="matched", menus=menu_json(menus_by_place[place.id]), naver={
                        **dataclasses.asdict(place),
                        "distance_m": distance_m(store.lat, store.lng, place.lat, place.lng)})
            entries.append(entry)
            if len(entries) % PROGRESS_EVERY == 0:
                self.stdout.write(f"{len(entries)}/{len(shops)}")
            if failures_in_a_row >= MAX_CONSECUTIVE_FAILURES:
                break

        counts = self.write(options["output"], options["stores"], len(shops), entries)
        self.stdout.write(self.style.SUCCESS(
            f"{options['output']}: 음식점 {len(entries)}/{len(shops)} / 찾음 {counts['matched']} / "
            f"못 찾음 {counts['not_found']} / 실패 {counts['failed']} / "
            f"메뉴 {sum(len(e['menus']) for e in entries)}"))
        if failures_in_a_row >= MAX_CONSECUTIVE_FAILURES:
            raise CommandError(f"요청이 {failures_in_a_row}번 연속 실패해 멈췄습니다 (네이버 차단 가능성). "
                               f"처리한 {len(entries)}곳까지만 저장했습니다.")

    def write(self, output: pathlib.Path, stores_path: pathlib.Path, in_radius: int,
              entries: list[dict]) -> Counter:
        counts = Counter({"matched": 0, "not_found": 0, "failed": 0})
        counts.update(e["status"] for e in entries)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({
            "fetched_at": timezone.localtime().isoformat(timespec="seconds"),
            "stores_file": stores_path.name,
            "areas": {area: {"lat": lat, "lng": lng, "radius_m": radius}
                      for area, (lat, lng, radius) in AREAS.items()},
            "counts": {"in_radius": in_radius, **counts},
            "stores": entries,
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return counts
