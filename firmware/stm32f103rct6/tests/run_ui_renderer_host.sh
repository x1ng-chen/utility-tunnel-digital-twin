#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -f "$out/ui_renderer" "$out/ui_menu"; rmdir "$out"' EXIT
gcc -std=c11 -Wall -Wextra -Werror -Itests/stubs -ICore/Inc \
    Core/Src/kk_ui_catalog.c Core/Src/kk_ui_motion.c Core/Src/ui_renderer.c Core/Src/ui_state.c tests/ui_renderer_host_test.c \
    -o "$out/ui_renderer"
"$out/ui_renderer"
gcc -std=c11 -Wall -Wextra -Werror -Itests/stubs -ICore/Inc \
    Core/Src/kk_ui_catalog.c Core/Src/kk_ui_motion.c Core/Src/ui_renderer.c Core/Src/ui_state.c Core/Src/ui_menu.c tests/ui_menu_host_test.c \
    -o "$out/ui_menu"
"$out/ui_menu"
