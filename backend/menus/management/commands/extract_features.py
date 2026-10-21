# AI-generated: written with Codex (OpenAI) and reviewed by the team.
"""Extract once per dish name and share measurements across standalone/set rows."""
from __future__ import annotations
import datetime
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from pydantic import ValidationError
from menus import llm
from menus.features import extractor
from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION, LLM_FEATURE_KEYS
from menus.models import Food

def cached_features(food):
    if food.feature_version != FEATURE_VERSION:
        return None
    if not isinstance(food.features, dict) or not isinstance(food.feature_std, dict):
        return None
    if set(food.features) != set(FEATURE_KEYS) or set(food.feature_std) != set(FEATURE_KEYS):
        return None
    if food.features["meal_variety"] != float(food.is_set) or food.feature_std["meal_variety"] != 0:
        return None
    try:
        return extractor.FoodFeatures.model_validate({
            key: {"mean": food.features[key], "std": food.feature_std[key]}
            for key in LLM_FEATURE_KEYS
        })
    except (ValidationError, TypeError):
        return None

class Command(BaseCommand):
    help = "Extract mean/std for preprocessed dishes, once per name."

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
        for food in (Food.objects.filter(menu_items__date=date, is_food=True)
                     .order_by("name", "is_set", "pk").distinct()):
            targets.setdefault(food.name, []).append(food)
        names = list(targets)
        variants = {}
        for food in Food.objects.filter(name__in=names).order_by("-extracted_at", "pk"):
            variants.setdefault(food.name, []).append(food)
        pending, cached = [], {}
        for name in names:
            source = next(((food, stats) for food in variants[name]
                           if (stats := cached_features(food)) is not None), None)
            if not options["force"] and source is not None:
                if all(cached_features(food) == source[1] for food in targets[name]):
                    continue
                cached[name] = source
            pending.append(name)
        if options["limit"]:
            pending = pending[:options["limit"]]
        if not pending:
            self.stdout.write(f"{date}: 새로 태깅할 음식 없음")
            return
        missing = [name for name in pending if name not in cached or options["force"]]
        results, failed = {}, []
        if missing:
            if not extractor.api_key_available():
                raise CommandError(f"{llm.key_name()}가 없습니다. 레포 루트의 .env에 넣어 주세요.")
            results, failed = extractor.extract(
                missing, extractor.build_llm(), batch_size=options["batch_size"],
                on_progress=self.stdout.write,
            )
        now = timezone.now()
        completed = 0
        for name in pending:
            if name in results:
                stats, model, extracted_at = results[name].features, llm.model_id(), now
            elif name in cached and not options["force"]:
                source, stats = cached[name]
                model, extracted_at = source.extraction_model, source.extracted_at
            else:
                continue
            values = stats.model_dump()
            means = {key: value["mean"] for key, value in values.items()}
            stds = {key: value["std"] for key, value in values.items()}
            if options["dry_run"]:
                self.stdout.write(f"{name}: {values}")
            else:
                with transaction.atomic():
                    for food in targets[name]:
                        suffix = " (세트)" if food.is_set else ""
                        base = (food.display_name or food.name).removesuffix(" (세트)")
                        food.display_name = base[:50 - len(suffix)] + suffix
                        food.features = means | {"meal_variety": float(food.is_set)}
                        food.feature_std = stds | {"meal_variety": 0.0}
                        food.feature_version = FEATURE_VERSION
                        food.extraction_model = model
                        food.extracted_at = extracted_at
                        food.save(update_fields=["display_name", "features", "feature_std",
                                                 "feature_version", "extraction_model", "extracted_at"])
            completed += 1
        self.stdout.write(f"완료: 이름 {completed}개 {'확인' if options['dry_run'] else '저장'}, 실패 {len(failed)}개")
        if failed:
            raise CommandError(f"특징을 뽑지 못한 음식 {len(failed)}개 (예: {', '.join(failed[:3])}). 다시 실행하세요.")
