#!/bin/sh
# Strict ARM compile of the CTRL-01 contract test and of the Node A sources that
# carry the clock, peripheral and pin configuration.  Needs arm-none-eabi-gcc on
# PATH (or ARM_GCC set to it); the real STM32 HAL headers are included, so this
# cannot run on a host compiler.
set -eu
cd "$(dirname "$0")/.."
CC=${ARM_GCC:-arm-none-eabi-gcc}
if ! command -v "$CC" >/dev/null 2>&1; then
    echo "run_node_a_contract_arm.sh needs arm-none-eabi-gcc (set ARM_GCC)" >&2
    exit 1
fi
FLAGS="-std=c11 -Wall -Wextra -Werror -fsyntax-only -DSTM32F103xE -DNODE_A_FIRMWARE=1"
INCLUDES="-ICore/Inc -IDrivers/STM32F1xx_HAL_Driver/Inc
          -IDrivers/CMSIS/Device/ST/STM32F1xx/Include -IDrivers/CMSIS/Include"

# shellcheck disable=SC2086
"$CC" $FLAGS $INCLUDES tests/node_a_sensor_map_test.c
# shellcheck disable=SC2086
"$CC" $FLAGS $INCLUDES Core/Src/node_a.c
# shellcheck disable=SC2086
"$CC" $FLAGS $INCLUDES Core/Src/stm32f1xx_hal_msp.c
echo "Node A ARM clock/pin contract test: PASS"
