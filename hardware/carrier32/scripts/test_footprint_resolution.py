import unittest
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FootprintResolutionChecks(unittest.TestCase):
    def test_project_table_resolves_power_footprints(self):
        import sys

        os.environ["KICAD10_FOOTPRINT_DIR"] = "D:/KiCad/share/kicad/footprints"
        sys.path.insert(0, str(ROOT / ".venv" / "Lib" / "site-packages"))
        import pcb_netlist

        for lib_id in (
            "Capacitor_SMD:C_0603_1608Metric",
            "Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical",
            "Fuse:Fuse_1812_4532Metric",
            "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
            "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            "Package_TO_SOT_SMD:SOT-23-5",
            "Resistor_SMD:R_0603_1608Metric",
            "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal",
            "TestPoint:TestPoint_Plated_Hole_D2.0mm",
        ):
            with self.subTest(lib_id=lib_id):
                self.assertIsNotNone(pcb_netlist.resolve_footprint_path(lib_id, ROOT))


if __name__ == "__main__":
    unittest.main()
