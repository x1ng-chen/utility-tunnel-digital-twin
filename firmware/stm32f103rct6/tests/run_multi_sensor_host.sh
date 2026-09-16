#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -f "$out/multi_sensor"; rmdir "$out"' EXIT
gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -ICore/Inc \
    Core/Src/multi_sensor.c tests/multi_sensor_host_test.c \
    -o "$out/multi_sensor"
"$out/multi_sensor"
