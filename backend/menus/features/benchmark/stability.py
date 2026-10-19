# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Stability: does a dish get the same numbers when it is extracted again?

Reported per condition (runs.py): `repeat` shows the model's own randomness,
`shuffle_foods` adds the effect of batch neighbours, `shuffle_features` the
effect of the rubric's order. Per condition:
- mean SD: standard deviation over runs of each (dish, feature) mean, averaged; also for stds
- flips: cells whose mean was <= LOW in one run and >= HIGH in another
and how far the conditions' averaged means are apart.
"""

from __future__ import annotations

import numpy as np

from . import HIGH, LOW


def evaluate(runset) -> dict:
    repeats = {condition: dishes for condition, dishes in runset.repeats().items() if dishes}
    if not repeats:
        return {"title": "3. Stability", "skipped": "No dish was extracted twice under one condition."}
    lines, by_feature, cells, averaged = [], [], [], {}
    for condition, dishes in sorted(repeats.items()):
        names = sorted(dishes)
        runs = min(len(v) for v in dishes.values())
        means = np.array([[dishes[n][i][0] for i in range(runs)] for n in names])  # dish x run x feature
        stds = np.array([[dishes[n][i][1] for i in range(runs)] for n in names])
        averaged[condition] = {n: means[i].mean(axis=0) for i, n in enumerate(names)}
        sd, sd_std = means.std(axis=1, ddof=1), stds.std(axis=1, ddof=1)
        low, high = means.min(axis=1), means.max(axis=1)
        flips = (low <= LOW) & (high >= HIGH)
        lines.append(f"`{condition}`: {len(names)} dishes x {runs} runs; mean SD of means {sd.mean():.3f} "
                     f"(largest {sd.max():.2f}), of stds {sd_std.mean():.3f}; flips {flips.mean():.2%}")
        for j, key in enumerate(runset.keys):
            by_feature.append([condition, key, round(float(sd[:, j].mean()), 3), round(float(sd_std[:, j].mean()), 3),
                               round(float(flips[:, j].mean()), 4)])
        for i, j in zip(*np.nonzero(high - low >= 0.2)):
            cells.append([condition, names[i], runset.keys[j], float(low[i, j]), float(high[i, j]),
                          "flip" if flips[i, j] else ""])
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
