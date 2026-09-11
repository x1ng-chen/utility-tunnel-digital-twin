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


def start_critical_command(port: serial.Serial, command_id: str) -> None:
    send_and_read(port, "#UITEST RESET")
    require_contains(send_and_read(port, "#UITEST MQTT 1"), "command=idle")
    for _ in range(3):
        send_and_read(port, "#UITEST DOWN")
    require_contains(send_and_read(port, "#UITEST PRESS"), "page=fans")
    require_contains(send_and_read(port, "#UITEST DOWN"), "row=1")
    require_contains(send_and_read(port, "#UITEST PRESS"), "dialog=confirm")
    require_contains(send_and_read(port, "#UITEST PRESS"), "command=sending")
    require_contains(send_and_read(port, f"#UITEST BIND {command_id}"), "command=sending")


def enter_critical_fans_row(port: serial.Serial, mqtt_online: bool = False, safety_locked: bool = False) -> None:
    send_and_read(port, "#UITEST RESET")
    if mqtt_online:
        require_contains(send_and_read(port, "#UITEST MQTT 1"), "command=idle")
    if safety_locked:
        require_contains(send_and_read(port, "#UITEST SAFETY 1"), "command=idle")
    for _ in range(3):
        send_and_read(port, "#UITEST DOWN")
    require_contains(send_and_read(port, "#UITEST PRESS"), "page=fans")
    require_contains(send_and_read(port, "#UITEST DOWN"), "row=1")


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

        # A long press must only change navigation while a dispatched command
        # waits for its acknowledgement; a new press cannot send another one.
        start_critical_command(port, "keep-1")
        require_contains(send_and_read(port, "#UITEST LONG_PRESS"), "page=home row=0 dialog=none command=sending")
        require_contains(send_and_read(port, "#UITEST PRESS"), "command=sending")

        # Only the currently bound command ID can complete the lifecycle.
        require_contains(send_and_read(port, "#UITEST ACK another-1 ACCEPT"), "command=sending")
        require_contains(send_and_read(port, "#UITEST ACK keep-1 ACCEPT"), "command=accepted")

        start_critical_command(port, "reject-1")
        require_contains(send_and_read(port, "#UITEST ACK reject-1 REJECT"), "command=rejected")

        start_critical_command(port, "timeout-1")
        require_contains(send_and_read(port, "#UITEST TICK 5000"), "command=timeout")
        require_contains(send_and_read(port, "#UITEST ACK timeout-1 ACCEPT"), "command=timeout")

        # Offline MQTT and the active safety lock leave navigation readable but
        # prevent a critical row from opening a confirmation or sending.
        enter_critical_fans_row(port)
        require_contains(send_and_read(port, "#UITEST MQTT 0"), "command=idle")
        require_contains(send_and_read(port, "#UITEST PRESS"), "dialog=none command=idle")

        enter_critical_fans_row(port, mqtt_online=True, safety_locked=True)
        require_contains(send_and_read(port, "#UITEST PRESS"), "dialog=none command=idle")

    print("UiState serial probe: PASS")


if __name__ == "__main__":
    main()
