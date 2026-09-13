"""Bench probe: python tests/node_a_clock_serial_probe.py --port COM6.

The firmware reports the peripheral registers it programmed, so this validator
checks the register readbacks and re-derives every frequency from those
registers instead of trusting the firmware's own arithmetic.
"""
import argparse
import re
import time

import serial


def number(fields, name):
    """Register readbacks arrive as 0x... hex, frequencies as decimal."""
    return int(fields[name], 0)


def validate_clock(fields):
    expected = {
        "sysclk": 72000000,
        "hclk": 72000000,
        "pclk1": 36000000,
        "pclk2": 72000000,
        "fan_pwm": 25000,
        "uart1": 9600,
        "uart2": 9600,
        "ws_spi": 4500000,
        "sht30_ms": 20,
    }
    for name, value in expected.items():
        assert number(fields, name) == value, (name, fields.get(name))
    assert 650 <= number(fields, "ws_cell_ns") <= 1850, fields["ws_cell_ns"]

    pclk1 = number(fields, "pclk1")
    pclk2 = number(fields, "pclk2")
    rcc_cfgr = number(fields, "rcc_cfgr")
    flash_acr = number(fields, "flash_acr")
    uart1_brr = number(fields, "uart1_brr")
    uart2_brr = number(fields, "uart2_brr")
    tim4_psc = number(fields, "tim4_psc")
    tim4_arr = number(fields, "tim4_arr")
    spi2_cr1 = number(fields, "spi2_cr1")

    # HSE and PLL must be enabled and locked, with PLLCLK selected.
    rcc_cr = number(fields, "rcc_cr")
    assert rcc_cr & 0x00010000, "HSE is off"
    assert rcc_cr & 0x01000000, "PLL is off"
    assert (rcc_cfgr & 0x3) == 0x2 and ((rcc_cfgr >> 2) & 0x3) == 0x2, (
        "SYSCLK is not PLLCLK")
    assert ((rcc_cfgr >> 4) & 0xF) == 0, "AHB prescaler is not /1"
    assert ((rcc_cfgr >> 8) & 0x7) == 0x4, "APB1 prescaler is not /2"
    assert ((rcc_cfgr >> 11) & 0x7) == 0, "APB2 prescaler is not /1"
    assert ((rcc_cfgr >> 16) & 0x1) == 0x1, "PLL source is not HSE"
    assert ((rcc_cfgr >> 18) & 0xF) + 2 == 9, "PLL multiplier is not x9"
    assert rcc_cfgr == 0x001D840A, hex(rcc_cfgr)

    # Two FLASH wait states with the prefetch buffer on.
    assert (flash_acr & 0x7) == 0x2, "FLASH latency is not two wait states"
    assert flash_acr & 0x10, "FLASH prefetch is off"

    # Re-derive the ADC clock, timer carrier, baud rates and SPI clock from the
    # registers the MCU actually holds.
    adc_divider = (((rcc_cfgr >> 14) & 0x3) + 1) * 2
    assert number(fields, "adc") == pclk2 // adc_divider == 12000000
    assert number(fields, "adc") <= 12000000, "ADC clock exceeds 12 MHz"

    apb1_prescaled = ((rcc_cfgr >> 8) & 0x7) != 0
    timer_hz = pclk1 * 2 if apb1_prescaled else pclk1
    assert number(fields, "fan_pwm") == timer_hz // ((tim4_psc + 1) * (tim4_arr + 1))
    assert (tim4_psc, tim4_arr) == (0, 2879), (tim4_psc, tim4_arr)

    # BRR holds USARTDIV in sixteenths, so the programmed baud is PCLK / BRR.
    assert (uart1_brr, uart2_brr) == (7500, 3750), (uart1_brr, uart2_brr)
    assert number(fields, "uart1") == pclk2 // uart1_brr == 9600
    assert number(fields, "uart2") == pclk1 // uart2_brr == 9600
    assert pclk2 % uart1_brr == 0 and pclk1 % uart2_brr == 0, "baud error"

    spi_divider = 1 << (((spi2_cr1 >> 3) & 0x7) + 1)
    assert (spi2_cr1 & 0x354) == 0x354, "SPI2 master/software-slave/BR/SPE changed"
    assert number(fields, "ws_spi") == pclk1 // spi_divider == 4500000
    assert number(fields, "ws_cell_ns") == 6 * 1000000000 // 4500000

    # The HAL tick must have been re-derived from the 72 MHz HCLK.
    assert number(fields, "systick_load") == 71999, fields["systick_load"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    args = parser.parse_args()

    with serial.Serial(args.port, 9600, timeout=0.2) as port:
        port.reset_input_buffer()
        port.write(b"#NODETEST CLOCK\n")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            line = port.readline().decode("ascii", errors="replace").strip()
            if not line.startswith("#CLOCK "):
                continue
            fields = dict(re.findall(r"(\w+)=(\w+)", line))
            try:
                validate_clock(fields)
            except (AssertionError, KeyError, ValueError) as error:
                raise AssertionError(line) from error
            print(line)
            break
        else:
            raise AssertionError(
                "No #CLOCK response (command absent or board unavailable)")


if __name__ == "__main__":
    main()
