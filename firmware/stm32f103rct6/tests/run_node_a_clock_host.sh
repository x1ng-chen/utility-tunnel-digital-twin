#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-python3}
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python

# Derives the CTRL-01 clock, peripheral, pin and interrupt contract from the
# production sources and the STM32 HAL headers.
"$PYTHON" tests/node_a_clock_host_test.py
# Exercises the bench probe's register validator without a serial device.
"$PYTHON" tests/node_a_clock_serial_probe_host_test.py
# The probe and the baseline modeller must at least parse and start.
"$PYTHON" -m py_compile tests/node_a_clock_serial_probe.py \
    tests/node_a_clock_baseline.py
# Re-derive the stored pre-retune 8 MHz baseline from git history.
"$PYTHON" tests/node_a_clock_baseline.py --check tests/node_a_clock_baseline.txt
