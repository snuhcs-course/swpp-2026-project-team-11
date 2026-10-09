# AI-generated: written with Claude (Anthropic) and reviewed by the team.
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


class Command(BaseCommand):
    help = "Export one day's candidate dishes and the feature schema as JSON."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=datetime.date.fromisoformat, default=None,
                            help="YYYY-MM-DD (default: today in Asia/Seoul)")
        parser.add_argument("--meal", choices=["BR", "LU", "DN"], default=None,
                            help="one meal only (default: the whole day)")
        parser.add_argument("--output", default=None, help="write to this file instead of stdout")

    def handle(self, *args, **options):
        date = options["date"] or timezone.localdate()
        candidates = services.get_candidates(date, options["meal"])
        text = json.dumps({
            "date": date.isoformat(),
            "meal": options["meal"],
            "feature_version": FEATURE_VERSION,
            "features": services.get_feature_schema(),
            "candidates": candidates,
        }, ensure_ascii=False, indent=2)

        if options["output"]:
            pathlib.Path(options["output"]).write_text(text + "\n", encoding="utf-8")
            self.stdout.write(f"{date} {options['meal'] or '전체'}: 후보 {len(candidates)}개 -> {options['output']}")
        else:
            self.stdout.write(text)
