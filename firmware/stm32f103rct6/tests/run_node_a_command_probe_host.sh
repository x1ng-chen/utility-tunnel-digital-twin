#!/bin/sh
# Exercises the Node A command probe without a serial device: its telemetry
# validator has to keep up with the wire the producer actually emits, so a
# producer change fails here rather than at the bench.
set -eu
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-python3}
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python

# The probe itself must at least parse (it imports pyserial only when run).
"$PYTHON" -m py_compile tests/node_a_command_serial_probe.py
"$PYTHON" tests/node_a_command_serial_probe_host_test.py
