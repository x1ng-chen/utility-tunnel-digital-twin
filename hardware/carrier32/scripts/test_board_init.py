import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "kicad_tool_board_init.py"
KICAD_PYTHON = Path("D:/KiCad/bin/python.exe")
KICAD_TOOL = ROOT / ".venv" / "Scripts" / "kicad-tool.exe"


class BoardInitChecks(unittest.TestCase):
    def test_creates_four_edge_segments_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = Path(tmp) / "test.kicad_pcb"
            result = subprocess.run(
                [str(KICAD_PYTHON), str(SCRIPT), str(board), "240", "160"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            query = subprocess.run(
                [str(KICAD_TOOL), "pcb", "query", "list", str(board), "drawings", "--format", "json"],
                capture_output=True, text=True,
            )
            self.assertEqual(query.returncode, 0, query.stderr)
            drawings = json.loads(query.stdout)["items"]
            edges = [item for item in drawings if item.get("layer") == "Edge.Cuts"]
            self.assertEqual(len(edges), 4)

            again = subprocess.run(
                [str(KICAD_PYTHON), str(SCRIPT), str(board), "240", "160"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(again.returncode, 0)
            self.assertIn("already exists", again.stderr)


if __name__ == "__main__":
    unittest.main()
