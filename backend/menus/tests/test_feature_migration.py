# AI-generated: written with Codex (OpenAI) and reviewed by the team.
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from menus.management.commands.fetch_menus import menu_lines, store
from menus.models import Food, MenuItem
from menus.preprocess.mapper import Mapping
from menus.tests.test_preprocess_store import DAY, record


class SetStorageTests(TestCase):
    def test_all_mapping_sources_use_dish_count_and_keep_standalone_identity(self):
        for source in ("override", "fixed", "cache", "llm", "rule"):
            with self.subTest(source=source):
                records = [record("돈까스"), record("돈까스와 우동")]
                lines = menu_lines(records)
                mappings = {key: Mapping(True, ("돈까스",) if name == "돈까스"
                                         else ("돈까스", "우동"), source)
                            for key, name in lines.items()}
                store(DAY, records, mappings)
                plain = Food.objects.get(name="돈까스", is_set=False)
                combo = Food.objects.get(name="돈까스", is_set=True)
                self.assertNotEqual(plain.pk, combo.pk)
                self.assertEqual(MenuItem.objects.get(raw_name="돈까스").food_id, plain.pk)
                self.assertEqual(MenuItem.objects.filter(food=combo).count(), 1)
                self.assertEqual(Food.objects.count(), 3)
                self.assertTrue(Food.objects.get(name="우동").is_set)

    def test_uniqueness_is_name_and_set_status(self):
        Food.objects.create(name="돈까스")
        Food.objects.create(name="돈까스", is_set=True)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            Food.objects.create(name="돈까스", is_set=True)


class FeatureMigrationTests(TransactionTestCase):
    def test_existing_rows_and_menu_links_are_preserved(self):
        old_target = [("menus", "0002_menu_lines_and_dish_items")]
        new_target = [("menus", "0003_food_feature_moments_and_sets")]
        executor = MigrationExecutor(connection)
        executor.migrate(old_target)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(new_target))
        old = executor.loader.project_state(old_target).apps
        food = old.get_model("menus", "Food").objects.create(
            name="김치찌개", features={"spicy": .7}, feature_version="v1", is_food=True)
        hall = old.get_model("menus", "Restaurant").objects.create(code="test", name="test")
        item = old.get_model("menus", "MenuItem").objects.create(
            date=DAY, meal="LU", restaurant=hall, raw_name="김치찌개", food=food)
        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        new = executor.loader.project_state(new_target).apps
        migrated = new.get_model("menus", "Food").objects.get(pk=food.pk)
        self.assertFalse(migrated.is_set)
        self.assertEqual(migrated.feature_std, {})
        self.assertEqual(migrated.features, {"spicy": .7})
        self.assertEqual(migrated.feature_version, "v1")
        self.assertEqual(new.get_model("menus", "MenuItem").objects.get(pk=item.pk).food_id, food.pk)
