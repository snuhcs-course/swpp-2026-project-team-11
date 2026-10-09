# AI-generated: written with OpenAI Codex and reviewed by the team.
"""Compare greedy and lookahead policies with a shared deterministic oracle."""
import datetime
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from menus.services import get_candidates, get_feature_schema
from question_engines.decision_tree.evaluation import compare_policies


class Command(BaseCommand):
    help = "Run a no-key, paired synthetic cafeteria-engine benchmark."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True, type=datetime.date.fromisoformat)
        parser.add_argument("--meal", choices=["BR", "LU", "DN"], default="LU")
        parser.add_argument("--trials", type=int, default=12)
        parser.add_argument("--seed", type=int, default=20261006)
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options):
        context = {"date": options["date"].isoformat(), "meal": options["meal"]}
        try:
            report = compare_policies(get_candidates(options["date"], options["meal"]), get_feature_schema(),
                trials=options["trials"], seed=options["seed"], context=context)
        except ValueError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(report["summary"], indent=2))
        if options["output"]:
            options["output"].parent.mkdir(parents=True, exist_ok=True)
            options["output"].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
