#!/usr/bin/env python3
"""Exercise the Node B UiState diagnostic adapter over USART1."""

from __future__ import annotations

import argparse
import time

import serial


def read_ui_line(port: serial.Serial, timeout_s: float = 1.5) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        line = port.readline().decode("ascii", errors="replace").strip()
        if line.startswith("#UI "):
            return line
    raise AssertionError("timed out waiting for #UI diagnostic output")


def send_and_read(port: serial.Serial, command: str) -> str:
    port.write((command + "\n").encode("ascii"))
    port.flush()
    return read_ui_line(port)


def require_contains(line: str, expected: str) -> None:
    if expected not in line:
        raise AssertionError(f"expected {expected!r} in {line!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Node B USART1 port, for example COM6")
    parser.add_argument("--baud", type=int, default=9600)
    args = parser.parse_args()

    with serial.Serial(args.port, args.baud, timeout=0.1, write_timeout=1) as port:
        port.reset_input_buffer()
        assert send_and_read(port, "#UITEST RESET") == "#UI page=home row=0 dialog=none command=idle"
        require_contains(send_and_read(port, "#UITEST DOWN"), "row=1")
        require_contains(send_and_read(port, "#UITEST LONG_PRESS"), "page=home row=0")

        # Row 3 is FANS. Both-start is a critical command, so the first
        # press opens confirmation and the second one sends it.
        send_and_read(port, "#UITEST RESET")
        for _ in range(3):
            send_and_read(port, "#UITEST DOWN")
        require_contains(send_and_read(port, "#UITEST PRESS"), "page=fans")
        require_contains(send_and_read(port, "#UITEST DOWN"), "row=1")
        require_contains(send_and_read(port, "#UITEST PRESS"), "dialog=confirm")
        require_contains(send_and_read(port, "#UITEST PRESS"), "command=sending")
        require_contains(send_and_read(port, "#UITEST TICK 5000"), "command=timeout")

    print("UiState serial probe: PASS")


if __name__ == "__main__":
    main()
