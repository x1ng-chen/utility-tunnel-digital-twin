#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
CC=${ARM_GCC:-arm-none-eabi-gcc}
FLAGS="-std=c11 -Wall -Wextra -Werror -fsyntax-only -DSTM32F103xE"
INCLUDES="-ICore/Inc -IDrivers/STM32F1xx_HAL_Driver/Inc -IDrivers/CMSIS/Device/ST/STM32F1xx/Include -IDrivers/CMSIS/Include"
"$CC" $FLAGS $INCLUDES Core/Src/multi_sensor.c Core/Src/sensor_telemetry.c tests/sensor_telemetry_host_test.c
echo "sensor_telemetry host test: PASS"
