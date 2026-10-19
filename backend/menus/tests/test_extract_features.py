# AI-generated: written with Codex (OpenAI) and reviewed by the team.
import datetime
import io
import json
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from pydantic import ValidationError

from menus import services
from menus.features import extractor
from menus.features.prompt import SYSTEM_PROMPT, PROMPT_VERSION
from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION, LLM_FEATURE_KEYS
from menus.models import Food, MenuItem, Restaurant

DAY = datetime.date(2026, 9, 29)

def moments(**overrides):
    return {key: {"mean": 0.5, "std": 0.1} for key in LLM_FEATURE_KEYS} | overrides

class FakeLLM:
    """Structured output with deterministic values; no key or network."""
    def __init__(self, drop_in_batches=(), fail_on_batches=False, always_fail=()):
        self.drop_in_batches = set(drop_in_batches)
        self.fail_on_batches = fail_on_batches
        self.always_fail = set(always_fail)
        self.calls = []

    def invoke(self, messages):
        names = [item["input_name"] for item in json.loads(messages[-1].content)["items"]]
        self.calls.append(names)
        if self.fail_on_batches and len(names) > 1:
            raise ValueError("model returned invalid JSON")
        items = []
        for name in names:
            if name in self.always_fail or (len(names) > 1 and name in self.drop_in_batches):
                continue
            items.append({"input_name": name, "features": moments(
                spicy={"mean": 0.87 if name == "육개장" else 0.0,
                       "std": 0.12 if name == "육개장" else 0.0})})
        return extractor.FoodBatch.model_validate({"items": items})

class SchemaTests(SimpleTestCase):
    def test_output_has_32_measurements_and_storage_has_33(self):
        self.assertEqual(tuple(extractor.FoodFeatures.model_fields), LLM_FEATURE_KEYS)
        self.assertEqual(len(FEATURE_KEYS), 33)
        self.assertNotIn("meal_variety", LLM_FEATURE_KEYS)

    def test_prompt_uses_accepted_rubric_without_questions(self):
        self.assertEqual(PROMPT_VERSION, "food-name-32-v2-mean-std-draft7")
        for key in LLM_FEATURE_KEYS:
            self.assertIn("| " + key, SYSTEM_PROMPT)
        self.assertIn("통상적인 1인", SYSTEM_PROMPT)
        self.assertNotIn("Would you", SYSTEM_PROMPT)
        self.assertIn("0.1 단위에 제한하지 않는다", SYSTEM_PROMPT)

    def test_invalid_moments_are_rejected(self):
        for mean, std in [(1.3, 0), (0, .01), (1, .01), (.01, .2),
                          (.5, .51), (.5, -.1), (float("nan"), 0),
                          (.5, float("inf")), (True, 0), ("0.5", 0), (.123, .1)]:
            with self.subTest(mean=mean, std=std), self.assertRaises(ValidationError):
                extractor.FeatureStats(mean=mean, std=std)

    def test_valid_boundary_moments(self):
        for mean, std in [(0, 0), (1, 0), (.5, .5), (.2, .4), (.87, .12)]:
            self.assertEqual(extractor.FeatureStats(mean=mean, std=std).std, std)

    def test_missing_or_extra_features_are_rejected(self):
        for payload in [moments() | {"meal_variety": {"mean": 1, "std": 0}},
                        {k: v for k, v in moments().items() if k != "spicy"}]:
            with self.assertRaises(ValidationError):
                extractor.FoodFeatures.model_validate(payload)

    def test_wrong_or_duplicate_name_is_not_assigned_to_requested_food(self):
        item = {"input_name": "다른 음식", "features": moments()}
        llm = mock.Mock()
        llm.invoke.return_value = {"items": [item]}
        self.assertEqual(extractor.extract_batch(["육개장"], llm), {})
        item["input_name"] = "육개장"
        llm.invoke.return_value = {"items": [item, item]}
        self.assertEqual(extractor.extract_batch(["육개장"], llm), {})

class ExtractFeaturesCommandTests(TestCase):
    def setUp(self):
        self.restaurant = Restaurant.objects.create(code="학생회관식당", name="학생회관식당")
        for name in ["육개장", "짜장면", "냉모밀"]:
            food = Food.objects.create(name=name, is_food=True, food_group="기존 분류")
            MenuItem.objects.create(date=DAY, meal="LU", restaurant=self.restaurant,
                                    raw_name=name, food=food, price=3000)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(extractor, "api_key_available", return_value=True).start()

    def run_command(self, llm, *args):
        out = io.StringIO()
        with mock.patch.object(extractor, "build_llm", return_value=llm):
            call_command("extract_features", "--date", DAY.isoformat(), *args, stdout=out)
        return out.getvalue()

    def test_tags_and_saves_mean_std_without_tenth_rounding(self):
        llm = FakeLLM()
        self.run_command(llm)
        self.assertEqual(len(llm.calls), 1)
        food = Food.objects.get(name="육개장")
        self.assertEqual(food.feature_version, FEATURE_VERSION)
        self.assertEqual(food.features["spicy"], .87)
        self.assertEqual(food.feature_std["spicy"], .12)
        self.assertEqual(set(food.features), set(FEATURE_KEYS))
        self.assertEqual(food.food_group, "기존 분류")
        self.assertEqual(food.features["meal_variety"], 0)
        self.assertEqual(food.feature_std["meal_variety"], 0)

    def test_already_tagged_foods_are_skipped(self):
        self.run_command(FakeLLM())
        llm = FakeLLM()
        self.assertIn("새로 태깅할 음식 없음", self.run_command(llm))
        self.assertEqual(llm.calls, [])

    def test_force_retags_once_per_name_and_leaves_unserved_variants_untouched(self):
        other = Food.objects.create(name="육개장", is_set=True, is_food=True)
        MenuItem.objects.create(date=DAY, meal="DN", restaurant=self.restaurant,
                                raw_name="육개장 정식", food=other, price=5000)
        unserved = Food.objects.create(name="냉모밀", is_set=True, is_food=True,
                                       display_name="시원한 냉모밀", feature_version="v1",
                                       features={"cold": 1.0})
        Food.objects.filter(name="육개장", is_set=False).update(display_name="옛날 육개장")
        self.run_command(FakeLLM())
        llm = FakeLLM()
        self.run_command(llm, "--force")
        self.assertEqual(sum(call.count("육개장") for call in llm.calls), 1)
        other.refresh_from_db()
        unserved.refresh_from_db()
        plain = Food.objects.get(name="육개장", is_set=False)
        self.assertEqual(other.features["spicy"], plain.features["spicy"])
        self.assertEqual(other.feature_std, plain.feature_std)
        self.assertEqual(other.features["meal_variety"], 1)
        self.assertEqual(other.display_name, "육개장 (세트)")
        self.assertEqual(plain.display_name, "옛날 육개장")
        self.assertEqual(unserved.feature_version, "v1")
        self.assertEqual(unserved.display_name, "시원한 냉모밀")
        self.assertEqual(unserved.features, {"cold": 1.0})

    def test_existing_name_cache_fills_new_variant_without_key_or_call(self):
        self.run_command(FakeLLM())
        other = Food.objects.create(name="육개장", is_set=True, is_food=True)
        MenuItem.objects.create(date=DAY, meal="DN", restaurant=self.restaurant,
                                raw_name="육개장 정식", food=other, price=5000)
        llm = FakeLLM()
        with mock.patch.object(extractor, "api_key_available", return_value=False):
            self.run_command(llm)
        self.assertEqual(llm.calls, [])
        other.refresh_from_db()
        self.assertEqual(other.feature_version, FEATURE_VERSION)

    def test_corrupt_versioned_cache_is_reextracted(self):
        self.run_command(FakeLLM())
        Food.objects.filter(name="육개장").update(feature_std={})
        llm = FakeLLM()
        self.run_command(llm)
        self.assertEqual(llm.calls, [["육개장"]])

    def test_preprocessing_exclusions_are_not_sent_to_llm(self):
        Food.objects.filter(name="짜장면").update(is_food=False)
        llm = FakeLLM()
        self.run_command(llm)
        self.assertNotIn("짜장면", llm.calls[0])

    def test_names_missing_from_a_batch_are_retried_alone(self):
        llm = FakeLLM(drop_in_batches=["냉모밀"])
        self.run_command(llm)
        self.assertEqual(llm.calls[1], ["냉모밀"])
        self.assertEqual(Food.objects.filter(feature_version=FEATURE_VERSION).count(), 3)

    def test_failed_batch_falls_back_to_one_by_one(self):
        llm = FakeLLM(fail_on_batches=True)
        self.run_command(llm)
        self.assertEqual(len(llm.calls), 4)

    def test_failed_names_remain_untagged_and_command_fails(self):
        with self.assertRaisesMessage(CommandError, "특징을 뽑지 못한 음식 1개"):
            self.run_command(FakeLLM(always_fail=["냉모밀"]))
        self.assertEqual(Food.objects.get(name="냉모밀").feature_version, "")
        self.assertEqual(Food.objects.get(name="육개장").feature_version, FEATURE_VERSION)

    def test_dry_run_writes_nothing_including_cached_variants(self):
        self.run_command(FakeLLM(), "--dry-run")
        self.assertFalse(Food.objects.filter(feature_version=FEATURE_VERSION).exists())
        self.run_command(FakeLLM())
        other = Food.objects.create(name="육개장", is_set=True, is_food=True)
        MenuItem.objects.create(date=DAY, meal="DN", restaurant=self.restaurant,
                                raw_name="육개장 정식", food=other, price=5000)
        self.run_command(FakeLLM(), "--dry-run")
        other.refresh_from_db()
        self.assertEqual(other.feature_version, "")

    def test_limit_counts_names_and_rejects_nonpositive_options(self):
        other = Food.objects.create(name="냉모밀", is_set=True, is_food=True)
        MenuItem.objects.create(date=DAY, meal="DN", restaurant=self.restaurant,
                                raw_name="냉모밀 정식", food=other, price=5000)
        llm = FakeLLM()
        self.run_command(llm, "--limit", "1")
        self.assertEqual(llm.calls, [["냉모밀"]])
        self.assertEqual(Food.objects.filter(feature_version=FEATURE_VERSION).count(), 2)
        for option in ("--batch-size", "--limit"):
            with self.assertRaises(CommandError):
                self.run_command(FakeLLM(), option, "0")

    def test_missing_api_key_is_a_clear_error(self):
        with mock.patch.object(extractor, "api_key_available", return_value=False):
            with self.assertRaisesMessage(CommandError, "GOOGLE_API_KEY"):
                self.run_command(FakeLLM())

class GetCandidatesTests(TestCase):
    def test_versions_are_not_mixed_and_default_candidate_keys_stay_stable(self):
        hall = Restaurant.objects.create(code="hall", name="학생회관식당")
        for version in ("v1", "v2"):
            food = Food.objects.create(name=version, is_food=True, feature_version=version,
                                       features={"spicy": .5}, feature_std={"spicy": .1})
            MenuItem.objects.create(date=DAY, meal="LU", restaurant=hall, raw_name=version, food=food)
        self.assertEqual([c["name"] for c in services.get_candidates(DAY)], ["v1"])
        [candidate] = services.get_candidates(DAY, feature_version="v2")
        self.assertEqual(candidate["name"], "v2")
        self.assertEqual(set(candidate), {"food_id", "name", "display_name", "food_group", "features", "offers"})
        [with_std] = services.get_candidates(DAY, feature_version="v2", include_std=True)
        self.assertEqual(with_std["feature_std"], {"spicy": .1})
        self.assertEqual(len(services.get_feature_schema("v1")), 23)
        self.assertEqual(len(services.get_feature_schema("v2")), 33)
        with self.assertRaises(ValueError):
            services.get_candidates(DAY, feature_version="v0")
