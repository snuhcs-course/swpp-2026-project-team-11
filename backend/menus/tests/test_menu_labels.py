import datetime
import io
import json
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from pydantic import ValidationError

from menus import labels, llm, services
from menus.allergens import ALLERGEN_VERSION
from menus.features.schema import FEATURE_KEYS
from menus.models import Food, MenuItem, MenuLabel, Restaurant, StoreMenu

DAY = datetime.date(2026, 11, 3)
LONG = '한입치킨 세트 - 버거운치킨버거 + 후라이드치킨 반마리 + 음료 1잔 = 17,100원'
BUFFET = '<뷔페>+핫커리 & 치킨까스+소세지볶음+그린샐러드'
PROMO = '[인기만점] 탕수육 소(2인)'


class FakeLabels:
    def __init__(self, missing=()):
        self.calls = []
        self.missing = set(missing)

    def invoke(self, messages):
        names = [item['input_name'] for item in json.loads(messages[-1].content)['items']]
        self.calls.append(names)
        return labels.LabelBatch.model_validate({'items': [
            {'input_name': name, 'label': '대표 메뉴'} for name in names if name not in self.missing]})


class LabelRulesTests(SimpleTestCase):
    def test_detects_difficult_clean_names(self):
        for name in (LONG, BUFFET, PROMO, '치킨+밥', '한' * 21):
            with self.subTest(name=name): self.assertTrue(labels.needs_label(name))
        for name in ('탕수육 소(2인)', '한' * 20, '덮밥 = 5,000원', '<코너>+김치찌개'):
            with self.subTest(name=name): self.assertFalse(labels.needs_label(name))

    def test_blank_labels_are_invalid(self):
        with self.assertRaises(ValidationError):
            labels.LabelAnnotation(input_name=LONG, label='  ')


class LabelTests(TestCase):
    def setUp(self):
        place = Restaurant.objects.create(code='hall', name='Hall')
        self.food = Food.objects.create(name='치킨', is_food=True, feature_version='v2',
            features=dict.fromkeys(FEATURE_KEYS, 0.5), feature_std=dict.fromkeys(FEATURE_KEYS, 0.1),
            allergens=[], allergen_version=ALLERGEN_VERSION)
        self.place = place
        for name in (LONG, BUFFET, '덮밥 = 5,000원'):
            MenuItem.objects.create(restaurant=place, date=DAY, meal='LU', raw_name=name, food=self.food)
        StoreMenu.objects.create(restaurant=place, raw_name=LONG, food=self.food, allergen_version=ALLERGEN_VERSION)
        StoreMenu.objects.create(restaurant=place, raw_name=PROMO, food=self.food, allergen_version=ALLERGEN_VERSION)

    def command(self, *args, model=None, key=True):
        out = io.StringIO()
        with mock.patch.object(llm, 'api_key_available', return_value=key), mock.patch.object(labels, 'build_llm', return_value=model or FakeLabels()):
            call_command('tag_menu_labels', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_counts_all_deduplicated_names_without_key_or_calls(self):
        out = io.StringIO()
        with mock.patch.object(labels, 'build_llm', side_effect=AssertionError('no LLM allowed')), \
                mock.patch.object(llm, 'api_key_available', side_effect=AssertionError('no key check allowed')):
            call_command('tag_menu_labels', '--all', '--dry-run', stdout=out)
        out = out.getvalue()
        self.assertIn('Names: 3; initial model calls: 1', out)
        self.assertEqual(MenuLabel.objects.count(), 0)

    def test_date_stores_force_and_version(self):
        model = FakeLabels()
        self.command('--date', DAY.isoformat(), model=model)
        self.assertEqual(set(model.calls[0]), {LONG, BUFFET})
        self.assertEqual(MenuLabel.objects.count(), 2)
        again = FakeLabels()
        self.command('--date', DAY.isoformat(), model=again)
        self.assertFalse(again.calls)
        self.command('--stores', model=again)
        self.assertEqual(again.calls, [[PROMO]])
        forced = FakeLabels()
        self.command('--stores', '--force', model=forced)
        self.assertEqual(set(forced.calls[0]), {LONG, PROMO})
        MenuLabel.objects.filter(name=LONG).update(version='old')
        changed = FakeLabels()
        self.command('--stores', model=changed)
        self.assertEqual(changed.calls, [[LONG]])

    def test_failed_response_leaves_name_for_retry(self):
        with self.assertRaises(CommandError):
            self.command('--stores', model=FakeLabels(missing=[PROMO]))
        self.assertTrue(MenuLabel.objects.filter(name=LONG).exists())
        self.assertFalse(MenuLabel.objects.filter(name=PROMO).exists())

    def test_both_catalogues_preserve_raw_name_and_use_current_label_or_base(self):
        MenuLabel.objects.create(name=LONG, label='한입치킨 세트', version=labels.LABEL_VERSION)
        MenuLabel.objects.create(name=BUFFET, label='오래된 이름', version='old')
        rows = {x['name']: x for x in services.get_catalog(DAY, 'LU')[0]}
        self.assertEqual(rows[LONG]['display_name'], '한입치킨 세트')
        self.assertEqual(rows[BUFFET]['display_name'], '핫커리 & 치킨까스+소세지볶음+그린샐러드')
        self.assertEqual(rows['덮밥 = 5,000원']['display_name'], '덮밥')
        stores = {x['name']: x for x in services.get_store_catalog('LU')[0]}
        self.assertEqual(stores[LONG]['display_name'], '한입치킨 세트')
        self.assertEqual(stores[PROMO]['display_name'], PROMO)
