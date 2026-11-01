import datetime
import io
import json
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from pydantic import ValidationError

from menus import allergens, llm
from menus.allergens import ALLERGEN_KEYS, ALLERGEN_VERSION, SYSTEM_PROMPT
from menus.models import Food, MenuItem, Restaurant

DAY = datetime.date(2026, 9, 29)
TAGS = {"돈까스": ["pork", "wheat", "egg", "wheat"], "카레우동": ["wheat", "soybean"], "샐러드": []}


class FakeLLM:
    """Answers from TAGS (no allergens for other names); no key or network."""
    def __init__(self, always_fail=()):
        self.always_fail = set(always_fail)
        self.calls = []

    def invoke(self, messages):
        names = [item["input_name"] for item in json.loads(messages[-1].content)["items"]]
        self.calls.append(names)
        return allergens.AllergenBatch.model_validate({"items": [
            {"input_name": name, "allergens": TAGS.get(name, [])} for name in names if name not in self.always_fail]})


class SchemaTests(SimpleTestCase):
    def test_the_19_labelled_allergens_are_all_in_the_prompt(self):
        self.assertEqual(len(ALLERGEN_KEYS), 19)
        for key in ALLERGEN_KEYS:
            self.assertIn(f"- {key}: ", SYSTEM_PROMPT)

    def test_unknown_allergen_keys_are_rejected(self):
        with self.assertRaises(ValidationError):
            allergens.AllergenAnnotation(input_name="돈까스", allergens=["nuts"])

    def test_keys_are_unique_and_in_list_order(self):
        annotation = allergens.AllergenAnnotation(input_name="돈까스", allergens=TAGS["돈까스"])
        self.assertEqual(annotation.keys(), ["egg", "wheat", "pork"])


class ExtractAllergensTests(TestCase):
    def setUp(self):
        hall = Restaurant.objects.create(code="hall", name="Hall")
        for name, is_set in [("돈까스", False), ("돈까스", True), ("카레우동", False), ("샐러드", False)]:
            food = Food.objects.create(name=name, is_set=is_set, is_food=True)
            MenuItem.objects.create(date=DAY, meal="LU", restaurant=hall, raw_name=name, food=food)

    def run_command(self, *args, model=None, key=True):
        model = model or FakeLLM()
        out = io.StringIO()
        with mock.patch.object(llm, "api_key_available", return_value=key), \
                mock.patch.object(allergens, "build_llm", return_value=model):
            call_command("extract_allergens", "--date", DAY.isoformat(), *args, stdout=out)
        return model, out.getvalue()

    def stored(self):
        return {(food.name, food.is_set): (food.allergens, food.allergen_version)
                for food in Food.objects.all()}

    def test_tags_each_name_once_and_shares_it_with_the_set(self):
        model, _ = self.run_command()
        self.assertEqual(model.calls, [["돈까스", "샐러드", "카레우동"]])
        self.assertEqual(self.stored(), {
            ("돈까스", False): (["egg", "wheat", "pork"], ALLERGEN_VERSION),
            ("돈까스", True): (["egg", "wheat", "pork"], ALLERGEN_VERSION),
            ("카레우동", False): (["soybean", "wheat"], ALLERGEN_VERSION),
            ("샐러드", False): ([], ALLERGEN_VERSION),
        })

    def test_tagged_names_are_not_sent_again(self):
        self.run_command()
        model, out = self.run_command()
        self.assertEqual(model.calls, [])
        self.assertIn("새로 태깅할 음식 없음", out)

    def test_a_new_variant_copies_the_tags_of_its_name_without_a_call(self):
        Food.objects.filter(name="돈까스", is_set=False).update(allergens=["pork"],
                                                             allergen_version=ALLERGEN_VERSION)
        Food.objects.exclude(name="돈까스").update(allergens=[], allergen_version=ALLERGEN_VERSION)
        model, _ = self.run_command()
        self.assertEqual(model.calls, [])
        self.assertEqual(self.stored()[("돈까스", True)], (["pork"], ALLERGEN_VERSION))

    def test_an_old_version_is_tagged_again(self):
        Food.objects.update(allergens=["pork"], allergen_version="old")
        model, _ = self.run_command()
        self.assertEqual(model.calls, [["돈까스", "샐러드", "카레우동"]])

    def test_force_sends_tagged_names_again(self):
        self.run_command()
        model, _ = self.run_command("--force", "--limit", "1")
        self.assertEqual(model.calls, [["돈까스"]])

    def test_dry_run_prints_without_saving(self):
        _, out = self.run_command("--dry-run")
        self.assertIn("돈까스: egg, wheat, pork", out)
        self.assertIn("샐러드: -", out)
        self.assertFalse(Food.objects.exclude(allergen_version="").exists())

    def test_a_failed_name_fails_the_run_and_stays_untagged(self):
        with self.assertRaisesMessage(CommandError, "알레르기 정보를 뽑지 못한 음식 1개"):
            self.run_command(model=FakeLLM(always_fail=["카레우동"]))
        self.assertEqual(self.stored()[("카레우동", False)], ([], ""))
        self.assertEqual(self.stored()[("샐러드", False)], ([], ALLERGEN_VERSION))

    def test_requires_an_api_key(self):
        with self.assertRaisesMessage(CommandError, "GOOGLE_API_KEY"):
            self.run_command(key=False)
