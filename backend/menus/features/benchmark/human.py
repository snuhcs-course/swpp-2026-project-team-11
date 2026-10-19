# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Human reference ratings: raters score dishes with the extractor's rubric.

The form (export_feature_rating_form) is one CSV per rater:

    name, rater, recipe_notes, spicy_mean, spicy_std, sweet_mean, sweet_std, ...

- `<key>_mean`, `<key>_std`: 0 to 1, at most two decimals, std² <= mean * (1 - mean);
  the same rules as the extractor's answer (menus/features/instructions.txt)
- `recipe_notes`: the recipes or serving examples looked at before judging the stds
- a blank cell is skipped; a header may carry a label after a colon ("spicy_mean: 매운맛 평균")
- without a `rater` column, the file name is the rater

Comparison, on the dishes and features both raters (or the LLM and a rater) scored:
- rater agreement: mean absolute difference between two raters, averaged over rater pairs
- LLM vs raters: mean absolute difference between the LLM and each rater, averaged over raters.
  Same scale, so a ratio near 1 means the LLM is as far from people as people are from each other.
- Spearman correlation of the LLM's means with the raters' average
Means and stds are compared separately.
"""

from __future__ import annotations

import csv
import math
import pathlib
from collections import defaultdict
from itertools import combinations

import numpy as np

from menus.features.schema import LLM_FEATURE_KEYS, RUBRIC

FIELDS = ("mean", "std")


def _number(text, where):
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"{where}: {text!r} is not a number") from None
    if not math.isfinite(value) or abs(value - round(value, 2)) > 1e-9:
        raise ValueError(f"{where}: {text!r} must be a number with at most two decimals")
    return value


def load(paths) -> dict[str, dict[str, dict]]:
    """{rater: {dish: {"mean": {key: value}, "std": {key: value}, "notes": str}}}."""
    ratings = defaultdict(dict)
    for path in map(pathlib.Path, paths):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for line, row in enumerate(csv.DictReader(f), start=2):
                row = {(key or "").split(":")[0].strip(): (value or "").strip() for key, value in row.items()}
                name, rater = row.pop("name", ""), row.pop("rater", "") or path.stem
                notes = row.pop("recipe_notes", "")
                if not name:
                    continue
                entry = {"mean": {}, "std": {}, "notes": notes}
                for column, text in row.items():
                    key, _, field = column.rpartition("_")
                    if key not in LLM_FEATURE_KEYS or field not in FIELDS:
                        raise ValueError(f"{path.name}: unknown column {column!r}")
                    if text:
                        entry[field][key] = _number(text, f"{path.name} line {line}, {column}")
                for key in entry["mean"].keys() & entry["std"].keys():
                    mean, std = entry["mean"][key], entry["std"][key]
                    if not (0 <= mean <= 1 and 0 <= std <= 0.5) or std * std > mean * (1 - mean) + 1e-9:
                        raise ValueError(f"{path.name} line {line}, {key}: mean {mean} / std {std} breaks "
                                         "0 <= mean <= 1, 0 <= std <= 0.5 or std² <= mean(1 - mean)")
                ratings[rater][name] = entry
    return dict(ratings)


def reference(ratings) -> dict[str, tuple[dict, dict]]:
    """{dish: (means, stds)} averaged over raters, for dishes with every feature rated."""
    result = {}
    for name in sorted({name for dishes in ratings.values() for name in dishes}):
        entries = [dishes[name] for dishes in ratings.values() if name in dishes]
        averaged = []
        for field in FIELDS:
            values = {key: [e[field][key] for e in entries if key in e[field]] for key in LLM_FEATURE_KEYS}
            if not all(values.values()):
                break
            averaged.append({key: float(np.mean(v)) for key, v in values.items()})
        else:
            result[name] = tuple(averaged)
    return result


def spearman(a, b) -> float:
    def ranks(values):
        values = np.asarray(values, dtype=float)
        result = np.empty(len(values))
        result[values.argsort(kind="stable")] = np.arange(len(values))
        for value in np.unique(values):  # ties share their average rank
            result[values == value] = result[values == value].mean()
        return result
    if len(a) < 3 or len(set(a)) < 2 or len(set(b)) < 2:
        return float("nan")
    return float(np.corrcoef(ranks(a), ranks(b))[0, 1])


def _mean(values) -> float:
    return float(np.mean(values)) if values else float("nan")


def compare(runset, ratings, field) -> tuple[list, dict]:
    """Per-feature rows and overall numbers for `field` ("mean" or "std")."""
    raters = sorted(ratings)
    index = {key: i for i, key in enumerate(runset.keys)}
    llm = runset.mean if field == "mean" else runset.std
    rows, pooled = [], defaultdict(list)
    for key in LLM_FEATURE_KEYS:
        if key not in index:
            continue
        between = [abs(ratings[a][n][field][key] - ratings[b][n][field][key]) for a, b in combinations(raters, 2)
                   for n in ratings[a].keys() & ratings[b].keys()
                   if key in ratings[a][n][field] and key in ratings[b][n][field]]
        against, model, people = [], [], []
        for name in sorted({n for r in raters for n in ratings[r]}):
            values = [ratings[r][name][field][key] for r in raters if key in ratings[r].get(name, {}).get(field, {})]
            vector = llm(name)
            if values and vector is not None:
                against += [abs(vector[index[key]] - v) for v in values]
                model.append(float(vector[index[key]]))
                people.append(float(np.mean(values)))
        pooled["between"] += between
        pooled["against"] += against
        rater_gap, llm_gap = _mean(between), _mean(against)
        rows.append([key, len(model), round(rater_gap, 3), round(llm_gap, 3),
                     round(llm_gap / rater_gap, 2) if rater_gap > 0 else "", round(spearman(model, people), 2)])
    overall = {"raters": _mean(pooled["between"]), "llm": _mean(pooled["against"])}
    return rows, overall


def evaluate(runset, ratings) -> dict:
    title = "4. Human reference"
    if not ratings:
        return {"title": title, "skipped": "No rating file. Make the form with export_feature_rating_form "
                "and pass the filled copies with --ratings."}
    rated = {name for dishes in ratings.values() for name in dishes}
    shared = sorted(n for n in rated if runset.mean(n) is not None)
    if not shared:
        return {"title": title, "skipped": "None of the rated dishes are in the runs file."}
    lines = [f"{len(shared)} dishes rated by {len(ratings)} rater(s): {', '.join(sorted(ratings))}."]
    tables = []
    for field in FIELDS:
        rows, overall = compare(runset, ratings, field)
        ratio = overall["llm"] / overall["raters"] if overall["raters"] > 0 else float("nan")
        lines.append(f"{field}: LLM vs raters {overall['llm']:.3f}, rater vs rater "
                     + (f"{overall['raters']:.3f} (ratio {ratio:.2f})" if not math.isnan(overall["raters"])
                        else "- (one rater: no agreement to compare with)"))
        tables.append((f"human_{field}.csv", f"Per feature, {field}s",
                       ["feature", "dishes", "rater vs rater", "LLM vs raters", "ratio", "Spearman"], rows, len(rows)))
    return {"title": title, "lines": lines, "tables": tables}


def write_form(path, names) -> None:
    """A blank rating form: one row per dish, a mean and a std column per rubric feature."""
    labels = {feature["key"]: feature["label_ko"] for feature in RUBRIC["features"]}
    header = ["name", "rater", "recipe_notes"]
    for key in LLM_FEATURE_KEYS:
        header += [f"{key}_mean: {labels[key]} 평균", f"{key}_std: {labels[key]} 표준편차"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for name in names:
            writer.writerow([name] + [""] * (len(header) - 1))
