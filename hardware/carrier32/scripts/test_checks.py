import csv
import tempfile
import unittest
from pathlib import Path

from hardware.carrier32.scripts import check_design_inputs
from hardware.carrier32.scripts import check_net_contract


DESIGN_FIELDS = ["id", "status", "value", "unit", "source", "date", "notes"]
NET_FIELDS = [
    "asset_code",
    "node",
    "connector_pin",
    "mcu_pin",
    "signal_type",
    "voltage_domain",
    "active_level",
]


class CsvFixture(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def write_csv(self, name, fields, rows):
        path = self.root / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path


class DesignInputChecks(CsvFixture):
    def test_fabrication_rejects_unverified_required_row(self):
        path = self.write_csv(
            "inputs.csv",
            DESIGN_FIELDS,
            [
                {
                    "id": "ENCLOSURE_INTERNAL_WIDTH",
                    "status": "measurement_required",
                    "value": "",
                    "unit": "mm",
                    "source": "",
                    "date": "",
                    "notes": "Measure before board outline release",
                }
            ],
        )

        errors = check_design_inputs.validate(path, phase="fabrication")

        self.assertEqual(
            errors,
            ["ENCLOSURE_INTERNAL_WIDTH: status must be verified for fabrication"],
        )

    def test_verified_row_requires_value_source_and_date(self):
        path = self.write_csv(
            "inputs.csv",
            DESIGN_FIELDS,
            [
                {
                    "id": "FAN01_RATED_CURRENT",
                    "status": "verified",
                    "value": "",
                    "unit": "A",
                    "source": "",
                    "date": "",
                    "notes": "",
                }
            ],
        )

        errors = check_design_inputs.validate(path, phase="schematic")

        self.assertEqual(
            errors,
            [
                "FAN01_RATED_CURRENT: verified row requires value",
                "FAN01_RATED_CURRENT: verified row requires source",
                "FAN01_RATED_CURRENT: verified row requires date",
            ],
        )

    def test_duplicate_evidence_id_is_rejected(self):
        row = {
            "id": "FAN01_RATED_CURRENT",
            "status": "verified",
            "value": "0.2",
            "unit": "A",
            "source": "project owner",
            "date": "2026-09-22",
            "notes": "",
        }
        path = self.write_csv("inputs.csv", DESIGN_FIELDS, [row, row])

        errors = check_design_inputs.validate(path, phase="schematic")

        self.assertIn("FAN01_RATED_CURRENT: duplicate id", errors)


class NetContractChecks(CsvFixture):
    def sensor_rows(self):
        contracts = [
            ("SHT-01", "A", "PB6/PB7", "i2c"),
            ("SHT-02", "A", "PB6/PB7", "i2c"),
            ("SHT-03", "A", "PB10/PB11", "i2c"),
            ("SHT-04", "A", "PB10/PB11", "i2c"),
            ("MQ7-01", "A", "PC1", "analog"),
            ("MQ4-01", "A", "PC2", "analog"),
            ("O2-01", "A", "PC3", "analog"),
            ("MQ7-02", "A", "PA0", "analog"),
            ("MQ4-02", "A", "PA4", "analog"),
            ("O2-02", "A", "PA5", "analog"),
            ("MQ7-03", "A", "PB1", "analog"),
            ("MQ2-01", "A", "PB12", "digital"),
            ("FLAME-01", "A", "PB14", "digital"),
            ("LEVEL-01", "A", "PC0", "digital"),
            ("FLAME-02", "A", "PC8", "digital"),
            ("FLAME-03", "A", "PC9", "digital"),
            ("MQ2-02", "A", "PC10", "digital"),
            ("MQ2-03", "A", "PC11", "digital"),
            ("LEVEL-02", "A", "PC12", "digital"),
            ("LEVEL-03", "A", "PC13", "digital"),
            ("MQ4-03", "B", "PA0", "analog"),
            ("MQ4-04", "B", "PA1", "analog"),
            ("MQ4-05", "B", "PA4", "analog"),
            ("O2-03", "B", "PA6", "analog"),
            ("MQ7-04", "B", "PB0", "analog"),
            ("MQ7-05", "B", "PB1", "analog"),
            ("FLAME-04", "B", "PC6", "digital"),
            ("FLAME-05", "B", "PC7", "digital"),
            ("MQ2-04", "B", "PC8", "digital"),
            ("MQ2-05", "B", "PC9", "digital"),
            ("LEVEL-04", "B", "PC10", "digital"),
            ("LEVEL-05", "B", "PC11", "digital"),
        ]
        return [
            {
                "asset_code": asset,
                "node": node,
                "connector_pin": f"J{index}.SIG",
                "mcu_pin": pin,
                "signal_type": signal_type,
                "voltage_domain": "3V3",
                "active_level": "n/a",
            }
            for index, (asset, node, pin, signal_type) in enumerate(contracts, start=1)
        ]

    def test_exactly_thirty_two_unique_sensor_assets_pass(self):
        path = self.write_csv("nets.csv", NET_FIELDS, self.sensor_rows())

        errors = check_net_contract.validate(path)

        self.assertEqual(errors, [])

    def test_missing_sensor_is_rejected(self):
        path = self.write_csv("nets.csv", NET_FIELDS, self.sensor_rows()[:-1])

        errors = check_net_contract.validate(path)

        self.assertIn("sensor count must be 32, found 31", errors)

    def test_duplicate_asset_and_connector_are_rejected(self):
        rows = self.sensor_rows()
        rows[-1]["asset_code"] = rows[0]["asset_code"]
        rows[-1]["connector_pin"] = rows[0]["connector_pin"]
        path = self.write_csv("nets.csv", NET_FIELDS, rows)

        errors = check_net_contract.validate(path)

        self.assertIn("SHT-01: duplicate asset_code", errors)
        self.assertIn("J1.SIG: duplicate connector_pin", errors)

    def test_conflicting_duplicate_mcu_pin_is_rejected(self):
        rows = self.sensor_rows()
        rows[1]["node"] = rows[0]["node"]
        rows[1]["mcu_pin"] = rows[0]["mcu_pin"]
        rows[1]["signal_type"] = "digital"
        path = self.write_csv("nets.csv", NET_FIELDS, rows)

        errors = check_net_contract.validate(path)

        self.assertIn("A/PB6/PB7: conflicting duplicate MCU pin", errors)

    def test_shared_i2c_bus_is_allowed(self):
        rows = self.sensor_rows()
        rows[1]["node"] = rows[0]["node"]
        rows[1]["mcu_pin"] = rows[0]["mcu_pin"]
        rows[1]["signal_type"] = "i2c"
        path = self.write_csv("nets.csv", NET_FIELDS, rows)

        errors = check_net_contract.validate(path)

        self.assertEqual(errors, [])

    def test_frozen_mcu_pin_mapping_is_enforced(self):
        rows = self.sensor_rows()
        rows[0].update(
            {
                "asset_code": "SHT-01",
                "node": "A",
                "mcu_pin": "PB6/PB7",
                "signal_type": "i2c",
            }
        )
        rows[1].update(
            {
                "asset_code": "SHT-02",
                "node": "A",
                "mcu_pin": "PB6/PB7",
                "signal_type": "i2c",
            }
        )
        rows[2].update(
            {
                "asset_code": "SHT-03",
                "node": "A",
                "mcu_pin": "PB10/PB11",
                "signal_type": "i2c",
            }
        )
        rows[3].update(
            {
                "asset_code": "SHT-04",
                "node": "A",
                "mcu_pin": "PB10/PB11",
                "signal_type": "i2c",
            }
        )
        rows[4]["asset_code"] = "MQ7-01"
        rows[4]["node"] = "A"
        rows[4]["mcu_pin"] = "PC2"
        path = self.write_csv("nets.csv", NET_FIELDS, rows)

        errors = check_net_contract.validate(path)

        self.assertIn("MQ7-01: expected A/PC1, found A/PC2", errors)


if __name__ == "__main__":
    unittest.main()
