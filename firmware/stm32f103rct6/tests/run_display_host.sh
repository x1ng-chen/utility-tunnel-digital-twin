#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -f "$out/raster" "$out/bus"; rmdir "$out"' EXIT
includes='-ICore/Inc -IDrivers/STM32F1xx_HAL_Driver/Inc -IDrivers/CMSIS/Device/ST/STM32F1xx/Include -IDrivers/CMSIS/Include'
gcc -std=c11 -D_GNU_SOURCE -DNODE_B_FIRMWARE -DSTM32F103xE -DUSE_HAL_DRIVER -O2 \
    -ffunction-sections -fdata-sections -Wno-int-to-pointer-cast $includes \
    Core/Src/st7735.c tests/display_host_test.c -Wl,--gc-sections -o "$out/raster"
"$out/raster"
gcc -std=c11 -D_GNU_SOURCE -DNODE_B_FIRMWARE -DSTM32F103xE -DUSE_HAL_DRIVER -O2 \
    -ffunction-sections -fdata-sections -Wno-int-to-pointer-cast $includes \
    Core/Src/st7735_bus_node_b.c tests/display_bus_host_test.c -Wl,--gc-sections -o "$out/bus"
"$out/bus"
python3 tests/display_clock_host_test.py
python3 tests/display_run_host_test.py
python3 tests/display_serial_probe_host_test.py
