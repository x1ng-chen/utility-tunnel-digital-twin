#!/bin/sh
# Runs the two host suites that make up the PlatformIO `native` environment.
#
# `pio test -e native` is the intended entry point, but it needs gcc/g++ on
# PATH; on the Windows host used for this branch the native parser does not
# find them, so this script performs the same build directly.  It compiles the
# same sources with the same flags, and it compiles BOTH roles into one binary,
# which is what the suites assume: they cover role-specific routing and
# cross-role rejection together.
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

run_suite() {
  name="$1"
  g++ -std=gnu++17 -Wall -Wextra -Werror -Iinclude -Isrc \
      src/screen_protocol.cpp src/screen_routing.cpp "test/$name/test_main.cpp" \
      -o "$out/$name"
  "$out/$name"
}

run_suite test_screen_protocol
run_suite test_screen_routing
echo "native host suites: ok"
