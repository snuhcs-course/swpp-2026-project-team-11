# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Paired tests for "is the LLM engine better than the decision tree on the same scenarios?".

Both engines play the same scenarios, so each scenario gives one pair. Each
engine's repeats are averaged per scenario first, so a scenario counts once.

- bootstrap_ci:  confidence interval of the mean difference, resampling scenarios
- wilcoxon:      signed-rank test on the per-scenario differences (normal approximation
                 with tie correction; zero differences are dropped)
- mcnemar:       exact test on binary outcomes (each engine by majority over its repeats)
- weighted_kappa: agreement between people's and the simulated user's answers
"""

from __future__ import annotations

import math
import random
import statistics

import numpy as np


def bootstrap_ci(values, level=0.95, rounds=2000, seed=0) -> tuple[float, float]:
    values = list(values)
    if not values:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(rounds))
    low = means[int((1 - level) / 2 * rounds)]
    high = means[min(rounds - 1, int((1 + level) / 2 * rounds))]
    return low, high


def _normal_two_sided(z) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def wilcoxon(differences) -> float:
    """Two-sided p-value of the signed-rank test (nan with fewer than 5 nonzero pairs)."""
    nonzero = [d for d in differences if d != 0]
    n = len(nonzero)
    if n < 5:
        return float("nan")
    ordered = sorted(nonzero, key=abs)
    ranks, i = [0.0] * n, 0
    ties = 0.0
    while i < n:
        j = i
        while j + 1 < n and abs(ordered[j + 1]) == abs(ordered[i]):
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        t = j - i + 1
        ties += t ** 3 - t
        i = j + 1
    positive = sum(rank for rank, d in zip(ranks, ordered) if d > 0)
    mean = n * (n + 1) / 4
    variance = n * (n + 1) * (2 * n + 1) / 24 - ties / 48
    return _normal_two_sided((positive - mean) / math.sqrt(variance)) if variance > 0 else float("nan")


def mcnemar(only_first: int, only_second: int) -> float:
    """Exact two-sided p-value from the discordant pairs."""
    n = only_first + only_second
    if n == 0:
        return 1.0
    k = min(only_first, only_second)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def weighted_kappa(a, b) -> float:
    """Linearly weighted Cohen's kappa for two lists of levels 0..2 (nan when undefined)."""
    if not len(a):
        return float("nan")
    observed = np.zeros((3, 3))
    for x, y in zip(a, b):
        observed[x, y] += 1
    observed /= observed.sum()
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0))
    weights = np.abs(np.subtract.outer(np.arange(3), np.arange(3))) / 2
    disagreement = (weights * expected).sum()
    return float(1 - (weights * observed).sum() / disagreement) if disagreement else float("nan")
