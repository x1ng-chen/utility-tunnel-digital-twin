"""Render an electrical-label-preserving visual overview of the four modules.

The authoritative schematic remains carrier32.kicad_sch. This companion view
obtains pin positions and labels exclusively through kicad-tool query commands.
"""

from __future__ import annotations

import html
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / ".venv" / "Scripts" / "kicad-tool.exe"
SCHEMATIC = ROOT / "carrier32.kicad_sch"
OUTPUT = ROOT / "build" / "demo" / "module-overview.svg"
REFS = ("J_MCU_A", "J_MCU_B", "J_TFT_A", "J_TFT_B")


def query(*args: str) -> dict:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [str(TOOL), "sch", "query", *args, "--format", "json"],
        check=True, capture_output=True, text=True, env=env,
    )
    return json.loads(result.stdout)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def text(x: int, y: int, value: object, size: int = 16, color: str = "#dceafa",
         anchor: str = "start", weight: int = 400) -> str:
    return (f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
            f'font-family="Segoe UI,Arial,sans-serif" text-anchor="{anchor}" '
            f'font-weight="{weight}">{esc(value)}</text>')


def rect(x: int, y: int, w: int, h: int, fill: str, stroke: str = "none",
         rx: int = 0, sw: int = 1) -> str:
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def pin_map(symbol: dict, labels: dict[tuple[float, float], str]) -> dict[int, str]:
    result = {}
    for pin in symbol["pins"]:
        position = pin["absolute"]
        key = (round(position["x"], 3), round(position["y"], 3))
        result[int(pin["number"])] = labels.get(key, "NC")
    return result


def mcu_card(x: int, y: int, ref: str, pins: dict[int, str]) -> str:
    width, height = 726, 688
    accent = "#46bfda" if ref.endswith("A") else "#f2bd6b"
    side = ref[-1]
    parts = [rect(x, y, width, height, "#172b3d", "#46708b", 18, 2),
             rect(x + 19, y + 20, width - 38, 56, "#24445a", rx=10),
             text(x + 38, y + 58, f"STM32F103RCT6 模块 {side}", 27, "#ffffff", weight=700),
             text(x + width - 30, y + 55, ref, 17, accent, "end", 700),
             text(x + 35, y + 106, "载板 2×20 排针 · 信号按原理图针号显示", 16, "#a9c4d8"),
             rect(x + 290, y + 158, 146, 412, "#113d46", accent, 12, 3),
             rect(x + 314, y + 290, 98, 98, "#223a48", "#9ec0d2", 8, 2),
             text(x + 363, y + 344, "STM32", 18, "#ffffff", "middle", 700),
             text(x + 363, y + 366, "F103RC", 13, "#a9c4d8", "middle")]
    for row in range(20):
        yy = y + 143 + row * 24
        odd, even = row * 2 + 1, row * 2 + 2
        parts.extend([
            rect(x + 23, yy - 15, 266, 22, "#20394d", rx=4),
            rect(x + 438, yy - 15, 266, 22, "#20394d", rx=4),
            text(x + 32, yy + 1, f"{odd:02d}", 14, accent, weight=700),
            text(x + 66, yy + 1, pins[odd], 13, "#edf7ff"),
            text(x + 449, yy + 1, f"{even:02d}", 14, accent, weight=700),
            text(x + 482, yy + 1, pins[even], 13, "#edf7ff"),
            rect(x + 281, yy - 9, 8, 8, "#d7a957", rx=2),
            rect(x + 438, yy - 9, 8, 8, "#d7a957", rx=2),
        ])
    parts.append(text(x + 34, y + height - 26, "注：绿色板块为展示图；真实电气对象是双排针模块座。", 15, "#a9c4d8"))
    return "\n".join(parts)


def tft_card(x: int, y: int, ref: str, pins: dict[int, str]) -> str:
    width, height = 726, 485
    accent = "#46bfda" if ref.endswith("A") else "#f2bd6b"
    side = ref[-1]
    parts = [rect(x, y, width, height, "#172b3d", "#46708b", 18, 2),
             rect(x + 19, y + 20, width - 38, 56, "#24445a", rx=10),
             text(x + 38, y + 58, f"ST7735S 屏幕模块 {side}", 27, "#ffffff", weight=700),
             text(x + width - 30, y + 55, ref, 17, accent, "end", 700),
             text(x + 35, y + 108, "载板 1×8 排针 · SPI 显示接口", 16, "#a9c4d8"),
             rect(x + 348, y + 130, 327, 280, "#0d4650", accent, 14, 3),
             rect(x + 367, y + 146, 289, 221, "#071921", "#8edbdc", 5, 2),
             rect(x + 381, y + 160, 261, 192, "#154d76", rx=2),
             text(x + 511, y + 235, "Carrier32", 26, "#e8f6ff", "middle", 700),
             text(x + 511, y + 270, "DISPLAY " + side, 19, "#b7e1ef", "middle"),
             rect(x + 398, y + 385, 226, 16, "#d8a64f", rx=3)]
    for num in range(1, 9):
        yy = y + 150 + (num - 1) * 34
        parts.extend([rect(x + 27, yy - 19, 292, 27, "#20394d", rx=4),
                      text(x + 37, yy, f"{num:02d}", 16, accent, weight=700),
                      text(x + 80, yy, pins[num], 16, "#edf7ff")])
    parts.append(text(x + 34, y + height - 25, "注：画面为 3D/外观示意，针脚信号来自当前原理图。", 15, "#a9c4d8"))
    return "\n".join(parts)


def main() -> None:
    label_items = query("list", str(SCHEMATIC), "labels")["items"]
    labels = {(round(item["at"]["x"], 3), round(item["at"]["y"], 3)): item["text"]
              for item in label_items}
    symbols = {ref: query("symbol", str(SCHEMATIC), ref) for ref in REFS}
    maps = {ref: pin_map(symbols[ref], labels) for ref in REFS}
    assert all(len(maps[ref]) == (40 if "MCU" in ref else 8) for ref in REFS)
    sections = [rect(0, 0, 1550, 1360, "#0b1724"),
                text(48, 63, "Carrier32 · 双控制器 / 双屏幕模块", 34, "#ffffff", weight=700),
                text(48, 96, "原理图可读性补充视图  |  四个模块的针号与网络名称取自 carrier32.kicad_sch", 18, "#afc6d7"),
                mcu_card(40, 135, "J_MCU_A", maps["J_MCU_A"]),
                mcu_card(784, 135, "J_MCU_B", maps["J_MCU_B"]),
                tft_card(40, 841, "J_TFT_A", maps["J_TFT_A"]),
                tft_card(784, 841, "J_TFT_B", maps["J_TFT_B"])]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1550" height="1360" '
                      'viewBox="0 0 1550 1360">\n' + "\n".join(sections) + "\n</svg>\n",
                      encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
