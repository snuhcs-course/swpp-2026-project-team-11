"""Explicit backfill for databases created before durable menu IDs."""
import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from menus.menu_registry import register_menu_ids


class Command(BaseCommand):
    help = "Register existing source recipes without model calls or feature changes."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=["all", "cafeteria", "general"], default="all")
        parser.add_argument("--date", type=datetime.date.fromisoformat)

    @transaction.atomic
    def handle(self, *args, **options):
        for source in ("cafeteria", "general"):
            if options["source"] in ("all", source):
                count = register_menu_ids(source, date=options["date"])
                self.stdout.write(f"Registered {count} {source} recipe keys")
