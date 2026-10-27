cmake_minimum_required(VERSION 3.22)
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
project(four_controller C ASM)

set(BOARD_ID "1" CACHE STRING "Physical board number, 1 through 4")
if(NOT BOARD_ID MATCHES "^[1-4]$")
    message(FATAL_ERROR "BOARD_ID must be a single board number from 1 to 4")
endif()

set(TARGET "four_ctrl0${BOARD_ID}")
set(CMAKE_C_STANDARD 11)

get_filename_component(BASE "${CMAKE_CURRENT_LIST_DIR}/../stm32f103rct6" ABSOLUTE)
set(HAL "${BASE}/Drivers/STM32F1xx_HAL_Driver")
set(HAL_PARTS hal hal_cortex hal_adc hal_adc_ex hal_dma hal_flash hal_flash_ex
              hal_gpio hal_gpio_ex hal_pwr hal_rcc hal_rcc_ex hal_uart)

set(SOURCES
    Core/Src/main.c
    Core/Src/board_config.c
    Core/Src/board_io.c
    Core/Src/actuators.c
    Core/Src/screen.c
    Core/Src/joystick.c
  Core/Src/menu.c
    Core/Src/st7735.c
    Core/Src/modbus_slave.c
    "${BASE}/Core/Src/system_stm32f1xx.c"
    "${BASE}/startup_stm32f103xe.s")
foreach(PART IN LISTS HAL_PARTS)
    list(APPEND SOURCES "${HAL}/Src/stm32f1xx_${PART}.c")
endforeach()

add_executable(${TARGET}.elf ${SOURCES})
target_include_directories(${TARGET}.elf PRIVATE
    Core/Inc
    "${BASE}/Core/Inc"
    "${HAL}/Inc" "${HAL}/Inc/Legacy"
    "${BASE}/Drivers/CMSIS/Include"
    "${BASE}/Drivers/CMSIS/Device/ST/STM32F1xx/Include")
target_compile_definitions(${TARGET}.elf PRIVATE
    USE_HAL_DRIVER STM32F103xE BOARD_ID=${BOARD_ID})
target_compile_options(${TARGET}.elf PRIVATE
    -mcpu=cortex-m3 -mthumb -Os -g3 -Wall -Wextra -Werror
    -ffunction-sections -fdata-sections)
target_link_options(${TARGET}.elf PRIVATE
    -mcpu=cortex-m3 -mthumb
    "-T${BASE}/STM32F103xx_FLASH.ld" --specs=nano.specs --specs=nosys.specs
    -Wl,--gc-sections -Wl,--print-memory-usage
    "-Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/${TARGET}.map")
add_custom_command(TARGET ${TARGET}.elf POST_BUILD
    COMMAND arm-none-eabi-objcopy -O binary "$<TARGET_FILE:${TARGET}.elf>"
            "${CMAKE_CURRENT_BINARY_DIR}/${TARGET}.bin"
    COMMAND arm-none-eabi-size "$<TARGET_FILE:${TARGET}.elf>")
