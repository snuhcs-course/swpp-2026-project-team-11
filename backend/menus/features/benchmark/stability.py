# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Stability: does a dish get the same numbers when it is extracted again?

Reported per condition (runs.py): `repeat` shows the model's own randomness,
`shuffle_foods` adds the effect of batch neighbours, `shuffle_features` the
effect of the rubric's order. Per condition:
- mean SD: standard deviation over runs of each (dish, feature) mean, averaged; also for stds
- flips: cells whose mean was <= LOW in one run and >= HIGH in another
and how far the conditions' averaged means are apart. Each dish counts all of its
runs. An SD from two runs is noisy, so conditions with different run counts are
not compared closely (the report says so).
"""

from __future__ import annotations

import numpy as np

from . import HIGH, LOW


def evaluate(runset) -> dict:
    repeats = {condition: dishes for condition, dishes in runset.repeats().items() if dishes}
    if not repeats:
        return {"title": "3. Stability", "skipped": "No dish was extracted twice under one condition."}
    lines, by_feature, cells, averaged, run_counts = [], [], [], {}, {}
    for condition, dishes in sorted(repeats.items()):
        names = sorted(dishes)
        per_dish = [(np.array([m for m, _ in dishes[n]]), np.array([s for _, s in dishes[n]])) for n in names]
        averaged[condition] = {n: means.mean(axis=0) for n, (means, _) in zip(names, per_dish)}
        sd = np.array([means.std(axis=0, ddof=1) for means, _ in per_dish])  # dish x feature
        sd_std = np.array([stds.std(axis=0, ddof=1) for _, stds in per_dish])
        low = np.array([means.min(axis=0) for means, _ in per_dish])
        high = np.array([means.max(axis=0) for means, _ in per_dish])
        flips = (low <= LOW) & (high >= HIGH)
        counts = sorted({len(dishes[n]) for n in names})
        run_counts[condition] = counts
        runs = str(counts[0]) if len(counts) == 1 else f"{counts[0]}-{counts[-1]}"
        lines.append(f"`{condition}`: {len(names)} dishes x {runs} runs; mean SD of means {sd.mean():.3f} "
                     f"(largest {sd.max():.2f}), of stds {sd_std.mean():.3f}; flips {flips.mean():.2%}")
        for j, key in enumerate(runset.keys):
            by_feature.append([condition, key, round(float(sd[:, j].mean()), 3), round(float(sd_std[:, j].mean()), 3),
                               round(float(flips[:, j].mean()), 4)])
        for i, j in zip(*np.nonzero(high - low >= 0.2)):
            cells.append([condition, names[i], runset.keys[j], float(low[i, j]), float(high[i, j]),
                          "flip" if flips[i, j] else ""])
    if len({tuple(c) for c in run_counts.values()}) > 1:
        lines.append("The conditions have different run counts (" + ", ".join(
            f"{c} {'/'.join(map(str, n))}" for c, n in run_counts.items()) + "). An SD from two runs is noisy, so "
            "small differences between conditions are not meaningful.")
    conditions = sorted(averaged)
    for a, first in enumerate(conditions):
        for second in conditions[a + 1:]:
            shared = sorted(averaged[first].keys() & averaged[second].keys())
            if shared:
                gap = np.mean([np.abs(averaged[first][n] - averaged[second][n]) for n in shared])
                lines.append(f"`{first}` vs `{second}`: averaged means of {len(shared)} shared dishes "
                             f"differ by {gap:.3f} per feature")
    cells.sort(key=lambda row: row[3] - row[4])
    return {"title": "3. Stability", "lines": lines, "tables": [
        ("stability_by_feature.csv", "Per feature",
         ["condition", "feature", "mean_sd_of_means", "mean_sd_of_stds", "flip_rate"], by_feature, 0),
        ("stability_unstable_cells.csv", "Least stable (dish, feature) cells",
         ["condition", "dish", "feature", "lowest mean", "highest mean", "flip"], cells, 15)]}
