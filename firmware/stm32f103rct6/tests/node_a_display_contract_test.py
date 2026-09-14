#!/usr/bin/env python3
"""Source model of the Node A secondary display contract.

The bus host test drives the adapter against mapped registers; this test covers
what a register double cannot see: that the display owns only free pins, that
SWD stays available while JTAG stays released, that the SPI3 bit rate follows
the production clock macros instead of a repeated constant, and that the
secondary screen stays read-only (no MQTT parsing, no joystick input)."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def function(source, name):
    """Return the body of a C function by brace matching."""
    start = source.index(name)
    start = source.index("{", start)
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated function {name}")


NODE_A = read("Core/Src/node_a.c")
MSP = read("Core/Src/stm32f1xx_hal_msp.c")
IT = read("Core/Src/stm32f1xx_it.c")
DISPLAY_HEADER = read("Core/Inc/st7735.h")
ADAPTER = read("Core/Src/st7735_bus_node_a.c")
SCREEN = read("Core/Src/node_a_status_screen.c")
CMAKE = read("CMakeLists.txt")


def pin_map(source):
    pins = dict(re.findall(r"^#define\s+(\w+)_Pin\s+(GPIO_PIN_\d+)", source,
                           re.MULTILINE))
    ports = dict(re.findall(r"^#define\s+(\w+)_GPIO_Port\s+(GPIO\w+)", source,
                            re.MULTILINE))
    return pins, ports


def pin_number(macro):
    return int(macro.rsplit("_", 1)[1])


def check_display_pins():
    """The display must sit on pins no preserved Node A peripheral owns."""
    branch = DISPLAY_HEADER[DISPLAY_HEADER.index("#elif defined(NODE_A_FIRMWARE)"):
                            DISPLAY_HEADER.index("#else")]
    pins = dict(re.findall(r"#define\s+(LCD_\w+_PIN)\s+(GPIO_PIN_\d+)", branch))
    ports = dict(re.findall(r"#define\s+(LCD_\w+_PORT)\s+(GPIO\w+)", branch))
    assert pins == {"LCD_SCK_PIN": "GPIO_PIN_3", "LCD_MOSI_PIN": "GPIO_PIN_5",
                    "LCD_RES_PIN": "GPIO_PIN_4", "LCD_DC_PIN": "GPIO_PIN_5",
                    "LCD_CS_PIN": "GPIO_PIN_6", "LCD_BLK_PIN": "GPIO_PIN_7"}, pins
    assert ports == {"LCD_CTRL_PORT": "GPIOC", "LCD_SPI_PORT": "GPIOB"}, ports

    display = {("GPIOB", pin_number(pins[name])) for name in
               ("LCD_SCK_PIN", "LCD_MOSI_PIN")}
    display |= {("GPIOC", pin_number(pins[name])) for name in
                ("LCD_RES_PIN", "LCD_DC_PIN", "LCD_CS_PIN", "LCD_BLK_PIN")}

    owned, owned_ports = pin_map(NODE_A)
    preserved = {f"{owned_ports[name]}{pin_number(owned[name])}": name
                 for name in owned if name in owned_ports}
    buses = re.findall(r"static const SoftI2cBus (\w+) = \{(GPIO\w+), (GPIO_PIN_\d+), "
                       r"(GPIO_PIN_\d+)\};", NODE_A)
    for name, port, scl, sda in buses:
        preserved[f"{port}{pin_number(scl)}"] = name
        preserved[f"{port}{pin_number(sda)}"] = name
    for key, name in {"GPIOA9": "USART1_TX", "GPIOA10": "USART1_RX",
                      "GPIOA2": "USART2_TX", "GPIOA3": "USART2_RX",
                      "GPIOC1": "ADC_CO", "GPIOC2": "ADC_METHANE",
                      "GPIOC3": "ADC_OXYGEN"}.items():
        preserved[key] = name

    for port, number in display:
        key = f"{port}{number}"
        assert key not in preserved, (
            f"the secondary display collides with {preserved[key]} on {key}")
    assert "GPIOB8" in preserved and preserved["GPIOB8"] == "FAN1_PWM", preserved
    assert "GPIOB9" in preserved and preserved["GPIOB9"] == "FAN2_PWM", preserved
    # SPI3 keeps its default pins, so no remap may be enabled anywhere.
    for source in (NODE_A, MSP, ADAPTER):
        assert "__HAL_AFIO_REMAP_SPI3" not in source, (
            "SPI3 must stay on its default PB3/PB5 pins")
    return f"display={sorted(display)} preserved={len(preserved)}"


def check_swd_preserved():
    """PB3 is JTDO: JTAG must stay disabled while SWD stays available."""
    msp_init = function(MSP, "HAL_MspInit")
    assert "__HAL_AFIO_REMAP_SWJ_NOJTAG();" in msp_init, msp_init
    for source in (NODE_A, MSP, ADAPTER, IT):
        for forbidden in ("__HAL_AFIO_REMAP_SWJ_DISABLE",
                          "__HAL_AFIO_REMAP_SWJ_NOJTAG_NOJTRST",
                          "AFIO_MAPR_SWJ_CFG_RESET"):
            assert forbidden not in source, forbidden
    return "jtag=disabled swd=retained"


def check_spi_bit_rate():
    """Derive the display clock from the CR1 field the adapter really writes."""
    cr1 = re.search(r"SPI3->CR1 = ([^;]+);", ADAPTER)
    assert cr1, "the adapter must configure SPI3->CR1 explicitly"
    assignment = cr1.group(1)
    field = 0
    for bit in re.findall(r"SPI_CR1_BR_(\d)", assignment):
        field |= 1 << int(bit)
    assert "SPI_CR1_BR" in assignment or field == 0, assignment
    divider = 1 << (field + 1)

    contract = read("Core/Inc/node_a_clock_contract.h")
    assert "NODE_A_HSE_HZ" in contract and "(HSE_VALUE)" in contract
    hal_conf = read("Core/Inc/stm32f1xx_hal_conf.h")
    hse = int(re.search(r"#define\s+HSE_VALUE\s+(\d+)", hal_conf).group(1))
    assert "RCC_PLL_MUL9" in contract, "the contract must keep the x9 PLL"
    multiplier = 9
    apb1_divider = int(re.search(r"#define\s+NODE_A_APB1_DIVIDER\s+(\d+)UL",
                                 contract).group(1))
    sysclk = hse * multiplier
    pclk1 = sysclk // apb1_divider
    hz = pclk1 // divider
    assert hz == 18000000, (hz, divider, pclk1)
    assert field == 0, "18 MHz from a 36 MHz PCLK1 needs BR = 0b000"
    assert "NODE_A_DISPLAY_IRQ_PRIORITY" in contract
    tach = int(re.search(r"#define\s+NODE_A_TACH_IRQ_PRIORITY\s+(\d+)U",
                         contract).group(1))
    display = int(re.search(r"#define\s+NODE_A_DISPLAY_IRQ_PRIORITY\s+(\d+)U",
                            contract).group(1))
    assert tach < display < 15, (tach, display)
    return f"pclk1={pclk1} divider={divider} spi={hz} prio=tach{tach}<dsp{display}"


def check_interrupt_wiring():
    """Both boards share one IRQ file; each DMA vector keeps its own guard."""
    node_a_guard = IT[IT.index("NODE_A_FIRMWARE"):]
    assert "void DMA2_Channel2_IRQHandler(void)" in node_a_guard
    assert "St7735Bus_DmaIrqHandler();" in node_a_guard
    node_b = function(IT, "DMA1_Channel3_IRQHandler")
    assert "St7735Bus_DmaIrqHandler();" in node_b
    assert "DMA2_Channel2_IRQn" not in node_b
    return "vectors=nodeA:dma2ch2 nodeB:dma1ch3"


def strip_c_noise(source):
    """Drop comments and string bodies: only real code tokens may be matched."""
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    source = re.sub(r"//[^\n]*", " ", source)
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', source)


def check_read_only_screen():
    """The secondary screen observes Node A; it never commands it."""
    for source, name in ((NODE_A, "node_a.c"), (SCREEN, "node_a_status_screen.c")):
        code = strip_c_noise(source)
        for forbidden in ("Joystick_", "joystick.h", "ADC1_IN10", "ADC1_IN11"):
            assert forbidden not in code, f"{name} must not take joystick input"
    code = strip_c_noise(SCREEN)
    for forbidden in ("MQTT", "mqtt", "esp_rx", "Command_ProcessPayload",
                      "NodeACommand_Apply", "QueueEspLine"):
        assert forbidden not in code, (
            f"the status screen must not parse the command stream: {forbidden}")
    # A parser that main never pumps is not a feature: the time sync and the
    # display tick both have to be reached from the main loop.
    main = function(NODE_A, "int main(void)")
    assert "EspTime_Poll();" in main, "the main loop must pump the time sync"
    assert "Status_Tick(now);" in main, "the main loop must tick the screen"
    assert "ST7735_Init();" in main, "the panel must be initialised at boot"
    tick = function(NODE_A, "Status_Tick")
    assert "NetworkTime_ToSnapshot(&esp_clock" in tick
    assert "NodeAStatus_Update(&status_screen" in tick
    assert "NetworkTime_Update(&esp_clock" in NODE_A, "Node A must consume ut.time.sync.v1"
    assert "memset(&status_sensors" in main, "the snapshot must start defined"
    # The display must not read sensors itself: the values come from the
    # telemetry block, so no second I2C transaction is added per frame.
    tick_tokens = ("Sht30_Read", "Ina226_Read", "GasAdc_ReadRaw", "Fan1Tach_ReadRpm")
    for token in tick_tokens:
        assert token not in tick, f"the display tick must not re-read {token}"
    return "read_only=no_joystick no_mqtt time=network_time"


def check_alarm_reaction_path():
    """A fresh gas sample must move the safety state and the panel first.

    The INA226 software-I2C reads that follow the gas sample are budgeted at
    thousands of milliseconds, so an alarm evaluated before them but painted
    after them would take the screen over far too late.  Node A therefore has to
    re-run the gas safety transition and the display tick on the sample it just
    took, before either blocking read."""
    main = function(NODE_A, "int main(void)")
    gas_sample = main.index("GasAlarm_Update(")
    ina = [index for index in range(len(main))
           if main.startswith("Ina226_Read(", index)]
    assert len(ina) == 2, f"expected exactly two INA226 reads, found {len(ina)}"

    redraw = [index for index in range(len(main))
              if main.startswith("Status_Tick(now)", index)]
    assert redraw, "the main loop must tick the screen"
    assert len(redraw) == 2, (
        "the tick belongs on both the telemetry and the plain path, not on a "
        f"shared trailing one: {len(redraw)}")
    assert main.count("telemetry_due") == 4, (
        "one telemetry-due computation must drive both the tick and the block")

    after_sample = [index for index in redraw if index > gas_sample]
    assert after_sample, (
        "a fresh gas sample must repaint before the loop moves on")
    for index in ina:
        assert after_sample[0] < index, (
            "the gas repaint must precede every blocking INA226 read")
    assert len(after_sample) == 1, "the telemetry path must repaint exactly once"

    before_sample = [index for index in redraw if index < gas_sample]
    assert len(before_sample) == 1, (
        "the plain path must keep its own repaint, after the smoke/flame polls")
    for poll in ("Smoke_Poll(now);", "Flame_Poll(now);", "Level_Poll(now);"):
        assert main.index(poll) < before_sample[0], (
            f"{poll} must be sampled by the repaint that precedes telemetry")
    assert main.index("GasVentilation_Update(now);") < before_sample[0], (
        "the plain path must keep re-evaluating ventilation")

    # The gas transition has to run again on the sample the alarm was computed
    # from; running it only before the sample would delay the relay and fans.
    transitions = [index for index in range(len(main))
                   if main.startswith("GasVentilation_Update(now);", index)]
    assert len(transitions) == 2, len(transitions)
    assert before_sample[0] < transitions[1] < after_sample[0], (
        "the gas transition must sit between the two repaints")
    return "gas_sample<vent<repaint<ina226"


def check_build_registration():
    """Each adapter is registered for exactly one variant."""
    blocks = {}
    pattern = re.compile(
        r'if\(FIRMWARE_VARIANT STREQUAL "(node_a|node_b)"\)\s*\n\s*'
        r"target_sources\((.*?)\n\s*\)", re.S)
    for variant, body in pattern.findall(CMAKE):
        blocks[variant] = body
    assert set(blocks) == {"node_a", "node_b"}, sorted(blocks)
    for source in ("Core/Src/st7735_bus_node_a.c", "Core/Src/node_a_status_screen.c",
                   "Core/Src/network_time.c"):
        assert source in blocks["node_a"], source
    assert "Core/Src/st7735_bus_node_b.c" in blocks["node_b"]
    for variant, body in blocks.items():
        other = "node_b" if variant == "node_a" else "node_a"
        assert f"st7735_bus_{other}.c" not in body, (
            f"the {other} adapter must never link into the {variant} image")
    return "cmake=node_a_only"


def main():
    print("Node A display contract model:")
    print("  " + check_display_pins())
    print("  " + check_swd_preserved())
    print("  " + check_spi_bit_rate())
    print("  " + check_interrupt_wiring())
    print("  " + check_read_only_screen())
    print("  " + check_alarm_reaction_path())
    print("  " + check_build_registration())
    print("Node A display contract model: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
