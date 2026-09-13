#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -f "$out/node_a_command"; rmdir "$out"' EXIT
gcc -std=c11 -Wall -Wextra -Werror -ICore/Inc \
    Core/Src/node_a_command.c tests/node_a_command_host_test.c \
    -o "$out/node_a_command"
"$out/node_a_command"
