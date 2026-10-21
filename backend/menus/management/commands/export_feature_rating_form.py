# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""python manage.py export_feature_rating_form --runs runs.jsonl --output rating_form.xlsx
       [--all invariant] [--close variant] [--n 50 --segment all]

Write a blank rating form for human raters, with a mean and a std column per rubric
feature and a recipe_notes column. The dishes come from the runs file:
  --all KIND     every dish of that kind
  --close KIND   each dish of that kind whose closest dish is a collision (mean gap
                 <= COLLISION, distribution.py), together with that dish, which may be
                 a triplet-only dish: do raters tell them apart?
  --n, --segment a random sample of the rest, spread over cafeterias or food groups
The rows are grouped by kind (고정 메뉴, 매일 바뀌는 메뉴, 비교용 예시) and shuffled within
a kind so that similar dishes are not next to each other; <output>_selection.csv
says why each dish is in the form (raters do not see it).

A .xlsx output is an Excel workbook with input checks, the rater's guide and the
rubric; any other is a CSV. Each rater fills in a copy with the extractor's rubric
(menus/features/instructions.txt, rubric.json); the copies go to
benchmark_features --ratings. The format is in menus/features/benchmark/human.py.
"""

from __future__ import annotations

import csv
import pathlib
import random

from django.core.management.base import BaseCommand, CommandError

from menus.features.benchmark import distribution, human, runs

KINDS = (runs.VARIANT, runs.INVARIANT)
LABELS = {runs.INVARIANT: "고정 메뉴", runs.VARIANT: "매일 바뀌는 메뉴", runs.SUITE: "비교용 예시", runs.MENU: "메뉴"}


class Command(BaseCommand):
    help = "Write a blank human rating form for a selection of the benchmarked dishes."

    def add_arguments(self, parser):
        parser.add_argument("--runs", required=True, help="runs file from collect_feature_runs")
        parser.add_argument("--output", required=True)
        parser.add_argument("--all", action="append", choices=KINDS, default=[], help="every dish of this kind")
        parser.add_argument("--close", action="append", choices=KINDS, default=[],
                            help="dishes of this kind with a close dish, and that dish")
        parser.add_argument("--n", type=int, default=50, help="number of other dishes to sample")
        parser.add_argument("--segment", choices=(*KINDS, "all"), default="all",
                            help="which dishes to sample (default: all menu dishes)")
        parser.add_argument("--seed", type=int, default=0)

    def handle(self, *args, **options):
        try:
            runset = runs.RunSet(runs.load(options["runs"]))
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error
        reasons = {}  # dish -> (reason, close dish, mean gap); the first reason wins
        for name in runset.names(set(options["all"])) if options["all"] else []:
            reasons[name] = ("all", "", "")
        if options["close"]:
            for name, partner, gap in distribution.neighbours(runset, set(options["close"])):
                reasons.setdefault(name, ("close", partner, gap))
                reasons.setdefault(partner, ("close", name, gap))
        pool = runset.menu_names() if options["segment"] == "all" else runset.names({options["segment"]})
        pool = [name for name in pool if name not in reasons]
        for name in runs.stratified_sample(pool, runset.group, options["n"], options["seed"]):
            reasons[name] = ("sample", "", "")
        if not reasons:
            raise CommandError("고를 음식이 없습니다.")
        sources = {record.name: record.source for record in runset.records}
        names = sorted(reasons)
        random.Random(options["seed"]).shuffle(names)
        names.sort(key=lambda name: list(LABELS).index(sources[name]))
        output = pathlib.Path(options["output"])
        human.write_form(output, [(name, LABELS[sources[name]]) for name in names])
        selection = output.with_name(f"{output.stem}_selection.csv")
        with open(selection, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "source", "reason", "close dish", "mean gap"])
            writer.writerows([name, sources[name], *reasons[name]] for name in sorted(reasons))
        self.stdout.write(self.style.SUCCESS(f"음식 {len(names)}개 평가 양식 -> {output} (선정 이유 {selection.name})"))
