"""External annotations survive source refreshes and never bypass allergen filtering."""
import io
import json
from pathlib import Path
import tempfile
import datetime
from contextlib import contextmanager

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.db import connection

from menus import services
from menus.allergens import ALLERGEN_VERSION
from menus.features.schema import FEATURE_KEYS
from menus.models import Food, MenuItem, Restaurant, SalesMenu, StoreMenu


class MenuProfileTests(TestCase):
    def setUp(self):
        self.restaurant = Restaurant.objects.create(code="shop", name="Example restaurant", source="naver")
        self.item = StoreMenu.objects.create(restaurant=self.restaurant, raw_name="A set",
                                             description="Pork rice and noodles", price=9000,
                                             allergens=[], allergen_version=ALLERGEN_VERSION)
        self.addCleanup(setattr, services, "_store_menus", None)
        self.profile = dict(name="A set", store_code="shop", description=self.item.description,
                            features=dict.fromkeys(FEATURE_KEYS, .5),
                            feature_std=dict.fromkeys(FEATURE_KEYS, .1),
                            annotation_version="test-v1", std_source="heuristic proxy")

    def import_rows(self, rows, *arguments):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"profiles.json"
            path.write_text(json.dumps(rows))
            call_command("import_menu_features", "--file", str(path), *arguments, stdout=io.StringIO())

    def candidates(self, allergies=frozenset()):
        services._store_menus = None
        return services.get_store_catalog("LU", allergies)[0]

    def test_imported_profile_works_without_legacy_component_tags_and_keeps_provenance(self):
        self.import_rows([self.profile])
        [candidate] = self.candidates()
        self.assertEqual(candidate["name"], "A set")
        self.assertEqual(candidate["features"], self.profile["features"])
        self.assertEqual(SalesMenu.objects.get().annotation_metadata["std_source"], "heuristic proxy")

    def test_changed_recipe_is_withheld_until_reimport_and_gets_its_own_identity(self):
        self.import_rows([self.profile])
        identifier = self.candidates()[0]["food_id"]
        self.item.delete()
        StoreMenu.objects.create(restaurant=self.restaurant, raw_name="A set", description="Chicken rice",
                                 price=11000, allergens=[], allergen_version=ALLERGEN_VERSION)
        with self.assertLogs("menus.services", level="WARNING"):
            self.assertFalse(self.candidates())
        self.import_rows([self.profile | {"description": "Chicken rice"}])
        self.assertNotEqual(self.candidates()[0]["food_id"], identifier)

    def test_same_named_size_variants_and_price_only_refreshes_are_distinct_and_stable(self):
        large = self.profile | {"description": "Pork rice and noodles for four"}
        StoreMenu.objects.create(restaurant=self.restaurant, raw_name="A set", description=large["description"],
                                 price=19000)
        self.import_rows([self.profile, large])
        before = {row["offers"][0]["price"]: row["food_id"] for row in self.candidates()}
        self.assertEqual(len(before), 2)
        self.item.price = 10000
        self.item.save()
        after = {row["offers"][0]["price"]: row["food_id"] for row in self.candidates()}
        self.assertEqual(after[10000], before[9000])
        self.assertEqual(after[19000], before[19000])

    def test_annotation_never_bypasses_unknown_or_excluded_allergens(self):
        self.import_rows([self.profile])
        self.item.allergens = ["egg"]
        self.item.save()
        self.assertFalse(self.candidates(frozenset({"egg"})))
        self.item.allergen_version = ""
        self.item.allergens = []
        self.item.save()
        self.assertFalse(self.candidates(frozenset({"egg"})))

    def test_reimport_changes_features_without_changing_id_or_reloading_source_rows(self):
        self.import_rows([self.profile])
        [before] = services.get_store_catalog("LU")[0]
        previous = SalesMenu.objects.get().updated_at
        self.import_rows([self.profile | {"features": dict.fromkeys(FEATURE_KEYS, .8)}])
        [after] = services.get_store_catalog("LU")[0]
        self.assertEqual(after["food_id"], before["food_id"])
        self.assertEqual(after["features"]["rice"], .8)
        self.assertGreater(SalesMenu.objects.get().updated_at, previous)

    def test_dry_run_and_invalid_or_conflicting_files_do_not_write(self):
        self.import_rows([self.profile], "--dry-run")
        self.assertFalse(SalesMenu.objects.exists())
        for bad in [self.profile | {"features": {"rice": 2}},
                    self.profile | {"features": dict.fromkeys(FEATURE_KEYS, .6)}]:
            with self.assertRaises(CommandError):
                self.import_rows([self.profile, bad])
            self.assertFalse(SalesMenu.objects.exists())

    def test_same_title_in_different_restaurants_has_independent_profiles(self):
        other = Restaurant.objects.create(code="other", name="Other restaurant", source="naver")
        StoreMenu.objects.create(restaurant=other, raw_name="A set", description=self.item.description)
        profile = self.profile | {"store_code": "other", "features": dict.fromkeys(FEATURE_KEYS, .8)}
        self.import_rows([self.profile, profile])
        rows = self.candidates()
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r["food_id"] for r in rows}), 2)
        self.assertEqual({r["features"]["rice"] for r in rows}, {.5, .8})

    def test_equivalent_profiles_merge_offers_and_rejection_moves_on_for_dt_and_rl(self):
        from recommend.tests.helpers import post
        other = Restaurant.objects.create(code="other", name="Other restaurant", source="naver")
        StoreMenu.objects.create(restaurant=other, raw_name="A set", description=self.item.description, price=12000)
        self.import_rows([self.profile, self.profile | {"store_code": "other"}])
        [candidate] = self.candidates()
        self.assertEqual({o["restaurant"] for o in candidate["offers"]}, {"Example restaurant", "Other restaurant"})
        self.assertEqual({o["price"] for o in candidate["offers"]}, {9000, 12000})
        for engine in ("decision_tree", "rl"):
            state = post(self.client, "/api/sessions/", {"source": "general", "engine": engine}).json()
            self.assertEqual(state["candidate_count"], 1)
            url = f"/api/sessions/{state['session_id']}/"
            guess = post(self.client, url+"recommend-now/").json()["step"]
            after = post(self.client, url+"feedback/", {"guess_id": guess["guess_id"], "accepted": False}).json()
            self.assertEqual(after["step"]["type"], "unavailable")

    def test_equal_vectors_do_not_erase_different_components_or_portions(self):
        cases = [({"components": ["pork rice"]}, {"components": ["chicken noodles"]}, self.item.description),
                 ({"components": ["pork rice"]}, {"components": ["pork rice"]}, "Pork rice, 4인분입니다")]
        for left_meta, right_meta, description in cases:
            with self.subTest(description=description):
                SalesMenu.objects.all().delete()
                other, _ = Restaurant.objects.get_or_create(code="other", defaults={"name": "Other restaurant", "source": "naver"})
                StoreMenu.objects.filter(restaurant=other).delete()
                StoreMenu.objects.create(restaurant=other, raw_name="A set", description=description)
                self.import_rows([self.profile | left_meta, self.profile | right_meta | {"store_code": "other", "description": description}])
                self.assertEqual(len(self.candidates()), 2)


@contextmanager
def read_only_sqlite():
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA query_only=ON")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA query_only=OFF")


class CatalogueReadOnlyTests(TestCase):
    def setUp(self):
        self.restaurant = Restaurant.objects.create(code="shop", name="Shop")
        self.food = Food.objects.create(name="Rice", is_food=True, feature_version="v2",
                                       features=dict.fromkeys(FEATURE_KEYS, .5),
                                       feature_std=dict.fromkeys(FEATURE_KEYS, .1))
        self.addCleanup(setattr, services, "_store_menus", None)

    def test_source_save_prepares_ids_and_cold_readers_and_export_only_read(self):
        day = datetime.date(2026, 11, 3)
        MenuItem.objects.create(date=day, meal="LU", restaurant=self.restaurant, raw_name="Rice", food=self.food)
        StoreMenu.objects.create(restaurant=self.restaurant, raw_name="Rice", food=self.food)
        count = SalesMenu.objects.count()
        self.assertEqual(count, 2)
        with read_only_sqlite():
            self.assertEqual(len(services.get_catalog(day, "LU")[0]), 1)
            self.assertEqual(len(services.get_store_catalog("LU")[0]), 1)
            call_command("export_candidates", "--date", day.isoformat(), stdout=io.StringIO())
        self.assertEqual(SalesMenu.objects.count(), count)

    def test_unprepared_read_does_not_register_and_explicit_backfill_restores_it(self):
        StoreMenu.objects.create(restaurant=self.restaurant, raw_name="Rice", food=self.food)
        SalesMenu.objects.all().delete()
        with read_only_sqlite(), self.assertLogs("menus.services", level="WARNING"):
            self.assertFalse(services.get_store_catalog("LU")[0])
        self.assertFalse(SalesMenu.objects.exists())
        call_command("register_menu_ids", "--source", "general", stdout=io.StringIO())
        with read_only_sqlite():
            self.assertEqual(len(services.get_store_catalog("LU")[0]), 1)
