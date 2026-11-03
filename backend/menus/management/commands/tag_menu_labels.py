"""Tag difficult raw menu names once; a dry run makes no model calls."""
from __future__ import annotations

import datetime
import math

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from menus import labels, llm
from menus.models import MenuItem, MenuLabel, StoreMenu


class Command(BaseCommand):
    help = "Tag long or symbol-heavy sales-menu names with short display labels."

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group()
        scope.add_argument("--date", type=datetime.date.fromisoformat)
        scope.add_argument("--stores", action="store_true")
        scope.add_argument("--all", action="store_true")
        parser.add_argument("--batch-size", type=int, default=25)
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--dry-run", action="store_true", help="Count names and calls without invoking the model or writing")

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size must be positive")
        names = set()
        if not options["stores"]:
            items = MenuItem.objects.all()
            if not options["all"]:
                items = items.filter(date=options["date"] or timezone.localdate())
            names.update(items.values_list("raw_name", flat=True))
        if options["stores"] or options["all"]:
            names.update(StoreMenu.objects.values_list("raw_name", flat=True))
        names = sorted(name for name in names if labels.needs_label(name))
        if not options["force"]:
            current = set(MenuLabel.objects.filter(version=labels.LABEL_VERSION).values_list("name", flat=True))
            names = [name for name in names if name not in current]
        batches = math.ceil(len(names) / batch_size)
        self.stdout.write(f"Names: {len(names)}; initial model calls: {batches}; maximum with individual retries: {batches + len(names)}")
        if options["dry_run"] or not names:
            return
        if not llm.api_key_available():
            raise CommandError(f"{llm.key_name()} is missing.")
        results, failed = labels.extract(names, labels.build_llm(), batch_size, self.stdout.write)
        for name, result in results.items():
            MenuLabel.objects.update_or_create(name=name, defaults={"label": result.label, "version": labels.LABEL_VERSION})
        if results:
            from menus import services
            services._store_menus = None
        self.stdout.write(f"Saved: {len(results)}; failed: {len(failed)}")
        if failed:
            raise CommandError(f"Could not label {len(failed)} names; rerun to retry.")
