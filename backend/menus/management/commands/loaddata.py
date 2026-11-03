"""Fixture loading is a source writer and prepares its recipe IDs once complete."""
from django.core.management.commands.loaddata import Command as LoadData
from django.db import connections, transaction

from menus.menu_registry import register_menu_ids
from menus.models import SalesMenu


class Command(LoadData):
    def handle(self, *fixture_labels, **options):
        using = options["database"]
        with transaction.atomic(using=using):
            result = super().handle(*fixture_labels, **options)
            if SalesMenu._meta.db_table in connections[using].introspection.table_names():
                for source in ("cafeteria", "general"):
                    register_menu_ids(source, using=using)
        return result
