#!/bin/sh
# Seeded-defect gate for the Node A display suites.  Deliberately kept out of
# CI: it copies the tree once per mutation and recompiles both host binaries,
# so it takes about a minute.
set -eu
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-python3}
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python
"$PYTHON" tests/node_a_display_mutation_check.py
