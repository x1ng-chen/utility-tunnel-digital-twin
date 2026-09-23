import csv
import tempfile
import unittest
from pathlib import Path

from hardware.carrier32.scripts import check_connector_contract


ROOT = Path(__file__).resolve().parents[1]
NET_CONTRACT = ROOT / "config" / "net-contract.csv"
CONNECTOR_CONTRACT = ROOT / "config" / "connector-contract.csv"


class ConnectorContractChecks(unittest.TestCase):
    def test_all_32_assets_have_keyed_board_pin_assignments(self):
        self.assertEqual(check_connector_contract.validate(CONNECTOR_CONTRACT, NET_CONTRACT), [])

        with CONNECTOR_CONTRACT.open(encoding="utf-8", newline="") as handle:
            rows = {row["asset_code"]: row for row in csv.DictReader(handle)}
        self.assertEqual(len(rows), 32)
        self.assertEqual(
            (rows["SHT-01"]["pin1"], rows["SHT-01"]["pin2"],
             rows["SHT-01"]["pin3"], rows["SHT-01"]["pin4"]),
            ("GND", "3V3_SENSORS", "A_PB7_SDA", "A_PB6_SCL"),
        )
        self.assertEqual(rows["MQ4-01"]["pin2"], "5V_MQ4")
        self.assertEqual(rows["MQ4-01"]["pin3"], "A_PC2")
        self.assertEqual(rows["MQ2-01"]["pin2"], "5V_MQ2")
        self.assertEqual(rows["MQ2-01"]["pin3"], "A_PB12")
        self.assertEqual(rows["LEVEL-01"]["pin2"], "5V_SENSORS")

    def test_swapped_power_pins_are_rejected(self):
        with CONNECTOR_CONTRACT.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
            fields = list(rows[0])
        rows[0]["pin1"], rows[0]["pin2"] = rows[0]["pin2"], rows[0]["pin1"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "swapped.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            errors = check_connector_contract.validate(path, NET_CONTRACT)
        self.assertTrue(any("pin1 must be GND" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
