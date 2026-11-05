import csv
import datetime
import io
import pathlib
import tempfile

import openpyxl

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from menus.features.benchmark import review
from menus.features.schema import FEATURE_KEYS, FEATURE_VERSION, LLM_FEATURE_KEYS
from menus.models import Food, MenuItem, Restaurant, StoreMenu


def dish(name, is_set=False, spicy=0.5):
    return {"name": name, "food_group": "국", "is_set": is_set, "served": [f"학생회관식당: {name}"],
            "features": {key: 0.0 for key in FEATURE_KEYS} | {"spicy": spicy},
            "feature_std": {key: 0.0 for key in FEATURE_KEYS}, "model": "google:fake"}


def fill(path, verdicts, rater=None):
    """Write `verdicts` ({name: (verdict, wrong keys)}) into a review workbook, as a rater would."""
    book = openpyxl.load_workbook(path)
    sheet = book[review.SHEET]
    if rater:
        sheet["B1"] = rater
    for row in range(5, sheet.max_row + 1):
        name = sheet.cell(row, 1).value
        if name in verdicts:
            sheet.cell(row, 2, verdicts[name][0])
            sheet.cell(row, 3, verdicts[name][1])
    book.save(path)


class ReviewTests(SimpleTestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = pathlib.Path(folder.name)

    def test_every_rater_gets_the_shared_dishes_and_a_fair_share_of_the_rest(self):
        assignment = review.assign(range(23), ["kim", "lee", "park"], overlap=5)
        shared = set.intersection(*(set(mine) for mine in assignment.values()))
        self.assertEqual(len(shared), 5)
        self.assertEqual(set().union(*assignment.values()), set(range(23)))
        self.assertEqual(sorted(len(mine) for mine in assignment.values()), [11, 11, 11])  # 5 + 18 / 3
        self.assertEqual(assignment, review.assign(range(23), ["kim", "lee", "park"], overlap=5))

    def test_a_workbook_shows_the_llms_values_and_reads_back_the_verdicts(self):
        path = self.folder / "kim.xlsx"
        review.write(path, "kim", "cafeteria 2026-11-02", [dish("김치찌개", spicy=0.6), dish("김치찌개", is_set=True),
                                                         dish("짬뽕", spicy=0.1)])
        book = openpyxl.load_workbook(path)
        self.assertEqual(book.sheetnames, ["검토", "요약", "안내", "루브릭"])
        sheet = book[review.SHEET]
        header = [c.value for c in sheet[4]]
        self.assertEqual(header[:7], list(review.COLUMNS))
        self.assertEqual(header[7:], [f"{key}_{field}" for key in LLM_FEATURE_KEYS for field in ("mean", "std")])
        self.assertEqual((sheet["A5"].value, sheet["H5"].value, sheet["F6"].value), ("김치찌개", 0.6, "세트"))
        self.assertIn("SEARCH(\",spicy,\"", book["요약"]["C11"].value)

        fill(path, {"김치찌개": (review.REASONABLE, None), "짬뽕": (review.PARTLY, "spicy， soupy")})
        rows = review.load([path])
        self.assertEqual([(r["name"], r["set"], r["verdict"], r["wrong"]) for r in rows],
                         [("김치찌개", False, "합리적", []), ("김치찌개", True, "합리적", []),
                          ("짬뽕", False, "일부 틀림", ["spicy", "soupy"])])
        self.assertEqual({(r["rater"], r["source"]) for r in rows}, {("kim", "cafeteria 2026-11-02")})

    def test_a_wrong_verdict_or_key_names_the_cell(self):
        path = self.folder / "kim.xlsx"
        review.write(path, "kim", "general", [dish("짬뽕")])
        fill(path, {"짬뽕": ("좋음", None)})
        with self.assertRaisesMessage(ValueError, "row 5: verdict '좋음'"):
            review.load([path])
        fill(path, {"짬뽕": (review.PARTLY, "spicy, 매운맛")})
        with self.assertRaisesMessage(ValueError, "row 5: unknown feature keys 매운맛"):
            review.load([path])

    def test_the_pass_bar_agreement_and_wrong_features(self):
        def rated(rater, name, verdict, wrong=()):
            return {"rater": rater, "source": "general", "name": name, "set": False, "verdict": verdict,
                    "wrong": list(wrong)}
        reviews = ([rated("kim", f"r{i}", review.REASONABLE) for i in range(16)]
                   + [rated("kim", "p1", review.PARTLY, ["spicy"]), rated("kim", "p2", review.PARTLY, ["spicy", "sweet"]),
                      rated("kim", "p3", review.PARTLY, ["soupy"]), rated("kim", "u1", review.UNREASONABLE),
                      rated("kim", "x", review.UNKNOWN), rated("lee", "r0", review.REASONABLE),
                      rated("lee", "p1", review.UNREASONABLE)])
        summary = review.summarize(reviews[:-2])["general"]
        self.assertEqual((summary["judged"], summary["share"][review.REASONABLE], summary["share"][review.UNREASONABLE]),
                         (20, 0.8, 0.05))
        self.assertTrue(summary["passed"])  # exactly at the bar
        self.assertEqual(summary["wrong"][0], ("spicy", 2))
        summary = review.summarize(reviews)["general"]
        self.assertFalse(summary["passed"])  # 17 / 22 reasonable, 2 / 22 unreasonable
        self.assertEqual((summary["shared_dishes"], summary["agreement"]), (2, 0.5))
        self.assertIn("| general | 2 | 21 | 23 | 22 |", review.report({"general": summary}))


class CommandTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = pathlib.Path(folder.name)
        values = {key: 0.1 for key in FEATURE_KEYS}
        food = lambda name, **kw: Food.objects.create(name=name, is_food=True, features=values, feature_std=values,
                                                      feature_version=FEATURE_VERSION, **kw)
        hall = Restaurant.objects.create(code="hall", name="학생회관식당")
        for name, is_set in (("제육덮밥", False), ("돈가스", False), ("돈가스", True)):
            MenuItem.objects.create(date=datetime.date(2026, 11, 2), meal="LU", restaurant=hall,
                                    raw_name=name, food=food(name, is_set=is_set))
        old = Food.objects.create(name="라면", is_food=True, features={"spicy": 0.5}, feature_version="v1")
        MenuItem.objects.create(date=datetime.date(2026, 11, 2), meal="LU", restaurant=hall, raw_name="라면", food=old)
        for code, category, names in (("a", "중식", ("짜장면", "짬뽕", "탕수육")), ("b", "분식", ("떡볶이", "김밥"))):
            shop = Restaurant.objects.create(code=code, name=f"{category}집", source="naver", category=category)
            for name in names:
                StoreMenu.objects.create(restaurant=shop, raw_name=name, description="매운맛 선택", food=food(name))

    def export(self, *args):
        out = io.StringIO()
        call_command("export_feature_review", *args, "--raters", "kim,lee", "--output-dir", str(self.folder),
                     stdout=out)
        return out.getvalue()

    def test_a_day_is_split_between_the_raters_and_reported(self):
        self.assertIn("음식 3개 (공통 3개)", self.export("--date", "2026-11-02"))  # 라면 has old features
        with open(self.folder / "cafeteria_assignment.csv", encoding="utf-8-sig") as f:
            self.assertEqual(list(csv.reader(f))[1:], [["돈가스", "", "kim, lee"], ["돈가스", "세트", "kim, lee"],
                                                       ["제육덮밥", "", "kim, lee"]])
        for rater in ("kim", "lee"):
            fill(self.folder / f"cafeteria_{rater}.xlsx",
                 {"제육덮밥": (review.REASONABLE, None), "돈가스": (review.UNREASONABLE, None)})
        out = io.StringIO()
        report = self.folder / "report.md"
        call_command("report_feature_review", "--reviews", *map(str, self.folder.glob("*.xlsx")),
                     "--output", str(report), stdout=out)
        self.assertIn("| cafeteria 2026-11-02 | 2 | 3 | 6 | 6 | 33.3% | 0.0% | 66.7% | 0 | no | 100.0% (3) |",
                      report.read_text(encoding="utf-8"))

    def test_restaurant_dishes_are_sampled_over_their_categories(self):
        self.export("--stores", "--n", "2", "--overlap", "0")
        sheet = openpyxl.load_workbook(self.folder / "general_kim.xlsx")[review.SHEET]
        self.assertEqual(sheet["B2"].value, "general")
        self.assertIn("(매운맛 선택)", sheet["G5"].value)  # the menu board's description
        with open(self.folder / "general_assignment.csv", encoding="utf-8-sig") as f:
            names = [row[0] for row in list(csv.reader(f))[1:]]
        self.assertEqual(len(names), 2)
        self.assertEqual(len({"짜장면", "짬뽕", "탕수육"} & set(names)), 1)  # one per category

    def test_nothing_to_review_and_nothing_reviewed_are_refused(self):
        with self.assertRaisesMessage(CommandError, "현재 feature가 있는 음식이 없습니다"):
            self.export("--date", "2026-11-03")
        self.export("--date", "2026-11-02")
        with self.assertRaisesMessage(CommandError, "판정이 적힌 행이 없습니다"):
            call_command("report_feature_review", "--reviews", str(self.folder / "cafeteria_kim.xlsx"),
                         stdout=io.StringIO())
