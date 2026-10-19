# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Integrity: the one pass/fail section. Every record must have the right keys and bounded values.

- keys: an extraction run measures the 32 rubric features; a food copied from the
  database (stored) also carries meal_variety, so 33
- bounds: 0 <= mean <= 1, 0 <= std <= 0.5, and std² <= mean * (1 - mean), the
  largest variance a measurement in [0, 1] with that mean can have

Records that fail are listed and left out of every other section.
"""

from __future__ import annotations

import math

from menus.features.schema import FEATURE_KEYS, LLM_FEATURE_KEYS

from .runs import STORED

TOLERANCE = 1e-9


def problems(record) -> list[str]:
    expected = set(FEATURE_KEYS if record.condition == STORED else LLM_FEATURE_KEYS)
    found = []
    for label, values in (("means", record.means), ("stds", record.stds)):
        if set(values) != expected:
            missing, extra = sorted(expected - set(values)), sorted(set(values) - expected)
            found.append(f"{label} keys: missing {missing or '-'}, extra {extra or '-'}")
    for key in sorted(expected & set(record.means) & set(record.stds)):
        mean, std = record.means[key], record.stds[key]
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (mean, std)):
            found.append(f"{key}: not a finite number")
        elif not (0 <= mean <= 1 and 0 <= std <= 0.5):
            found.append(f"{key}: mean {mean} or std {std} out of range")
        elif std * std > mean * (1 - mean) + TOLERANCE:
            found.append(f"{key}: std² {std * std:.4f} > mean(1-mean) {mean * (1 - mean):.4f}")
    return found


def evaluate(records) -> tuple[dict, list]:
    """(the report section, the records that passed)."""
    rows, valid = [], []
    for record in records:
        found = problems(record)
        rows += [[record.run, record.name, problem] for problem in found]
        if not found:
            valid.append(record)
    bad = len(records) - len(valid)
    lines = [f"{len(records)} records, {bad} with problems; those are left out of the other sections."]
    return {"title": "1. Integrity", "lines": lines,
            "checks": [("records with 33/32 keys and bounded values", f"{len(valid)}/{len(records)}",
                        "all", bad == 0)],
            "tables": [("integrity_problems.csv", "Problems", ["run", "dish", "problem"], rows, 20)]}, valid
