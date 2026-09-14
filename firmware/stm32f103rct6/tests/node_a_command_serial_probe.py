#!/usr/bin/env python3
"""Exercise the Node A command dispatcher and truthful telemetry over USART1.

The probe talks to the `#NODETEST` diagnostic adapter in node_a.c.  It injects
`ut.command.v1` payloads directly, bypassing the MQTT framing, and observes the
`ut.command.ack.v1` acknowledgement plus the `ut.telemetry.v1` output.

The telemetry contract this pins:

* one frame per telemetry interval, rotating through the cycle, so each frame
  carries its own monotonic ``seq`` (a whole cycle shares no value);
* the fan's actual duty is reported in ``diag.pwmPercent`` - the legacy
  Web/IoTDA controller path may hold it at any 0..100 percent, so it is not the
  menu's 0/30/60/100 preset ladder;
* the operational gas state is the ``methane.*`` / ``oxygen.alarm`` /
  ``co.alarm`` vocabulary in the gas status frame.

``#NODETEST TELEMETRY`` forces one whole rotation so the probe can observe the
cycle within its timeout.

Run against a flashed Node A image::

    python tests/node_a_command_serial_probe.py --port COM6 --baud 9600
"""

from __future__ import annotations

import argparse
import json
import time

try:  # the host test imports this module without pyserial installed
    import serial
except ImportError:  # pragma: no cover - exercised by the host test
    serial = None


TELEMETRY_SCHEMA = "ut.telemetry.v1"
FRAME_COUNT = 6

# Metrics the gas status frame is the only producer of.  The oxygen and CO
# channels are uncalibrated, so their alarm flags must never claim a good
# quality; methane is the operational channel.
GAS_QUALITY = {
    "methane.alarm": ("good", "missing"),
    "methane.warning": ("good", "missing"),
    "oxygen.alarm": ("suspect", "missing"),
    "co.alarm": ("suspect", "missing"),
}


def send(port: "serial.Serial", line: str) -> None:
    port.write((line + "\n").encode("ascii"))
    port.flush()


def read_until(port: "serial.Serial", predicate, timeout_s: float = 3.0) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        raw = port.readline()
        if not raw:
            continue
        line = raw.decode("ascii", errors="replace").strip()
        if line and predicate(line):
            return line
    raise AssertionError("timed out waiting for a matching line")


def read_state(port: "serial.Serial") -> dict:
    line = read_until(port, lambda l: l.startswith("#STATE "))
    fields = line.split()
    state: dict = {}
    for field in fields[1:]:
        key, _, value = field.partition("=")
        if key:
            state[key] = int(value)
    return state


def require_state(port: "serial.Serial", **expected) -> None:
    state = read_state(port)
    for key, value in expected.items():
        if state.get(key) != value:
            raise AssertionError(f"expected {key}={value} in {state!r}")


def read_ack(port: "serial.Serial", command_id: str, timeout_s: float = 3.0) -> dict:
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


def readings_by_metric(frames: list[dict]) -> dict:
    """Flattens a burst's frames into one (asset, metric) -> reading mapping.

    The key is the pair, because the two fans report the same metric names for
    different assets - exactly as the consumer indexes them.  A repeated pair
    would mean the producer emitted the same reading twice in one cycle, which
    is itself a fault worth failing on rather than silently overwriting.
    """
    readings: dict = {}
    for frame in frames:
        for reading in frame.get("readings", []):
            key = (reading.get("assetCode"), reading.get("metric"))
            if key in readings:
                raise AssertionError(f"reading {key} appears twice in one cycle")
            readings[key] = reading
    return readings


def validate_telemetry_burst(frames: list[dict]) -> dict:
    """Checks one forced rotation against the producer's wire contract.

    Returns the flattened readings so a caller (or a test) can make the
    value-level assertions; everything structural lives here.
    """
    if not frames:
        raise AssertionError("no telemetry frame observed")
    if len(frames) != FRAME_COUNT:
        raise AssertionError(f"expected {FRAME_COUNT} frames in a rotation, got {len(frames)}")

    sequences = [frame.get("seq") for frame in frames]
    for frame in frames:
        if frame.get("schema") != TELEMETRY_SCHEMA:
            raise AssertionError(f"unexpected schema in {frame.get('schema')!r}")
    # One frame is one sequenced snapshot: the consumer drops a repeated
    # sequence as a duplicate, so two frames may never share a value.
    if len(set(sequences)) != len(sequences):
        raise AssertionError(f"frames share a sequence: {sequences}")
    if sequences != sorted(sequences):
        raise AssertionError(f"sequences are not monotonic: {sequences}")

    readings = readings_by_metric(frames)

    # The fan's actual duty rides in the diagnostic block, not as a ladder
    # reading, and the two fans report their own.
    fan_frames = [f for f in frames if '"FAN-01"' in json.dumps(f)]
    if len(fan_frames) != 1:
        raise AssertionError("expected exactly one FAN-01 frame in a rotation")
    if "diag" not in fan_frames[0] or "pwmPercent" not in fan_frames[0]["diag"]:
        raise AssertionError("the fan frame must report diag.pwmPercent")
    duty = fan_frames[0]["diag"]["pwmPercent"]
    if not isinstance(duty, int) or not 0 <= duty <= 100:
        raise AssertionError(f"diag.pwmPercent out of range: {duty!r}")

    for metric, allowed in GAS_QUALITY.items():
        key = ("GAS-01", metric)
        if key not in readings:
            raise AssertionError(f"the gas status frame is missing {metric}")
        quality = readings[key].get("quality")
        if quality not in allowed:
            raise AssertionError(f"{metric} quality {quality!r} not in {allowed}")

    if ("CTRL-01", "led.mode") not in readings:
        raise AssertionError("the actuator frame is missing led.mode")
    return readings


def read_telemetry_burst(port: "serial.Serial", timeout_s: float = 5.0) -> list[dict]:
    """Collects one forced rotation of `ut.telemetry.v1` frames."""
    frames: list[dict] = []
    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline and len(frames) < FRAME_COUNT:
        raw = port.readline()
        if not raw:
            continue
        line = raw.decode("ascii", errors="replace").strip()
        if f'"schema":"{TELEMETRY_SCHEMA}"' not in line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        frames.append(payload)

    if not frames:
        raise AssertionError("no telemetry frame observed")
    return frames


def inject(port: "serial.Serial", command_id: str, action: str, ttl_ms: int = 10000,
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

        # Invalid action and value leave the actuator state unchanged.  The menu
        # ladder is a COMMAND contract and stays one: 45 is not a preset the
        # screen can send, even though telemetry reports any applied 0..100.
        inject(port, "bad-act", "no_such_action")
        ack = read_ack(port, "bad-act")
        assert ack["status"] == "rejected", ack
        inject(port, "bad-duty", "fan1_duty", value=45)
        ack = read_ack(port, "bad-duty")
        assert ack["status"] == "rejected", ack
        require_state(port, fan1=0)

        # A malformed schema still carries a safe cmdId; the rejection must
        # echo it so the sender can match the failure.
        send(port, '#NODETEST CMD {"schema":"wrong.v1","cmdId":"recover-1",'
             '"action":"fan1_duty","ttlMs":10000,"value":60}')
        ack = read_ack(port, "recover-1")
        assert ack["status"] == "rejected" and ack["reason"] == "invalid_command", ack
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

        # Truthful telemetry: one forced rotation, so every frame of the cycle
        # is observable.  Each frame carries its own sequence, the fan's actual
        # duty is diag.pwmPercent, and the gas status frame carries the
        # operational alarm vocabulary with its channel quality.
        send(port, "#NODETEST RESET")
        inject(port, "tel-1", "fan1_duty", value=60)
        assert read_ack(port, "tel-1")["status"] == "accepted"
        inject(port, "tel-2", "led_mode", value=3)  # yellow
        assert read_ack(port, "tel-2")["status"] == "accepted"
        send(port, "#NODETEST TELEMETRY")
        frames = read_telemetry_burst(port)
        readings = validate_telemetry_burst(frames)
        fan_frame = next(f for f in frames if '"FAN-01"' in json.dumps(f))
        assert fan_frame["diag"]["pwmPercent"] == 60, fan_frame
        assert readings[("CTRL-01", "led.mode")]["value"] == 3, readings

    print("Node A command serial probe: PASS")


if __name__ == "__main__":
    main()
