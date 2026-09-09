cmake_minimum_required(VERSION 3.22)

#
# This file is generated only once,
# and is not re-generated if converter is called multiple times.
#
# User is free to modify the file as much as necessary
#

# Setup compiler settings
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS ON)


# Define the build type
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Debug")
endif()

# Set the project name
set(CMAKE_PROJECT_NAME stm32_controller)

# Enable compile command to ease indexing with e.g. clangd
set(CMAKE_EXPORT_COMPILE_COMMANDS TRUE)

# Core project settings
project(${CMAKE_PROJECT_NAME})
message("Build type: " ${CMAKE_BUILD_TYPE})

# Node A is the active controller image: SHT30 acquisition plus ESP8266
# telemetry. The old TFT/DHT11 bench remains available only as `bench` for
# historical regression work and must not be flashed as the active controller.
set(FIRMWARE_VARIANT "node_a" CACHE STRING "Firmware image to build")
set_property(CACHE FIRMWARE_VARIANT PROPERTY STRINGS bench node_a node_b)
if(FIRMWARE_VARIANT STREQUAL "node_a")
    set(STM32_APP_MAIN "${CMAKE_CURRENT_SOURCE_DIR}/Core/Src/node_a.c")
elseif(FIRMWARE_VARIANT STREQUAL "node_b")
    set(STM32_APP_MAIN "${CMAKE_CURRENT_SOURCE_DIR}/Core/Src/node_b.c")
elseif(FIRMWARE_VARIANT STREQUAL "bench")
    set(STM32_APP_MAIN "${CMAKE_CURRENT_SOURCE_DIR}/Core/Src/main.c")
else()
    message(FATAL_ERROR "Unknown FIRMWARE_VARIANT: ${FIRMWARE_VARIANT}")
endif()

# Enable CMake support for ASM and C languages
enable_language(C ASM)

# Create an executable object type
add_executable(${CMAKE_PROJECT_NAME})

if(FIRMWARE_VARIANT STREQUAL "node_a")
    target_compile_definitions(${CMAKE_PROJECT_NAME} PRIVATE NODE_A_FIRMWARE=1)
endif()

# Add STM32CubeMX generated sources
add_subdirectory(cmake/stm32cubemx)

# Link directories setup
target_link_directories(${CMAKE_PROJECT_NAME} PRIVATE
    # Add user defined library search paths
)

# Add sources to executable
target_sources(${CMAKE_PROJECT_NAME} PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/Core/Src/st7735.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/Core/Src/ui_menu.c"
)

# The display driver sends every pixel over software SPI. Keep the rest of
# Debug easy to inspect, but optimize the two display-critical source files.
set_source_files_properties(
    "${CMAKE_CURRENT_SOURCE_DIR}/Core/Src/st7735.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/Core/Src/ui_menu.c"
    PROPERTIES COMPILE_OPTIONS "-O3"
)

# Add include paths
target_include_directories(${CMAKE_PROJECT_NAME} PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/Core/Inc"
)

# Generate the raw binary used by STM32CubeProgrammer/UART bootloader after
# every successful link. The CubeMX CMake project otherwise only updates ELF.
add_custom_command(TARGET ${CMAKE_PROJECT_NAME} POST_BUILD
    COMMAND "${CMAKE_OBJCOPY}" -O binary
            "$<TARGET_FILE_NAME:${CMAKE_PROJECT_NAME}>"
            "${CMAKE_PROJECT_NAME}.bin"
    WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
    COMMENT "Generating ${CMAKE_PROJECT_NAME}.bin"
)

# Add project symbols (macros)
target_compile_definitions(${CMAKE_PROJECT_NAME} PRIVATE
    # Add user defined symbols
)

# Remove wrong libob.a library dependency when using cpp files
list(REMOVE_ITEM CMAKE_C_IMPLICIT_LINK_LIBRARIES ob)

# Add linked libraries
target_link_libraries(${CMAKE_PROJECT_NAME}
    stm32cubemx

    # Add user defined libraries
)
