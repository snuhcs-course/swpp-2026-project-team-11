"""python manage.py extract_allergens [--date YYYY-MM-DD | --stores] [--dry-run]

Tags one day's dishes with allergens (menus/allergens.py), once per name: the
standalone and set rows of a dish share the answer, and a name tagged with the
current ALLERGEN_VERSION is not sent again unless --force.

With --stores it tags the menu lines of the restaurants near the stations instead:
a whole line with its description ("낙지볶음+콩나물국+계란찜+공기밥"), sides included,
since the dishes kept for recommendation leave sides out. Lines with the same text
share the answer.
"""
from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from menus import allergens, llm
from menus.allergens import ALLERGEN_VERSION
from menus.models import Food, StoreMenu
from menus.preprocess.store_lines import allergen_text


def _dishes(date: datetime.date) -> tuple[dict, dict]:
    """({name: [Food]} served on `date`, {name: tags} already known for those names)."""
    targets = {}
    for food in Food.objects.filter(menu_items__date=date, is_food=True).order_by("name", "pk").distinct():
        targets.setdefault(food.name, []).append(food)
    known = dict(Food.objects.filter(name__in=targets, allergen_version=ALLERGEN_VERSION)
                 .values_list("name", "allergens"))
    return targets, known


def _store_lines() -> tuple[dict, dict]:
    """({line text: [StoreMenu]}, {line text: tags} already known for those texts)."""
    targets, known = {}, {}
    for row in StoreMenu.objects.order_by("raw_name", "description", "pk"):
        text = allergen_text(row.raw_name, row.description)
        targets.setdefault(text, []).append(row)
        if row.allergen_version == ALLERGEN_VERSION:
            known.setdefault(text, row.allergens)
    return targets, known


class Command(BaseCommand):
    help = "Tag preprocessed dishes (or restaurant menu lines) with the allergens they may contain."

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group()
        scope.add_argument("--date", type=datetime.date.fromisoformat, default=None)
        scope.add_argument("--stores", action="store_true",
                           help="the menu lines of the restaurants near the stations instead of a day's dishes")
        parser.add_argument("--batch-size", type=int, default=25)
        parser.add_argument("--limit", type=int, default=None, help="Maximum number of distinct names")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--dry-run", action="store_true",
                            help="Call the model and print results without database writes")

    def handle(self, *args, **options):
        if options["batch_size"] < 1 or (options["limit"] is not None and options["limit"] < 1):
            raise CommandError("--batch-size와 --limit은 양수여야 합니다.")
        if options["stores"]:
            (targets, known), scope = _store_lines(), "일반 식당"
        else:
            date = options["date"] or timezone.localdate()
            (targets, known), scope = _dishes(date), date
        if options["force"]:
            known = {}
        pending = [name for name, rows in targets.items()
                   if options["force"] or any(row.allergen_version != ALLERGEN_VERSION for row in rows)]
        pending = pending[:options["limit"]]
        if not pending:
            self.stdout.write(f"{scope}: 새로 태깅할 음식 없음")
            return
        missing = [name for name in pending if name not in known]
        results, failed = {}, []
        if missing:
            if not llm.api_key_available():
                raise CommandError(f"{llm.key_name()}가 없습니다. 레포 루트의 .env에 넣어 주세요.")
            results, failed = allergens.extract(missing, allergens.build_llm(),
                                                batch_size=options["batch_size"],
                                                on_progress=self.stdout.write)
        completed, tagged = 0, []
        for name in pending:
            if name in results:
                keys = results[name].keys()
            elif name in known:
                keys = known[name]
            else:
                continue
            if options["dry_run"]:
                self.stdout.write(f"{name}: {', '.join(keys) or '-'}")
            else:
                for row in targets[name]:
                    row.allergens, row.allergen_version = keys, ALLERGEN_VERSION
                    tagged.append(row)
            completed += 1
        if tagged:
            type(tagged[0]).objects.bulk_update(tagged, ["allergens", "allergen_version"], batch_size=1000)
        self.stdout.write(f"완료: 이름 {completed}개 {'확인' if options['dry_run'] else '저장'}, 실패 {len(failed)}개")
        if failed:
            raise CommandError(f"알레르기 정보를 뽑지 못한 음식 {len(failed)}개 (예: {', '.join(failed[:3])}). "
                               "다시 실행하세요.")
