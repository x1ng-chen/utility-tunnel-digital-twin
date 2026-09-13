#!/bin/sh
# Seeded-defect check for the CTRL-01 contract test.  Deliberately kept out of
# the CI path because it copies the tree and re-runs the model test once per
# mutation (about a minute); run it when the contract test changes.
set -eu
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-python3}
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python
"$PYTHON" tests/node_a_clock_mutation_check.py
