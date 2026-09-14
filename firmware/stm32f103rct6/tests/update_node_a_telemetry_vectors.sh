#!/bin/sh
# Regenerates tests/vectors/node_a_telemetry_vectors.h from the Node A producer
# formatter.  Run this after an intentional telemetry schema change, then re-run
# tests/run_node_a_telemetry_host.sh and the ESP suite.
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -f "$out/node_a_telemetry_vectors"; rmdir "$out"' EXIT
gcc -std=c11 -Wall -Wextra -Werror -ICore/Inc \
    Core/Src/node_a_telemetry.c tests/node_a_telemetry_vectors.c \
    -o "$out/node_a_telemetry_vectors"
"$out/node_a_telemetry_vectors" > tests/vectors/node_a_telemetry_vectors.h
echo "updated tests/vectors/node_a_telemetry_vectors.h"
