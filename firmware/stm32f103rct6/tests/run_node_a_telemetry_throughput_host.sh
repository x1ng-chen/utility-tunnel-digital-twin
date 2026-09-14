#!/bin/sh
# Multi-cycle throughput and backpressure contract for the Node A telemetry
# schedule.  Drives the real formatter and the real UART queue together under a
# virtual 9600-baud clock, so the whole-cycle burst that could not drain is
# covered by a test rather than by a comment.
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -f "$out/node_a_telemetry_throughput"; rmdir "$out"' EXIT

# gnu11 for memmem, which the line classifier uses.
gcc -std=gnu11 -Wall -Wextra -Werror -ICore/Inc -Itests -Itests/native_stubs \
    Core/Src/node_a_telemetry.c Core/Src/uart_tx_queue.c \
    tests/node_a_telemetry_throughput_host_test.c \
    -o "$out/node_a_telemetry_throughput"
"$out/node_a_telemetry_throughput"
