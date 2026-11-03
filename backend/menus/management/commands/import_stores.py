"""python manage.py import_stores --file stores.json [--dry-run] [--limit N] [--allow-partial] [--no-llm]
                                    [--review PATH]

Import the restaurants near the stations and their menu boards from a crawl file
(menus/sources/naver_stores.py) for general menu mode. Each menu line is resolved to
the dishes it stands for (menus/preprocess/store_lines.py) and stored as one StoreMenu
per dish; dishes share their Food rows with the cafeteria menus.

A file replaces the menus of the earlier import, so run this whenever the stores are
crawled again. A file that is not a whole crawl (failed or missing stores) is refused,
so a broken run cannot wipe menus; --allow-partial imports it and keeps the earlier
menus of those stores. --limit imports the first N restaurants and replaces only their
menus: use it to try the prompt on a local database.

Allergen tags of a menu line (extract_allergens --stores) carry over to the same line
(name and description) in the new file.

--dry-run reads the file and the cache only, with no LLM call and no write: it prints
what would be imported and how many menu lines the LLM would get.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from menus import llm as menu_llm
from menus.allergens import ALLERGEN_VERSION
from menus.management.commands.fetch_menus import ensure_foods
from menus.models import Restaurant, StoreMenu
from menus.menu_registry import register_menu_ids
from menus.preprocess import mapper, store_lines
from menus.preprocess.mapper import NAME_MAX
from menus.preprocess.review import line_rows, write_csv
from menus.sources import naver_stores

HEADER = ["type", "restaurants", "line", "dishes", "source"]
SKIPPED = {"failed": "실패", "not_matched": "미매칭", "no_menu": "메뉴 없음", "cafe_or_bakery": "카페·베이커리",
           "same_place": "중복"}
TEXT_MAX = 500  # StoreMenu.raw_name and description max_length


def _restaurant_fields(store: naver_stores.StoreRecord) -> dict:
    return {"name": store.name, "lat": store.lat, "lng": store.lng, "source": "naver",
            "category": store.category, "address": store.address, "place_id": store.place_id}


@transaction.atomic
def store(stores, entries, mappings, replace_codes: set[str] | None = None) -> Counter:
    """Upsert the restaurants and replace the menus: one StoreMenu per (line, dish). Returns counts.

    With replace_codes, only the menus of those restaurants are replaced; others keep
    theirs. Written with few queries, as fetch_menus.store is: the shared database is remote.
    """
    stats = Counter(entry.dropped for entry in entries if entry.dropped)
    existing = {r.code: r for r in Restaurant.objects.filter(code__in=[s.code for s in stores])}
    for s in stores:
        if s.code in existing:
            for field, value in _restaurant_fields(s).items():
                setattr(existing[s.code], field, value)
    if existing:
        Restaurant.objects.bulk_update(list(existing.values()), list(_restaurant_fields(stores[0])),
                                       batch_size=500)
    created = Restaurant.objects.bulk_create(
        [Restaurant(code=s.code, **_restaurant_fields(s)) for s in stores if s.code not in existing],
        batch_size=1000)
    restaurants = existing | {r.code: r for r in created}

    tagged = {(raw_name, description): allergens for raw_name, description, allergens in StoreMenu.objects
              .filter(allergen_version=ALLERGEN_VERSION).values_list("raw_name", "description", "allergens")}
    old = StoreMenu.objects.filter(restaurant__source="naver")
    (old if replace_codes is None else old.filter(restaurant__code__in=list(replace_codes))).delete()

    kept = [(entry, mappings[entry.key]) for entry in entries if not entry.dropped]
    foods, stats["new_foods"] = ensure_foods({
        (dish[:NAME_MAX], len(mapping.dishes) > 1)
        for _, mapping in kept if mapping.is_meal for dish in mapping.dishes})
    items, seen = [], set()
    for entry, mapping in kept:
        if not mapping.is_meal:
            stats["not_meal"] += 1
            continue
        if not mapping.dishes:
            stats["unnamed"] += 1
            continue
        if len(mapping.dishes) > 1:
            stats["split_lines"] += 1
        raw_name, description = entry.raw_name[:TEXT_MAX], entry.description[:TEXT_MAX]
        allergens = tagged.get((raw_name, description))
        for dish in mapping.dishes:
            food = foods[(dish[:NAME_MAX], len(mapping.dishes) > 1)]
            unique = (entry.store.code, raw_name, food.pk)  # as unique_store_menu_per_dish
            if unique in seen:  # a menu board can list a line twice
                continue
            seen.add(unique)
            items.append(StoreMenu(
                restaurant=restaurants[entry.store.code], raw_name=raw_name, description=description,
                food=food, price=entry.price,
                allergens=allergens or [], allergen_version=ALLERGEN_VERSION if allergens is not None else ""))
    StoreMenu.objects.bulk_create(items, batch_size=1000)
    register_menu_ids("general", restaurant_ids=[place.pk for place in restaurants.values()])

    stats["restaurants"] = len(restaurants)
    stats["menu_items"] = len(items)
    stats["dishes"] = len({item.food_id for item in items})
    return stats


def review_rows(entries, lines, mappings) -> list[list]:
    """Rows for a person to check: the lines the rules dropped, then those of review.line_rows."""
    dropped, places = defaultdict(set), defaultdict(set)
    for entry in entries:
        (dropped[(entry.dropped, entry.name)] if entry.dropped else places[entry.key]).add(entry.store.name)
    rows = [[f"rule_{kind}", ", ".join(sorted(names)), name, "", "rule"]
            for (kind, name), names in sorted(dropped.items())]
    # The ref ("A세트 @홍콩반점") is what overrides.json "lines" matches.
    return rows + line_rows({key: {"name": line.ref, "cafeterias": places[key]} for key, line in lines.items()},
                            mappings)


class Command(BaseCommand):
    help = "Import the restaurants near the stations and their menus from a crawl file."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="the crawl JSON")
        parser.add_argument("--dry-run", action="store_true",
                            help="print what would be imported; no LLM call, no write")
        parser.add_argument("--limit", type=int, default=None, help="import only the first N restaurants")
        parser.add_argument("--allow-partial", action="store_true",
                            help="import a file with failed or missing stores, keeping their earlier menus")
        parser.add_argument("--no-llm", action="store_true",
                            help="do not call the LLM; new lines are stored as one dish each")
        parser.add_argument("--review", default=None, help="also write a review CSV here")
        parser.add_argument("--batch-size", type=int, default=25)

    def handle(self, *args, **options):
        if options["batch_size"] < 1 or (options["limit"] is not None and options["limit"] < 1):
            raise CommandError("--batch-size와 --limit은 양수여야 합니다.")
        try:
            data = naver_stores.read(options["file"])
        except (OSError, ValueError) as error:
            raise CommandError(f"크롤 파일을 읽지 못했습니다: {error}") from error
        problems = naver_stores.incomplete(data)
        if problems and not (options["dry_run"] or options["allow_partial"]):
            raise CommandError(
                f"크롤 파일이 완전하지 않습니다 ({', '.join(problems)}). 다시 수집하거나, 그 가게들의 기존 메뉴를 "
                "남기고 가져오려면 --allow-partial을 붙이세요.")
        stores, skipped = naver_stores.parse(data)
        stores = stores[:options["limit"]]
        entries = store_lines.entries(stores)
        lines = store_lines.distinct_lines(entries)
        rules = Counter(entry.dropped for entry in entries if entry.dropped)
        self.stdout.write(
            f"가게 {len(stores)}곳 (파일 {len(data['stores'])}곳, 제외: "
            + ", ".join(f"{SKIPPED[k]} {v}" for k, v in skipped.items())
            + f") / 메뉴 줄 {len(entries)} (규칙 제외: 공지 {rules['notice']}, 술·음료 {rules['drink']}) "
            f"/ 서로 다른 줄 {len(lines)}")
        if problems:
            self.stdout.write(self.style.WARNING(f"완전하지 않은 크롤 파일: {', '.join(problems)}"))
        if options["dry_run"]:
            self.dry_run(data, stores, entries, lines, options["batch_size"])
            return

        llm = None
        if not options["no_llm"]:
            if menu_llm.api_key_available():
                llm = mapper.build_llm()
            else:
                self.stdout.write(f"{menu_llm.key_name()}가 없어 새 메뉴 줄은 LLM 없이 한 덩어리로 저장합니다.")
        mappings = store_lines.map_store_lines(lines, llm, on_progress=self.stdout.write,
                                               batch_size=options["batch_size"])
        if options["limit"] is not None:
            replace_codes = {s.code for s in stores}
        elif problems:
            replace_codes = naver_stores.settled_codes(data)
        else:
            replace_codes = None
        stats = store(stores, entries, mappings, replace_codes)
        if options["review"]:
            rows = review_rows(entries, lines, mappings)
            write_csv(options["review"], HEADER, rows)
            counts = Counter(row[0] for row in rows)
            self.stdout.write(f"검토 행 {len(rows)}개 ({', '.join(f'{k} {v}' for k, v in sorted(counts.items()))})"
                              f" -> {options['review']}")
        sources = Counter(m.source for m in mappings.values())
        self.stdout.write(self.style.SUCCESS(
            f"가게 {stats['restaurants']} / 메뉴 {stats['menu_items']} / 요리 {stats['dishes']} "
            f"(신규 {stats['new_foods']}) / 세트 나눔 {stats['split_lines']} / 식사 아님 {stats['not_meal']} / "
            f"요리 이름 없음 {stats['unnamed']} / 서로 다른 줄 {len(lines)} "
            f"({', '.join(f'{k} {v}' for k, v in sorted(sources.items()))})"))
        if llm is not None:
            fallen = [lines[key].name for key, m in mappings.items() if m.source == "rule"]
            if fallen:
                raise CommandError(
                    f"LLM이 메뉴 줄 {len(fallen)}개를 처리하지 못해 한 덩어리로 저장했습니다 "
                    f"(예: {', '.join(fallen[:3])}). 키·할당량을 확인하고 다시 실행하세요.")

    def dry_run(self, data, stores, entries, lines, batch_size):
        categories, excluded = Counter(), Counter()
        for store in data["stores"]:
            if store["status"] != "matched" or not store.get("naver") or not store.get("menus"):
                continue
            serves = naver_stores.serves_meals(store)
            categories[(serves, f"{store.get('category') or '-'}/{store.get('subcategory') or '-'}")] += 1
            if not serves:
                excluded[store["naver"].get("category") or "-"] += 1
        self.stdout.write("매칭되고 메뉴가 있는 가게의 업종 (상가정보 중분류/소분류):")
        for (serves, category), count in sorted(categories.items(), key=lambda kv: (not kv[0][0], -kv[1])):
            self.stdout.write(f"  {'넣음' if serves else '제외'} {category} {count}")
        if excluded:
            self.stdout.write("제외한 가게의 네이버 카테고리: "
                              + ", ".join(f"{name} {count}" for name, count in excluded.most_common(20)))
        far = [s for s in stores if s.match_distance_m is not None and s.match_distance_m > 100]
        if far:
            self.stdout.write(f"상가정보와 네이버 위치가 100m 넘게 떨어진 가게 {len(far)}곳 (예: "
                              + ", ".join(f"{s.name} {s.match_distance_m}m" for s in far[:5]) + ")")
        for kind, label in (("notice", "공지"), ("drink", "술·음료")):
            names = list(dict.fromkeys(e.name for e in entries if e.dropped == kind))
            if names:
                self.stdout.write(f"규칙으로 뺀 {label} {len(names)}종 (예: {', '.join(names[:8])})")
        pending = len(lines) - len(store_lines.known_answers(lines))
        self.stdout.write(self.style.SUCCESS(
            f"LLM에 보낼 줄 {pending}개 (나머지 {len(lines) - pending}개는 덮어쓰기·캐시) "
            f"-> 호출 약 {math.ceil(pending / batch_size)}회 (배치 {batch_size}줄, 재시도 별도). "
            f"그 뒤 새 요리마다 특징·알레르기 태깅이 따로 필요합니다."))
