# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py run_daily_pipeline [--date YYYY-MM-DD] [--review PATH]

One day's menu, start to finish (default: today in Seoul):
  1. fetch_menus      - download, split combos, merge duplicates, store
  2. extract_features - tag the new dishes with feature values
  3. export_preprocess_review (with --review) - CSV for a person to check

Run it once a day; it needs GOOGLE_API_KEY. Re-running is safe: lines and dishes
resolved before are reused, so only new menu lines cost LLM calls. If a step fails
(e.g. Gemini errors on some lines), the other steps still run and the command then
exits with an error, so the daily GitHub Actions run fails visibly.
"""

from __future__ import annotations

import datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from menus import services
from menus.features.extractor import api_key_available


class Command(BaseCommand):
    help = "Fetch, preprocess and tag one day's cafeteria menu (and optionally export a review CSV)."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=datetime.date.fromisoformat, default=None,
                            help="YYYY-MM-DD (default: today in Asia/Seoul)")
        parser.add_argument("--review", default=None, help="also write the review CSV here")

    def handle(self, *args, **options):
        if not api_key_available():
            raise CommandError("GOOGLE_API_KEY가 없습니다. 레포 루트의 .env에 넣어 주세요.")
        date = options["date"] or timezone.localdate()
        day = date.isoformat()

        steps = [("[1/3] 메뉴 수집·전처리", ["fetch_menus", "--date", day]),
                 ("[2/3] 새 요리 특징 추출", ["extract_features", "--date", day])]
        if options["review"]:
            steps.append(("[3/3] 검토용 CSV",
                          ["export_preprocess_review", "--date", day, "--output", options["review"]]))
        errors = []
        for title, command in steps:
            self.stdout.write(title)
            try:
                call_command(*command, stdout=self.stdout)
            except CommandError as error:  # keep going: later steps still help, then fail below
                errors.append(f"{command[0]}: {error}")

        counts = {meal: len(services.get_candidates(date, meal)) for meal in ("BR", "LU", "DN")}
        self.stdout.write(self.style.SUCCESS(
            f"{day} 추천 후보: 아침 {counts['BR']} / 점심 {counts['LU']} / 저녁 {counts['DN']} "
            f"/ 하루 {len(services.get_candidates(date))}"))
        if errors:
            raise CommandError("\n".join(errors))
