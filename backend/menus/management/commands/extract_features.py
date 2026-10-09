# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py extract_features [--date YYYY-MM-DD] [--batch-size 25] [--limit N] [--force] [--dry-run]

Tag the dishes served on one day (default: today in Seoul) with feature
probabilities via Gemini. Dishes already tagged under the current
FEATURE_VERSION are skipped, so only new dishes cost an LLM call.
"""

from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from menus.features import extractor
from menus.features.schema import FEATURE_VERSION
from menus.models import Food


class Command(BaseCommand):
    help = "Extract food features for one day's dishes with an LLM."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=datetime.date.fromisoformat, default=None,
                            help="YYYY-MM-DD (default: today in Asia/Seoul)")
        parser.add_argument("--batch-size", type=int, default=25)
        parser.add_argument("--limit", type=int, default=None,
                            help="tag at most N dishes (for a quick check)")
        parser.add_argument("--force", action="store_true",
                            help="re-tag dishes that are already tagged")
        parser.add_argument("--dry-run", action="store_true",
                            help="print the results instead of saving them")

    def handle(self, *args, **options):
        date = options["date"] or timezone.localdate()
        foods = Food.objects.filter(menu_items__date=date).distinct().order_by("name")
        if not options["force"]:
            foods = foods.exclude(feature_version=FEATURE_VERSION)
        foods = list(foods[:options["limit"]] if options["limit"] else foods)
        if not foods:
            self.stdout.write(f"{date}: 새로 태깅할 음식 없음")
            return
        if not extractor.api_key_available():
            raise CommandError("GOOGLE_API_KEY가 없습니다. 레포 루트의 .env에 넣어 주세요.")

        self.stdout.write(f"{date}: 음식 {len(foods)}개 태깅 ({extractor.MODEL}, {FEATURE_VERSION})")
        results, failed = extractor.extract(
            [food.name for food in foods], extractor.build_llm(),
            batch_size=options["batch_size"], on_progress=self.stdout.write,
        )

        if options["dry_run"]:
            self.print_table(results)
        else:
            now = timezone.now()
            for food in foods:
                annotation = results.get(food.name)
                if annotation is None:
                    continue
                food.is_food = annotation.is_food
                food.display_name = annotation.display_name[:50]
                food.food_group = annotation.food_group[:30]
                food.features = {k: round(v, 1) for k, v in annotation.features.model_dump().items()}
                food.feature_version = FEATURE_VERSION
                food.extraction_model = extractor.MODEL
                food.extracted_at = now
                food.save()

        self.stdout.write(self.style.SUCCESS(
            f"완료: {len(results)}개 {'확인' if options['dry_run'] else '저장'}, 실패 {len(failed)}개"))
        for name in failed:
            self.stdout.write(self.style.WARNING(f"  실패: {name}"))

    def print_table(self, results):
        for name, annotation in results.items():
            features = annotation.features.model_dump()
            top = sorted((k for k, v in features.items() if v >= 0.7), key=lambda k: -features[k])
            mark = "O" if annotation.is_food else "X"
            self.stdout.write(f"[{mark}] {annotation.display_name} ({annotation.food_group}) "
                              f"<- {name}\n      {', '.join(f'{k}={features[k]:.1f}' for k in top)}")
