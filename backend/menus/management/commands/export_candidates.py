"""python manage.py export_candidates [--date YYYY-MM-DD] [--meal BR|LU|DN] [--output FILE]

Dump one day's candidates (default: today in Seoul) and the feature schema as JSON,
so the question engines can be developed without running the pipeline or an API key.
"""

from __future__ import annotations

import datetime
import json
import pathlib

from django.core.management.base import BaseCommand
from django.utils import timezone

from menus import services
from menus.features.schema import FEATURE_VERSION
from menus.models import MenuItem


class Command(BaseCommand):
    help = "Export one day's candidate dishes and the feature schema as JSON."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=datetime.date.fromisoformat, default=None,
                            help="YYYY-MM-DD (default: today in Asia/Seoul)")
        parser.add_argument("--meal", choices=["BR", "LU", "DN"], default=None,
                            help="one meal only (default: the whole day)")
        parser.add_argument("--output", default=None, help="write to this file instead of stdout")
        parser.add_argument("--feature-version", choices=["v1", FEATURE_VERSION], default=None)

    def handle(self, *args, **options):
        date = options["date"] or timezone.localdate()
        meal = options["meal"]
        version = options["feature_version"]
        if version is None:
            items = MenuItem.objects.filter(date=date, food__is_food=True)
            if meal:
                items = items.filter(meal=meal)
            has_v2 = items.exists() and not items.exclude(food__feature_version=FEATURE_VERSION).exists()
            version = FEATURE_VERSION if has_v2 else "v1"
        candidates = services.get_candidates(date, meal, feature_version=version,
                                             include_std=(version == FEATURE_VERSION))
        text = json.dumps({
            "date": date.isoformat(),
            "meal": options["meal"],
            "feature_version": version,
            "features": services.get_feature_schema(version),
            "candidates": candidates,
        }, ensure_ascii=False, indent=2)

        if options["output"]:
            pathlib.Path(options["output"]).write_text(text + "\n", encoding="utf-8")
            self.stdout.write(f"{date} {options['meal'] or '전체'}: 후보 {len(candidates)}개 -> {options['output']}")
        else:
            self.stdout.write(text)
