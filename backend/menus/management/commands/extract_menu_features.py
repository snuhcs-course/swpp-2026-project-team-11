"""Extract complete campus-menu profiles; no canonical classification."""
import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from menus.features.daily import annotate

class Command(BaseCommand):
    help='Extract the current 53-feature mean/std/mask profile of whole campus menus.'
    def add_arguments(self,parser):
        parser.add_argument('--date',type=datetime.date.fromisoformat,default=None)
        parser.add_argument('--batch-size',type=int,default=8)
    def handle(self,*args,**options):
        if options['batch_size']<1:raise CommandError('Batch size must be positive')
        failed,complete=annotate(options['date'] or timezone.localdate(),batch_size=options['batch_size'])
        self.stdout.write(f'Campus profiles: {complete}; unresolved: {len(failed)}')
        if failed:raise CommandError(f'{len(failed)} campus menus have no current profile')
