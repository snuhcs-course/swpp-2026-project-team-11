import csv
import pathlib
import tempfile

from django.test import SimpleTestCase

from menus.sources import stores

COLUMNS = ["상가업소번호", "상호명", "지점명", "상권업종대분류코드", "상권업종중분류명",
           "상권업종소분류코드", "상권업종소분류명", "도로명주소", "층정보", "경도", "위도"]


def store_row(store_id, name, branch, lat, lng, top_code="I2", sub_code="I20103"):
    return {"상가업소번호": store_id, "상호명": name, "지점명": branch, "상권업종대분류코드": top_code,
            "상권업종중분류명": "한식", "상권업종소분류코드": sub_code, "상권업종소분류명": "국/탕/찌개류",
            "도로명주소": "서울특별시 관악구 봉천로 466", "층정보": "1", "경도": lng, "위도": lat}


def write_stores(path: pathlib.Path, rows: list[dict]) -> None:
    """A CSV with the columns we read, quoted like the real file."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


class ReadFoodStoresTests(SimpleTestCase):
    def test_food_shops_without_cafes(self):
        path = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory())) / "stores.csv"
        write_stores(path, [
            store_row("1", " 코시 ", "서울대입구점", 37.48, 126.95),
            store_row("2", "스타벅스", "", 37.48, 126.95, sub_code="I21201"),
            store_row("3", "파리바게뜨", "", 37.48, 126.95, sub_code="I21001"),
            store_row("4", "편의점", "", 37.48, 126.95, top_code="G2", sub_code="G20405"),
            store_row("5", "호프", "", 37.48, 126.95, sub_code="I21104"),
        ])
        shops = list(stores.read_food_stores(path))
        self.assertEqual([s.id for s in shops], ["1", "5"])
        self.assertEqual(shops[0], stores.Store(
            id="1", name="코시", branch="서울대입구점", category="한식", subcategory="국/탕/찌개류",
            lat=37.48, lng=126.95, road_address="서울특별시 관악구 봉천로 466", floor="1"))
