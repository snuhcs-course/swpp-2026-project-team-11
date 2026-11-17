"""Import operational menu mappings into the existing durable sales-menu registry."""
import hashlib
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from menus.menu_profiles import offer_key, description_digest
from menus.models import SalesMenu, StoreMenu
from menus.personal import mapping_import
from menus.personal.offers import MAPPING_VERSION


class Command(BaseCommand):
    help = 'Preview a complete sales-menu mapping; --apply replaces general mappings in the selected DB. No model calls.'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=Path, required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        try:
            index = mapping_import.load(options['file'])
            source_hash = hashlib.sha256(options['file'].read_bytes()).hexdigest()
        except (OSError, ValueError) as error:
            raise CommandError(str(error)) from error
        records = StoreMenu.objects.values_list('restaurant__code', 'restaurant__name', 'raw_name', 'description').distinct()
        prepared = {}
        for code, owner, name, description in records:
            target = mapping_import.resolve(index, owner, name)
            key = offer_key('general', code, name, description)
            if key in prepared and prepared[key].annotation_metadata['canonical_id'] != target:
                raise CommandError('Source menus collide with different canonical targets')
            prepared[key] = SalesMenu(key=key, source='general', restaurant_code=code, name=name,
                description_sha256=description_digest(description), annotation_metadata={
                    'mapping_version': MAPPING_VERSION, 'canonical_id': target, 'source_sha256': source_hash})
        if not prepared:
            raise CommandError('No general sales menus in the selected database')
        active = sum(row.annotation_metadata['canonical_id'] is not None for row in prepared.values())
        self.stdout.write(f'General mapping: {len(prepared)} offers; {active} active; {len(prepared)-active} excluded')
        if options['apply']:
            with transaction.atomic():
                # The old general recipe/profile route is replaced, not layered.
                SalesMenu.objects.filter(source='general').delete()
                SalesMenu.objects.bulk_create(prepared.values(), batch_size=500)
            from menus import services
            services._store_menus = None
            self.stdout.write('Imported mappings; original menus, prices and allergen tags preserved')
