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


def dish(number, name, is_set=False, spicy=0.5):
    return {"id": number, "name": name, "food_group": "국", "is_set": is_set, "served": [f"학생회관식당: {name}"],
            "features": {key: 0.0 for key in FEATURE_KEYS} | {"spicy": spicy},
            "feature_std": {key: 0.0 for key in FEATURE_KEYS}, "model": "google:fake"}


def fill(path, rows, rater=None):
    """Write `rows` ({name: (status, ["spicy_mean", ...])}) into a review workbook, as a rater would."""
    book = openpyxl.load_workbook(path)
    sheet = book[review.SHEET]
    if rater:
        sheet["B1"] = rater
    column = {sheet.cell(4, index).value: index for index in range(1, sheet.max_column + 1)}
    for row in range(review.FIRST, sheet.max_row + 1):
        name = sheet.cell(row, column["name"]).value
        if name in rows:
            status, wrong = rows[name]
            sheet.cell(row, column["status"], status)
            for value in wrong:
                sheet.cell(row, column[f"{value}_wrong"], "x")
    book.save(path)


def rated(rater, number, wrong=(), status=review.DONE):
    marks = {field: [key for key, f in wrong if f == field] for field in ("mean", "std")}
    return {"rater": rater, "source": "general", "id": str(number), "name": f"d{number}", "status": status,
            "wrong": marks}


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

    def test_a_sample_gives_each_group_its_share(self):
        group = lambda item: "a" if item < 56 else "b" if item < 86 else "c"  # 56, 30, 14
        picked = review.proportional_sample(range(100), group, 10)
        self.assertEqual([sum(group(i) == g for i in picked) for g in "abc"], [6, 3, 1])  # 5.6, 3.0, 1.4
        self.assertEqual(picked, review.proportional_sample(range(100), group, 10))
        self.assertEqual(review.proportional_sample(range(4), group, 10), [0, 1, 2, 3])

    def test_a_workbook_shows_the_llms_values_and_reads_back_the_marks(self):
        path = self.folder / "kim.xlsx"
        review.write(path, "kim", "cafeteria 2026-11-02", [dish(1, "김치찌개", spicy=0.6), dish(2, "돈가스", True),
                                                         dish(3, "짬뽕", spicy=0.1)])
        book = openpyxl.load_workbook(path)
        self.assertEqual(book.sheetnames, ["검토", "요약", "안내", "루브릭"])
        sheet = book[review.SHEET]
        header = [c.value for c in sheet[4]]
        self.assertEqual(header, list(review.COLUMNS) + review.value_columns())
        self.assertEqual(header[7:11], ["spicy_mean", "spicy_mean_wrong", "spicy_std", "spicy_std_wrong"])
        self.assertEqual((sheet["A5"].value, sheet["B5"].value, sheet["H5"].value, sheet["E6"].value),
                         (1, "김치찌개", 0.6, "세트"))
        self.assertIn('"완료",\'검토\'!$I$5:$I$7,"X"', book["요약"]["C7"].value)  # spicy mean marks

        fill(path, {"김치찌개": (review.DONE, []), "짬뽕": (review.DONE, ["spicy_mean", "soupy_std"])})
        rows = review.load([path])  # 돈가스 has no status yet
        self.assertEqual([(r["id"], r["name"], r["status"], r["wrong"]) for r in rows],
                         [("1", "김치찌개", "완료", {"mean": [], "std": []}),
                          ("3", "짬뽕", "완료", {"mean": ["spicy"], "std": ["soupy"]})])
        self.assertEqual({(r["rater"], r["source"]) for r in rows}, {("kim", "cafeteria 2026-11-02")})

    def test_a_wrong_mark_or_status_names_the_cell(self):
        path = self.folder / "kim.xlsx"
        review.write(path, "kim", "general", [dish(1, "짬뽕")])
        fill(path, {"짬뽕": ("", ["spicy_mean"])})
        with self.assertRaisesMessage(ValueError, "row 5: values are marked X but the status is blank"):
            review.load([path])
        fill(path, {"짬뽕": ("좋음", [])})
        with self.assertRaisesMessage(ValueError, "row 5: status '좋음'"):
            review.load([path])
        book = openpyxl.load_workbook(path)
        book[review.SHEET]["I5"] = "O"
        book.save(path)
        with self.assertRaisesMessage(ValueError, "row 5: spicy_mean_wrong is 'O'"):
            review.load([path])

    def test_the_pass_bar_per_field_and_feature(self):
        keys = LLM_FEATURE_KEYS
        # 20 dishes x 32 means, 32 wrong: overall 95%; at most 3 wrong per feature: 85%.
        wrong = [(keys[k], "mean") for k in range(10) for _ in range(3)] + [(keys[10], "mean")] * 2
        reviews = [rated("kim", i, [w for j, w in enumerate(wrong) if j % 20 == i]) for i in range(20)]
        summary = review.summarize(reviews)["general"]
        self.assertEqual((summary["done"], summary["fields"]["mean"]["overall"]), (20, 0.95))
        self.assertEqual(min(summary["fields"]["mean"]["feature"].values()), 0.85)
        self.assertTrue(summary["passed"])  # exactly at both bars
        reviews[0]["wrong"]["mean"].append(keys[20])
        self.assertFalse(review.summarize(reviews)["general"]["passed"])  # overall 94.8%
        reviews[0]["wrong"]["mean"].pop()
        reviews[19]["wrong"]["std"].append(keys[0])
        reviews[18]["wrong"]["std"].append(keys[0])
        reviews[17]["wrong"]["std"].append(keys[0])
        reviews[16]["wrong"]["std"].append(keys[0])
        summary = review.summarize(reviews)["general"]
        self.assertGreater(summary["fields"]["std"]["overall"], 0.99)
        self.assertFalse(summary["fields"]["std"]["passed"])  # spicy std 80%
        self.assertFalse(summary["passed"])

    def test_agreement_on_shared_dishes(self):
        reviews = [rated("kim", 1, [("spicy", "mean")]), rated("lee", 1, [("spicy", "mean"), ("sweet", "std")]),
                   rated("kim", 2), rated("lee", 3, status=review.UNKNOWN)]
        summary = review.summarize(reviews)["general"]
        self.assertEqual((summary["dishes"], summary["done"], summary["unknown"], summary["shared_dishes"]), (3, 3, 1, 1))
        self.assertEqual((summary["agreement"], summary["wrong_agreement"]), (63 / 64, 0.5))
        self.assertIn("| general | 2 | 3 | 3 | 1 | 97.9% | spicy 33.3% | 99.0% | sweet 66.7% | no | 98.4% (1) | 50.0% |",
                      review.report({"general": summary}))


def export_book(path, menus):
    """A per-dish export like the team's: a title row, the header, then ({column: value}, means)."""
    keys = [f"x ({key}) {suffix}" for suffix in ("평균", "표준편차") for key in FEATURE_KEYS]
    columns = ["후보 ID", "원본 메뉴명", "식당 목록", "식당별 원본 설명", "식당별 유형", "특성 추출 모델",
               "구성 음식(원본 연결)", "음식 분류", "feature 버전"] + keys
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "일반 음식"
    sheet.append(["메추 음식별 특성 · 일반 음식"])
    sheet.append(columns)
    for values, means in menus:
        means = {key: 0.0 for key in FEATURE_KEYS} | means
        sheet.append([values.get(c) for c in columns[:9]] + [means[k] for k in FEATURE_KEYS] + [0.1] * len(FEATURE_KEYS))
    book.save(path)


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

    def assignment(self, kind):
        with open(self.folder / f"{kind}_assignment.csv", encoding="utf-8-sig") as f:
            return list(csv.reader(f))[1:]

    def test_a_day_is_split_between_the_raters_and_reported(self):
        self.assertIn("음식 3개 중 3개 (공통 3개)", self.export("--date", "2026-11-02"))  # 라면 has old features
        self.assertEqual([row[1:] for row in self.assignment("cafeteria")],
                         [["돈가스", "", "학생회관식당", "kim, lee"], ["돈가스", "세트", "학생회관식당", "kim, lee"],
                          ["제육덮밥", "", "학생회관식당", "kim, lee"]])
        for rater in ("kim", "lee"):
            fill(self.folder / f"cafeteria_{rater}.xlsx",
                 {"제육덮밥": (review.DONE, []), "돈가스": (review.DONE, ["spicy_mean"])})
        out = io.StringIO()
        report = self.folder / "report.md"
        call_command("report_feature_review", "--reviews", *map(str, self.folder.glob("*.xlsx")),
                     "--output", str(report), stdout=out)
        text = report.read_text(encoding="utf-8")
        self.assertIn("| cafeteria 2026-11-02 | 2 | 3 | 6 | 0 | 97.9% | spicy 33.3% | 100.0% |", text)
        self.assertIn("| no | 100.0% (3) | 100.0% |", text)

    def test_a_day_can_be_sampled(self):
        self.assertIn("음식 3개 중 2개 (공통 1개)", self.export("--date", "2026-11-02", "--n", "2", "--overlap", "1"))
        self.assertEqual(len(self.assignment("cafeteria")), 2)

    def test_restaurant_dishes_are_sampled_in_proportion_to_their_categories(self):
        self.export("--stores", "--n", "3", "--overlap", "0")
        sheet = openpyxl.load_workbook(self.folder / "general_kim.xlsx")[review.SHEET]
        self.assertEqual(sheet["B2"].value, "general")
        self.assertIn("(매운맛 선택)", sheet["F5"].value)  # the menu board's description
        groups = [row[3] for row in self.assignment("general")]
        self.assertEqual(sorted(groups), ["분식", "중식", "중식"])  # 1.8 and 1.2 of 3

    def test_the_teams_export_is_grouped_into_dishes(self):
        path = self.folder / "export.xlsx"
        export_book(path, [
            ({"후보 ID": 12, "원본 메뉴명": "LA갈비 (250g)", "식당 목록": "1. 풍년옥", "식당별 원본 설명": "1: 숯불",
              "식당별 유형": "1: 한식", "특성 추출 모델": "1: gpt-test", "구성 음식(원본 연결)": "LA갈비",
              "feature 버전": FEATURE_VERSION}, {"beef": 0.9}),
            ({"후보 ID": 11, "원본 메뉴명": "대패 LA갈비", "식당 목록": "1. 목구멍\n2. 목구멍 2호점",
              "식당별 유형": "1, 2: 육류,고기요리", "특성 추출 모델": "1, 2: gpt-test",
              "구성 음식(원본 연결)": "LA갈비", "feature 버전": FEATURE_VERSION}, {"beef": 0.9}),
            ({"후보 ID": 13, "원본 메뉴명": "LA갈비 세트", "식당 목록": "1. 풍년옥", "식당별 유형": "1: 한식",
              "구성 음식(원본 연결)": "LA갈비", "feature 버전": FEATURE_VERSION}, {"beef": 0.9, "meal_variety": 1}),
            ({"후보 ID": 14, "원본 메뉴명": "옛 메뉴", "식당 목록": "1. 풍년옥", "구성 음식(원본 연결)": "옛 메뉴",
              "feature 버전": "v1"}, {}),
            ({"원본 메뉴명": "보류 메뉴", "구성 음식(원본 연결)": "보류", "feature 버전": FEATURE_VERSION}, {}),
        ])
        self.assertIn("general: 음식 2개 중 2개", self.export("--workbook", str(path)))
        self.assertEqual(self.assignment("general"), [["11", "LA갈비", "", "육류,고기요리", "kim, lee"],
                                                      ["13", "LA갈비", "세트", "한식", "kim, lee"]])
        sheet = openpyxl.load_workbook(self.folder / "general_kim.xlsx")[review.SHEET]
        served = {sheet.cell(row, 1).value: sheet.cell(row, 6).value for row in (5, 6)}
        self.assertEqual(served[11], "목구멍: 대패 LA갈비\n목구멍 2호점: 대패 LA갈비\n풍년옥: LA갈비 (250g) (숯불)")
        self.assertIn("gpt-test", sheet["C2"].value)

    def test_nothing_to_review_and_nothing_reviewed_are_refused(self):
        with self.assertRaisesMessage(CommandError, "현재 feature가 있는 음식이 없습니다"):
            self.export("--date", "2026-11-03")
        self.export("--date", "2026-11-02")
        with self.assertRaisesMessage(CommandError, "상태가 적힌 행이 없습니다"):
            call_command("report_feature_review", "--reviews", str(self.folder / "cafeteria_kim.xlsx"),
                         stdout=io.StringIO())
