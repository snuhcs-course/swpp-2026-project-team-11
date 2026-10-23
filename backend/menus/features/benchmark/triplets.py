# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Similarity triplets: the anchor must be closer to `near` than to `far`.

A triplet file is a JSON list or a CSV with these fields:

    anchor, near, far, kind, source, note

- kind: `close` when `near` and `far` are both close alternatives to the anchor
  (치즈버거 / 더블치즈버거 / 치킨버거), `distinct` when `far` is clearly another dish
- source: `ai` (drafted by an LLM, to be checked by a person) or `human`
- note: optional

Distance is the mean absolute difference of the means; the pass rate under cosine
distance is reported next to it. data/triplets.json is an AI draft.
"""

from __future__ import annotations

import csv
import json
import pathlib
from collections import defaultdict

import numpy as np

PATH = pathlib.Path(__file__).parent / "data" / "triplets.json"
KINDS = ("close", "distinct")
SOURCES = ("ai", "human")
FIELDS = ("anchor", "near", "far", "kind", "source")


def load(path=None) -> list[dict]:
    path = pathlib.Path(path or PATH)
    if path.suffix == ".csv":
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    else:
        rows = json.loads(path.read_text(encoding="utf-8"))
    triplets = []
    for number, row in enumerate(rows, start=1):
        row = {key: (value or "").strip() for key, value in row.items()}
        where = f"{path.name} triplet {number}"
        if any(not row.get(field) for field in FIELDS):
            raise ValueError(f"{where}: needs {', '.join(FIELDS)}")
        if row["kind"] not in KINDS or row["source"] not in SOURCES:
            raise ValueError(f"{where}: kind must be {' or '.join(KINDS)}, source {' or '.join(SOURCES)}")
        if len({row["anchor"], row["near"], row["far"]}) != 3:
            raise ValueError(f"{where}: anchor, near and far must be three different dishes")
        triplets.append({field: row[field] for field in FIELDS} | {"note": row.get("note", "")})
    return triplets


def names(triplets) -> set[str]:
    return {t[field] for t in triplets for field in ("anchor", "near", "far")}


def _cosine(a, b) -> float:
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return 1.0 - float(a @ b / norm) if norm else 1.0


def evaluate(runset, triplets) -> dict:
    title = "5. Triplets"
    rows, missing, passed, cosine = [], set(), defaultdict(list), []
    for t in triplets:
        vectors = {field: runset.mean(t[field]) for field in ("anchor", "near", "far")}
        absent = [t[f] for f, v in vectors.items() if v is None]
        if absent:
            missing.update(absent)
            continue
        near = float(np.abs(vectors["anchor"] - vectors["near"]).mean())
        far = float(np.abs(vectors["anchor"] - vectors["far"]).mean())
        ok = near < far
        for group in ("all", f"kind:{t['kind']}", f"source:{t['source']}"):
            passed[group].append(ok)
        cosine.append(_cosine(vectors["anchor"], vectors["near"]) < _cosine(vectors["anchor"], vectors["far"]))
        rows.append([t["kind"], t["source"], t["anchor"], t["near"], t["far"], round(near, 3), round(far, 3),
                     round(far - near, 3), "pass" if ok else "FAIL"])
    if not rows:
        return {"title": title, "skipped": "None of the triplet dishes are in the runs file."}
    lines = [f"{len(rows)} of {len(triplets)} triplets evaluated: {np.mean(passed['all']):.1%} pass "
             f"(a random vector passes 50%); with cosine distance {np.mean(cosine):.1%}.",
             "By kind and source: " + ", ".join(f"{group.split(':')[1]} {np.mean(v):.0%} ({len(v)})"
                                                for group, v in sorted(passed.items()) if group != "all")]
    if missing:
        lines.append(f"Skipped {len(triplets) - len(rows)}; not extracted: {', '.join(sorted(missing)[:12])}"
                     + (" ..." if len(missing) > 12 else ""))
    header = ["kind", "source", "anchor", "near", "far", "d_near", "d_far", "margin", "result"]
    failures = sorted((r for r in rows if r[-1] == "FAIL"), key=lambda r: r[7])
    return {"title": title, "lines": lines, "tables": [("triplets.csv", "All triplets", header, rows, 0),
                                                       ("triplets_failed.csv", "Failed (worst first)", header,
                                                        failures, 15)]}
