"""Human review of the extracted features (P21): people judge, value by value, whether the
LLM's mean and std of each feature of a dish are reasonable, instead of rating the dish
themselves (human.py).

export_feature_review writes one workbook per rater and source; report_feature_review
reads the filled copies. The sheet "검토" holds, from the row whose first cell is `id`:

    id, name, status, food_group, set, served, comment,
    <key>_mean, <key>_mean_wrong, <key>_std, <key>_std_wrong, ...

with the rater in B1 and the source in B2 ("cafeteria 2026-11-02", "general").

- status: 완료 once every value of the row is judged, 판단 불가 when the rater does not know
  the dish (left out). Rows without a status are not counted.
- <key>_<field>_wrong: X when that value is wrong, blank when it is reasonable. A mean is
  wrong when it is WRONG_GAP or more off what the rubric gives the dish; a std when it
  plainly contradicts how much the dish's recipes vary (0 for a dish made many ways).

Hard dishes are oversampled: a dish is hard with HARD_SIGNALS or more of these signals,
the quartiles taken over the pool sampled from: a set (its values combine several dishes);
no cuisine or several at MIDDLE[0] or more; the most means between MIDDLE (top quarter,
above zero); the largest mean std (top quarter, above zero). Half of a sample is hard (HARD_SHARE). The raters do not
see which; the hidden sheet "표본" holds each dish's stratum and the pool's size per stratum.

Accuracy is the share of reasonable values on the completed rows, for means and stds
separately, each stratum weighted by its share of the pool, so the oversampling does not
lower it. The pass bar,
per source and field, fixed before any review: overall accuracy >= PASS_OVERALL and every
feature's accuracy >= PASS_FEATURE. A source passes when both fields pass. Each rater
reviews different dishes (OVERLAP 0), as many hard ones as the others; with shared dishes
the report adds the raters' agreement on their values.
"""

from __future__ import annotations

import pathlib
import random
from collections import defaultdict
from itertools import combinations

import numpy as np
import openpyxl
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from menus.features.schema import FEATURE_VERSION, LLM_FEATURE_KEYS, RUBRIC

from .human import BOLD, BROKEN, FIELDS, FIXED, FONT, HEAD, INPUT, KEY_FONT, cell, write_rubric

SHEET = "검토"
SAMPLE_SHEET = "표본"
STATUSES = ("완료", "판단 불가")
DONE, UNKNOWN = STATUSES
WRONG = "X"
WRONG_GAP = 0.3
PASS_OVERALL = 0.95
PASS_FEATURE = 0.85
OVERLAP = 0
CUISINES = ("korean", "chinese", "japanese", "western", "southeast_asian", "indian")
MIDDLE = (0.3, 0.7)
TOP_QUARTER = 0.75
HARD_SIGNALS = 2
HARD_SHARE = 0.5
STRATA = ("hard", "other")
COLUMNS = ("id", "name", "status", "food_group", "set", "served", "comment")
LABELS = ("번호", "음식", "상태", "분류", "세트", "판매 예", "의견")
FIRST = 5
STD_FONT = Font(name="Arial", size=9, color="808080")


def value_columns() -> list[str]:
    return [f"{key}_{field}{suffix}" for key in LLM_FEATURE_KEYS for field in FIELDS for suffix in ("", "_wrong")]


def proportional_sample(ids, group_of, n, seed=0) -> list:
    """Up to `n` ids, each group given its share of `n` (largest remainder), drawn at random."""
    rng = random.Random(seed)
    groups = defaultdict(list)
    for item in sorted(ids):
        groups[group_of(item)].append(item)
    n = min(n, len(ids))
    quota = {group: n * len(members) / len(ids) for group, members in groups.items()}
    take = {group: int(q) for group, q in quota.items()}
    order = sorted(groups, key=lambda group: (take[group] - quota[group], rng.random()))
    for group in order[:n - sum(take.values())]:
        take[group] += 1
    return sorted(item for group in sorted(groups) for item in rng.sample(groups[group], take[group]))


def signals(dishes) -> dict[object, list[str]]:
    """{id: the dish's hardness signals}, the quartiles taken over `dishes` ({id: dish})."""
    def middle(dish):
        return sum(MIDDLE[0] <= (dish["features"].get(key) or 0) <= MIDDLE[1] for key in LLM_FEATURE_KEYS)

    def spread(dish):
        return float(np.mean([dish["feature_std"].get(key) or 0 for key in LLM_FEATURE_KEYS]))

    top_middle = np.quantile([middle(d) for d in dishes.values()], TOP_QUARTER)
    top_spread = np.quantile([spread(d) for d in dishes.values()], TOP_QUARTER)
    out = {}
    for pk, dish in dishes.items():
        cuisines = sum((dish["features"].get(key) or 0) >= MIDDLE[0] for key in CUISINES)
        hits = (("set", dish["is_set"]), ("cuisine", cuisines != 1), ("middle", 0 < middle(dish) >= top_middle),
                ("spread", 0 < spread(dish) >= top_spread))
        out[pk] = [name for name, hit in hits if hit]
    return out


def stratum(found) -> str:
    return STRATA[0] if len(found) >= HARD_SIGNALS else STRATA[1]


def oversample(ids, strata, group_of, n, seed=0) -> list:
    """Up to `n` ids, HARD_SHARE of them hard (as many as there are), each stratum sampled in proportion to its groups."""
    hard = [pk for pk in ids if strata[pk] == STRATA[0]]
    other = [pk for pk in ids if strata[pk] == STRATA[1]]
    n = min(n, len(ids))
    take = min(round(n * HARD_SHARE), len(hard))
    take = max(take, n - len(other))
    return sorted(proportional_sample(hard, group_of, take, seed) + proportional_sample(other, group_of, n - take, seed))


def assign(dishes, raters, overlap=OVERLAP, seed=0, stratum_of=None) -> dict[str, list]:
    """{rater: dishes}: `overlap` dishes for everyone, the rest split evenly (within each stratum
    of `stratum_of`), each list shuffled."""
    rng = random.Random(seed)
    dishes = sorted(dishes)
    rng.shuffle(dishes)
    shared, rest = dishes[:overlap], dishes[overlap:]
    if stratum_of:
        rest.sort(key=stratum_of)
    out = {}
    for index, rater in enumerate(raters):
        mine = shared + rest[index::len(raters)]
        rng.shuffle(mine)
        out[rater] = mine
    return out


def write(path, rater, source, dishes, population) -> None:
    """A review workbook: one row per dish ({"id", "name", "food_group", "is_set", "served", "features",
    "feature_std", "model", "signals"}), the LLM's values fixed and a wrong mark to fill beside each.
    `population`: {stratum: dishes in the pool}, for weighting."""
    book = openpyxl.Workbook()
    form = book.active
    form.title = SHEET
    models = ", ".join(sorted({d["model"] for d in dishes if d["model"]})) or "?"
    cell(form, 1, 1, "검토자", BOLD)
    cell(form, 1, 2, rater, fill=INPUT)
    cell(form, 2, 1, "출처", BOLD)
    cell(form, 2, 2, source, fill=FIXED)
    cell(form, 1, 3, f"값마다 틀렸으면 오른쪽 노란 칸에 {WRONG}, 맞으면 비워 둡니다. 한 행을 다 보면 상태에 '{DONE}'. "
                     "기준은 '안내'와 '루브릭' 시트에 있습니다.")
    cell(form, 2, 3, f"LLM 추출값 ({models}, feature {FEATURE_VERSION}, rubric {RUBRIC['prompt_version']}): "
                     "mean은 그 음식에서 그 특징이 얼마나 두드러지는지(0~1), std는 레시피·식당에 따른 차이.")
    for row in (1, 2):
        form.merge_cells(start_row=row, start_column=3, end_row=row, end_column=30)
    last = FIRST + len(dishes) - 1
    labels = {feature["key"]: feature["label_ko"] for feature in RUBRIC["features"]}
    for index, (column, label) in enumerate(zip(COLUMNS, LABELS), start=1):
        cell(form, 3, index, label, BOLD, HEAD)
        cell(form, 4, index, column, KEY_FONT, HEAD)
    start = len(COLUMNS) + 1
    for offset, key in enumerate(LLM_FEATURE_KEYS):
        column = start + 4 * offset
        cell(form, 3, column, f"{labels[key]} ({key})", BOLD, HEAD)
        form.merge_cells(start_row=3, start_column=column, end_row=3, end_column=column + 3)
    for index, key in enumerate(value_columns(), start=start):
        cell(form, 4, index, key, KEY_FONT, HEAD)
    for row, dish in enumerate(dishes, start=FIRST):
        fixed = [dish["id"], dish["name"], None, dish["food_group"], "세트" if dish["is_set"] else "",
                 "\n".join(dish["served"]), None]
        for index, value in enumerate(fixed, start=1):
            cell(form, row, index, value, fill=INPUT if index in (3, 7) else FIXED)
        for offset, key in enumerate(LLM_FEATURE_KEYS):
            column = start + 4 * offset
            cell(form, row, column, dish["features"].get(key)).number_format = "0.00"
            cell(form, row, column + 2, dish["feature_std"].get(key), STD_FONT).number_format = "0.00"
            for mark in (column + 1, column + 3):
                cell(form, row, mark, None, fill=INPUT)
    end = get_column_letter(start + len(value_columns()) - 1)
    status = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True,
                            showErrorMessage=True, errorTitle="상태", error="목록에서 고르세요.")
    marks = DataValidation(type="list", formula1=f'"{WRONG}"', allow_blank=True,
                           showErrorMessage=True, errorTitle="판정", error=f"틀렸으면 {WRONG}, 맞으면 비워 두세요.")
    form.add_data_validation(status)
    form.add_data_validation(marks)
    status.add(f"C{FIRST}:C{last}")
    for offset in range(2 * len(LLM_FEATURE_KEYS)):
        mark = get_column_letter(start + 2 * offset + 1)
        marks.add(f"{mark}{FIRST}:{mark}{last}")
        form.conditional_formatting.add(f"{mark}{FIRST}:{mark}{last}", FormulaRule(
            fill=BROKEN, formula=[f'{mark}{FIRST}="{WRONG}"']))
    form.conditional_formatting.add(f"C{FIRST}:C{last}", FormulaRule(
        fill=BROKEN, formula=[f'AND($C{FIRST}="",COUNTIF($H{FIRST}:${end}{FIRST},"{WRONG}")>0)']))
    for offset in range(len(LLM_FEATURE_KEYS)):
        mean = get_column_letter(start + 4 * offset)
        form.conditional_formatting.add(f"{mean}{FIRST}:{mean}{last}", ColorScaleRule(
            start_type="num", start_value=0, start_color="FFFFFF", end_type="num", end_value=1, end_color="5B9BD5"))
    for letter, width in zip("ABCDEFG", (6, 20, 9, 9, 5, 34, 22)):
        form.column_dimensions[letter].width = width
    for offset in range(len(value_columns())):
        form.column_dimensions[get_column_letter(start + offset)].width = 5 if offset % 2 == 0 else 3.5
    form.freeze_panes = f"D{FIRST}"
    _write_summary(book.create_sheet("요약"), last, start)
    _write_guide(book.create_sheet("안내"))
    write_rubric(book.create_sheet("루브릭"))
    _write_sample(book.create_sheet(SAMPLE_SHEET), dishes, population)
    book.save(path)


def _write_sample(sample, dishes, population) -> None:
    sample.sheet_state = "hidden"
    sample.append(["stratum", "pool"])
    for name in STRATA:
        sample.append([name, population.get(name, 0)])
    sample.append([])
    sample.append(["id", "stratum", "signals"])
    for dish in dishes:
        sample.append([dish["id"], stratum(dish["signals"]), ", ".join(dish["signals"])])


def _write_summary(summary, last, start) -> None:
    status = f"'{SHEET}'!$C${FIRST}:$C${last}"
    cell(summary, 1, 1, "이 파일의 결과 (전체 결과와 통과 여부는 report_feature_review)", BOLD)
    cell(summary, 2, 1, DONE)
    cell(summary, 2, 2, f'=COUNTIF({status},"{DONE}")')
    cell(summary, 3, 1, UNKNOWN)
    cell(summary, 3, 2, f'=COUNTIF({status},"{UNKNOWN}")')
    cell(summary, 4, 1, f"통과 기준 (mean, std 각각): 전체 정확도 ≥ {PASS_OVERALL:.0%}, feature마다 ≥ {PASS_FEATURE:.0%}", BOLD)
    for index, text in enumerate(("key", "이름", "mean X", "mean 정확도", "std X", "std 정확도"), start=1):
        cell(summary, 6, index, text, BOLD, HEAD)
    first = 7
    for row, key in enumerate(LLM_FEATURE_KEYS, start=first):
        cell(summary, row, 1, key)
        cell(summary, row, 2, next(f["label_ko"] for f in RUBRIC["features"] if f["key"] == key))
        for index, field in enumerate(FIELDS):
            mark = get_column_letter(start + 4 * (row - first) + 2 * index + 1)
            count = 3 + 2 * index
            cell(summary, row, count, f'=COUNTIFS({status},"{DONE}",\'{SHEET}\'!${mark}${FIRST}:${mark}${last},"{WRONG}")')
            cell(summary, row, count + 1, f'=IF($B$2=0,"",1-{get_column_letter(count)}{row}/$B$2)').number_format = "0.0%"
    total = first + len(LLM_FEATURE_KEYS)
    cell(summary, total, 1, "전체", BOLD)
    for count in (3, 5):
        letter = get_column_letter(count)
        cell(summary, total, count, f"=SUM({letter}{first}:{letter}{total - 1})")
        cell(summary, total, count + 1, f'=IF($B$2=0,"",1-{letter}{total}/($B$2*{len(LLM_FEATURE_KEYS)}))'
             ).number_format = "0.0%"
    for letter, width in zip("ABCDEF", (16, 12, 8, 11, 8, 11)):
        summary.column_dimensions[letter].width = width


def _write_guide(guide) -> None:
    lines = [
        ("Metchu! feature 검토", BOLD),
        ("LLM이 음식 이름으로 추출한 32개 feature의 mean과 std가 합리적인지, 값 하나하나 사람이 판단합니다. "
         "값을 새로 매기지 않고, 주어진 값이 그 음식에 맞는지만 봅니다.", FONT),
        ("", FONT), ("작성 순서", BOLD),
        ("1. '검토' 시트 B1의 이름을 확인합니다.", FONT),
        ("2. 음식마다 판매 예(식당·메뉴 줄)를 보고, 모르는 음식이면 레시피나 사진을 찾아봅니다. "
         f"그래도 모르면 상태에 '{UNKNOWN}'를 고르고 다음 음식으로 넘어갑니다.", FONT),
        ("3. 각 feature의 mean과 std를 '루브릭' 시트 기준과 비교합니다. 틀린 값이면 그 값 오른쪽 노란 칸에 "
         f"{WRONG}를 넣고, 맞으면 비워 둡니다.", FONT),
        (f"   mean이 틀림: 루브릭으로 보아 {WRONG_GAP} 이상 어긋남 (예: 짬뽕 spicy 0.10). 그보다 작은 차이는 맞는 것으로 봅니다.", FONT),
        ("   std가 틀림: 레시피·식당에 따른 차이와 분명히 맞지 않음 (예: 식당마다 크게 다른 음식인데 std 0, "
         "어디서나 같은 특징인데 std가 큼).", FONT),
        (f"4. 한 행의 64개 값을 다 봤으면 상태에 '{DONE}'를 고릅니다. 상태가 빈 행은 집계하지 않습니다.", FONT),
        ("5. 의견에는 눈에 띄게 틀린 값을 짧게 적습니다 (예: spicy 0.1 → 0.7). 선택 사항입니다.", FONT),
        ("6. 다른 검토자와 상의하지 않고, .xlsx 그대로 저장해 제출합니다.", FONT),
        ("", FONT), ("범례", BOLD),
    ]
    for row, (text, font) in enumerate(lines, start=1):
        cell(guide, row, 1, text, font)
    row = len(lines) + 1
    for text, fill in (("입력하는 칸", INPUT), ("수정하지 않는 칸", FIXED),
                       (f"{WRONG} 표시한 값 / {WRONG}가 있는데 상태가 빈 행", BROKEN)):
        cell(guide, row, 1, text, fill=fill)
        row += 1
    guide.column_dimensions["A"].width = 110


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def load(paths) -> list[dict]:
    """Every row with a status: {"rater", "source", "id", "name", "status", "wrong": {field: [keys]},
    "stratum", "population"}."""
    reviews = []
    for path in paths:
        if pathlib.Path(path).name.startswith("~$"):  # Excel's lock file of an open workbook
            continue
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sample = list(book[SAMPLE_SHEET].iter_rows(values_only=True))
        population = {row[0]: row[1] for row in sample[1:1 + len(STRATA)]}
        strata = {_text(row[0]): row[1] for row in sample[2 + len(STRATA):] if row and row[0] is not None}
        rows = list(book[SHEET].iter_rows(values_only=True))
        rater, source = _text(rows[0][1]), _text(rows[1][1])
        header = next(i for i, row in enumerate(rows) if _text(row[0]) == "id")
        column = {_text(name): index for index, name in enumerate(rows[header])}
        for number, row in enumerate(rows[header + 1:], start=header + 2):
            if not _text(row[column["name"]]):
                continue
            where = f"{path}, row {number}"
            wrong = {field: [] for field in FIELDS}
            for key in LLM_FEATURE_KEYS:
                for field in FIELDS:
                    mark = _text(row[column[f"{key}_{field}_wrong"]]).upper()
                    if mark not in ("", WRONG):
                        raise ValueError(f"{where}: {key}_{field}_wrong is {mark!r}; use {WRONG} or leave it blank")
                    if mark:
                        wrong[field].append(key)
            status = _text(row[column["status"]])
            if not status:
                if any(wrong.values()):
                    raise ValueError(f"{where}: values are marked {WRONG} but the status is blank")
                continue
            if status not in STATUSES:
                raise ValueError(f"{where}: status {status!r} is not one of {', '.join(STATUSES)}")
            reviews.append({"rater": rater or str(path), "source": source, "id": _text(row[column["id"]]),
                            "name": _text(row[column["name"]]), "status": status, "wrong": wrong,
                            "stratum": strata[_text(row[column["id"]])], "population": population})
    return reviews


def _accuracy(rows, field, keys) -> float:
    return 1 - sum(len(set(r["wrong"][field]) & set(keys)) for r in rows) / (len(rows) * len(keys))


def _weighted(by_stratum, field, keys) -> float | None:
    """The strata's accuracies weighted by their share of the pool (over the strata with completed rows)."""
    if not by_stratum:
        return None
    population = next(iter(by_stratum.values()))[0]["population"]
    total = sum(population[name] for name in by_stratum)
    return sum(population[name] / total * _accuracy(rows, field, keys) for name, rows in by_stratum.items())


def summarize(reviews) -> dict[str, dict]:
    """Per source: accuracy of the means and stds overall and per feature (weighted over the strata),
    the pass, accuracy per stratum, and the raters' agreement on the values of shared dishes."""
    out = {}
    for source in sorted({r["source"] for r in reviews}):
        rows = [r for r in reviews if r["source"] == source]
        done = [r for r in rows if r["status"] == DONE]
        by_stratum = defaultdict(list)
        for r in done:
            by_stratum[r["stratum"]].append(r)
        fields = {}
        for field in FIELDS:
            feature = {key: _weighted(by_stratum, field, [key]) for key in LLM_FEATURE_KEYS}
            overall = _weighted(by_stratum, field, LLM_FEATURE_KEYS)
            fields[field] = {"overall": overall, "feature": feature,
                             "passed": bool(done) and overall >= PASS_OVERALL - 1e-9
                                       and min(feature.values()) >= PASS_FEATURE - 1e-9}
        by_dish = defaultdict(list)
        for r in done:
            by_dish[r["id"]].append({(field, key) for field in FIELDS for key in r["wrong"][field]})
        same = marked = both = 0
        pairs = [(a, b) for marks in by_dish.values() for a, b in combinations(marks, 2)]
        for a, b in pairs:
            same += 2 * len(LLM_FEATURE_KEYS) - len(a ^ b)
            marked += len(a | b)
            both += len(a & b)
        out[source] = {
            "ratings": len(rows), "dishes": len({r["id"] for r in rows}), "raters": len({r["rater"] for r in rows}),
            "done": len(done), "unknown": len(rows) - len(done), "fields": fields,
            "strata": {name: {"done": len(by_stratum[name]), "pool": rows[0]["population"][name],
                              **{field: _accuracy(by_stratum[name], field, LLM_FEATURE_KEYS) if by_stratum[name]
                                 else None for field in FIELDS}} for name in STRATA},
            "passed": all(f["passed"] for f in fields.values()),
            "shared_dishes": sum(len(marks) > 1 for marks in by_dish.values()),
            "agreement": same / (len(pairs) * 2 * len(LLM_FEATURE_KEYS)) if pairs else None,
            "wrong_agreement": both / marked if marked else None}
    return out


def report(summary) -> str:
    rate = lambda value: "-" if value is None else f"{value:.1%}"
    lines = ["# Feature extraction: human review", "",
             f"Accuracy: the share of values judged reasonable on completed rows, the hard and other dishes "
             f"weighted by their share of the pool (hard dishes are half of each sample). Pass, per source and for means and "
             f"stds each: overall >= {PASS_OVERALL:.0%} and every feature >= {PASS_FEATURE:.0%} (fixed before the "
             f"review). A mean is wrong when it is {WRONG_GAP} or more off the rubric; a std when it plainly "
             "contradicts the recipe spread. Agreement: the share of values two raters of a shared dish judged alike; "
             f"{WRONG} agreement: the same among values either of them marked {WRONG}.", "",
             "| source | raters | dishes | completed | unknown | mean | worst mean | std | worst std | pass | "
             f"agreement (shared dishes) | {WRONG} agreement |", "|" + "---|" * 12]
    for source, s in summary.items():
        cells = []
        for field in FIELDS:
            f = s["fields"][field]
            worst = min(LLM_FEATURE_KEYS, key=lambda key: f["feature"][key]) if s["done"] else None
            cells += [rate(f["overall"]), f"{worst} {rate(f['feature'][worst])}" if worst else "-"]
        agreement = "-" if s["agreement"] is None else f"{rate(s['agreement'])} ({s['shared_dishes']})"
        lines.append(f"| {source} | {s['raters']} | {s['dishes']} | {s['done']} | {s['unknown']} | "
                     + " | ".join(cells) + f" | {'yes' if s['passed'] else 'no'} | {agreement} | "
                     f"{rate(s['wrong_agreement'])} |")
    lines += ["", f"**By stratum** (hard: {HARD_SIGNALS}+ signals, half of each sample; accuracy unweighted)", "",
              "| source | stratum | pool | completed | mean | std |", "|---|---|---|---|---|---|"]
    for source, s in summary.items():
        lines += [f"| {source} | {name} | {g['pool']} | {g['done']} | {rate(g['mean'])} | {rate(g['std'])} |"
                  for name, g in s["strata"].items()]
    labels = {feature["key"]: feature["label_ko"] for feature in RUBRIC["features"]}
    for source, s in summary.items():
        lines += ["", f"**Accuracy per feature, {source}**", "", "| key | 이름 | mean | std |", "|---|---|---|---|"]
        lines += [f"| {key} | {labels[key]} | {rate(s['fields']['mean']['feature'][key])} | "
                  f"{rate(s['fields']['std']['feature'][key])} |" for key in LLM_FEATURE_KEYS]
    return "\n".join(lines) + "\n"
