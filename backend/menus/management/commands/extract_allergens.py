"""python manage.py extract_allergens [--date YYYY-MM-DD] [--dry-run]

Tags one day's dishes with allergens (menus/allergens.py), once per name: the
standalone and set rows of a dish share the answer, and a name tagged with the
current ALLERGEN_VERSION is not sent again unless --force.
"""
from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from menus import allergens, llm
from menus.allergens import ALLERGEN_VERSION
from menus.models import Food


class Command(BaseCommand):
    help = "Tag preprocessed dishes with the allergens they may contain, once per name."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=datetime.date.fromisoformat, default=None)
        parser.add_argument("--batch-size", type=int, default=25)
        parser.add_argument("--limit", type=int, default=None, help="Maximum number of distinct names")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--dry-run", action="store_true",
                            help="Call the model and print results without database writes")

    def handle(self, *args, **options):
        if options["batch_size"] < 1 or (options["limit"] is not None and options["limit"] < 1):
            raise CommandError("--batch-size와 --limit은 양수여야 합니다.")
        date = options["date"] or timezone.localdate()
        targets = {}
        for food in Food.objects.filter(menu_items__date=date, is_food=True).order_by("name", "pk").distinct():
            targets.setdefault(food.name, []).append(food)
        known = {} if options["force"] else dict(
            Food.objects.filter(name__in=targets, allergen_version=ALLERGEN_VERSION)
            .values_list("name", "allergens"))
        pending = [name for name, foods in targets.items()
                   if options["force"] or any(food.allergen_version != ALLERGEN_VERSION for food in foods)]
        pending = pending[:options["limit"]]
        if not pending:
            self.stdout.write(f"{date}: 새로 태깅할 음식 없음")
            return
        missing = [name for name in pending if name not in known]
        results, failed = {}, []
        if missing:
            if not llm.api_key_available():
                raise CommandError(f"{llm.key_name()}가 없습니다. 레포 루트의 .env에 넣어 주세요.")
            results, failed = allergens.extract(missing, allergens.build_llm(),
                                                batch_size=options["batch_size"],
                                                on_progress=self.stdout.write)
        completed = 0
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
                Food.objects.filter(pk__in=[food.pk for food in targets[name]]).update(
                    allergens=keys, allergen_version=ALLERGEN_VERSION)
            completed += 1
        self.stdout.write(f"완료: 이름 {completed}개 {'확인' if options['dry_run'] else '저장'}, 실패 {len(failed)}개")
        if failed:
            raise CommandError(f"알레르기 정보를 뽑지 못한 음식 {len(failed)}개 (예: {', '.join(failed[:3])}). "
                               "다시 실행하세요.")
