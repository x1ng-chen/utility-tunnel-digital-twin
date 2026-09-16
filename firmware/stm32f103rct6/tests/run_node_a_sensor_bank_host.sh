#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
CC=${ARM_GCC:-arm-none-eabi-gcc}
FLAGS="-std=c11 -Wall -Wextra -Werror -fsyntax-only -DSTM32F103xE -DNODE_A_FIRMWARE=1"
INCLUDES="-ICore/Inc -IDrivers/STM32F1xx_HAL_Driver/Inc -IDrivers/CMSIS/Device/ST/STM32F1xx/Include -IDrivers/CMSIS/Include"
"$CC" $FLAGS $INCLUDES Core/Src/node_a_sensor_bank.c tests/node_a_sensor_bank_host_test.c
echo "node_a_sensor_bank host test: PASS"
