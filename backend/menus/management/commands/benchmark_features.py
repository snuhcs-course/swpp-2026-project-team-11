# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py benchmark_features --runs runs.jsonl [--ratings a.csv b.csv] [--output-dir DIR]

Write the feature extraction benchmark (menus/features/benchmark): report.md,
summary.json, one CSV per table and histograms. No LLM call. A section whose input
is missing (no repeats, no rating file) is skipped. --strict exits with an error
when the integrity check fails.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from menus.features.benchmark import human, report, runs, triplets


class Command(BaseCommand):
    help = "Benchmark feature extraction from stored runs (no LLM call)."

    def add_arguments(self, parser):
        parser.add_argument("--runs", required=True, help="runs file from collect_feature_runs")
        parser.add_argument("--ratings", nargs="*", default=[], help="filled rating forms, one per rater")
        parser.add_argument("--triplets", default=None, help="triplet file (default: the AI draft)")
        parser.add_argument("--policy", choices=("preference", "greedy", "lookahead"),
                            default=settings.RECOMMEND_DT_POLICY, help="decision-tree policy for downstream")
        parser.add_argument("--trials", type=int, default=None, help="downstream targets (default: every rated dish)")
        parser.add_argument("--output-dir", default="feature_benchmark_report")
        parser.add_argument("--no-plots", action="store_true")
        parser.add_argument("--strict", action="store_true", help="fail when the integrity check fails")

    def handle(self, *args, **options):
        try:
            records = runs.load(options["runs"])
            ratings = human.load(options["ratings"]) if options["ratings"] else None
            triplet_list = triplets.load(options["triplets"])
            if not records:
                raise ValueError("runs 파일에 기록이 없습니다.")
            results = report.run_sections(records, ratings, triplet_list, options["policy"], options["trials"])
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error
        path = report.write(results, records, options["output_dir"], plots=not options["no_plots"])
        for result in results:
            self.stdout.write(f"{report.status(result).upper():9s}{result['title']}")
        self.stdout.write(f"리포트 -> {path}")
        if options["strict"] and report.status(results[0]) == "fail":
            raise CommandError("integrity 검사 실패: integrity_problems.csv를 확인하세요.")
