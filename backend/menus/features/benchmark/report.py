# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Run the sections and write report.md, summary.json, one CSV per table and histograms.

Every section returns {"title", "lines", "tables", "checks"?} or {"title", "skipped"}.
Distribution, stability and human run once per kind of menu dish when the runs
file has variant and invariant dishes (runs.py); the others run once.
"""

from __future__ import annotations

import csv
import json
import pathlib

from . import distribution, downstream, human, integrity, stability, triplets
from .runs import RunSet, provenance

SEGMENTED = ("distribution", "stability", "human")


def run_sections(records, ratings=None, triplet_list=(), policy="preference", trials=None) -> list[dict]:
    section, valid = integrity.evaluate(records)
    results = [section]
    if not valid:
        return results
    runset = RunSet(valid)
    parts = [(None, runset)] + [(kind, runset.subset({kind})) for kind in runset.segments()]
    evaluate = {"distribution": lambda rs: distribution.evaluate(rs),
                "stability": lambda rs: stability.evaluate(rs),
                "human": lambda rs: human.evaluate(rs, ratings)}
    for name in SEGMENTED:
        for kind, part in parts:
            result = evaluate[name](part)
            if kind:
                result["title"] += f" ({kind})"
            results.append(result | {"segment": kind, "runset": part})
    results.append(triplets.evaluate(runset, triplet_list))
    results.append(downstream.evaluate(runset, human.reference(ratings or {}), policy, trials))
    return results


def status(result) -> str:
    if "skipped" in result:
        return "skipped"
    if "checks" not in result:
        return "reported"
    return "pass" if all(ok for *_, ok in result["checks"]) else "fail"


def _table(header, rows) -> list[str]:
    cell = lambda value: str(value).replace("|", "\\|")
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(map(cell, row)) + " |" for row in rows)]


def _file(name, result) -> str:
    return name if not result.get("segment") else name.replace(".", f"_{result['segment']}.", 1)


def write(results, records, output_dir, plots=True) -> pathlib.Path:
    output = pathlib.Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    run_ids = sorted({r.run for r in records})
    text = ["# Feature extraction benchmark", "",
            f"{len(records)} records in {len(run_ids)} runs: {', '.join(run_ids)}. "
            + ". ".join(f"{field}: {', '.join(values) or '-'}" for field, values in provenance(records).items()) + ".", "",
            "Only integrity passes or fails. The other sections are measurements to read; "
            "see menus/features/benchmark/ for what each one means.", "",
            "## Summary", "", *_table(["section", "result"], [[r["title"], status(r)] for r in results]), ""]
    for result in results:
        text += [f"## {result['title']}", ""]
        if "skipped" in result:
            text += [f"Skipped: {result['skipped']}", ""]
            continue
        text += [f"- {line}" for line in result["lines"]]
        text += [f"- {label}: {value} (expected {limit}) {'pass' if ok else 'FAIL'}"
                 for label, value, limit, ok in result.get("checks", [])] + [""]
        if result["title"].startswith("2. Distribution") and plots:
            image = _file("histograms.png", result)
            distribution.plot(result["runset"], output / image)
            text += [f"![Feature histograms]({image})", ""]
        for file_name, title, header, rows, shown in result["tables"]:
            file_name = _file(file_name, result)
            with open(output / file_name, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows([header, *rows])
            if shown and rows:
                more = f", first {shown} of {len(rows)}" if len(rows) > shown else ""
                text += [f"**{title}** (`{file_name}`{more})", "", *_table(header, rows[:shown]), ""]
            else:
                text += [f"**{title}**: {len(rows)} rows in `{file_name}`", ""]
    summary = [{"section": r["title"], "status": status(r), "skipped": r.get("skipped"),
                "lines": r.get("lines", [])} for r in results]
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    path = output / "report.md"
    path.write_text("\n".join(text), encoding="utf-8")
    return path
