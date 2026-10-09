# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import datetime
import io
import re
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from pydantic import ValidationError

from menus import services
from menus.features import extractor
from menus.features.prompt import FEW_SHOT_EXAMPLES, SYSTEM_PROMPT
from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION
from menus.models import Food, MenuItem, Restaurant

DAY = datetime.date(2026, 9, 29)


def features(**overrides) -> dict:
    return {key: 0.5 for key in FEATURE_KEYS} | overrides


class FakeLLM:
    """Answers like the structured-output Gemini client, without a network call."""

    def __init__(self, drop_in_batches=(), fail_on_batches=False, always_fail=()):
        self.drop_in_batches = set(drop_in_batches)
        self.fail_on_batches = fail_on_batches
        self.always_fail = set(always_fail)
        self.calls = []

    def invoke(self, messages):
        names = [re.sub(r"^\d+\.\s*", "", line)
                 for line in messages[-1].content.splitlines()[1:]]
        self.calls.append(names)
        if self.fail_on_batches and len(names) > 1:
            raise ValueError("model returned invalid JSON")
        items = []
        for name in names:
            if name in self.always_fail or (len(names) > 1 and name in self.drop_in_batches):
                continue
            items.append({
                "input_name": name,
                "is_food": name != "공기밥",
                "display_name": name,
                "food_group": "국/탕",
                "features": features(spicy=0.87 if name == "육개장" else 0.0),
            })
        return extractor.FoodBatch.model_validate({"items": items})


class SchemaTests(SimpleTestCase):
    def test_output_model_matches_schema(self):
        self.assertEqual(tuple(extractor.FoodFeatures.model_fields), FEATURE_KEYS)

    def test_prompt_lists_every_feature(self):
        for key in FEATURE_KEYS:
            self.assertIn(f"- {key}:", SYSTEM_PROMPT)

    def test_few_shot_examples_are_valid_output(self):
        for example in FEW_SHOT_EXAMPLES:
            annotation = extractor.FoodAnnotation.model_validate(example)
            self.assertEqual(tuple(annotation.features.model_dump()), FEATURE_KEYS)

    def test_out_of_range_probability_is_rejected(self):
        with self.assertRaises(ValidationError):
            extractor.FoodFeatures.model_validate(features(spicy=1.3))

    def test_loose_name_matching(self):
        llm = mock.Mock()
        llm.invoke.return_value = extractor.FoodBatch.model_validate({"items": [{
            "input_name": "1. 쇠고기 육개장", "is_food": True, "display_name": "육개장",
            "food_group": "국/탕", "features": features()}]})
        self.assertEqual(list(extractor.extract_batch(["쇠고기육개장"], llm)), ["쇠고기육개장"])


class ExtractFeaturesCommandTests(TestCase):
    def setUp(self):
        restaurant = Restaurant.objects.create(code="학생회관식당", name="학생회관식당")
        for name in ["육개장", "공기밥", "냉모밀"]:
            food = Food.objects.create(name=name)
            MenuItem.objects.create(date=DAY, meal="LU", restaurant=restaurant,
                                    raw_name=name, food=food, price=3000)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(extractor, "api_key_available", return_value=True).start()

    def run_command(self, llm, *args) -> str:
        out = io.StringIO()
        with mock.patch.object(extractor, "build_llm", return_value=llm):
            call_command("extract_features", "--date", DAY.isoformat(), *args, stdout=out)
        return out.getvalue()

    def test_tags_and_saves_the_days_foods(self):
        llm = FakeLLM()
        self.run_command(llm)

        self.assertEqual(len(llm.calls), 1)
        food = Food.objects.get(name="육개장")
        self.assertEqual(food.feature_version, FEATURE_VERSION)
        self.assertEqual(food.features["spicy"], 0.9)  # rounded to 0.1
        self.assertEqual(set(food.features), set(FEATURE_KEYS))
        self.assertEqual(food.extraction_model, extractor.MODEL)
        self.assertFalse(Food.objects.get(name="공기밥").is_food)

    def test_already_tagged_foods_are_skipped(self):
        self.run_command(FakeLLM())
        llm = FakeLLM()
        output = self.run_command(llm)
        self.assertEqual(llm.calls, [])
        self.assertIn("새로 태깅할 음식 없음", output)

    def test_force_retags(self):
        self.run_command(FakeLLM())
        llm = FakeLLM()
        self.run_command(llm, "--force")
        self.assertEqual(len(llm.calls), 1)

    def test_names_missing_from_a_batch_are_retried_alone(self):
        llm = FakeLLM(drop_in_batches=["냉모밀"])
        self.run_command(llm)
        self.assertEqual(llm.calls[1], ["냉모밀"])
        self.assertEqual(Food.objects.filter(feature_version=FEATURE_VERSION).count(), 3)

    def test_failed_batch_falls_back_to_one_by_one(self):
        llm = FakeLLM(fail_on_batches=True)
        self.run_command(llm)
        self.assertEqual(len(llm.calls), 1 + 3)
        self.assertEqual(Food.objects.filter(feature_version=FEATURE_VERSION).count(), 3)

    def test_foods_that_keep_failing_stay_untagged(self):
        output = self.run_command(FakeLLM(always_fail=["냉모밀"]))
        self.assertIn("실패 1개", output)
        self.assertEqual(Food.objects.get(name="냉모밀").feature_version, "")

    def test_dry_run_saves_nothing(self):
        output = self.run_command(FakeLLM(), "--dry-run")
        self.assertIn("육개장", output)
        self.assertFalse(Food.objects.filter(feature_version=FEATURE_VERSION).exists())

    def test_missing_api_key_is_a_clear_error(self):
        with mock.patch.object(extractor, "api_key_available", return_value=False):
            with self.assertRaisesMessage(CommandError, "GOOGLE_API_KEY"):
                self.run_command(FakeLLM())


class GetCandidatesTests(TestCase):
    def setUp(self):
        hall = Restaurant.objects.create(code="학생회관식당", name="학생회관식당")
        dorm = Restaurant.objects.create(code="기숙사식당", name="기숙사식당")

        def food(name, **kwargs):
            defaults = dict(is_food=True, feature_version=FEATURE_VERSION, features=features())
            return Food.objects.create(name=name, **(defaults | kwargs))

        yukgaejang = food("육개장", display_name="육개장")
        rice = food("공기밥", is_food=False)
        untagged = food("냉모밀", is_food=None, feature_version="", features={})
        old = food("짜장면", feature_version="v0")
        for restaurant, meal, dish, price in [
            (hall, "LU", yukgaejang, 3000), (dorm, "DN", yukgaejang, 6000),
            (hall, "LU", rice, 700), (hall, "LU", untagged, 5900), (hall, "LU", old, 4500),
        ]:
            MenuItem.objects.create(date=DAY, meal=meal, restaurant=restaurant,
                                    raw_name=dish.name, food=dish, price=price)

    def test_only_tagged_meals_are_candidates(self):
        [candidate] = services.get_candidates(DAY)
        self.assertEqual(candidate["name"], "육개장")
        self.assertEqual(set(candidate["features"]), set(FEATURE_KEYS))
        self.assertEqual(candidate["offers"], [
            {"restaurant": "학생회관식당", "meal": "LU", "price": 3000},
            {"restaurant": "기숙사식당", "meal": "DN", "price": 6000},
        ])

    def test_meal_filter(self):
        [candidate] = services.get_candidates(DAY, meal="DN")
        self.assertEqual([o["meal"] for o in candidate["offers"]], ["DN"])
        self.assertEqual(services.get_candidates(DAY, meal="BR"), [])

    def test_defaults_to_today(self):
        with mock.patch("django.utils.timezone.localdate", return_value=DAY):
            self.assertEqual(len(services.get_candidates()), 1)

    def test_feature_schema(self):
        schema = services.get_feature_schema()
        self.assertEqual([f["key"] for f in schema], list(FEATURE_KEYS))
        self.assertTrue(all(f["question"].endswith("?") for f in schema))
