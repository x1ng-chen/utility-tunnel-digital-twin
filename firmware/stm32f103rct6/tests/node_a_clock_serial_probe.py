"""Bench probe: python tests/node_a_clock_serial_probe.py --port COM6."""
import argparse
import re
import time

import serial


def validate_clock(fields):
    expected = {
        "sysclk": 72000000,
        "hclk": 72000000,
        "pclk1": 36000000,
        "pclk2": 72000000,
        "adc": 12000000,
        "fan_pwm": 25000,
        "uart1": 9600,
        "uart2": 9600,
        "sht30_ms": 20,
        "ws_spi": 4500000,
    }
    for name, value in expected.items():
        assert int(fields[name]) == value, (name, fields.get(name))
    assert 1200 <= int(fields["ws_cell_ns"]) <= 1400


parser = argparse.ArgumentParser()
parser.add_argument("--port", required=True)
args = parser.parse_args()

with serial.Serial(args.port, 9600, timeout=0.2) as port:
    port.reset_input_buffer()
    port.write(b"#NODETEST CLOCK\n")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        line = port.readline().decode("ascii", errors="replace").strip()
        if not line.startswith("#CLOCK "):
            continue
        fields = dict(re.findall(r"(\w+)=(\d+)", line))
        try:
            validate_clock(fields)
        except (AssertionError, KeyError, ValueError) as error:
            raise AssertionError(line) from error
        print(line)
        break
    else:
        raise AssertionError("No #CLOCK response (command absent or board unavailable)")
