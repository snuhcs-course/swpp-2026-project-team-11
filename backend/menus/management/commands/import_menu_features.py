"""Import external whole-menu annotations; collected/generated data stays outside Git."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from menus.features.schema import FEATURE_VERSION
from menus.menu_profiles import description_digest, offer_key, title, validate_features
from menus.models import SalesMenu


class Command(BaseCommand):
    help = "Import a JSON array of original menu profiles, without model calls."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=Path, required=True)
        parser.add_argument("--source", choices=["general", "cafeteria"], default="general")
        parser.add_argument("--dry-run", action="store_true", help="validate only; no DB writes")

    def handle(self, *args, **options):
        try:
            items = json.loads(options["file"].read_text(encoding="utf-8"))
            if not isinstance(items, list):
                raise ValueError("Expected a JSON array")
            rows = {}
            for item in items:
                name, code = item["name"], item["store_code"]
                description = item.get("description", "")
                if (not isinstance(name, str) or not title(name) or len(name) > 500
                        or not isinstance(code, str) or not code or len(code) > 100
                        or not isinstance(description, str)):
                    raise ValueError("Invalid menu name, source description or restaurant code")
                if item.get("feature_schema_version", FEATURE_VERSION) != FEATURE_VERSION:
                    raise ValueError("Only the current feature schema is supported")
                validate_features(item["features"], item["feature_std"])
                key = offer_key(options["source"], code, name, description)
                metadata = {field: item[field] for field in (
                    "model", "reasoning_effort", "annotation_version", "std_source",
                    "interpreted_description", "source_corrected", "components") if field in item}
                fields = dict(source=options["source"], restaurant_code=code, name=title(name),
                              description_sha256=description_digest(description),
                              features=item["features"], feature_std=item["feature_std"],
                              feature_version=FEATURE_VERSION, annotation_metadata=metadata)
                if key in rows and rows[key] != fields:
                    raise ValueError(f"Conflicting profiles for {code}: {name}")
                rows[key] = fields
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise CommandError(str(error)) from error
        if not options["dry_run"]:
            with transaction.atomic():
                existing = {row.key: row for row in SalesMenu.objects.filter(key__in=rows)}
                created, updated = [], []
                for key, fields in rows.items():
                    if key in existing:
                        row = existing[key]
                        for field, value in fields.items():
                            setattr(row, field, value)
                        row.updated_at = timezone.now()
                        updated.append(row)
                    else:
                        created.append(SalesMenu(key=key, **fields))
                SalesMenu.objects.bulk_create(created, batch_size=500)
                if updated:
                    SalesMenu.objects.bulk_update(updated, [*next(iter(rows.values())), "updated_at"], batch_size=500)
        self.stdout.write(f"{'Validated' if options['dry_run'] else 'Imported'} {len(rows)} menu profiles")
