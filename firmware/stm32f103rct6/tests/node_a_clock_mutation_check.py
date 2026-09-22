"""Mutation check for the CTRL-01 clock/peripheral contract test.

The contract test is only as good as the defects it can catch, so this tool
copies the firmware tree to a temporary directory, injects one realistic defect
at a time into the copy, runs tests/node_a_clock_host_test.py against it and
reports whether the defect was caught.  The working tree is never modified.

    python3 tests/node_a_clock_mutation_check.py

Every seeded defect below is a change that would be a real firmware problem
(wrong clock, wrong PWM carrier, unbounded bus loop, lost deadline, ...), so a
MISSED line means the contract test has a hole worth closing.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

SOURCE = pathlib.Path(__file__).resolve().parent.parent
TEST = "tests/node_a_clock_host_test.py"

# (description, file, exact text to replace, replacement)
MUTATIONS = [
    # Tach counter wrap and RPM arithmetic.
    ("tach delta computed without the uint32 wrap",
     "Core/Src/node_a.c", "delta = pulses - fan1_tach_last_pulses;",
     "delta = (pulses < fan1_tach_last_pulses) ? 0U : (pulses - fan1_tach_last_pulses);"),
    ("tach counter widened to save a 'wrap' guard",
     "Core/Src/node_a.c", "static volatile uint32_t fan1_tach_pulses;",
     "static volatile uint64_t fan1_tach_pulses;"),
    ("tach RPM multiply widened back to 32 bits",
     "Core/Src/node_a.c", "return (uint32_t)(((uint64_t)delta * 60000ULL) /",
     "return (uint32_t)(((uint32_t)delta * 60000UL) /"),
    ("fan2 tach path alone gains a pulse clamp",
     "Core/Src/node_a.c", "delta = pulses - fan2_tach_last_pulses;",
     "delta = pulses - fan2_tach_last_pulses;\n  if (delta > 60000U) delta = 0U;"),
    ("pulses per revolution changed 2 -> 1",
     "Core/Src/node_a.c", "#define FAN_TACH_PULSES_PER_REVOLUTION            2U",
     "#define FAN_TACH_PULSES_PER_REVOLUTION            1U"),
    # Deadlines and budgets.
    ("deadline sign flipped (+ -> -) in Sht30_Read",
     "Core/Src/node_a.c", "const uint32_t deadline_ms = HAL_GetTick() + NODE_A_SHT30_TIMEOUT_MS;",
     "const uint32_t deadline_ms = HAL_GetTick() - NODE_A_SHT30_TIMEOUT_MS;"),
    ("deadline comparator inverted",
     "Core/Src/node_a.c", "return ((int32_t)((uint32_t)HAL_GetTick() - deadline_ms) >= 0) ? 1U : 0U;",
     "return ((int32_t)((uint32_t)HAL_GetTick() - deadline_ms) <= 0) ? 1U : 0U;"),
    ("deadline call-site polarity inverted in I2c_ReadRegister16",
     "Core/Src/node_a.c", "  if (I2c_DeadlineReached(deadline_ms) != 0U) return 0U;\n  *value =",
     "  if (I2c_DeadlineReached(deadline_ms) == 0U) return 0U;\n  *value ="),
    ("deadline check deleted from the I2c_WriteByte bit loop",
     "Core/Src/node_a.c", "    if (I2c_DeadlineReached(deadline_ms) != 0U) return 0U;\n    I2c_Sda(bus, (value & 0x80U)",
     "    I2c_Sda(bus, (value & 0x80U)"),
    ("helper arms its own 10 s deadline",
     "Core/Src/node_a.c", "  uint8_t high;\n  uint8_t low;\n  if (value == NULL) return 0U;",
     "  uint8_t high;\n  uint8_t low;\n  deadline_ms = HAL_GetTick() + NODE_A_INA226_TIMEOUT_MS;\n  if (value == NULL) return 0U;"),
    ("unbudgeted HAL_Delay added to the SHT30 byte loop",
     "Core/Src/node_a.c", "    response[i] = I2c_ReadByte(bus, i < (sizeof(response) - 1U), deadline_ms);",
     "    HAL_Delay(100U);\n    response[i] = I2c_ReadByte(bus, i < (sizeof(response) - 1U), deadline_ms);"),
    ("SHT30 conversion delay 20 -> 10 ms",
     "Core/Inc/node_a_clock_contract.h", "#define NODE_A_SHT30_MEASUREMENT_DELAY_MS            20UL",
     "#define NODE_A_SHT30_MEASUREMENT_DELAY_MS            10UL"),
    ("HAL_Delay overhead tick dropped from the budget model",
     "Core/Inc/node_a_clock_contract.h", "#define NODE_A_HAL_DELAY_OVERHEAD_TICKS               1UL",
     "#define NODE_A_HAL_DELAY_OVERHEAD_TICKS               0UL"),
    ("INA226 sample count 3 -> 2 (median reads out of bounds)",
     "Core/Inc/node_a_clock_contract.h", "#define NODE_A_INA226_SAMPLE_COUNT                    3UL",
     "#define NODE_A_INA226_SAMPLE_COUNT                    2UL"),
    ("third I2c_Recover call in Ina226_Read",
     "Core/Src/node_a.c", "    state->configured = 0U;\n    I2c_Recover(bus);\n    if (!Ina226_Configure(bus, state, reading, 1U, deadline_ms)",
     "    state->configured = 0U;\n    I2c_Recover(bus);\n    I2c_Recover(bus);\n    if (!Ina226_Configure(bus, state, reading, 1U, deadline_ms)"),
    # Bounded loops.
    ("unbounded while re-introduced in I2c_WriteByte",
     "Core/Src/node_a.c", "  uint8_t bit;\n  for (bit = 0U; bit < 8U; ++bit)\n  {\n    if (I2c_DeadlineReached(deadline_ms) != 0U) return 0U;",
     "  uint8_t bit;\n  for (bit = 0U; bit < 8U; ++bit)\n  {\n    while (HAL_GPIO_ReadPin(bus->port, bus->scl_pin) == GPIO_PIN_RESET) { }\n    if (I2c_DeadlineReached(deadline_ms) != 0U) return 0U;"),
    ("empty for(;;) re-introduced in the I2C region",
     "Core/Src/node_a.c", "  I2c_Sda(bus, GPIO_PIN_SET);\n  for (pulse = 0U; pulse < 9U; ++pulse)",
     "  I2c_Sda(bus, GPIO_PIN_SET);\n  for (;;) { }\n  for (pulse = 0U; pulse < 9U; ++pulse)"),
    ("bounded bus-state wait re-introduced as a for loop",
     "Core/Src/node_a.c", "  uint8_t bit;\n  for (bit = 0U; bit < 8U; ++bit)\n  {\n    if (I2c_DeadlineReached(deadline_ms) != 0U) return 0U;\n    I2c_Sda(bus, (value & 0x80U)",
     "  uint8_t bit;\n  for (bit = 0U; bit < 8U; ++bit)\n  {\n    uint16_t retry;\n    for (retry = 0U; retry < 250U; ++retry) { if (HAL_GPIO_ReadPin(bus->port, bus->scl_pin) != GPIO_PIN_RESET) break; }\n    if (I2c_DeadlineReached(deadline_ms) != 0U) return 0U;\n    I2c_Sda(bus, (value & 0x80U)"),
    # Clock tree, peripherals and pins.
    ("APB1/APB2 divider macros swapped between fields",
     "Core/Src/node_a.c", "clock.APB1CLKDivider = RCC_HCLK_DIV2;\n  clock.APB2CLKDivider = RCC_HCLK_DIV1;",
     "clock.APB1CLKDivider = RCC_HCLK_DIV1;\n  clock.APB2CLKDivider = RCC_HCLK_DIV2;"),
    ("APB1 /2 -> /1 (PCLK1 = 72 MHz)",
     "Core/Src/node_a.c", "clock.APB1CLKDivider = RCC_HCLK_DIV2;",
     "clock.APB1CLKDivider = RCC_HCLK_DIV1;"),
    ("HSE_VALUE 8 MHz -> 12 MHz",
     "Core/Inc/stm32f1xx_hal_conf.h", "#define HSE_VALUE    8000000U",
     "#define HSE_VALUE    12000000U"),
    ("FLASH latency 2 -> 1 wait state",
     "Core/Src/node_a.c", "HAL_RCC_ClockConfig(&clock, NODE_A_FLASH_LATENCY)",
     "HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_1)"),
    ("fan timer period 2879 -> 2871",
     "Core/Inc/node_a_clock_contract.h", "#define NODE_A_FAN_TIMER_PERIOD                    2879UL",
     "#define NODE_A_FAN_TIMER_PERIOD                    2871UL"),
    ("fan timer period alias becomes an expression",
     "Core/Src/node_a.c", "#define FAN_PWM_TIMER_PERIOD        NODE_A_FAN_TIMER_PERIOD",
     "#define FAN_PWM_TIMER_PERIOD        NODE_A_FAN_TIMER_PERIOD - 1U"),
    ("SPI2 BR_1 -> BR_0 (PCLK1/4)",
     "Core/Src/node_a.c", "SPI_CR1_BR_1; /* PCLK1 / 8 = 4.5 MHz. */",
     "SPI_CR1_BR_0; /* PCLK1 / 8 = 4.5 MHz. */"),
    ("second BR bit OR'd into SPI2 CR1",
     "Core/Src/node_a.c", "SPI_CR1_BR_1; /* PCLK1 / 8 = 4.5 MHz. */",
     "SPI_CR1_BR_1 | SPI_CR1_BR_0; /* PCLK1 / 8 = 4.5 MHz. */"),
    ("SPI2 enable statement deleted",
     "Core/Src/node_a.c", "  SPI2->CR1 |= SPI_CR1_SPE;\n", ""),
    ("WS2812 pixel count 18 -> 12",
     "Core/Src/node_a.c", "#define WS2812_PIXEL_COUNT                18U",
     "#define WS2812_PIXEL_COUNT                12U"),
    ("USART baud 9600 -> 19200",
     "Core/Inc/node_a_clock_contract.h", "#define NODE_A_UART_BAUD                            9600UL",
     "#define NODE_A_UART_BAUD                           19200UL"),
    ("gas ADC sample count 64 -> 32",
     "Core/Inc/node_a_clock_contract.h", "#define NODE_A_GAS_ADC_SAMPLE_COUNT                   64U",
     "#define NODE_A_GAS_ADC_SAMPLE_COUNT                   32U"),
    ("USART2 IRQ priority 1 -> 3 (below tach)",
     "Core/Inc/node_a_clock_contract.h", "#define NODE_A_ESP_IRQ_PRIORITY                       1U",
     "#define NODE_A_ESP_IRQ_PRIORITY                       3U"),
    ("tach EXTI priority 2 -> 3",
     "Core/Inc/node_a_clock_contract.h", "#define NODE_A_TACH_IRQ_PRIORITY                      2U",
     "#define NODE_A_TACH_IRQ_PRIORITY                      3U"),
    ("fan1 PWM PB8 -> PB10 (collides with i2c2)",
     "Core/Src/node_a.c", "#define FAN1_PWM_Pin                       GPIO_PIN_8",
     "#define FAN1_PWM_Pin                       GPIO_PIN_10"),
    ("flame input pull-up removed",
     "Core/Src/node_a.c", "gpio.Pin = FLAME_Pin; gpio.Mode = GPIO_MODE_INPUT; gpio.Pull = GPIO_PULLUP;",
     "gpio.Pin = FLAME_Pin; gpio.Mode = GPIO_MODE_INPUT; gpio.Pull = GPIO_NOPULL;"),
]


def run_test(tree):
    result = subprocess.run([sys.executable, TEST], cwd=str(tree),
                            capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip().splitlines()


def main():
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="node_a_mutation_"))
    tree = scratch / SOURCE.name
    shutil.copytree(SOURCE, tree,
                    ignore=shutil.ignore_patterns("build*", "__pycache__"))
    print(f"scratch copy: {tree}")

    clean, output = run_test(tree)
    if not clean:
        print("the unmodified copy must pass before mutations mean anything:")
        print("\n".join(output[-10:]))
        shutil.rmtree(scratch, ignore_errors=True)
        return 1

    missed = []
    for label, relative, old, new in MUTATIONS:
        path = tree / relative
        original = path.read_text(encoding="utf-8")
        if old not in original:
            print(f"SKIP (pattern not found): {label}")
            missed.append(f"{label} [pattern not found]")
            continue
        path.write_text(original.replace(old, new, 1), encoding="utf-8")
        still_passes, output = run_test(tree)
        path.write_text(original, encoding="utf-8")
        detail = f"  <- {output[-1][:90]}" if not still_passes else ""
        print(f"{'MISSED' if still_passes else 'caught'}: {label}{detail}")
        if still_passes:
            missed.append(label)

    shutil.rmtree(scratch, ignore_errors=True)
    print()
    print(f"mutation result: {len(MUTATIONS) - len(missed)}/{len(MUTATIONS)} caught")
    if missed:
        print("uncaught defects:\n  " + "\n  ".join(missed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
