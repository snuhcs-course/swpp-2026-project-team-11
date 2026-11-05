"""Human review of the extracted features (P21): people judge whether the LLM's means
and stds of each dish are reasonable, instead of rating the dish themselves (human.py).

export_feature_review writes one workbook per rater and source; report_feature_review
reads the filled copies. The sheet "검토" holds, from the row whose first cell is `name`:

    name, verdict, wrong_features, comment, food_group, set, served, <key>_mean, <key>_std, ...

with the rater in B1 and the source in B2 ("cafeteria 2026-11-02", "general").

- verdict: 합리적 (no wrong feature), 일부 틀림 (1-3), 비합리적 (4 or more, or the dish was
  taken for another), 판단 불가 (the rater does not know the dish; left out of the shares)
- wrong_features: the wrong features' keys, comma-separated. A feature is wrong when its
  mean is WRONG_GAP or more off what the rubric gives the dish, or its std plainly
  contradicts how much its recipes vary (0 for a dish made many ways).

The pass bar, per source, on the judged dishes, fixed before any review: reasonable >=
PASS_REASONABLE and unreasonable <= MAX_UNREASONABLE. Every rating counts, so a shared
dish counts once per rater. The raters share OVERLAP dishes per source, for agreement:
the share of rater pairs giving a shared dish the same verdict.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from itertools import combinations

import openpyxl
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from menus.features.schema import FEATURE_VERSION, LLM_FEATURE_KEYS, RUBRIC

from .human import BOLD, BROKEN, FIXED, FONT, HEAD, INPUT, KEY_FONT, cell, write_rubric

SHEET = "검토"
VERDICTS = ("합리적", "일부 틀림", "비합리적", "판단 불가")
REASONABLE, PARTLY, UNREASONABLE, UNKNOWN = VERDICTS
WRONG_GAP = 0.3
PASS_REASONABLE = 0.80
MAX_UNREASONABLE = 0.05
OVERLAP = 10
COLUMNS = ("name", "verdict", "wrong_features", "comment", "food_group", "set", "served")
LABELS = ("음식", "판정", "틀린 feature (key, 쉼표로)", "의견", "분류", "세트", "판매 예")
STD_FONT = Font(name="Arial", size=9, color="808080")


def assign(dishes, raters, overlap=OVERLAP, seed=0) -> dict[str, list]:
    """{rater: dishes}: `overlap` dishes for everyone, the rest split evenly, each list shuffled."""
    rng = random.Random(seed)
    dishes = sorted(dishes)
    rng.shuffle(dishes)
    shared, rest = dishes[:overlap], dishes[overlap:]
    out = {}
    for index, rater in enumerate(raters):
        mine = shared + rest[index::len(raters)]
        rng.shuffle(mine)
        out[rater] = mine
    return out


def write(path, rater, source, dishes) -> None:
    """A review workbook: one row per dish ({"name", "food_group", "is_set", "served", "features",
    "feature_std", "model"}), the LLM's values fixed and the verdict columns to fill."""
    book = openpyxl.Workbook()
    form = book.active
    form.title = SHEET
    models = ", ".join(sorted({d["model"] for d in dishes if d["model"]})) or "?"
    cell(form, 1, 1, "검토자", BOLD)
    cell(form, 1, 2, rater, fill=INPUT)
    cell(form, 2, 1, "출처", BOLD)
    cell(form, 2, 2, source, fill=FIXED)
    cell(form, 1, 3, "노란 칸(판정·틀린 feature·의견)만 입력하세요. 기준은 '안내'와 '루브릭' 시트에 있습니다.")
    cell(form, 2, 3, f"LLM 추출값 ({models}, feature {FEATURE_VERSION}, rubric {RUBRIC['prompt_version']}): "
                     "mean은 그 음식에서 그 특징이 얼마나 두드러지는지(0~1), std는 레시피·식당에 따른 차이.")
    for row in (1, 2):
        form.merge_cells(start_row=row, start_column=3, end_row=row, end_column=20)
    first, last = 5, 4 + len(dishes)
    labels = {feature["key"]: feature["label_ko"] for feature in RUBRIC["features"]}
    keys = [f"{key}_{field}" for key in LLM_FEATURE_KEYS for field in ("mean", "std")]
    for index, (column, label) in enumerate(zip(COLUMNS, LABELS), start=1):
        cell(form, 3, index, label, BOLD, HEAD)
        cell(form, 4, index, column, KEY_FONT, HEAD)
    start = len(COLUMNS) + 1
    for offset, key in enumerate(LLM_FEATURE_KEYS):
        column = start + 2 * offset
        cell(form, 3, column, f"{labels[key]} ({key})", BOLD, HEAD)
        form.merge_cells(start_row=3, start_column=column, end_row=3, end_column=column + 1)
    for index, key in enumerate(keys, start=start):
        cell(form, 4, index, key, KEY_FONT, HEAD)
    for row, dish in enumerate(dishes, start=first):
        fixed = [dish["name"], None, None, None, dish["food_group"], "세트" if dish["is_set"] else "",
                 "\n".join(dish["served"])]
        for index, value in enumerate(fixed, start=1):
            cell(form, row, index, value, fill=INPUT if 2 <= index <= 4 else FIXED)
        for offset, key in enumerate(LLM_FEATURE_KEYS):
            column = start + 2 * offset
            cell(form, row, column, dish["features"].get(key)).number_format = "0.00"
            cell(form, row, column + 1, dish["feature_std"].get(key), STD_FONT).number_format = "0.00"
    verdict = DataValidation(type="list", formula1='"' + ",".join(VERDICTS) + '"', allow_blank=True,
                             showErrorMessage=True, errorTitle="판정", error="목록에서 고르세요.")
    form.add_data_validation(verdict)
    verdict.add(f"B{first}:B{last}")
    form.conditional_formatting.add(f"C{first}:C{last}", FormulaRule(
        fill=BROKEN, formula=[f'AND($B{first}="{PARTLY}",$C{first}="")']))
    for offset in range(len(LLM_FEATURE_KEYS)):
        mean = get_column_letter(start + 2 * offset)
        form.conditional_formatting.add(f"{mean}{first}:{mean}{last}", ColorScaleRule(
            start_type="num", start_value=0, start_color="FFFFFF", end_type="num", end_value=1, end_color="5B9BD5"))
    for letter, width in zip("ABCDEFG", (22, 11, 20, 24, 10, 6, 34)):
        form.column_dimensions[letter].width = width
    for index in range(start, start + len(keys)):
        form.column_dimensions[get_column_letter(index)].width = 6
    form.freeze_panes = f"E{first}"
    _write_summary(book.create_sheet("요약"), first, last)
    _write_guide(book.create_sheet("안내"))
    write_rubric(book.create_sheet("루브릭"))
    book.save(path)


def _write_summary(summary, first, last) -> None:
    verdicts, wrong = f"'{SHEET}'!$B${first}:$B${last}", f"'{SHEET}'!$C${first}:$C${last}"
    cell(summary, 1, 1, "이 파일의 결과 (전체 결과와 통과 여부는 report_feature_review)", BOLD)
    for index, text in enumerate(("판정", "음식 수", "비율 (판단 불가 제외)"), start=1):
        cell(summary, 2, index, text, BOLD, HEAD)
    judged = f'(COUNTA({verdicts})-COUNTIF({verdicts},"{UNKNOWN}"))'
    for row, verdict in enumerate(VERDICTS, start=3):
        cell(summary, row, 1, verdict)
        cell(summary, row, 2, f'=COUNTIF({verdicts},"{verdict}")')
        if verdict != UNKNOWN:
            cell(summary, row, 3, f"=IF({judged}=0,\"\",B{row}/{judged})").number_format = "0.0%"
    cell(summary, 8, 1, f"통과 기준: 합리적 ≥ {PASS_REASONABLE:.0%}, 비합리적 ≤ {MAX_UNREASONABLE:.0%}", BOLD)
    for index, text in enumerate(("key", "이름", "틀렸다고 한 음식 수"), start=1):
        cell(summary, 10, index, text, BOLD, HEAD)
    for row, feature in enumerate((f for f in RUBRIC["features"] if f["key"] in LLM_FEATURE_KEYS), start=11):
        cell(summary, row, 1, feature["key"])
        cell(summary, row, 2, feature["label_ko"])
        cell(summary, row, 3, f'=SUMPRODUCT(--ISNUMBER(SEARCH(",{feature["key"]},",'
                              f'","&SUBSTITUTE({wrong}," ","")&",")))')
    for letter, width in zip("ABC", (24, 12, 22)):
        summary.column_dimensions[letter].width = width


def _write_guide(guide) -> None:
    lines = [
        ("Metchu! feature 검토", BOLD),
        ("LLM이 음식 이름으로 추출한 32개 feature가 합리적인지 사람이 판단합니다. 값을 새로 매기지 않고, "
         "주어진 값이 그 음식에 맞는지만 봅니다.", FONT),
        ("", FONT), ("작성 순서", BOLD),
        ("1. '검토' 시트 B1의 이름을 확인합니다.", FONT),
        ("2. 음식마다 판매 예(식당·메뉴 줄)를 보고, 모르는 음식이면 레시피나 사진을 찾아봅니다. 그래도 모르면 '판단 불가'.", FONT),
        ("3. 각 feature의 mean과 std를 '루브릭' 시트 기준과 비교합니다.", FONT),
        (f"   틀린 feature: mean이 루브릭으로 보아 {WRONG_GAP} 이상 어긋남 (예: 짬뽕 spicy 0.10), "
         "또는 std가 레시피 차이와 분명히 맞지 않음 (예: 식당마다 크게 다른 음식인데 std 0).", FONT),
        ("   그보다 작은 차이는 틀린 것으로 보지 않습니다.", FONT),
        ("4. 판정을 고릅니다.", FONT),
        (f"   {REASONABLE}: 틀린 feature 없음 / {PARTLY}: 1~3개 / {UNREASONABLE}: 4개 이상, 또는 다른 음식으로 이해함 / "
         f"{UNKNOWN}: 음식을 몰라 판단할 수 없음", FONT),
        ("5. 틀린 feature의 key를 쉼표로 적습니다 (예: spicy, soupy). key는 4행 또는 '루브릭' 시트에 있습니다. "
         "의견에는 어떻게 틀렸는지 짧게 적습니다 (예: spicy 0.1 → 0.7).", FONT),
        ("6. 다른 검토자와 상의하지 않고, .xlsx 그대로 저장해 제출합니다.", FONT),
        ("", FONT), ("범례", BOLD),
    ]
    for row, (text, font) in enumerate(lines, start=1):
        cell(guide, row, 1, text, font)
    row = len(lines) + 1
    for text, fill in (("입력하는 칸", INPUT), ("수정하지 않는 칸", FIXED), (f"{PARTLY}인데 틀린 feature가 비어 있음", BROKEN)):
        cell(guide, row, 1, text, fill=fill)
        row += 1
    guide.column_dimensions["A"].width = 110


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def load(paths) -> list[dict]:
    """Every rated row of the filled workbooks: {"rater", "source", "name", "set", "verdict", "wrong"}."""
    known = set(LLM_FEATURE_KEYS)
    reviews = []
    for path in paths:
        sheet = openpyxl.load_workbook(path, read_only=True, data_only=True)[SHEET]
        rows = list(sheet.iter_rows(values_only=True))
        rater, source = _text(rows[0][1]), _text(rows[1][1])
        header = next(i for i, row in enumerate(rows) if _text(row[0]) == "name")
        for number, row in enumerate(rows[header + 1:], start=header + 2):
            verdict = _text(row[1])
            if not _text(row[0]) or not verdict:
                continue
            where = f"{path}, row {number}"
            if verdict not in VERDICTS:
                raise ValueError(f"{where}: verdict {verdict!r} is not one of {', '.join(VERDICTS)}")
            wrong = [key.strip() for key in _text(row[2]).replace("，", ",").split(",") if key.strip()]
            unknown = [key for key in wrong if key not in known]
            if unknown:
                raise ValueError(f"{where}: unknown feature keys {', '.join(unknown)}")
            reviews.append({"rater": rater or str(path), "source": source, "name": _text(row[0]),
                            "set": bool(_text(row[5])), "verdict": verdict, "wrong": wrong})
    return reviews


def summarize(reviews) -> dict[str, dict]:
    """Per source: the verdict shares on judged dishes, the pass, agreement on shared dishes and
    how often each feature was called wrong."""
    out = {}
    for source in sorted({r["source"] for r in reviews}):
        rows = [r for r in reviews if r["source"] == source]
        judged = [r for r in rows if r["verdict"] != UNKNOWN]
        counts = Counter(r["verdict"] for r in rows)
        share = {v: counts[v] / len(judged) if judged else None for v in VERDICTS[:3]}
        by_dish = defaultdict(list)
        for r in rows:
            by_dish[r["name"], r["set"]].append(r["verdict"])
        pairs = [a == b for verdicts in by_dish.values() if len(verdicts) > 1 for a, b in combinations(verdicts, 2)]
        out[source] = {
            "ratings": len(rows), "dishes": len(by_dish), "raters": len({r["rater"] for r in rows}),
            "judged": len(judged), "counts": {v: counts[v] for v in VERDICTS}, "share": share,
            "passed": bool(judged) and share[REASONABLE] >= PASS_REASONABLE - 1e-9
                      and share[UNREASONABLE] <= MAX_UNREASONABLE + 1e-9,
            "shared_dishes": sum(len(v) > 1 for v in by_dish.values()),
            "agreement": sum(pairs) / len(pairs) if pairs else None,
            "wrong": Counter(key for r in judged for key in r["wrong"]).most_common()}
    return out


def report(summary) -> str:
    lines = ["# Feature extraction: human review", "",
             f"Pass, per source, on judged dishes: {REASONABLE} >= {PASS_REASONABLE:.0%} and {UNREASONABLE} <= "
             f"{MAX_UNREASONABLE:.0%} (fixed before the review). A feature is wrong when its mean is {WRONG_GAP} or "
             "more off the rubric or its std plainly contradicts the recipe spread.", "",
             "| source | raters | dishes | ratings | judged | 합리적 | 일부 틀림 | 비합리적 | 판단 불가 | pass | "
             "agreement (shared dishes) |", "|" + "---|" * 11]
    for source, s in summary.items():
        rate = lambda v: "-" if s["share"][v] is None else f"{s['share'][v]:.1%}"
        agreement = "-" if s["agreement"] is None else f"{s['agreement']:.1%} ({s['shared_dishes']})"
        lines.append(f"| {source} | {s['raters']} | {s['dishes']} | {s['ratings']} | {s['judged']} | "
                     f"{rate(REASONABLE)} | {rate(PARTLY)} | {rate(UNREASONABLE)} | {s['counts'][UNKNOWN]} | "
                     f"{'yes' if s['passed'] else 'no'} | {agreement} |")
    for source, s in summary.items():
        lines += ["", f"**Features called wrong, {source}** (ratings)", "",
                  ", ".join(f"{key} {n}" for key, n in s["wrong"]) or "none"]
    return "\n".join(lines) + "\n"
