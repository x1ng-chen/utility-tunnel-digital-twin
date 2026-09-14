"""Exercise the Node A command probe's telemetry validator without a device.

The probe is the plan's Task 7 Step 4 acceptance gate, so its contract has to
keep up with the wire the producer actually emits.  This drives
`validate_telemetry_burst` - the structural half of the probe - over synthetic
rotations, so a producer change that invalidates the probe fails here instead
of at the bench.
"""

import ast
import json
import pathlib


PROBE = pathlib.Path(__file__).with_name("node_a_command_serial_probe.py")
TREE = ast.parse(PROBE.read_text(encoding="utf-8"), filename=str(PROBE))

# The probe's module-level constants and the validator under test.  Importing
# the module itself would pull in pyserial, which the host test must not need;
# json is injected because the extracted functions use it.
WANTED = {
    "TELEMETRY_SCHEMA", "FRAME_COUNT", "GAS_QUALITY",
    "readings_by_metric", "validate_telemetry_burst",
}
NAMESPACE: dict = {"json": json}
for node in TREE.body:
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id in WANTED for t in node.targets
    ):
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(PROBE), "exec"),
             NAMESPACE)
    elif isinstance(node, ast.FunctionDef) and node.name in WANTED:
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(PROBE), "exec"),
             NAMESPACE)

assert set(NAMESPACE) >= WANTED, sorted(WANTED - set(NAMESPACE))
validate = NAMESPACE["validate_telemetry_burst"]


def frame(sequence: int, readings: list, diag: dict | None = None) -> dict:
    payload = {"schema": "ut.telemetry.v1", "seq": sequence, "readings": readings}
    if diag is not None:
        payload["diag"] = diag
    return payload


def reading(asset: str, metric: str, value: int, unit: str, quality: str) -> dict:
    return {"assetCode": asset, "metric": metric, "value": value,
            "unit": unit, "quality": quality}


# One healthy rotation, exactly the shape the producer emits: environment,
# both fans (duty in diag.pwmPercent), gas status, gas raw, actuators.
GOOD = [
    frame(1, [reading("ENV-01", "temperature", 23, "degC", "good"),
              reading("ENV-01", "humidity", 52, "%RH", "good")]),
    frame(2, [reading("FAN-01", "supply.voltage", 11, "V", "good"),
              reading("FAN-01", "rotational.speed", 2400, "rpm", "good")],
          {"relayActive": 1, "pwmPercent": 60}),
    frame(3, [reading("FAN-02", "supply.voltage", 11, "V", "good"),
              reading("FAN-02", "rotational.speed", 1600, "rpm", "good")],
          {"relayActive": 1, "pwmPercent": 45}),
    frame(4, [reading("GAS-01", "methane.alarm", 0, "bool", "good"),
              reading("GAS-01", "methane.warning", 0, "bool", "good"),
              reading("GAS-01", "oxygen.alarm", 0, "bool", "suspect"),
              reading("GAS-01", "co.alarm", 0, "bool", "suspect")]),
    frame(5, [reading("GAS-01", "methane.raw", 0, "adc", "good")]),
    frame(6, [reading("CTRL-01", "led.mode", 3, "enum", "good"),
              reading("CTRL-01", "led.brightnessPercent", 75, "percent", "good")]),
]

readings = validate(GOOD)
assert readings[("CTRL-01", "led.mode")]["value"] == 3
assert readings[("GAS-01", "methane.alarm")]["quality"] == "good"
# The two fans share a metric name and are told apart by their asset code.
assert readings[("FAN-01", "supply.voltage")]["value"] == 11
assert readings[("FAN-02", "supply.voltage")]["value"] == 11


def rejected(frames: list, label: str) -> None:
    try:
        validate(frames)
    except AssertionError:
        return
    raise AssertionError(f"accepted {label}")


# A whole-cycle burst that shares one sequence is the pre-C2 wire form: the
# consumer drops every frame after the first as a duplicate.
rejected([dict(f, seq=7) for f in GOOD], "a burst sharing one sequence")

# Frames out of order would trip the consumer's sequence gate.
rejected([GOOD[1], GOOD[0], GOOD[2], GOOD[3], GOOD[4], GOOD[5]],
         "a rotation with out-of-order sequences")

# A short cycle is a producer that dropped a frame.
rejected(GOOD[:5], "a five-frame rotation")

# The fan's actual duty has to be in the diagnostic block, not a ladder reading.
rejected(
    [dict(f, diag={}) if f["seq"] == 2 else f for f in GOOD],
    "a fan frame with no diag.pwmPercent",
)
rejected(
    [dict(f, diag={"pwmPercent": 145}) if f["seq"] == 2 else f for f in GOOD],
    "a fan frame whose duty exceeds 100",
)

# The operational gas vocabulary has to be present with a plausible quality.
rejected([f for f in GOOD if f["seq"] != 4], "a rotation with no gas status frame")
rejected(
    [dict(f, readings=[dict(r, quality="good") for r in f["readings"]])
     if f["seq"] == 4 else f for f in GOOD],
    "an uncalibrated oxygen channel claiming good quality",
)
rejected([dict(f, schema="ut.telemetry.v2") if f["seq"] == 1 else f for f in GOOD],
         "a frame with the wrong schema")

# The actuator frame is what carries the LED state the menu screen renders.
rejected([f for f in GOOD if f["seq"] != 6], "a rotation with no actuator frame")

# Two readings for the same metric in one cycle is a producer fault, not
# something to silently overwrite.
rejected(
    [dict(f, readings=f["readings"] + [reading("ENV-01", "temperature", 1, "degC", "good")])
     if f["seq"] == 1 else f for f in GOOD],
    "a cycle that repeats a metric",
)

print("Node A command probe validator: PASS")
