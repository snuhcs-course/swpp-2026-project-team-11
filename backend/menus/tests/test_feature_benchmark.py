# AI-generated: written with Claude (Anthropic) and reviewed by the team.
import csv
import datetime
import io
import json
import pathlib
import tempfile
from unittest import mock

import openpyxl

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from menus import llm as menu_llm
from menus.features import extractor, prompt
from menus.features.benchmark import (distribution, downstream, human, integrity, menu_set, report, runs,
                                      stability, triplets)
from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION, LLM_FEATURE_KEYS
from menus.management.commands.export_feature_rating_form import rounded
from menus.models import Food, MenuItem, MenuLine, Restaurant
from menus.normalize import dish_key
from menus.preprocess import fixed
from menus.preprocess.mapper import Mapping
from menus.sources import siksha
from menus.tests.test_fixed_menus import day, payload
from menus.tests.test_preprocess_llm import FakeLLM as PreprocessLLM

KEYS = ("spicy", "noodle", "soupy")


def record(name, run="repeat-0", source="menu", condition=None, means=None, stds=None, keys=KEYS):
    means = {k: 0.0 for k in keys} | (means or {})
    stds = {k: 0.0 for k in keys} | (stds or {})
    return runs.Record(run=run, condition=condition or run.rsplit("-", 1)[0], source=source, name=name,
                       means=means, stds=stds)


def runset(*records):
    return runs.RunSet(records)


def full(mean=0.5, std=0.1):
    return {k: mean for k in LLM_FEATURE_KEYS}, {k: std for k in LLM_FEATURE_KEYS}


class ExtractorFake:
    """Answers like the structured-output client and remembers each system prompt."""

    def __init__(self, mean=0.5):
        self.mean, self.prompts = mean, []

    def invoke(self, messages):
        self.prompts.append(messages[0].content)
        names = [item["input_name"] for item in json.loads(messages[-1].content)["items"]]
        return extractor.FoodBatch.model_validate({"items": [
            {"input_name": n, "features": {k: {"mean": self.mean, "std": 0.1} for k in LLM_FEATURE_KEYS}}
            for n in names]})


class PromptOrderTests(SimpleTestCase):
    def test_default_order_is_the_production_prompt(self):
        self.assertEqual(prompt.build_system_prompt(), prompt.SYSTEM_PROMPT)

    def test_shuffled_order_moves_the_rubric_blocks_and_the_key_line(self):
        order = tuple(reversed(LLM_FEATURE_KEYS))
        text = prompt.build_system_prompt(order)
        self.assertIn("출력 feature key 순서\n" + ", ".join(order), text)
        self.assertLess(text.index(f"| {order[0]}\n"), text.index(f"| {order[1]}\n"))
        with self.assertRaises(ValueError):
            prompt.build_system_prompt(LLM_FEATURE_KEYS[:-1])

    def test_extract_sends_the_given_prompt(self):
        llm = ExtractorFake()
        extractor.extract(["짬뽕"], llm, system_prompt="custom prompt")
        self.assertEqual(llm.prompts, ["custom prompt"])


class RunsTests(SimpleTestCase):
    def test_conditions_change_only_what_they_name(self):
        names = [f"dish{i}" for i in range(30)]
        repeat = runs.plan(names, "repeat", 2)
        foods = runs.plan(names, "shuffle_foods", 2)
        features = runs.plan(names, "shuffle_features", 2)
        self.assertEqual(repeat[0][1:], repeat[1][1:])
        self.assertEqual(repeat[0][2], LLM_FEATURE_KEYS)
        self.assertNotEqual(foods[0][1], foods[1][1])
        self.assertEqual(foods[0][2], LLM_FEATURE_KEYS)
        self.assertEqual(features[0][1], features[1][1])
        self.assertNotEqual(features[0][2], features[1][2])
        self.assertEqual(sorted(features[1][2]), sorted(LLM_FEATURE_KEYS))

    def test_means_and_stds_are_averaged_over_runs(self):
        rs = runset(record("짬뽕", "repeat-0", means={"spicy": 0.6}, stds={"spicy": 0.1}),
                    record("짬뽕", "repeat-1", means={"spicy": 0.8}, stds={"spicy": 0.3}))
        self.assertAlmostEqual(rs.mean("짬뽕")[0], 0.7)
        self.assertAlmostEqual(rs.std("짬뽕")[0], 0.2)
        self.assertIsNone(rs.mean("케이크"))

    def test_kinds_of_dish(self):
        rs = runset(record("마라탕", source="variant"), record("핫치킨버거", source="invariant"),
                    record("케이크", source="suite"))
        self.assertEqual(rs.segments(), ["variant", "invariant"])
        self.assertEqual(rs.menu_names(), ["마라탕", "핫치킨버거"])
        self.assertEqual(rs.subset({"variant"}).names(), ["마라탕"])

    def test_mixed_key_sets_are_refused(self):
        with self.assertRaisesMessage(ValueError, "different feature keys"):
            runset(record("짬뽕"), record("라면", keys=("spicy",)))


class IntegrityTests(SimpleTestCase):
    def test_extraction_needs_32_keys_and_stored_foods_33(self):
        means, stds = full()
        good_run = runs.Record("repeat-0", "repeat", "menu", "짬뽕", means, stds)
        good_stored = runs.Record("stored-0", "stored", "menu", "라면", means | {"meal_variety": 0.0},
                                  stds | {"meal_variety": 0.0})
        short_stored = runs.Record("stored-0", "stored", "menu", "우동", means, stds)
        section, valid = integrity.evaluate([good_run, good_stored, short_stored])
        self.assertEqual(valid, [good_run, good_stored])
        self.assertFalse(section["checks"][0][3])
        self.assertIn("missing ['meal_variety']", section["tables"][0][3][0][2])

    def test_variance_bound_and_ranges(self):
        means, stds = full()
        bad = [runs.Record("repeat-0", "repeat", "menu", "a", means | {"spicy": 0.05}, stds | {"spicy": 0.3}),
               runs.Record("repeat-0", "repeat", "menu", "b", means | {"spicy": 1.2}, stds),
               runs.Record("repeat-0", "repeat", "menu", "c", means | {"spicy": 1.0}, stds | {"spicy": 0.0})]
        found = [integrity.problems(r) for r in bad]
        self.assertIn("std²", found[0][0])
        self.assertIn("out of range", found[1][0])
        self.assertEqual(found[2], [])


    def test_more_than_two_decimals(self):
        record_ = runs.Record("repeat-0", "repeat", "menu", "짬뽕", *full(0.333, 0.1))
        self.assertIn("more than two decimals", integrity.problems(record_)[0])


class DistributionTests(SimpleTestCase):
    def test_histograms_and_collisions(self):
        result = distribution.evaluate(runset(record("짬뽕", means={"spicy": 0.9, "noodle": 1.0}),
                                              record("짬뽕밥", means={"spicy": 0.9, "noodle": 0.95}),
                                              record("우동", means={"noodle": 1.0, "soupy": 1.0})))
        rows = {row[0]: row for row in result["tables"][0][3]}
        self.assertEqual(rows["spicy"][6], "1 0 0 0 0 0 0 0 0 2 0")
        self.assertEqual(result["tables"][1][3], [["짬뽕", "짬뽕밥", 0.017]])


    def test_neighbours_are_the_closest_dish_within_the_collision_gap(self):
        rs = runset(record("짬뽕", source="variant", means={"spicy": 0.9, "noodle": 1.0}),
                    record("짬뽕밥", source="suite", means={"spicy": 0.9, "noodle": 0.95}),
                    record("우동", source="variant", means={"noodle": 1.0, "soupy": 1.0}),
                    record("핫치킨버거", source="invariant", means={"spicy": 0.85, "noodle": 1.0}))
        self.assertEqual(distribution.neighbours(rs, {"variant"}), [("짬뽕", "짬뽕밥", 0.017)])


class RatingFormTests(SimpleTestCase):
    def test_whole_kinds_close_pairs_and_a_sample(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = pathlib.Path(folder)
            runs.append(folder / "runs.jsonl", [
                record("짬뽕", source="variant", means={"spicy": 0.9, "noodle": 1.0}),
                record("짬뽕밥", source="suite", means={"spicy": 0.9, "noodle": 0.95}),
                record("비빔밥", source="variant", means={"spicy": 0.5}),
                record("우동", source="variant", means={"noodle": 1.0, "soupy": 1.0}),
                record("핫치킨버거", source="invariant")])
            out = io.StringIO()
            call_command("export_feature_rating_form", "--runs", str(folder / "runs.jsonl"), "--output",
                         str(folder / "form.csv"), "--all", "invariant", "--close", "variant", "--n", "1",
                         "--segment", "variant", stdout=out)
            self.assertIn("음식 4개", out.getvalue())
            rows = csv.reader((folder / "form_selection.csv").open(encoding="utf-8-sig"))
            selection = {row[0]: row[1:] for row in list(rows)[1:]}
            self.assertEqual(selection["짬뽕"], ["variant", "close", "짬뽕밥", "0.017"])
            self.assertEqual(selection["짬뽕밥"], ["suite", "close", "짬뽕", "0.017"])
            self.assertEqual(selection["핫치킨버거"][:2], ["invariant", "all"])
            self.assertEqual([r[1] for n, r in selection.items() if n in ("비빔밥", "우동")], ["sample"])
            self.assertEqual(set(human.load([folder / "form.csv"])["form"]), set(selection))
            lines = (folder / "form.csv").read_text(encoding="utf-8-sig").splitlines()[1:]
            self.assertEqual([line.split(",")[1] for line in lines],
                             ["고정 메뉴", "매일 바뀌는 메뉴", "매일 바뀌는 메뉴", "비교용 예시"])

    def test_llm_values_fill_the_same_form(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = pathlib.Path(folder)
            runs.append(folder / "runs.jsonl", [
                record("짬뽕", "repeat-0", "variant", means={"spicy": 0.6}, stds={"spicy": 0.1}, keys=LLM_FEATURE_KEYS),
                record("짬뽕", "repeat-1", "variant", means={"spicy": 0.72}, stds={"spicy": 0.2}, keys=LLM_FEATURE_KEYS),
                record("케이크", source="suite", keys=LLM_FEATURE_KEYS)])
            out = io.StringIO()
            call_command("export_feature_rating_form", "--runs", str(folder / "runs.jsonl"), "--output",
                         str(folder / "llm.xlsx"), "--all", "variant", "--all", "suite", "--n", "0", "--llm-values",
                         stdout=out)
            ratings = human.load([folder / "llm.xlsx"])
            self.assertEqual(list(ratings), ["LLM"])
            self.assertEqual((ratings["LLM"]["짬뽕"]["mean"]["spicy"], ratings["LLM"]["짬뽕"]["std"]["spicy"]),
                             (0.66, 0.15))  # averaged over the runs, rounded
            self.assertEqual(len(ratings["LLM"]["케이크"]["mean"]), len(LLM_FEATURE_KEYS))
            self.assertIn("std를 낮춘 칸 0개", out.getvalue())

    def test_rounding_keeps_the_std_bound(self):
        self.assertEqual(rounded(0.004, 0.007), (0.0, 0.0, True))
        self.assertEqual(rounded(0.014, 0.12), (0.01, 0.09, True))
        self.assertEqual(rounded(0.656, 0.149), (0.66, 0.15, False))

class StabilityTests(SimpleTestCase):
    def test_spread_flips_and_condition_gap(self):
        rs = runset(record("짬뽕", "repeat-0", means={"spicy": 0.2}), record("짬뽕", "repeat-1", means={"spicy": 0.8}),
                    record("짬뽕", "shuffle_features-0", means={"spicy": 0.5}),
                    record("짬뽕", "shuffle_features-1", means={"spicy": 0.5}))
        result = stability.evaluate(rs)
        self.assertIn("flips 33.33%", result["lines"][0])  # 1 of 3 features flipped
        self.assertIn("flips 0.00%", result["lines"][1])
        self.assertIn("differ by 0.000", result["lines"][2])
        self.assertEqual(result["tables"][1][3][0][:3], ["repeat", "짬뽕", "spicy"])

    def test_skipped_without_repeats(self):
        self.assertIn("skipped", stability.evaluate(runset(record("짬뽕"))))

    def test_every_run_of_a_dish_counts(self):
        rs = runset(record("짬뽕", "repeat-0", means={"spicy": 0.2}), record("짬뽕", "repeat-1", means={"spicy": 0.2}),
                    record("짬뽕", "repeat-2", means={"spicy": 0.8}),  # a third run another dish does not have
                    record("라면", "repeat-0"), record("라면", "repeat-1"),
                    record("라면", "shuffle_foods-0"), record("라면", "shuffle_foods-1"))
        lines = stability.evaluate(rs)["lines"]
        self.assertIn("`repeat`: 2 dishes x 2-3 runs", lines[0])
        self.assertIn("flips 16.67%", lines[0])  # 짬뽕's spicy, 1 of 6 cells
        self.assertIn("different run counts (repeat 2/3, shuffle_foods 2)", lines[2])


class HumanTests(SimpleTestCase):
    def form(self, rows, name="kim.csv", header=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = pathlib.Path(folder.name) / name
        header = header or "name,rater,recipe_notes,spicy_mean: 매운맛 평균,spicy_std,noodle_mean,noodle_std"
        path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8-sig")
        return path

    def test_form_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "form.csv"
            human.write_form(path, [("짬뽕", "매일 바뀌는 메뉴"), ("라면", "고정 메뉴")])
            text = path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(len(text[0].split(",")), 4 + 2 * len(LLM_FEATURE_KEYS))
            self.assertIn("spicy_mean: 매운맛 평균", text[0])
            self.assertTrue(text[1].startswith("짬뽕,매일 바뀌는 메뉴,"))
            self.assertEqual(human.load([path]), {"form": {"짬뽕": {"mean": {}, "std": {}, "notes": ""},
                                                           "라면": {"mean": {}, "std": {}, "notes": ""}}})

    def test_excel_form_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "form.xlsx"
            human.write_form(path, [("짬뽕", "매일 바뀌는 메뉴"), ("라면", "고정 메뉴")])
            self.assertEqual(human.load([path]), {"form": {"짬뽕": {"mean": {}, "std": {}, "notes": ""},
                                                           "라면": {"mean": {}, "std": {}, "notes": ""}}})
            book = openpyxl.load_workbook(path)
            self.assertEqual(book.sheetnames, ["평가", "안내", "루브릭"])
            sheet = book["평가"]
            self.assertEqual([c.value for c in sheet[4][:5]],
                             ["name", "kind", "recipe_notes", "spicy_mean", "spicy_std"])
            self.assertEqual([sheet["A6"].value, sheet["B6"].value], ["라면", "고정 메뉴"])
            sheet["B1"], sheet["C5"], sheet["D5"], sheet["E5"] = "kim", "레시피 2개", 0.6, 0.15
            book.save(path)
            self.assertEqual(human.load([path])["kim"]["짬뽕"],
                             {"mean": {"spicy": 0.6}, "std": {"spicy": 0.15}, "notes": "레시피 2개"})
            sheet["E5"] = 0.55
            book.save(path)
            with self.assertRaisesMessage(ValueError, "form.xlsx row 5, spicy"):
                human.load([path])

    def test_values_notes_and_rater_from_file_name(self):
        ratings = human.load([self.form(["짬뽕,,레시피 3개,0.6,0.15,0.98,", "라면,lee,,0.7,0.2,1,0"])])
        self.assertEqual(ratings["kim"]["짬뽕"], {"mean": {"spicy": 0.6, "noodle": 0.98}, "std": {"spicy": 0.15},
                                                 "notes": "레시피 3개"})
        self.assertEqual(ratings["lee"]["라면"]["std"], {"spicy": 0.2, "noodle": 0.0})

    def test_invalid_values_name_the_cell(self):
        cases = {"0.555": "two decimals", "abc": "not a number"}
        for text, message in cases.items():
            with self.assertRaisesMessage(ValueError, message):
                human.load([self.form([f"짬뽕,kim,,{text},0.1,1,0"])])
        with self.assertRaisesMessage(ValueError, "line 2, spicy"):
            human.load([self.form(["짬뽕,kim,,0.05,0.4,1,0"])])  # std² > mean(1 - mean)
        with self.assertRaisesMessage(ValueError, "unknown column 'umami_mean'"):
            human.load([self.form(["짬뽕,kim,,0.5"], header="name,rater,recipe_notes,umami_mean")])

    def test_reference_needs_every_feature(self):
        means, stds = full(0.5, 0.1)
        complete = {"mean": means, "std": stds, "notes": ""}
        partial = {"mean": {"spicy": 0.5}, "std": {"spicy": 0.1}, "notes": ""}
        other = {"mean": full(0.7, 0.1)[0], "std": stds, "notes": ""}
        reference = human.reference({"kim": {"짬뽕": complete, "라면": partial}, "lee": {"짬뽕": other}})
        self.assertEqual(set(reference), {"짬뽕"})
        self.assertAlmostEqual(reference["짬뽕"][0]["spicy"], 0.6)

    def test_llm_is_compared_with_how_far_raters_are_apart(self):
        rs = runset(record("짬뽕", means={"spicy": 0.6}), record("라면", means={"spicy": 0.5}))
        ratings = {"kim": {"짬뽕": {"mean": {"spicy": 0.5}, "std": {}, "notes": ""},
                           "라면": {"mean": {"spicy": 0.5}, "std": {}, "notes": ""}},
                   "lee": {"짬뽕": {"mean": {"spicy": 0.7}, "std": {}, "notes": ""},
                           "라면": {"mean": {"spicy": 0.5}, "std": {}, "notes": ""}}}
        rows, overall = human.compare(rs, ratings, "mean")
        self.assertAlmostEqual(overall["raters"], 0.1)   # (0.2 + 0) / 2
        self.assertAlmostEqual(overall["llm"], 0.05)     # (0.1 + 0.1 + 0 + 0) / 4
        self.assertEqual(rows[0][4], 0.5)
        result = human.evaluate(rs, ratings)
        self.assertIn("ratio 0.50", result["lines"][2])
        one = human.evaluate(rs, {"kim": ratings["kim"]})
        self.assertIn("one rater", one["lines"][2])
        self.assertIn("skipped", human.evaluate(rs, None))

    def test_raters_are_compared_on_the_dishes_in_the_runs(self):
        rs = runset(record("짬뽕", means={"spicy": 0.6}))
        rated = lambda value: {"mean": {"spicy": value}, "std": {}, "notes": ""}
        ratings = {"kim": {"짬뽕": rated(0.5), "라면": rated(0.0)}, "lee": {"짬뽕": rated(0.7), "라면": rated(1.0)}}
        _, overall = human.compare(rs, ratings, "mean")
        self.assertAlmostEqual(overall["raters"], 0.2)  # 라면 is not in the runs, so its 1.0 gap is left out

    def test_each_value_is_checked_even_without_its_pair(self):
        for row, cell in (("짬뽕,kim,,2,,1,0", "spicy_mean"), ("짬뽕,kim,,,0.6,1,0", "spicy_std")):
            with self.assertRaisesMessage(ValueError, f"line 2, {cell}"):
                human.load([self.form([row])])


class TripletTests(SimpleTestCase):
    def test_json_and_csv_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "t.csv"
            path.write_text("anchor,near,far,kind,source,note\n짬뽕,라면,케이크,distinct,human,\n", encoding="utf-8")
            self.assertEqual(triplets.load(path), [{"anchor": "짬뽕", "near": "라면", "far": "케이크",
                                                     "kind": "distinct", "source": "human", "note": ""}])
            bad = pathlib.Path(folder) / "bad.json"
            for row, message in (({"anchor": "a", "near": "b", "far": "c", "kind": "far", "source": "ai"}, "kind"),
                                 ({"anchor": "a", "near": "a", "far": "c", "kind": "close", "source": "ai"}, "three"),
                                 ({"anchor": "a", "near": "b", "kind": "close", "source": "ai"}, "needs")):
                bad.write_text(json.dumps([row]), encoding="utf-8")
                with self.assertRaisesMessage(ValueError, message):
                    triplets.load(bad)

    def test_pass_rates_by_kind_and_source(self):
        rs = runset(record("짬뽕", means={"spicy": 0.9, "noodle": 1.0}), record("라면", means={"spicy": 0.6, "noodle": 1.0}),
                    record("케이크"))
        result = triplets.evaluate(rs, [
            {"anchor": "짬뽕", "near": "라면", "far": "케이크", "kind": "distinct", "source": "ai"},
            {"anchor": "짬뽕", "near": "케이크", "far": "라면", "kind": "close", "source": "human"},
            {"anchor": "짬뽕", "near": "없는메뉴", "far": "라면", "kind": "close", "source": "ai"}])
        self.assertIn("2 of 3 triplets evaluated: 50.0% pass", result["lines"][0])
        self.assertIn("close 0% (1), distinct 100% (1), ai 100% (1), human 0% (1)", result["lines"][1])
        self.assertIn("없는메뉴", result["lines"][2])

    def test_ai_draft_is_valid(self):
        draft = triplets.load()
        self.assertGreaterEqual(len(draft), 50)
        self.assertEqual({t["kind"] for t in draft}, set(triplets.KINDS))
        self.assertEqual({t["source"] for t in draft}, {"ai"})


class DownstreamTests(SimpleTestCase):
    def reference(self):
        return {"짬뽕": ({k: 0.0 for k in LLM_FEATURE_KEYS} | {"spicy": 0.9, "noodle": 1.0}, full(0, 0)[1]),
                "물냉면": ({k: 0.0 for k in LLM_FEATURE_KEYS} | {"cold": 1.0, "noodle": 1.0}, full(0, 0)[1]),
                "비빔밥": ({k: 0.0 for k in LLM_FEATURE_KEYS} | {"rice": 1.0}, full(0, 0)[1])}

    def test_same_features_give_the_same_sessions(self):
        reference = self.reference()
        rs = runset(*[record(n, means=m, stds=s, keys=LLM_FEATURE_KEYS) for n, (m, s) in reference.items()])
        result = downstream.evaluate(rs, reference, "preference")
        human_row, ai_row = result["tables"][0][3]
        self.assertEqual(human_row[1:], ai_row[1:])
        self.assertIn("lose 0 and win 0", result["lines"][1])

    def test_candidates_carry_33_keys(self):
        rows = downstream.candidates({"짬뽕": full()})
        self.assertEqual(set(rows[0]["features"]), set(FEATURE_KEYS))
        self.assertEqual(rows[0]["features"]["meal_variety"], 0.0)

    def test_skipped_without_a_reference(self):
        self.assertIn("skipped", downstream.evaluate(runset(record("짬뽕")), {}, "preference"))


class IsolatedCatalog:
    """Mixin: the fixed-menu catalog holds only 버거운버거's 핫치킨버거 and 탄산음료, and there are
    no overrides, whatever the committed files contain."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = pathlib.Path(folder.name)
        catalog = self.folder / "fixed_menus.json"
        catalog.write_text(json.dumps({"restaurants": {"버거운버거": {"type": "fixed", "lines": {
            dish_key("핫치킨버거"): {"name": "핫치킨버거", "is_meal": True, "dishes": ["핫치킨버거"]},
            dish_key("탄산음료"): {"name": "탄산음료", "is_meal": False, "dishes": []},
        }}}}, ensure_ascii=False), encoding="utf-8")
        for patcher in (mock.patch.object(fixed, "CATALOG_PATH", catalog),
                        mock.patch("menus.preprocess.overrides.OVERRIDES_PATH", new=pathlib.Path("__no_overrides__.json"))):
            patcher.start()
            self.addCleanup(patcher.stop)


class CommandTests(IsolatedCatalog, TestCase):
    def setUp(self):
        super().setUp()
        self.runs_path = self.folder / "runs.jsonl"
        hall = Restaurant.objects.create(code="hall", name="학생회관식당")
        means, stds = full(0.5, 0.1)
        for name, is_set in (("짬뽕", False), ("짬뽕", True), ("핫치킨버거", False), ("라면", False)):
            food = Food.objects.create(name=name, is_set=is_set, is_food=True, feature_version=FEATURE_VERSION,
                                       features=means | {"meal_variety": float(is_set)},
                                       feature_std=stds | {"meal_variety": 0.0}, extraction_model="m")
            MenuItem.objects.create(date=datetime.date(2026, 10, 20), meal="LU", restaurant=hall,
                                    raw_name=name, food=food, price=5000)
        Food.objects.filter(name="라면").update(feature_version="v1")

    def collect(self, llm, *args):
        out = io.StringIO()
        with mock.patch.object(extractor, "build_llm", return_value=llm), \
             mock.patch.object(extractor, "api_key_available", return_value=True):
            call_command("collect_feature_runs", "--date", "2026-10-20", "--output", str(self.runs_path),
                         *args, stdout=out)
        return out.getvalue()

    def test_stored_copies_v2_foods_with_their_kind(self):
        self.collect(ExtractorFake(), "--stored")
        records = runs.load(self.runs_path)
        self.assertEqual({r.name: r.source for r in records},
                         {"짬뽕": "variant", "짬뽕 (세트)": "variant", "핫치킨버거": "invariant"})  # 라면 is v1
        self.assertEqual(integrity.evaluate(records)[0]["checks"][0][3], True)

    def test_conditions_are_stored_and_a_rerun_continues(self):
        llm = ExtractorFake()
        self.collect(llm, "--condition", "shuffle_features", "--repeats", "2", "--no-triplet-dishes")
        records = runs.load(self.runs_path)
        self.assertEqual({r.run for r in records}, {"shuffle_features-0", "shuffle_features-1"})
        self.assertEqual(len({r.prompt_hash for r in records}), 2)
        self.assertEqual(set(records[0].means), set(LLM_FEATURE_KEYS))
        again = ExtractorFake()
        self.assertIn("호출 약 0번", self.collect(again, "--condition", "shuffle_features", "--repeats", "2",
                                               "--no-triplet-dishes"))
        self.assertEqual(again.prompts, [])

    def test_a_run_from_another_model_or_prompt_is_not_continued(self):
        self.collect(ExtractorFake(), "--repeats", "1", "--no-triplet-dishes")
        with mock.patch.dict("os.environ", {"METCHU_MENU_MODEL": "openai:gpt-other"}), \
                self.assertRaisesMessage(CommandError, "repeat-0은 다른 설정"):
            self.collect(ExtractorFake(), "--repeats", "1", "--no-triplet-dishes")
        with self.assertRaisesMessage(CommandError, "shuffle_features-0은 다른 설정"):
            means, stds = full()
            runs.append(self.runs_path, [runs.Record("shuffle_features-0", "shuffle_features", "variant", "짬뽕",
                                                     means, stds, model=menu_llm.model_id(), prompt_hash="old")])
            self.collect(ExtractorFake(), "--condition", "shuffle_features", "--repeats", "1", "--no-triplet-dishes")

    def test_stored_runs_keep_a_file_of_their_own(self):
        self.collect(ExtractorFake(), "--stored")
        self.assertIn("건너뜁니다", self.collect(ExtractorFake(), "--stored"))
        self.assertEqual(len(runs.load(self.runs_path)), 3)  # not copied twice
        with self.assertRaisesMessage(CommandError, "--stored 기록"):
            self.collect(ExtractorFake(), "--repeats", "1", "--no-triplet-dishes")
        self.runs_path.unlink()
        self.collect(ExtractorFake(), "--repeats", "1", "--no-triplet-dishes")
        with self.assertRaisesMessage(CommandError, "LLM 추출 기록"):
            self.collect(ExtractorFake(), "--stored")

    def test_dry_run_counts_triplet_dishes_without_calling(self):
        llm = ExtractorFake()
        output = self.collect(llm, "--dry-run")
        self.assertIn("variant 2개 + invariant 1개", output)
        self.assertEqual(llm.prompts, [])
        self.assertFalse(self.runs_path.exists())

    def test_triplet_dishes_in_the_catalog_are_invariant(self):
        MenuItem.objects.filter(raw_name="핫치킨버거").delete()
        path = self.folder / "triplets.json"
        path.write_text(json.dumps([{"anchor": "짬뽕", "near": "핫치킨버거", "far": "케이크", "kind": "distinct",
                                     "source": "ai"}], ensure_ascii=False), encoding="utf-8")
        self.collect(ExtractorFake(), "--triplets", str(path))
        sources = {r.name: r.source for r in runs.load(self.runs_path)}
        self.assertEqual((sources["핫치킨버거"], sources["케이크"]), ("invariant", "suite"))

    def test_benchmark_and_rating_form(self):
        self.collect(ExtractorFake(), "--repeats", "2", "--no-triplet-dishes")
        form = self.folder / "form.csv"
        call_command("export_feature_rating_form", "--runs", str(self.runs_path), "--output", str(form),
                     stdout=io.StringIO())
        lines = form.read_text(encoding="utf-8-sig").splitlines()
        self.assertEqual(lines[1].split(",")[:2], ["핫치킨버거", "고정 메뉴"])
        self.assertEqual(sorted(line.split(",")[0] for line in lines[1:]), ["라면", "짬뽕", "핫치킨버거"])
        values = ",".join(["0.5", "0.1"] * len(LLM_FEATURE_KEYS))
        filled = [lines[0]] + [",".join(line.split(",")[:2]) + ",kim,," + values
                               for line in lines[1:]]
        form.write_text("\n".join(filled) + "\n", encoding="utf-8-sig")
        out, folder = io.StringIO(), self.folder / "report"
        call_command("benchmark_features", "--runs", str(self.runs_path), "--ratings", str(form),
                     "--output-dir", str(folder), "--no-plots", stdout=out)
        text = (folder / "report.md").read_text(encoding="utf-8")
        for heading in ("## 1. Integrity", "## 2. Distribution (variant)", "## 3. Stability", "## 4. Human reference",
                        "## 5. Triplets", "## 6. Downstream impact"):
            self.assertIn(heading, text)
        self.assertIn("PASS     1. Integrity", out.getvalue())
        self.assertIn(f"model: {menu_llm.model_id()}. prompt_hash:", text)
        self.assertTrue((folder / "2_distribution" / "distribution_variant.csv").exists())
        self.assertIn("(`2_distribution/distribution_variant.csv`)", text)
        self.assertIn("## 2. Distribution (invariant)\n\nSkipped: Fewer than two dishes.", text)

    def test_strict_fails_on_broken_records(self):
        means, stds = full()
        runs.append(self.runs_path, [runs.Record("repeat-0", "repeat", "menu", "짬뽕", means | {"spicy": 0.05},
                                                 stds | {"spicy": 0.4})])
        args = ["benchmark_features", "--runs", str(self.runs_path), "--output-dir", str(self.folder / "r"), "--no-plots"]
        call_command(*args, stdout=io.StringIO())
        with self.assertRaisesMessage(CommandError, "integrity"):
            call_command(*args, "--strict", stdout=io.StringIO())

    def test_pipeline_keeps_config_runs_and_sections_in_one_folder(self):
        results = self.folder / "results"
        args = ["run_feature_benchmark", "--name", "trial", "--date", "2026-10-20", "--conditions",
                "repeat:2,shuffle_features:1", "--results-dir", str(results)]
        llm = ExtractorFake()
        with mock.patch.object(extractor, "build_llm", return_value=llm), \
             mock.patch.object(extractor, "api_key_available", return_value=True):
            out = io.StringIO()
            call_command(*args, "--dry-run", stdout=out)
            self.assertEqual(llm.prompts, [])
            self.assertFalse(results.exists())
            self.assertIn("repeat x 2회 -> LLM 호출 약", out.getvalue())
            call_command(*args, stdout=io.StringIO())
            folder = results / "trial"
            config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["conditions"], {"repeat": 2, "shuffle_features": 1})
            self.assertEqual(config["extraction"]["model"], menu_llm.model_id())
            extraction = config["extraction"]
            self.assertEqual({r.run for r in runs.load(folder / "runs" / "runs.jsonl")},
                             {"repeat-0", "repeat-1", "shuffle_features-0"})
            self.assertIn("## 3. Stability", (folder / "report.md").read_text(encoding="utf-8"))
            self.assertTrue((folder / "3_stability" / "stability_by_feature.csv").exists())
            calls = len(llm.prompts)
            rating = folder / "4_human_reference" / "ratings" / "kim.csv"
            rating.parent.mkdir(parents=True)
            human.write_form(rating, [("짬뽕", "매일 바뀌는 메뉴")])
            call_command(*args, stdout=io.StringIO())  # a second run continues instead of repeating
            self.assertEqual(len(llm.prompts), calls)
            config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["ratings"], [str(rating)])  # the ratings folder is read by default
            self.assertEqual(config["extraction"], extraction)  # kept from the first extractions
            self.assertIn("rated by 1 rater(s): kim", (folder / "report.md").read_text(encoding="utf-8"))
            call_command(*args[:-4], "--conditions", "shuffle_foods:1", *args[-2:], stdout=io.StringIO())
            config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["conditions"], {"repeat": 2, "shuffle_features": 1, "shuffle_foods": 1})
            with self.assertRaisesMessage(CommandError, "추출 설정과 다릅니다 (batch_size, seed)"):
                call_command(*args, "--seed", "1", "--batch-size", "10", stdout=io.StringIO())
        with self.assertRaisesMessage(CommandError, "condition:count"):
            call_command("run_feature_benchmark", "--name", "x", "--date", "2026-10-20", "--conditions", "repeat")

    def test_histograms_are_drawn(self):
        self.collect(ExtractorFake(), "--stored")
        folder = self.folder / "report"
        call_command("benchmark_features", "--runs", str(self.runs_path), "--output-dir", str(folder),
                     stdout=io.StringIO())
        self.assertGreater((folder / "2_distribution" / "histograms_variant.png").stat().st_size, 1000)


HISTORY = {
    0: {"버거운버거": ["핫치킨버거", "탄산음료"], "학생회관식당": ["즉석 마라탕", "공기밥"]},
    1: {"버거운버거": ["핫치킨버거"], "학생회관식당": ["마라탕", "돈가스 카레우동"],
        "두레미담": ["핫치킨버거", "수제 핫치킨버거"]},
}
ANSWERS = {"즉석 마라탕": (True, ["마라탕"]), "마라탕": (True, ["마라탕"]), "공기밥": (False, []),
           "돈가스 카레우동": (True, ["돈까스", "카레우동"]), "수제 핫치킨버거": (True, ["핫치킨버거"])}


class MenuSetTests(IsolatedCatalog, TestCase):
    def mappings(self):
        lines = {menu_set.line_key(m)[0]: m for menus in HISTORY.values() for ms in menus.values() for m in ms}
        return {key: (Mapping(name == "핫치킨버거", (name,) if name == "핫치킨버거" else (), "fixed")
                      if name in ("핫치킨버거", "탄산음료") else Mapping(ANSWERS[name][0], tuple(ANSWERS[name][1]), "llm"))
                for key, name in lines.items()}

    def test_variant_dishes_are_gathered_over_days(self):
        result = menu_set.build(siksha.parse(payload(HISTORY)), self.mappings())
        self.assertEqual(result["days"], 2)
        # A catalog line is invariant wherever it is served, and so is a dish a fixed board has.
        self.assertEqual(result["invariant"], [{"name": "핫치킨버거", "restaurants": ["두레미담", "버거운버거"]}])
        variant = {d["name"]: d for d in result["variant"]}
        self.assertEqual(set(variant), {"마라탕", "돈까스", "카레우동"})
        self.assertEqual(variant["마라탕"]["lines"], ["즉석 마라탕", "마라탕"])
        self.assertEqual(variant["돈까스"]["dates"], [day(1).isoformat()])

    def test_a_catalog_dish_is_invariant_without_its_fixed_board(self):
        history = {0: {"두레미담": ["수제 핫치킨버거"]}}
        key = menu_set.line_key("수제 핫치킨버거")[0]
        result = menu_set.build(siksha.parse(payload(history)), {key: Mapping(True, ("핫치킨버거",), "llm")})
        self.assertEqual((result["invariant"], result["variant"]), ([{"name": "핫치킨버거", "restaurants": ["두레미담"]}], []))

    def test_segment_by_catalog(self):
        dishes = menu_set.catalog_dishes()
        self.assertEqual((menu_set.segment("핫치킨버거", dishes), menu_set.segment("마라탕", dishes)),
                         ("invariant", "variant"))

    def build(self, llm, *args):
        history = self.folder / "history.json"
        history.write_text(json.dumps(payload(HISTORY), ensure_ascii=False), encoding="utf-8")
        out = io.StringIO()
        with mock.patch("menus.preprocess.mapper.build_llm", return_value=llm), \
             mock.patch("menus.management.commands.build_eval_menu_set.api_key_available", return_value=True):
            call_command("build_eval_menu_set", "--from-json", str(history), "--output", str(self.folder / "menu_set.json"),
                         "--start", day(0).isoformat(), "--end", day(1).isoformat(), *args, stdout=out)
        return out.getvalue()

    def test_command_preprocesses_new_lines_once(self):
        llm = PreprocessLLM(ANSWERS)
        self.assertIn("새로 전처리할 줄 5개", self.build(llm, "--dry-run"))
        self.assertFalse(MenuLine.objects.exists())
        self.assertIn("invariant 1개 / variant 3개", self.build(llm))
        again = PreprocessLLM(ANSWERS)
        self.assertIn("새로 전처리할 줄 0개", self.build(again))
        self.assertEqual(again.calls, [])

    def test_collect_keeps_the_kind_from_the_menu_set(self):
        self.build(PreprocessLLM(ANSWERS))
        runs_path = self.folder / "runs.jsonl"
        with mock.patch.object(extractor, "build_llm", return_value=ExtractorFake()), \
             mock.patch.object(extractor, "api_key_available", return_value=True):
            call_command("collect_feature_runs", "--menu-set", str(self.folder / "menu_set.json"), "--repeats", "1",
                         "--no-triplet-dishes", "--output", str(runs_path), stdout=io.StringIO())
        self.assertEqual({r.name: r.source for r in runs.load(runs_path)},
                         {"마라탕": "variant", "돈까스": "variant", "카레우동": "variant", "핫치킨버거": "invariant"})
        with self.assertRaisesMessage(CommandError, "--menu-set"):
            call_command("collect_feature_runs", "--menu-set", "x.json", "--stored", "--output", str(runs_path))


class ReportTests(SimpleTestCase):
    def test_sections_run_per_kind_and_integrity_filters(self):
        means, stds = full()
        records = [runs.Record("repeat-0", "repeat", "variant", "짬뽕", means, stds),
                   runs.Record("repeat-0", "repeat", "invariant", "핫치킨버거", means, stds),
                   runs.Record("repeat-0", "repeat", "variant", "깨진값", means | {"spicy": 2.0}, stds)]
        results = report.run_sections(records)
        titles = [r["title"] for r in results]
        self.assertEqual(titles[:4], ["1. Integrity", "2. Distribution", "2. Distribution (variant)",
                                      "2. Distribution (invariant)"])
        self.assertEqual(report.status(results[0]), "fail")
        self.assertEqual(results[2]["skipped"], "Fewer than two dishes.")  # 깨진값 was left out
