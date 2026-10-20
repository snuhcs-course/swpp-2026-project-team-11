# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py export_feature_rating_form --runs runs.jsonl --output rating_form.xlsx [--n 50]

Write a blank rating form for human raters: a sample of the menu dishes in the
runs file, spread over cafeterias or food groups, with a mean and a std column per
rubric feature and a recipe_notes column. A .xlsx output is an Excel workbook with
input checks, the rater's guide and the rubric; any other is a CSV. Each rater fills
in a copy with the extractor's rubric (menus/features/instructions.txt, rubric.json);
the copies go to benchmark_features --ratings. The format is in menus/features/benchmark/human.py.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from menus.features.benchmark import human, runs


class Command(BaseCommand):
    help = "Write a blank human rating form for a sample of the benchmarked dishes."

    def add_arguments(self, parser):
        parser.add_argument("--runs", required=True, help="runs file from collect_feature_runs")
        parser.add_argument("--output", required=True)
        parser.add_argument("--n", type=int, default=50, help="number of dishes to rate")
        parser.add_argument("--segment", choices=(runs.VARIANT, runs.INVARIANT, "all"), default="all",
                            help="which dishes to sample (default: all menu dishes)")
        parser.add_argument("--seed", type=int, default=0)

    def handle(self, *args, **options):
        try:
            runset = runs.RunSet(runs.load(options["runs"]))
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error
        pool = runset.menu_names() if options["segment"] == "all" else runset.names({options["segment"]})
        if not pool:
            raise CommandError(f"runs 파일에 {options['segment']} 음식이 없습니다.")
        names = runs.stratified_sample(pool, runset.group, options["n"], options["seed"])
        human.write_form(options["output"], names)
        self.stdout.write(self.style.SUCCESS(f"음식 {len(names)}개 평가 양식 -> {options['output']}"))
