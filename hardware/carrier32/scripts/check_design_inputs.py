#!/usr/bin/env python3
"""Validate measured evidence required by the carrier32 release gates."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


REQUIRED_COLUMNS = {"id", "status", "value", "unit", "source", "date", "notes"}
SCHEMATIC_REQUIRED_IDS = {
    "KICAD_VERSION",
    "SENSOR_POPULATION",
    "FAN01_RATED_VOLTAGE",
    "FAN01_RATED_CURRENT",
    "FAN02_RATED_VOLTAGE",
    "FAN02_RATED_CURRENT",
}


def read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            return [], [f"missing columns: {', '.join(missing)}"]
        return [dict(row) for row in reader], []


def validate(path: Path | str, phase: str) -> list[str]:
    path = Path(path)
    rows, errors = read_rows(path)
    if errors:
        return errors

    ids = [row["id"].strip() for row in rows]
    for evidence_id, count in Counter(ids).items():
        if evidence_id and count > 1:
            errors.append(f"{evidence_id}: duplicate id")

    for row in rows:
        evidence_id = row["id"].strip()
        status = row["status"].strip()
        required = phase == "fabrication" or evidence_id in SCHEMATIC_REQUIRED_IDS
        if required and status != "verified":
            errors.append(f"{evidence_id}: status must be verified for {phase}")
            continue
        if status == "verified":
            for field in ("value", "source", "date"):
                if not row[field].strip():
                    errors.append(f"{evidence_id}: verified row requires {field}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("schematic", "fabrication"), required=True)
    parser.add_argument("csv_file", type=Path)
    args = parser.parse_args()

    errors = validate(args.csv_file, args.phase)
    if errors:
        for error in errors:
            print(f"BLOCKED: {error}")
        return 1
    print(f"design inputs ({args.phase}): PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
