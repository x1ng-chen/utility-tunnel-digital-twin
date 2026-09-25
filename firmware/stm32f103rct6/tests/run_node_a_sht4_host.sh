#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -f "$out/sht4"; rmdir "$out"' EXIT
gcc -std=c11 -Wall -Wextra -Werror -Itests/sensor_bank_stubs -ICore/Inc \
  Core/Src/node_a_sensor_bank.c Core/Src/multi_sensor.c \
  tests/node_a_sht4_host_test.c -o "$out/sht4"
"$out/sht4"
