#!/usr/bin/env python3
"""Exercise the Node A command dispatcher and truthful telemetry over USART1.

The probe talks to the `#NODETEST` diagnostic adapter in node_a.c.  It injects
`ut.command.v1` payloads directly, bypassing the MQTT framing, and observes the
`ut.command.ack.v1` acknowledgement plus the `ut.telemetry.v1` output.

Run against a flashed Node A image::

    python tests/node_a_command_serial_probe.py --port COM6 --baud 9600
"""

from __future__ import annotations

import argparse
import json
import time

import serial


def send(port: serial.Serial, line: str) -> None:
    port.write((line + "\n").encode("ascii"))
    port.flush()


def read_until(port: serial.Serial, predicate, timeout_s: float = 3.0) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        raw = port.readline()
        if not raw:
            continue
        line = raw.decode("ascii", errors="replace").strip()
        if line and predicate(line):
            return line
    raise AssertionError("timed out waiting for a matching line")


def read_state(port: serial.Serial) -> dict:
    line = read_until(port, lambda l: l.startswith("#STATE "))
    fields = line.split()
    state: dict = {}
    for field in fields[1:]:
        key, _, value = field.partition("=")
        if key:
            state[key] = int(value)
    return state


def require_state(port: serial.Serial, **expected) -> None:
    state = read_state(port)
    for key, value in expected.items():
        if state.get(key) != value:
            raise AssertionError(f"expected {key}={value} in {state!r}")


def read_ack(port: serial.Serial, command_id: str, timeout_s: float = 3.0) -> dict:
    def matches(line: str) -> bool:
        if '"schema":"ut.command.ack.v1"' not in line:
            return False
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return False
        return payload.get("cmdId") == command_id

    line = read_until(port, matches, timeout_s)
    return json.loads(line)


def read_telemetry_burst(port: serial.Serial, timeout_s: float = 5.0) -> list[dict]:
    """Collect every telemetry frame from the next single emission burst.

    Node A emits several `ut.telemetry.v1` frames sharing one monotonic
    sequence per cycle; return all frames observed for that sequence."""
    frames: list[dict] = []
    sequence: int | None = None
    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        raw = port.readline()
        if not raw:
            continue
        line = raw.decode("ascii", errors="replace").strip()
        if '"schema":"ut.telemetry.v1"' not in line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if sequence is None:
            sequence = payload.get("seq")
        if payload.get("seq") != sequence:
            continue
        frames.append(payload)
        if len(frames) >= 6:
            break

    if not frames:
        raise AssertionError("no telemetry frame observed")
    return frames


def inject(port: serial.Serial, command_id: str, action: str, ttl_ms: int = 10000,
           value: int | None = None, duty_percent: int | None = None) -> None:
    fields = [f'"schema":"ut.command.v1","cmdId":"{command_id}"',
              f'"action":"{action}","ttlMs":{ttl_ms}']
    if value is not None:
        fields.append(f'"value":{value}')
    if duty_percent is not None:
        fields.append(f'"dutyPercent":{duty_percent}')
    send(port, "#NODETEST CMD {" + ",".join(fields) + "}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Node A USART1 port, for example COM6")
    parser.add_argument("--baud", type=int, default=9600)
    args = parser.parse_args()

    with serial.Serial(args.port, args.baud, timeout=0.1, write_timeout=1) as port:
        port.reset_input_buffer()

        send(port, "#NODETEST RESET")
        require_state(port, fan1=100, fan2=100, relay=0, buzzer=0, muted=0, led_mode=0)

        # Fan presets: 30 / 60 / 100, applied value echoed in the ack.
        for duty in (30, 60, 100):
            inject(port, f"fan1-{duty}", "fan1_duty", value=duty)
            ack = read_ack(port, f"fan1-{duty}")
            assert ack["status"] == "accepted", ack
            assert ack["appliedValue"] == duty, ack
            require_state(port, fan1=duty)
        for duty in (30, 60, 100):
            inject(port, f"fan2-{duty}", "fan2_duty", value=duty)
            ack = read_ack(port, f"fan2-{duty}")
            assert ack["status"] == "accepted", ack
            assert ack["appliedValue"] == duty, ack
            require_state(port, fan2=duty)

        # Both-fans start and all-stop.
        inject(port, "both-1", "fans_both_start", value=0)
        assert read_ack(port, "both-1")["status"] == "accepted"
        require_state(port, fan1=100, fan2=100, relay=1)
        inject(port, "stop-1", "fans_all_stop", value=0)
        assert read_ack(port, "stop-1")["status"] == "accepted"
        require_state(port, fan1=0, fan2=0, relay=0)

        # LED mode and brightness.
        inject(port, "led-m", "led_mode", value=5)  # blue
        assert read_ack(port, "led-m")["status"] == "accepted"
        require_state(port, led_mode=5)
        inject(port, "led-b", "led_brightness", value=50)
        assert read_ack(port, "led-b")["status"] == "accepted"
        require_state(port, led_bright=50)

        # Buzzer test / mute / restore.
        inject(port, "buz-test", "buzzer_test", value=0)
        assert read_ack(port, "buz-test")["status"] == "accepted"
        inject(port, "buz-mute", "buzzer_mute", value=0)
        assert read_ack(port, "buz-mute")["status"] == "accepted"
        require_state(port, muted=1)
        inject(port, "buz-restore", "buzzer_restore", value=0)
        assert read_ack(port, "buz-restore")["status"] == "accepted"
        require_state(port, muted=0)

        # Invalid action and value leave the actuator state unchanged.
        inject(port, "bad-act", "no_such_action")
        ack = read_ack(port, "bad-act")
        assert ack["status"] == "rejected", ack
        inject(port, "bad-duty", "fan1_duty", value=45)
        ack = read_ack(port, "bad-duty")
        assert ack["status"] == "rejected", ack
        require_state(port, fan1=0)

        # Duplicate cmdId is reported once and never re-executed.
        inject(port, "dup-1", "fan1_duty", value=100)
        assert read_ack(port, "dup-1")["status"] == "accepted"
        inject(port, "dup-1", "fan1_duty", value=100)
        assert read_ack(port, "dup-1")["status"] == "duplicate"

        # Active safety rejects fan/safe-state commands and leaves state alone.
        send(port, "#NODETEST SAFETY 0 0 0 1")
        require_state(port, vent=1)
        inject(port, "safety-1", "fan1_duty", value=60)
        ack = read_ack(port, "safety-1")
        assert ack["status"] == "rejected", ack
        assert ack["reason"] == "automatic_ventilation_active", ack
        require_state(port, fan1=100)
        send(port, "#NODETEST SAFETY 0 0 0 0")

        # Truthful telemetry: one monotonic sequence per burst, with the fan
        # target duty and LED mode reported as first-class readings.
        send(port, "#NODETEST RESET")
        inject(port, "tel-1", "fan1_duty", value=60)
        assert read_ack(port, "tel-1")["status"] == "accepted"
        inject(port, "tel-2", "led_mode", value=3)  # yellow
        assert read_ack(port, "tel-2")["status"] == "accepted"
        send(port, "#NODETEST TELEMETRY")
        frames = read_telemetry_burst(port)
        sequences = {f["seq"] for f in frames}
        assert len(sequences) == 1, sequences
        readings = {r["metric"]: r for f in frames for r in f["readings"]}
        assert readings["target.dutyPercent"]["value"] == 60, readings
        assert readings["led.mode"]["value"] == 3, readings

    print("Node A command serial probe: PASS")


if __name__ == "__main__":
    main()
