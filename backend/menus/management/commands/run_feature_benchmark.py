# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py run_feature_benchmark --name NAME (--menu-set FILE | --date YYYY-MM-DD)

Run the feature extraction benchmark end to end and keep everything in one folder:

    feature_benchmark_results/NAME/
        config.json            what was run: dishes, conditions, extraction model, prompt, git commit
        report.md              every section's results (benchmark_features), summary.json
        runs/runs.jsonl        every extraction (collect_feature_runs)
        1_integrity/ ... 6_downstream_impact/   each section's CSVs and histograms
        4_human_reference/forms/     rating forms and the LLM's answers (export_feature_rating_form)
        4_human_reference/ratings/   the raters' filled copies, read when --ratings is not given

Each condition is collected the given number of times (default repeat 3,
shuffle_foods 2, shuffle_features 2). Running the same NAME again continues a
stopped run without repeating finished extractions, then rewrites the report.
--dry-run prints the LLM calls without making any.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import subprocess

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from menus import llm
from menus.features.benchmark import runs
from menus.features.prompt import PROMPT_VERSION
from menus.features.schema import FEATURE_VERSION

DEFAULT_CONDITIONS = "repeat:3,shuffle_foods:2,shuffle_features:2"
RATINGS = pathlib.Path("4_human_reference", "ratings")


def parse_conditions(text) -> list[tuple[str, int]]:
    """"repeat:3,shuffle_foods:2" -> [("repeat", 3), ("shuffle_foods", 2)]."""
    result = []
    for part in filter(None, (p.strip() for p in text.split(","))):
        condition, _, count = part.partition(":")
        if condition not in runs.CONDITIONS or not count.isdigit() or int(count) < 1:
            raise CommandError(f"--conditions takes condition:count pairs from {', '.join(runs.CONDITIONS)}: {part!r}")
        result.append((condition, int(count)))
    if not result:
        raise CommandError("--conditions is empty.")
    return result


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=settings.BASE_DIR, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


class Command(BaseCommand):
    help = "Collect extraction runs for every condition and write the benchmark report into one folder."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="folder name under --results-dir, e.g. 2026-10-20-luna")
        parser.add_argument("--menu-set", default=None, help="dishes from build_eval_menu_set")
        parser.add_argument("--date", type=datetime.date.fromisoformat, default=None, help="a day in the database")
        parser.add_argument("--conditions", default=DEFAULT_CONDITIONS, help=f"default: {DEFAULT_CONDITIONS}")
        parser.add_argument("--limit", type=int, default=None, help="at most N variant dishes")
        parser.add_argument("--invariant-limit", type=int, default=30)
        parser.add_argument("--batch-size", type=int, default=25)
        parser.add_argument("--triplets", default=None, help="triplet file (default: the AI draft)")
        parser.add_argument("--ratings", nargs="*", default=[],
                            help=f"filled rating forms, one per rater (default: NAME/{RATINGS}/)")
        parser.add_argument("--results-dir", default=str(pathlib.Path(settings.BASE_DIR).parent / "feature_benchmark_results"))
        parser.add_argument("--seed", type=int, default=0)
        parser.add_argument("--dry-run", action="store_true", help="print the LLM calls and stop")

    def handle(self, *args, **options):
        if bool(options["menu_set"]) == bool(options["date"]):
            raise CommandError("--menu-set과 --date 중 하나만 주세요.")
        conditions = parse_conditions(options["conditions"])
        folder = pathlib.Path(options["results_dir"]) / options["name"]
        runs_path = folder / "runs" / "runs.jsonl"
        ratings = options["ratings"] or sorted(str(path) for path in (folder / RATINGS).glob("*")
                                               if path.suffix in (".csv", ".xlsx") and not path.name.startswith("~$"))
        source = ["--menu-set", options["menu_set"]] if options["menu_set"] else ["--date", options["date"].isoformat()]
        common = [*source, "--output", str(runs_path), "--batch-size", str(options["batch_size"]),
                  "--invariant-limit", str(options["invariant_limit"]), "--seed", str(options["seed"])]
        common += ["--limit", str(options["limit"])] if options["limit"] is not None else []
        common += ["--triplets", options["triplets"]] if options["triplets"] else []
        if options["dry_run"]:
            common.append("--dry-run")
        else:
            runs_path.parent.mkdir(parents=True, exist_ok=True)
            (folder / "config.json").write_text(json.dumps({
                "name": options["name"], "updated_at": timezone.now().isoformat(),
                "dishes": {"menu_set": options["menu_set"], "date": options["date"] and options["date"].isoformat(),
                           "limit": options["limit"], "invariant_limit": options["invariant_limit"]},
                "conditions": dict(conditions), "batch_size": options["batch_size"], "seed": options["seed"],
                "triplets": options["triplets"], "ratings": ratings,
                "extraction_model": llm.model_id(), "feature_version": FEATURE_VERSION,
                "prompt_version": PROMPT_VERSION, "git_commit": git_commit(),
            }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

        for condition, count in conditions:
            self.stdout.write(f"== {condition} x {count}")
            call_command("collect_feature_runs", *common, "--condition", condition, "--repeats", str(count),
                         stdout=self.stdout)
        if options["dry_run"]:
            return
        self.stdout.write("== report")
        call_command("benchmark_features", "--runs", str(runs_path), "--output-dir", str(folder),
                     *(["--ratings", *ratings] if ratings else []),
                     *(["--triplets", options["triplets"]] if options["triplets"] else []), stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS(f"결과 -> {folder}"))
