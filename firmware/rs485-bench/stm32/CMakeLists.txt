cmake_minimum_required(VERSION 3.22)
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
project(rs485_controller_bench C ASM)
set(BENCH_SLAVE_ADDRESS "4" CACHE STRING "Physical board number, 1 through 4")
if(NOT BENCH_SLAVE_ADDRESS MATCHES "^[1-4]$")
    message(FATAL_ERROR "BENCH_SLAVE_ADDRESS must be a single board number from 1 to 4")
endif()
set(BENCH_TARGET "rs485_ctrl0${BENCH_SLAVE_ADDRESS}_bench")
set(CMAKE_C_STANDARD 11)
get_filename_component(BASE "${CMAKE_CURRENT_LIST_DIR}/../../stm32f103rct6" ABSOLUTE)
set(HAL "${BASE}/Drivers/STM32F1xx_HAL_Driver")
set(HAL_PARTS hal hal_cortex hal_dma hal_flash hal_flash_ex hal_gpio hal_gpio_ex hal_pwr hal_rcc hal_rcc_ex hal_uart)
set(SOURCES main.c "${BASE}/Core/Src/system_stm32f1xx.c" "${BASE}/startup_stm32f103xe.s")
foreach(PART IN LISTS HAL_PARTS)
    list(APPEND SOURCES "${HAL}/Src/stm32f1xx_${PART}.c")
endforeach()
add_executable(${BENCH_TARGET}.elf ${SOURCES})
target_include_directories(${BENCH_TARGET}.elf PRIVATE
    ../common "${BASE}/Core/Inc" "${HAL}/Inc" "${HAL}/Inc/Legacy"
    "${BASE}/Drivers/CMSIS/Include" "${BASE}/Drivers/CMSIS/Device/ST/STM32F1xx/Include")
target_compile_definitions(${BENCH_TARGET}.elf PRIVATE USE_HAL_DRIVER STM32F103xE USER_VECT_TAB_ADDRESS BENCH_ADDRESS=${BENCH_SLAVE_ADDRESS})
target_compile_options(${BENCH_TARGET}.elf PRIVATE -mcpu=cortex-m3 -mthumb -Os -g3 -Wall -Wextra -Werror
    -ffunction-sections -fdata-sections)
target_link_options(${BENCH_TARGET}.elf PRIVATE -mcpu=cortex-m3 -mthumb
    "-T${BASE}/STM32F103xx_FLASH.ld" --specs=nano.specs --specs=nosys.specs
    -Wl,--gc-sections -Wl,--print-memory-usage "-Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/${BENCH_TARGET}.map")
add_custom_command(TARGET ${BENCH_TARGET}.elf POST_BUILD
    COMMAND arm-none-eabi-objcopy -O binary "$<TARGET_FILE:${BENCH_TARGET}.elf>" "${CMAKE_CURRENT_BINARY_DIR}/${BENCH_TARGET}.bin"
    COMMAND arm-none-eabi-size "$<TARGET_FILE:${BENCH_TARGET}.elf>")
