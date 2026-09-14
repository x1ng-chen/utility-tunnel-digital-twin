#!/bin/sh
# Host contract for the bounded UART transmit queue both controller images use.
# No board or HAL is involved: the test supplies its own HAL_UART_Transmit.
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -f "$out/uart_tx_queue"; rmdir "$out"' EXIT

gcc -std=c11 -Wall -Wextra -Werror -ICore/Inc -Itests/native_stubs \
    Core/Src/uart_tx_queue.c tests/uart_tx_queue_host_test.c \
    -o "$out/uart_tx_queue"
"$out/uart_tx_queue"
