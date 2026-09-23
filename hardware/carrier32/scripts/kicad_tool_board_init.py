"""KiCad-native board initialization command for the local kicad-tool workflow.

Runs under KiCad's bundled Python/pcbnew. This command only creates a new
board: it refuses to overwrite one and does not place or route circuitry.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pcbnew


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("width_mm", type=float)
    parser.add_argument("height_mm", type=float)
    args = parser.parse_args()

    if args.board.exists():
        print(f"board already exists: {args.board}", file=sys.stderr)
        return 2
    if not (50 <= args.width_mm <= 300 and 50 <= args.height_mm <= 250):
        print("board dimensions outside 50..300 x 50..250 mm review envelope", file=sys.stderr)
        return 2

    board = pcbnew.NewBoard(str(args.board))
    board.SetCopperLayerCount(4)
    board.GetTitleBlock().SetTitle("Carrier32 reference board - unrouted")
    board.GetTitleBlock().SetComment(1, "240 x 160 mm architecture envelope; not fabrication release")

    x0 = pcbnew.FromMM(50)
    y0 = pcbnew.FromMM(50)
    x1 = pcbnew.FromMM(50 + args.width_mm)
    y1 = pcbnew.FromMM(50 + args.height_mm)
    points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        segment = pcbnew.PCB_SHAPE(board)
        segment.SetShape(pcbnew.SHAPE_T_SEGMENT)
        segment.SetStart(pcbnew.VECTOR2I(*start))
        segment.SetEnd(pcbnew.VECTOR2I(*end))
        segment.SetLayer(pcbnew.Edge_Cuts)
        segment.SetWidth(pcbnew.FromMM(0.05))
        board.Add(segment)

    args.board.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(args.board), board)
    print(f"initialized {args.board} ({args.width_mm:g} x {args.height_mm:g} mm, 4 layers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
