"""Profile migration and read-only catalogue construction with one current schema."""
import datetime
from unittest import mock
from django.test import TestCase
from django.core.management import call_command
from menus.models import Food, Restaurant, MenuItem, SalesMenu
from menus.features.schema import FEATURE_VERSION, FEATURE_KEYS
from menus import services
from menus.personal import offers

class ProfileMigrationTests(TestCase):
    def test_reset_is_preview_until_apply_and_preserves_food_identity_and_allergens(self):
        food=Food.objects.create(name='Old',feature_version='v2',features={'old':.5},feature_std={'old':.1},allergens=['milk'],allergen_version='allergy-v')
        call_command('reset_features');food.refresh_from_db();self.assertEqual(food.feature_version,'v2')
        call_command('reset_features','--apply');food.refresh_from_db();self.assertEqual(food.features,{})
        self.assertEqual(food.allergens,['milk']);self.assertEqual(food.name,'Old')

    def test_catalogue_reads_do_not_write_and_ignore_unmapped_store_profiles(self):
        hall=Restaurant.objects.create(code='hall',name='Hall')
        food=Food.objects.create(name='Rice',is_food=True,feature_version=FEATURE_VERSION,features=dict.fromkeys(FEATURE_KEYS,.5),feature_std=dict.fromkeys(FEATURE_KEYS,.1))
        day=datetime.date(2026,11,17);MenuItem.objects.create(date=day,meal='LU',restaurant=hall,food=food,raw_name='Rice')
        before=SalesMenu.objects.count()
        self.assertEqual(len(services.get_catalog(day,'LU')[0]),1)
        self.assertEqual(SalesMenu.objects.count(),before)
