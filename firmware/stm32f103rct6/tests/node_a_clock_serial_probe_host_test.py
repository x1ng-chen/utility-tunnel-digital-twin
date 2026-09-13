"""Exercise the clock probe's result validator without a serial device."""

import ast
import pathlib


probe = pathlib.Path(__file__).with_name("node_a_clock_serial_probe.py")
tree = ast.parse(probe.read_text(encoding="utf-8"), filename=str(probe))
wanted = {"number", "validate_clock"}
namespace = {}
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in wanted:
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(probe), "exec"),
             namespace)
assert set(namespace) >= wanted, "missing probe validator functions"
validate = namespace["validate_clock"]

# A healthy board as the new firmware would report it.
valid = {
    "sysclk": "72000000", "hclk": "72000000", "pclk1": "36000000",
    "pclk2": "72000000", "adc": "12000000", "fan_pwm": "25000",
    "uart1": "9600", "uart2": "9600", "sht30_ms": "20",
    "ws_spi": "4500000", "ws_cell_ns": "1333",
    "rcc_cr": "0x03030003", "rcc_cfgr": "0x001D840A", "flash_acr": "0x00000012",
    "uart1_brr": "7500", "uart2_brr": "3750", "tim4_psc": "0", "tim4_arr": "2879",
    "spi2_cr1": "0x00000354", "systick_load": "71999",
}
validate(valid)

# The same board would be rejected if the boot tick were never re-derived.
invalid_cases = [
    ("rcc_cr", "0x01030003"),   # PLLRDY clear: the PLL never locked
    ("rcc_cr", "0x03010003"),   # HSERDY clear: the crystal never settled
    ("rcc_cr", "0x03020003"),   # HSEON clear: the HSE was never enabled
    ("systick_load", "7999"),
    ("pclk1", "72000000"),
    ("rcc_cfgr", "0x001D800A"),
    ("rcc_cfgr", "0x001D8408"),
    ("flash_acr", "0x00000010"),
    ("uart2_brr", "7500"),
    ("tim4_arr", "319"),
    ("spi2_cr1", "0x0000035C"),
    ("ws_cell_ns", "1111"),
    ("adc", "24000000"),
    ("fan_pwm", "12500"),
    ("sht30_ms", "100"),
]
for field, value in invalid_cases:
    candidate = dict(valid)
    candidate[field] = value
    try:
        validate(candidate)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"accepted invalid {field}={value}")

for missing in list(valid):
    candidate = dict(valid)
    del candidate[missing]
    try:
        validate(candidate)
    except (AssertionError, KeyError):
        pass
    else:
        raise AssertionError(f"accepted a report without {missing}")

print("Node A clock serial probe validator test: PASS")
