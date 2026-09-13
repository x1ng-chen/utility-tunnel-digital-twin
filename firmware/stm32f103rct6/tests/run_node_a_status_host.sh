#!/bin/sh
# Host suites for the Node A secondary display.  The two C suites drive the
# real page model and the real SPI3/DMA2 adapter against a register double; the
# Python suite covers the source-level contracts a double cannot see.
set -eu
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-python3}
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python
out=$(mktemp -d)
trap 'rm -f "$out/status" "$out/bus"; rmdir "$out"' EXIT
includes='-ICore/Inc -IDrivers/STM32F1xx_HAL_Driver/Inc -IDrivers/CMSIS/Device/ST/STM32F1xx/Include -IDrivers/CMSIS/Include'

gcc -std=c11 -Wall -Wextra -Werror -Itests/stubs -ICore/Inc \
    Core/Src/node_a_status_screen.c tests/node_a_status_screen_host_test.c \
    -o "$out/status"
"$out/status"

gcc -std=c11 -D_GNU_SOURCE -DNODE_A_FIRMWARE -DSTM32F103xE -DUSE_HAL_DRIVER -O2 \
    -ffunction-sections -fdata-sections -Wno-int-to-pointer-cast $includes \
    Core/Src/st7735_bus_node_a.c tests/node_a_display_bus_host_test.c \
    -Wl,--gc-sections -o "$out/bus"
"$out/bus"

"$PYTHON" tests/node_a_display_contract_test.py
