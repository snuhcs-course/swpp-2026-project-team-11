# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py benchmark_engines --scenarios scenarios.json --sessions sessions.jsonl

Write the question engine benchmark (question_engines/benchmark/report.py):
report.md, summary.json, sessions.csv and one folder per section. No LLM call.
--human adds sessions played by people (the user study) and --simulator-check the
simulated user's agreement with them.
"""

from __future__ import annotations

import json
import pathlib

from django.core.management.base import BaseCommand, CommandError

from question_engines.benchmark import report, scenarios


def read_lines(paths) -> list[dict]:
    rows = []
    for path in paths:
        rows += [json.loads(line) for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows


class Command(BaseCommand):
    help = "Report the question engine benchmark (no LLM call)."

    def add_arguments(self, parser):
        parser.add_argument("--scenarios", required=True)
        parser.add_argument("--sessions", nargs="+", required=True, help="files from collect_engine_sessions")
        parser.add_argument("--human", nargs="*", default=[], help="files from play_engine_session")
        parser.add_argument("--simulator-check", nargs="*", default=[], help="files from validate_simulator")
        parser.add_argument("--output-dir", default="engine_benchmark_report")
        parser.add_argument("--no-plots", action="store_true")

    def handle(self, *args, **options):
        try:
            data = scenarios.load(options["scenarios"])
            records = read_lines(options["sessions"])
            human = read_lines(options["human"])
            checks = read_lines(options["simulator_check"])
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error
        if not records:
            raise CommandError("세션 파일에 세션이 없습니다.")
        path = report.write(data, records, options["output_dir"], human=human, checks=checks,
                            plots=not options["no_plots"])
        self.stdout.write(self.style.SUCCESS(f"세션 {len(records)}개 -> {path}"))
