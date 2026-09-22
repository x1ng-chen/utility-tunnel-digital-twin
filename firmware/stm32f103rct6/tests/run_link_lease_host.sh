#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -f "$out/link_lease"; rmdir "$out"' EXIT
gcc -std=c11 -Wall -Wextra -Werror -ICore/Inc \
  tests/link_lease_host_test.c -o "$out/link_lease"
"$out/link_lease"
