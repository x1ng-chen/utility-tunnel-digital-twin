#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -f "$out/node_a_telemetry" "$out/node_a_telemetry_vectors" "$out/generated.h"; rmdir "$out"' EXIT

# The producer contract: the formatter must reproduce the committed vectors the
# ESP consumer suite parses.
gcc -std=c11 -Wall -Wextra -Werror -ICore/Inc -Itests \
    Core/Src/node_a_telemetry.c tests/node_a_telemetry_host_test.c \
    -o "$out/node_a_telemetry"
"$out/node_a_telemetry"

# And the committed vectors must still be what the generator produces, so the
# consumer-side payloads can never drift away from the producer silently.
gcc -std=c11 -Wall -Wextra -Werror -ICore/Inc \
    Core/Src/node_a_telemetry.c tests/node_a_telemetry_vectors.c \
    -o "$out/node_a_telemetry_vectors"
"$out/node_a_telemetry_vectors" --check tests/vectors/node_a_telemetry_vectors.h
