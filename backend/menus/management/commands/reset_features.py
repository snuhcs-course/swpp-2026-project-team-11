"""Invalidate superseded feature data after taking an operational DB backup."""
from django.core.management.base import BaseCommand
from django.db import transaction
from menus.features.schema import FEATURE_VERSION
from menus.models import Food, SalesMenu

class Command(BaseCommand):
    help='Preview obsolete feature rows; --apply clears their feature data, preserving identities and allergens.'
    def add_arguments(self,parser):parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        rows=[Food.objects.exclude(feature_version=FEATURE_VERSION),SalesMenu.objects.exclude(feature_version=FEATURE_VERSION)]
        self.stdout.write('Obsolete feature rows: '+', '.join(str(q.exclude(feature_version='').count()) for q in rows))
        if options['apply']:
            with transaction.atomic():
                for query in rows:query.update(features={},feature_std={},feature_version='')
            self.stdout.write('Obsolete values cleared. Run extract_menu_features before serving campus menus.')
