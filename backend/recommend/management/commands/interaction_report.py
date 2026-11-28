"""python manage.py interaction_report [--dir DIR] [--since YYYY-MM-DD] [--all]

Print the key numbers of the interaction log: where solo sessions end, the questions that end
them, reaching a proposal, completion, and how group rooms end (recommend/interaction_report.py).
--dir defaults to METCHU_INTERACTION_LOG_DIR; --all adds the rest of the numbers.
"""
from __future__ import annotations

import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recommend import interaction_log, interaction_report


class Command(BaseCommand):
    help = "Print the key numbers of the interaction log."

    def add_arguments(self, parser):
        parser.add_argument("--dir", type=Path, help="Log directory (default: METCHU_INTERACTION_LOG_DIR)")
        parser.add_argument("--since", type=datetime.date.fromisoformat, help="First UTC day to read")
        parser.add_argument("--all", action="store_true", dest="full", help="Add the rest of the numbers")

    def handle(self, *args, **options):
        root = options["dir"] or interaction_log._root()
        if root is None or not root.is_dir():
            raise CommandError("No log directory: set METCHU_INTERACTION_LOG_DIR or pass --dir.")
        events = interaction_report.read(root, options["since"])
        self.stdout.write(interaction_report.report(events, full=options["full"]), ending="")
