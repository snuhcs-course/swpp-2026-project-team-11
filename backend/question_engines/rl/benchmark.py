"""Reproduce v20 catalogue preparation and first-decision latency on one CPU thread."""
import gc
import json
import statistics
import time
from pathlib import Path

import numpy as np

from .policy import FEATURE_KEYS, prepare


def main():
    root = Path(__file__).resolve().parents[3]
    dataset = root / "engine_benchmark_results/2026-10-20/scenarios.json"
    source = json.loads(dataset.read_text(encoding="utf-8"))["menus"]["2026-10-20/LU"]["candidates"]
    for size in (500, 2000, 4000, 12000):
        rng = np.random.default_rng(2312020)
        rows = []
        for index in range(size):
            food = source[index % len(source)]
            means = {key: float(np.clip(value + rng.normal(0, .035), 0, 1))
                     for key, value in food["features"].items()}
            rows.append({"features": means, "feature_std": food["feature_std"]})
        answers = np.full(len(FEATURE_KEYS), -1, dtype=np.int64)
        rejected = np.zeros(size, dtype=bool)
        elapsed = []
        for _ in range(7):
            gc.collect()
            start = time.perf_counter_ns()
            world = prepare(rows)
            world.decide(answers, rejected)
            elapsed.append((time.perf_counter_ns() - start) / 1e6)
            numeric_bytes = sum(array.nbytes for array in vars(world).values() if isinstance(array, np.ndarray))
            del world  # Each timed iteration binds a fresh catalogue.
        print(f"{size:>5} dishes: {statistics.median(elapsed):.1f} ms, {numeric_bytes / 2**20:.1f} MiB")


if __name__ == "__main__":
    main()
