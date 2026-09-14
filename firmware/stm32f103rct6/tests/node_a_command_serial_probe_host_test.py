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
import re


PROBE = pathlib.Path(__file__).with_name("node_a_command_serial_probe.py")
TREE = ast.parse(PROBE.read_text(encoding="utf-8"), filename=str(PROBE))
NODE_A = PROBE.parent.parent / "Core" / "Src" / "node_a.c"

# The probe's module-level constants and the validator under test.  Importing
# the module itself would pull in pyserial, which the host test must not need;
# json is injected because the extracted functions use it.
WANTED = {
    "TELEMETRY_SCHEMA", "FRAME_COUNT", "GAS_QUALITY",
    "ROTATION_SIGNATURES", "readings_by_metric", "validate_telemetry_burst",
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
              reading("ENV-01", "humidity", 52, "%RH", "good"),
              reading("GAS-01", "smoke.alarm", 0, "bool", "good"),
              reading("GAS-01", "flame.alarm", 0, "bool", "good"),
              reading("LEVEL-L01", "level.detected", 0, "bool", "good"),
              reading("GAS-01", "oxygen.raw", 812, "adc", "suspect"),
              reading("GAS-01", "oxygen.voltage", 654, "mV", "suspect")]),
    frame(2, [reading("FAN-01", "supply.voltage", 11, "V", "good"),
              reading("FAN-01", "motor.current", 320, "mA", "good"),
              reading("FAN-01", "rotational.speed", 2400, "rpm", "good")],
          {"relayActive": 1, "pwmPercent": 60}),
    frame(3, [reading("FAN-02", "supply.voltage", 11, "V", "good"),
              reading("FAN-02", "motor.current", 280, "mA", "good"),
              reading("FAN-02", "rotational.speed", 1600, "rpm", "good")],
          {"relayActive": 1, "pwmPercent": 45}),
    frame(4, [reading("GAS-01", "methane.alarm", 0, "bool", "good"),
              reading("GAS-01", "methane.warning", 0, "bool", "good"),
              reading("GAS-01", "oxygen.alarm", 0, "bool", "suspect"),
              reading("GAS-01", "co.alarm", 0, "bool", "suspect")]),
    frame(5, [reading("GAS-01", "flame.rawLevel", 0, "bool", "good"),
              reading("GAS-01", "methane.raw", 0, "adc", "good"),
              reading("GAS-01", "methane.voltage", 0, "mV", "good"),
              reading("GAS-01", "co.raw", 138, "adc", "suspect"),
              reading("GAS-01", "co.voltage", 111, "mV", "suspect")]),
    frame(6, [reading("CTRL-01", "led.mode", 3, "enum", "good"),
              reading("CTRL-01", "led.brightnessPercent", 75, "percent", "good"),
              reading("CTRL-01", "buzzer.active", 0, "bool", "good"),
              reading("CTRL-01", "buzzer.muted", 0, "bool", "good")]),
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

# A sequence gap is a dropped frame even when the remaining payloads are
# otherwise well formed.
rejected([dict(f, seq=(f["seq"] + 1 if f["seq"] >= 3 else f["seq"]))
          for f in GOOD], "a rotation with a sequence gap")

# Frames out of order would trip the consumer's sequence gate.
rejected([GOOD[1], GOOD[0], GOOD[2], GOOD[3], GOOD[4], GOOD[5]],
         "a rotation with out-of-order sequences")

# Fixed rotation slots are part of the producer contract: sequence 1 is the
# environment frame, sequence 2/3 are the two fans, then gas status/raw and
# actuators.  A sorted, contiguous burst with the wrong asset mapping is still
# corrupt and must be rejected.
wrong_mapping = list(GOOD)
wrong_mapping[0] = frame(1, GOOD[1]["readings"], GOOD[1].get("diag"))
rejected(wrong_mapping, "a rotation with a metric/asset mapping mismatch")

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

# The forced telemetry command is one complete, retryable rotation request.
# This source contract keeps the serial probe and the firmware's actual
# scheduling semantics aligned: a failed later frame leaves the request armed
# and the main loop consumes it only after QueueFullRotation reports success.
NODE_A_SOURCE = NODE_A.read_text(encoding="utf-8")
assert "test_telemetry_burst = 1U;" in NODE_A_SOURCE
burst_branch = re.search(
    r"if \(test_telemetry_burst != 0U\)\s*\{(?P<body>.*?)\}\s*else\s*\{",
    NODE_A_SOURCE,
    re.DOTALL,
)
assert burst_branch is not None
assert re.search(
    r"if \s*\(\s*SendTelemetryFullRotation[\s\S]*?!= 0U\s*\)",
    burst_branch.group("body"),
)
assert re.search(r"if \s*\(\s*SendTelemetryFullRotation[\s\S]*?\)\s*\{[\s\S]*?--test_telemetry_burst", burst_branch.group("body"))

# ACK space is a runtime policy on both UART queues, not only a static size
# assertion.  Ordinary lines must use the reserved-aware enqueue path; ACKs may
# consume the reserve but their refusal must be surfaced in #STATE diagnostics.
assert "UartTx_InitWithReserve(&esp_tx_queue, NODE_A_UART_ACK_RESERVE_BYTES);" in NODE_A_SOURCE
assert "UartTx_InitWithReserve(&debug_tx_queue, NODE_A_UART_ACK_RESERVE_BYTES);" in NODE_A_SOURCE
assert "UartTx_EnqueuePriority" in NODE_A_SOURCE
assert re.search(r"ack_enqueue_failures", NODE_A_SOURCE)
assert re.search(r"state_enqueue_failures", NODE_A_SOURCE)
assert re.search(r'#STATE [^\"]*ack_enqueue_failures', NODE_A_SOURCE)
assert re.search(
    r"Command_ProcessPayload\(node_test_line \+ 14U, HAL_GetTick\(\)\);"
    r"[\s\S]*?NodeTest_ReportState\(\);",
    NODE_A_SOURCE,
)

print("Node A command probe validator: PASS")
