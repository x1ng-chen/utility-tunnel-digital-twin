#!/usr/bin/env python3
"""Exercise the Node B joystick diagnostic adapter over USART1."""

from __future__ import annotations

import argparse
import time

import serial


CASES = [
    ("#JOYTEST 2048 2048 1 0\n", "NONE"),
    ("#JOYTEST 3600 2048 1 10\n", "RIGHT"),
    ("#JOYTEST 2048 400 1 20\n", "UP"),
    ("#JOYTEST 2048 2048 0 30\n", "PRESS"),
]


def read_joy_line(port: serial.Serial, timeout_s: float = 1.5) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        line = port.readline().decode("ascii", errors="replace").strip()
        if line.startswith("#JOY "):
            return line
    raise AssertionError("timed out waiting for #JOY diagnostic output")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Node B USART1 port, for example COM6")
    parser.add_argument("--baud", type=int, default=9600)
    args = parser.parse_args()

    with serial.Serial(args.port, args.baud, timeout=0.1, write_timeout=1) as port:
        port.reset_input_buffer()
        for command, expected in CASES:
            port.write(command.encode("ascii"))
            port.flush()
            actual = read_joy_line(port)
            if actual != f"#JOY {expected}":
                raise AssertionError(f"{command.strip()}: expected #JOY {expected!s}, got {actual!r}")

    print("Joystick serial probe: PASS")


if __name__ == "__main__":
    main()
