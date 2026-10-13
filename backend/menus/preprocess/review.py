# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""CSV files for a person to review preprocessing results in Excel."""

from __future__ import annotations

import csv
import pathlib

REVIEW_COLUMNS = ["ok (Y/N)", "correction"]  # filled in by the reviewer


def write_csv(path: str | pathlib.Path, header: list[str], rows: list[list]) -> None:
    """UTF-8 with a BOM, so Excel opens Korean text correctly by double-click."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header + REVIEW_COLUMNS)
        for row in rows:
            writer.writerow(list(row) + [""] * len(REVIEW_COLUMNS))
