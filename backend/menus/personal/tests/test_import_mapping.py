"""Operational mapping is imported into DB, never bundled into the application."""
import csv
import io
import tempfile
from pathlib import Path
from django.core.management import call_command, CommandError
from django.test import TestCase
from menus.models import Restaurant, StoreMenu, SalesMenu
from menus.personal.offers import mapping_index
from menus.services import get_store_catalog
from menus import services

class ImportMappingTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.file=Path(self.temp.name)/'mapping.csv'
        shop=Restaurant.objects.create(code='shop',name='Shop',source='naver')
        for menu in ['Cheese pizza','Unknown','Deleted dish']:
            StoreMenu.objects.create(restaurant=shop,raw_name=menu,price=9000,allergens=[])
        with self.file.open('w', encoding='utf-8') as f:
            writer=csv.writer(f);writer.writerow(['식당명','기존 음식명','정규화 음식명'])
            writer.writerows([['Shop','Cheese pizza','피자'],['Shop','Unknown','NULL'],['Shop','Deleted dish','덮밥']])
        services._store_menus=None;self.addCleanup(setattr,services,'_store_menus',None)

    def run_import(self,*args):
        out=io.StringIO();call_command('import_canonical_mapping','--file',str(self.file),*args,stdout=out);return out.getvalue()

    def test_preview_is_read_only_and_apply_replaces_only_general_profiles(self):
        old=SalesMenu.objects.create(key='old',source='general',name='Legacy')
        campus=SalesMenu.objects.create(key='campus',source='cafeteria',name='Campus')
        self.run_import();self.assertTrue(SalesMenu.objects.filter(pk=old.pk).exists())
        before=list(StoreMenu.objects.values('id','raw_name','price','allergens'))
        self.run_import('--apply')
        self.assertFalse(SalesMenu.objects.filter(key='old').exists())
        self.assertTrue(SalesMenu.objects.filter(pk=campus.pk).exists())
        self.assertEqual(list(StoreMenu.objects.values('id','raw_name','price','allergens')),before)
        self.assertEqual(len(mapping_index()),3)
        self.assertEqual(len(get_store_catalog('LU')[0]),1)
        self.assertEqual(get_store_catalog('LU')[0][0]['name'],'피자')

    def test_runtime_needs_no_csv_after_import_and_refreshes_cache(self):
        self.assertEqual(get_store_catalog('LU')[0],[])
        self.run_import('--apply');self.file.unlink()
        self.assertEqual(get_store_catalog('LU')[0][0]['offers'][0]['menu_name'],'Cheese pizza')

    def test_invalid_source_leaves_existing_db_mappings_untouched(self):
        self.run_import('--apply');before=list(SalesMenu.objects.values('key','annotation_metadata'))
        self.file.write_text('식당명,기존 음식명,정규화 음식명\nShop,Cheese pizza,unknown type\n', encoding='utf-8')
        with self.assertRaises(CommandError):self.run_import('--apply')
        self.assertEqual(list(SalesMenu.objects.values('key','annotation_metadata')),before)
