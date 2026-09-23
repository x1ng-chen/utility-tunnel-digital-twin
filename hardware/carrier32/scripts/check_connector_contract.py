"""Check the selected carrier-side 4-pin sensor interface."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


FOOTPRINT = "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical"
CONNECTOR_FIELDS = {"asset_code", "board_ref", "connector_footprint", "pin1", "pin2", "pin3", "pin4"}
NET_FIELDS = {"asset_code", "node", "connector_pin", "mcu_pin", "signal_type"}


def _read_rows(path: Path, required: set[str]) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or [])
        if missing:
            return [], [f"{path.name}: missing columns {', '.join(sorted(missing))}"]
        return list(reader), []


def _expected_supply(asset: str) -> str:
    family = asset.split("-", 1)[0]
    if family == "SHT":
        return "3V3_SENSORS"
    if family in {"MQ2", "MQ4", "MQ7"}:
        return f"5V_{family}"
    return "5V_SENSORS"


def validate(connector_csv: Path | str, net_contract_csv: Path | str) -> list[str]:
    connectors, errors = _read_rows(Path(connector_csv), CONNECTOR_FIELDS)
    nets, net_errors = _read_rows(Path(net_contract_csv), NET_FIELDS)
    errors.extend(net_errors)
    if errors:
        return errors

    assets = [row["asset_code"].strip() for row in connectors]
    refs = [row["board_ref"].strip() for row in connectors]
    expected = {row["asset_code"].strip(): row for row in nets}
    if len(connectors) != 32:
        errors.append(f"connector count must be 32, found {len(connectors)}")
    for key, count in Counter(assets).items():
        if count > 1:
            errors.append(f"{key}: duplicate asset_code")
    for key, count in Counter(refs).items():
        if count > 1:
            errors.append(f"{key}: duplicate board_ref")
    if set(assets) != set(expected):
        errors.append("connector assets must exactly match net contract assets")

    for row in connectors:
        asset = row["asset_code"].strip()
        net = expected.get(asset)
        if not net:
            continue
        ref = row["board_ref"].strip()
        if net["connector_pin"].split(".", 1)[0] != ref:
            errors.append(f"{asset}: board_ref differs from net contract")
        if row["connector_footprint"].strip() != FOOTPRINT:
            errors.append(f"{asset}: wrong connector footprint")
        if row["pin1"].strip() != "GND":
            errors.append(f"{asset}: pin1 must be GND")
        supply = _expected_supply(asset)
        if row["pin2"].strip() != supply:
            errors.append(f"{asset}: pin2 must be {supply}")
        node = net["node"].strip()
        mcu = net["mcu_pin"].strip()
        if net["signal_type"].strip() == "i2c":
            pins = mcu.split("/")
            if len(pins) != 2:
                errors.append(f"{asset}: I2C requires SCL/SDA MCU pins")
                continue
            signal3, signal4 = f"{node}_{pins[1]}_SDA", f"{node}_{pins[0]}_SCL"
        else:
            signal3, signal4 = f"{node}_{mcu}", "NC"
        if row["pin3"].strip() != signal3:
            errors.append(f"{asset}: pin3 must be {signal3}")
        if row["pin4"].strip() != signal4:
            errors.append(f"{asset}: pin4 must be {signal4}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("connector_csv", type=Path)
    parser.add_argument("net_contract_csv", type=Path)
    args = parser.parse_args()
    errors = validate(args.connector_csv, args.net_contract_csv)
    if errors:
        for error in errors:
            print(f"BLOCKED: {error}")
        return 1
    print("connector contract: PASS (32 keyed carrier-side interfaces)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
