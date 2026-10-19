# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Distribution: how each feature's means spread over the menu, and collisions.

Per feature: the share of dishes at <= LOW, in between and >= HIGH, the mean std,
and a histogram of means (11 bins, 0.0 to 1.0). A collision is two dishes whose
means differ by at most COLLISION per feature on average: no question can tell
them apart, so the engine can only guess between them.
"""

from __future__ import annotations

import numpy as np

from . import HIGH, LOW

COLLISION = 0.05


def matrix(runset) -> tuple[list[str], np.ndarray, np.ndarray]:
    names = runset.menu_names()
    return (names, np.array([runset.mean(name) for name in names]),
            np.array([runset.std(name) for name in names]))


def evaluate(runset) -> dict:
    names, means, stds = matrix(runset)
    if len(names) < 2:
        return {"title": "2. Distribution", "skipped": "Fewer than two dishes."}
    rows = []
    for j, key in enumerate(runset.keys):
        column = means[:, j]
        low, high = float((column <= LOW).mean()), float((column >= HIGH).mean())
        histogram = np.bincount(np.rint(column * 10).astype(int), minlength=11)[:11]
        rows.append([key, round(float(column.mean()), 2), round(low, 2), round(1 - low - high, 2),
                     round(high, 2), round(float(stds[:, j].mean()), 3), " ".join(map(str, histogram))])
    gap = np.abs(means[:, None, :] - means[None, :, :]).mean(axis=2)
    collisions = sorted(([names[a], names[b], round(float(gap[a, b]), 3)]
                         for a in range(len(names)) for b in range(a + 1, len(names)) if gap[a, b] <= COLLISION),
                        key=lambda row: row[2])
    return {"title": "2. Distribution",
            "lines": [f"{len(names)} dishes, {len(runset.keys)} features.",
                      f"Collisions (mean gap <= {COLLISION}): {len(collisions)} pairs."],
            "tables": [("distribution.csv", "Per feature (histogram: dishes at 0.0, 0.1, ... 1.0)",
                        ["feature", "mean", "low", "mid", "high", "mean std", "histogram"], rows, len(rows)),
                       ("distribution_collisions.csv", "Collisions", ["dish_a", "dish_b", "mean_gap"], collisions, 10)]}


def plot(runset, path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names, means, _ = matrix(runset)
    columns = 6
    rows = -(-len(runset.keys) // columns)
    figure, axes = plt.subplots(rows, columns, figsize=(3 * columns, 2.2 * rows), squeeze=False)
    edges = np.arange(-0.05, 1.1, 0.1)
    for axis, key, column in zip(axes.flat, runset.keys, means.T):
        axis.hist(column, bins=edges, color="#4c72b0")
        axis.set_title(key, fontsize=10)
        axis.set_xticks([0, 0.5, 1])
        axis.set_ylim(0, len(names))
    for axis in axes.flat[len(runset.keys):]:
        axis.axis("off")
    figure.suptitle(f"Feature means over {len(names)} dishes")
    figure.tight_layout()
    figure.savefig(path, dpi=110)
    plt.close(figure)
