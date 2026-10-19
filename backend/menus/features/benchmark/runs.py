# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Stored extraction runs: one JSON line per (run, dish).

    {"run": "shuffle_foods-0", "condition": "shuffle_foods", "source": "variant",
     "name": "짬뽕", "group": "학생회관식당", "means": {"spicy": 0.6, ...},
     "stds": {"spicy": 0.15, ...}, "model": "google:gemini-3.5-flash", "prompt_hash": "..."}

A run tags every dish once. `condition` says how it differs from the others:
  - repeat:           the same batches and prompt every time (the model's own randomness)
  - shuffle_foods:    new batch neighbours in every run
  - shuffle_features: the rubric's features in a new order in every run
  - stored:           copied from the database, no LLM call
`source` is the kind of dish (menu_set.py): variant, invariant (also a triplet dish
in the fixed-menu catalog), suite (named only by the triplet file and not in the
catalog, e.g. 케이크) or menu (not split into the two kinds).
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import random
from collections import defaultdict
from dataclasses import asdict, dataclass

import numpy as np

from menus.features.schema import LLM_FEATURE_KEYS

CONDITIONS = ("repeat", "shuffle_foods", "shuffle_features")
STORED = "stored"
VARIANT, INVARIANT, SUITE, MENU = "variant", "invariant", "suite", "menu"
MENU_SOURCES = (VARIANT, INVARIANT, MENU)


@dataclass(frozen=True)
class Record:
    run: str
    condition: str
    source: str
    name: str
    means: dict
    stds: dict
    group: str = ""
    model: str = ""
    prompt_hash: str = ""


def load(path) -> list[Record]:
    lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    return [Record(**json.loads(line)) for line in lines if line.strip()]


def append(path, records) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:12]


class RunSet:
    """Read-only views over records with one key set (see integrity.py for checking them)."""

    def __init__(self, records):
        self.records = list(records)
        if not self.records:
            raise ValueError("No records to benchmark.")
        self.keys = tuple(self.records[0].means)
        if any(set(r.means) != set(self.keys) or set(r.stds) != set(self.keys) for r in self.records):
            raise ValueError("Records with different feature keys; keep each key set in its own runs file.")
        self._by_name = defaultdict(list)
        for record in self.records:
            self._by_name[record.name].append(record)

    def vectors(self, record) -> tuple[np.ndarray, np.ndarray]:
        return (np.array([record.means[k] for k in self.keys], dtype=float),
                np.array([record.stds[k] for k in self.keys], dtype=float))

    def mean(self, name) -> np.ndarray | None:
        """The dish's means averaged over every stored run, or None when it was never tagged."""
        records = self._by_name.get(name)
        return np.mean([self.vectors(r)[0] for r in records], axis=0) if records else None

    def std(self, name) -> np.ndarray | None:
        records = self._by_name.get(name)
        return np.mean([self.vectors(r)[1] for r in records], axis=0) if records else None

    def names(self, sources=None) -> list[str]:
        return sorted(name for name, records in self._by_name.items()
                      if not sources or any(r.source in sources for r in records))

    def menu_names(self) -> list[str]:
        """Menu dishes, or every dish when the file holds no menu dish."""
        return self.names(MENU_SOURCES) or self.names()

    def group(self, name) -> str:
        return self._by_name[name][0].group

    def segments(self) -> list[str]:
        """The kinds of menu dish present, variant first."""
        present = {record.source for record in self.records}
        return [source for source in (VARIANT, INVARIANT) if source in present]

    def subset(self, sources) -> RunSet | None:
        records = [record for record in self.records if record.source in sources]
        return RunSet(records) if records else None

    def repeats(self) -> dict[str, dict[str, list[tuple[np.ndarray, np.ndarray]]]]:
        """{condition: {dish: [(means, stds) per run]}} for dishes tagged at least twice."""
        grouped = defaultdict(lambda: defaultdict(dict))
        for record in self.records:
            grouped[record.condition][record.name][record.run] = self.vectors(record)
        return {condition: {name: list(runs.values()) for name, runs in names.items() if len(runs) > 1}
                for condition, names in grouped.items()}


def provenance(records) -> dict[str, list[str]]:
    """The models, prompts and conditions behind `records`."""
    return {field: sorted({getattr(r, field) for r in records} - {""})
            for field in ("model", "prompt_hash", "condition")}


def stratified_sample(names, group_of, n, seed=0) -> list[str]:
    """Up to `n` names, taken round-robin from each group so small groups are not lost."""
    rng = random.Random(seed)
    groups = defaultdict(list)
    for name in sorted(names):
        groups[group_of(name)].append(name)
    for members in groups.values():
        rng.shuffle(members)
    picked, order = [], sorted(groups)
    while len(picked) < min(n, len(names)):
        for group in order:
            if groups[group] and len(picked) < n:
                picked.append(groups[group].pop())
    return sorted(picked)


def plan(names, condition, repeats, seed=0) -> list[tuple[str, list[str], tuple[str, ...]]]:
    """[(run id, dish names in batch order, rubric feature order)] for `repeats` runs."""
    if condition not in CONDITIONS:
        raise ValueError(f"condition must be one of {', '.join(CONDITIONS)}")
    base = sorted(names)
    random.Random(seed).shuffle(base)
    runs = []
    for index in range(repeats):
        order, features = list(base), list(LLM_FEATURE_KEYS)
        if condition == "shuffle_foods":
            random.Random(f"{seed}-foods-{index}").shuffle(order)
        elif condition == "shuffle_features":
            random.Random(f"{seed}-features-{index}").shuffle(features)
        runs.append((f"{condition}-{index}", order, tuple(features)))
    return runs


def calls(names, batch_size) -> int:
    return math.ceil(len(names) / batch_size)
