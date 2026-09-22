#!/usr/bin/env python3
"""Install the bundled KK_UI runtime only into a new target directory."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy the editable KK_UI runtime into a new project directory."
    )
    parser.add_argument("target", type=Path, help="new target directory")
    args = parser.parse_args()

    source = Path(__file__).resolve().parent.parent / "assets" / "kk-ui-runtime"
    target = args.target.resolve()
    if target.exists() or target.is_symlink():
        print(f"refusing to overwrite existing target: {target}", file=sys.stderr)
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    print(f"installed editable KK_UI runtime: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
