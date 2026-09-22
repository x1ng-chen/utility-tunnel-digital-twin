#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -f "$out/task8"; rmdir "$out"' EXIT
gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -ICore/Inc -Itests/stubs \
  Core/Src/screen_snapshot.c Core/Src/network_time.c Core/Src/menu_command.c \
  Core/Src/kk_ui_catalog.c Core/Src/kk_ui_motion.c \
  Core/Src/ui_state.c Core/Src/ui_renderer.c tests/task8_host_test.c -o "$out/task8"
"$out/task8"
python3 tests/node_b_uart_contract_test.py
