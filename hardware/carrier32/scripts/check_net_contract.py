#!/usr/bin/env python3
"""Validate the carrier32 sensor-to-MCU net contract."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


REQUIRED_COLUMNS = {
    "asset_code",
    "node",
    "connector_pin",
    "mcu_pin",
    "signal_type",
    "voltage_domain",
    "active_level",
}
EXPECTED_FAMILIES = {
    "SHT": 4,
    "LEVEL": 5,
    "MQ2": 5,
    "MQ4": 5,
    "MQ7": 5,
    "O2": 3,
    "FLAME": 5,
}
EXPECTED_PIN_MAP = {
    "SHT-01": ("A", "PB6/PB7"),
    "SHT-02": ("A", "PB6/PB7"),
    "SHT-03": ("A", "PB10/PB11"),
    "SHT-04": ("A", "PB10/PB11"),
    "MQ7-01": ("A", "PC1"),
    "MQ4-01": ("A", "PC2"),
    "O2-01": ("A", "PC3"),
    "MQ7-02": ("A", "PA0"),
    "MQ4-02": ("A", "PA4"),
    "O2-02": ("A", "PA5"),
    "MQ7-03": ("A", "PB1"),
    "MQ2-01": ("A", "PB12"),
    "FLAME-01": ("A", "PB14"),
    "LEVEL-01": ("A", "PC0"),
    "FLAME-02": ("A", "PC8"),
    "FLAME-03": ("A", "PC9"),
    "MQ2-02": ("A", "PC10"),
    "MQ2-03": ("A", "PC11"),
    "LEVEL-02": ("A", "PC12"),
    "LEVEL-03": ("A", "PC13"),
    "MQ4-03": ("B", "PA0"),
    "MQ4-04": ("B", "PA1"),
    "MQ4-05": ("B", "PA4"),
    "O2-03": ("B", "PA6"),
    "MQ7-04": ("B", "PB0"),
    "MQ7-05": ("B", "PB1"),
    "FLAME-04": ("B", "PC6"),
    "FLAME-05": ("B", "PC7"),
    "MQ2-04": ("B", "PC8"),
    "MQ2-05": ("B", "PC9"),
    "LEVEL-04": ("B", "PC10"),
    "LEVEL-05": ("B", "PC11"),
}


def validate(path: Path | str) -> list[str]:
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            return [f"missing columns: {', '.join(missing)}"]
        rows = [dict(row) for row in reader]

    errors: list[str] = []
    if len(rows) != 32:
        errors.append(f"sensor count must be 32, found {len(rows)}")

    assets = [row["asset_code"].strip() for row in rows]
    connectors = [row["connector_pin"].strip() for row in rows]
    for value, count in Counter(assets).items():
        if value and count > 1:
            errors.append(f"{value}: duplicate asset_code")
    for value, count in Counter(connectors).items():
        if value and count > 1:
            errors.append(f"{value}: duplicate connector_pin")

    family_counts = Counter(asset.rsplit("-", 1)[0] for asset in assets if "-" in asset)
    for family, expected in EXPECTED_FAMILIES.items():
        actual = family_counts.get(family, 0)
        if actual != expected:
            errors.append(f"{family}: expected {expected}, found {actual}")

    for row in rows:
        asset = row["asset_code"].strip()
        expected_pin = EXPECTED_PIN_MAP.get(asset)
        if expected_pin is None:
            continue
        actual_pin = (row["node"].strip(), row["mcu_pin"].strip())
        if actual_pin != expected_pin:
            errors.append(
                f"{asset}: expected {expected_pin[0]}/{expected_pin[1]}, "
                f"found {actual_pin[0]}/{actual_pin[1]}"
            )

    by_pin: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        node = row["node"].strip()
        pin = row["mcu_pin"].strip()
        if node not in {"A", "B"}:
            errors.append(f"{row['asset_code']}: node must be A or B")
        by_pin[(node, pin)].append(row)

    for (node, pin), members in by_pin.items():
        if len(members) <= 1:
            continue
        if not all(member["signal_type"].strip() == "i2c" for member in members):
            errors.append(f"{node}/{pin}: conflicting duplicate MCU pin")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", type=Path)
    args = parser.parse_args()
    errors = validate(args.csv_file)
    if errors:
        for error in errors:
            print(f"BLOCKED: {error}")
        return 1
    print("net contract: PASS (32 sensors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
