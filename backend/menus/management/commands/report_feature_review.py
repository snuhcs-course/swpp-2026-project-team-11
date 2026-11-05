"""python manage.py report_feature_review --reviews DIR/*.xlsx [--output report.md]

Read the filled feature review workbooks (export_feature_review) and report, per
source, the verdict shares, the pass against the bar fixed in
menus/features/benchmark/review.py, the raters' agreement on shared dishes and the
features called wrong. No LLM call.
"""

from __future__ import annotations

import pathlib

from django.core.management.base import BaseCommand, CommandError

from menus.features.benchmark import review


class Command(BaseCommand):
    help = "Report the human review of the extracted features."

    def add_arguments(self, parser):
        parser.add_argument("--reviews", nargs="+", required=True)
        parser.add_argument("--output", default=None, help="write the report here too")

    def handle(self, *args, **options):
        try:
            reviews = review.load(options["reviews"])
        except (OSError, ValueError, KeyError) as error:
            raise CommandError(str(error)) from error
        if not reviews:
            raise CommandError("상태가 적힌 행이 없습니다.")
        text = review.report(review.summarize(reviews))
        if options["output"]:
            pathlib.Path(options["output"]).write_text(text, encoding="utf-8")
        self.stdout.write(text)
