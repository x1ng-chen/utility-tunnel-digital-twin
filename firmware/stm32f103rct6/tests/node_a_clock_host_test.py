"""Persistent CTRL-01 clock/peripheral contract test.

Unlike a probe that echoes the same compile-time constants it checks, this test
parses the production sources and the STM32 HAL headers, resolves the selection
macros the firmware actually assigns (not merely mentions), derives the
resulting clock tree, peripheral divisors, RPM math, pin map and interrupt
order, and compares them with the declared contract.

What it catches: a retune, a swapped or re-pointed divider selection, a changed
timer period or SPI divisor, a changed pin, mode or pull, a changed interrupt
priority, a removed or inverted deadline check at any call site, a budget the
code has outgrown, a re-scoped deadline, and an unbounded or bus-waiting loop.
What it cannot catch by construction: a change inside the vendored HAL itself,
anything not expressed in the sources it parses, and behaviour that only exists
at run time on real hardware - run tests/node_a_clock_serial_probe.py against the
board for that.

Run it with:

    bash tests/run_node_a_clock_host.sh
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORE = ROOT / "Core"
DRIVERS = ROOT / "Drivers"
HAL_INC = DRIVERS / "STM32F1xx_HAL_Driver/Inc"
HAL_SRC = DRIVERS / "STM32F1xx_HAL_Driver/Src"
DEVICE = HAL_INC.parent.parent / "CMSIS/Device/ST/STM32F1xx/Include/stm32f103xe.h"
CORE_CM3 = DRIVERS / "CMSIS/Include/core_cm3.h"
SYSTEM_SRC = CORE / "Src/system_stm32f1xx.c"
NODE_A_SRC = CORE / "Src/node_a.c"
MSP_SRC = CORE / "Src/stm32f1xx_hal_msp.c"
NODE_B_BUS_SRC = CORE / "Src/st7735_bus_node_b.c"


def read(path):
    return pathlib.Path(path).read_text(encoding="utf-8")


NODE_A = read(NODE_A_SRC)
MSP = read(MSP_SRC)
NODE_B_BUS = read(NODE_B_BUS_SRC)
MAIN_H = read(CORE / "Inc/main.h")
SYSTEM = read(SYSTEM_SRC)
CONTRACT = read(CORE / "Inc/node_a_clock_contract.h")
SENSOR_MAP = read(CORE / "Inc/node_a_sensor_map.h")
HAL_CONF = read(CORE / "Inc/stm32f1xx_hal_conf.h")
HAL = read(HAL_INC / "stm32f1xx_hal.h")
HAL_RCC = read(HAL_INC / "stm32f1xx_hal_rcc.h")
HAL_RCC_EX = read(HAL_INC / "stm32f1xx_hal_rcc_ex.h")
HAL_RCC_C = read(HAL_SRC / "stm32f1xx_hal_rcc.c")
HAL_FLASH = read(HAL_INC / "stm32f1xx_hal_flash.h")
HAL_ADC = read(HAL_INC / "stm32f1xx_hal_adc.h")
HAL_UART = read(HAL_INC / "stm32f1xx_hal_uart.h")
HAL_C = read(HAL_SRC / "stm32f1xx_hal.c")
DEVICE_TEXT = read(DEVICE)
CORE_CM3_TEXT = read(CORE_CM3)


def strip_c_noise(source):
    """Remove comments and literals so brace/paren matching is reliable."""
    without_comments = re.sub(r"/\*.*?\*/|//[^\n]*", " ", source, flags=re.DOTALL)
    return re.sub(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', '""', without_comments)


def function(source, name):
    """Return the body of a function definition, braces balanced."""
    text = strip_c_noise(source)
    match = re.search(rf"\b{re.escape(name)}\s*\([^{{;]*?\)\s*\{{", text, re.DOTALL)
    assert match, f"function {name} not found"
    depth = 1
    end = match.end()
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[match.start():end]


def build_defines(*sources):
    """Collect object-like #define bodies (multi-line ones joined)."""
    defines = {}
    for source in sources:
        pattern = r"^[ \t]*#define[ \t]+(\w+)[ \t]+((?:[^\r\n\\]|\\(?:\r?\n))*)"
        for match in re.finditer(pattern, source, re.MULTILINE):
            name, body = match.group(1), match.group(2)
            body = re.sub(r"\\\r?\n", " ", body)
            # Strip whole, trailing-unterminated and line comments.
            body = re.sub(r"/\*.*?\*/|/\*.*$|//.*$", " ", body)
            defines[name] = body.strip()
    return defines


def build_enums(*sources):
    """Collect `NAME = value` members of the HAL enum types."""
    members = {}
    for source in sources:
        for block in re.findall(r"(?:typedef\s+)?enum\s*\{(.*?)\}", source,
                                re.DOTALL):
            for match in re.finditer(r"(\w+)\s*=\s*([^,\n]+)", block):
                members.setdefault(match.group(1), match.group(2).strip())
    return members


# #defines win over enum members; both are needed (HAL_TICK_FREQ_DEFAULT is an
# enumerator while the RCC selections are macros).  Library sources come first
# and the project configuration last, because C include guards make the first
# definition win: system_stm32f1xx.c carries an `#if !defined(HSE_VALUE)` 8 MHz
# fallback that must not shadow the crystal value in stm32f1xx_hal_conf.h.
DEFINES = {**build_enums(HAL, DEVICE_TEXT, HAL_ADC, HAL_RCC),
           **build_defines(DEVICE_TEXT, HAL_RCC, HAL_RCC_EX, HAL_FLASH, HAL_ADC,
                           HAL_UART, HAL, SYSTEM, SENSOR_MAP, HAL_CONF, CONTRACT,
                           NODE_A)}


FUNCTION_MACROS = {}
for _match in re.finditer(
        r"^[ \t]*#define[ \t]+(\w+)\(([^)\r\n]*)\)[ \t]+((?:[^\r\n\\]|\\(?:\r?\n))*)",
        CONTRACT, re.MULTILINE):
    FUNCTION_MACROS[_match.group(1)] = (
        [part.strip() for part in _match.group(2).split(",")],
        re.sub(r"\\\r?\n", " ", _match.group(3)))


def expand_calls(text):
    """Expand the contract's simple function-like macros before evaluation."""
    for _ in range(16):
        match = next((found for found in re.finditer(r"\b(\w+)\s*\(([^()]*)\)", text)
                      if found.group(1) in FUNCTION_MACROS), None)
        if match is None:
            return text
        params, body = FUNCTION_MACROS[match.group(1)]
        args = [arg.strip() for arg in match.group(2).split(",")]
        if len(args) != len(params):
            return text
        for param, arg in zip(params, args):
            body = re.sub(rf"\b{re.escape(param)}\b", arg, body)
        text = f"{text[:match.start()]}( {body} ){text[match.end():]}"
    return text


TERNARY = re.compile(r"\(([^()?:]+)\)\s*\?\s*([^()?:]+)\s*:\s*([^()?:]+)")


def resolve(expression, seen=()):
    """Evaluate a C macro expression using the collected defines."""
    text = re.sub(r"\(\s*(?:u?int(?:8|16|32|64)_t|void)\s*\)", "", expression)
    text = expand_calls(text)
    text = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)(?:[uUlL]+)\b", r"\1", text)
    while "?" in text:  # C ternary -> Python conditional expression
        expanded = TERNARY.sub(r"( \2 if \1 else \3 )", text)
        assert expanded != text, f"cannot translate ternary in {expression!r}"
        text = expanded
    # Blank the literals before scanning so a hex "0x7" is not read as "x7".
    scrubbed = re.sub(r"\b0[xX][0-9a-fA-F]+\b|\b\d+\b", "0", text)
    keywords = {"if", "else"}  # produced by the ternary translation above
    names = {}
    for name in set(re.findall(r"[A-Za-z_]\w*", scrubbed)) - set(seen) - keywords:
        assert name in DEFINES, f"unresolved macro {name} in {expression!r}"
        names[name] = resolve(DEFINES[name], seen + (name,))
    # C integer division truncates; every value here is non-negative.
    integer = re.sub(r"(?<!/)/(?!/)", "//", text)
    return int(eval(integer, {"__builtins__": {}}, names))  # noqa: S307


def value(name):
    """Value of a macro collected from any source, or of a numeric literal."""
    literal = re.fullmatch(r"(0[xX][0-9a-fA-F]+|\d+)[uUlL]*", str(name))
    if literal:
        return int(literal.group(1), 0)
    assert name in DEFINES, f"macro {name} not found"
    return resolve(name)


def raw_define(name, source):
    """Raw body of a define (continuations joined), including function-like ones."""
    pattern = rf"^[ \t]*#define[ \t]+{re.escape(name)}\b(.*?)(?<!\\)\r?\n"
    match = re.search(pattern, source, re.MULTILINE | re.DOTALL)
    assert match, f"define {name} not found"
    return re.sub(r"\\\r?\n", " ", match.group(1))


def header_asserts(snippet):
    """Assert the contract header contains a (whitespace-insensitive) assertion."""
    flat = re.sub(r"\s+", " ", CONTRACT)
    assert re.sub(r"\s+", " ", snippet) in flat, f"contract header lost: {snippet}"


def function_bodies(text):
    """Every function definition in an already noise-stripped region."""
    bodies = {}
    for match in re.finditer(r"\b(?!if\b|while\b|for\b|switch\b|return\b|sizeof\b)"
                             r"(\w+)\s*\([^{;]*?\)\s*\{", text):
        depth, end = 1, match.end()
        while depth:
            depth += (text[end] == "{") - (text[end] == "}")
            end += 1
        bodies.setdefault(match.group(1), text[match.start():end])
    return bodies


def pin_number(pin_macro):
    return int(re.search(r"GPIO_PIN_(\d+)", pin_macro).group(1))


def check_clock_tree():
    """Derive SYSCLK/HCLK/PCLK1/PCLK2 from the selections the firmware makes."""
    hse = value("HSE_VALUE")
    assert hse == 8_000_000, f"HSE_VALUE changed to {hse}"
    # The model must read the crystal value from the project configuration; the
    # HAL ships an 8 MHz fallback that would otherwise hide a real change.
    assert hse == int(re.search(r"#define\s+HSE_VALUE\s+(\d+)", HAL_CONF).group(1)), (
        "HSE_VALUE must come from stm32f1xx_hal_conf.h, not a library fallback")
    assert re.search(r"^#define\s+NODE_A_HSE_HZ\s+\(?HSE_VALUE\)?\s*$", CONTRACT,
                     re.MULTILINE), (
        "the contract must tie NODE_A_HSE_HZ to the HAL HSE_VALUE, not a literal")

    clock = function(NODE_A, "SystemClock_Config")

    def assignment(field):
        """The macro a SystemClock_Config assignment actually selects."""
        match = re.search(rf"\b\w+\.{field}\s*=\s*(\w+)\s*;", clock)
        assert match, f"SystemClock_Config must assign {field}"
        return match.group(1)

    # Check the assignments, not just the presence of the tokens: swapping two
    # divider macros between fields keeps every token in place while changing
    # the clock tree.
    expected_assignments = {
        "OscillatorType": "RCC_OSCILLATORTYPE_HSE",
        "HSEState": "RCC_HSE_ON",
        "HSEPredivValue": "RCC_HSE_PREDIV_DIV1",
        "PLLState": "RCC_PLL_ON",
        "PLLSource": "RCC_PLLSOURCE_HSE",
        "PLLMUL": "RCC_PLL_MUL9",
        "SYSCLKSource": "RCC_SYSCLKSOURCE_PLLCLK",
        "AHBCLKDivider": "RCC_SYSCLK_DIV1",
        "APB1CLKDivider": "RCC_HCLK_DIV2",
        "APB2CLKDivider": "RCC_HCLK_DIV1",
        "AdcClockSelection": "RCC_ADCPCLK2_DIV6",
        "PeriphClockSelection": "RCC_PERIPHCLK_ADC",
    }
    for field, macro in expected_assignments.items():
        assert assignment(field) == macro, (field, assignment(field))
    latency_arg = re.search(r"HAL_RCC_ClockConfig\(&clock,\s*(\w+)\)", clock)
    assert latency_arg and latency_arg.group(1) == "NODE_A_FLASH_LATENCY", (
        "the FLASH latency must come from the contract, not a literal")
    for call in ("HAL_RCC_OscConfig", "HAL_RCC_ClockConfig",
                 "HAL_RCCEx_PeriphCLKConfig"):
        assert call in clock, f"SystemClock_Config no longer calls {call}"

    # The HAL encodes "multiply by N" as N - 2 in the PLLMULL field.
    multiplier = (value(assignment("PLLMUL")) >> value("RCC_CFGR_PLLMULL_Pos")) + 2
    assert multiplier == value("NODE_A_PLL_MULTIPLIER") == 9
    prediv = value(assignment("HSEPredivValue"))
    assert prediv == 0, "HSE predivider /1 encoding changed"

    sysclk = (hse // (prediv + 1)) * multiplier
    assert sysclk == value("NODE_A_SYSCLK_HZ") == 72_000_000, sysclk

    # Prescaler tables from the CMSIS system file, indexed by the RCC_CFGR field.
    ahb_table = [int(v) for v in re.search(
        r"AHBPrescTable\[16U?\]\s*=\s*\{([^}]*)\}", SYSTEM).group(1).split(",")]
    apb_table = [int(v) for v in re.search(
        r"APBPrescTable\[8U?\]\s*=\s*\{([^}]*)\}", SYSTEM).group(1).split(",")]
    assert (len(ahb_table), len(apb_table)) == (16, 8)
    hpre = (value(assignment("AHBCLKDivider")) & value("RCC_CFGR_HPRE")) >> value(
        "RCC_CFGR_HPRE_Pos")
    ppre1 = (value(assignment("APB1CLKDivider")) & value("RCC_CFGR_PPRE1")) >> value(
        "RCC_CFGR_PPRE1_Pos")
    ppre2 = (value(assignment("APB2CLKDivider")) & value("RCC_CFGR_PPRE2")) >> value(
        "RCC_CFGR_PPRE2_Pos")
    hclk = sysclk >> ahb_table[hpre]
    pclk1 = hclk >> apb_table[ppre1]
    pclk2 = hclk >> apb_table[ppre2]
    assert (hclk, pclk1, pclk2) == (72_000_000, 36_000_000, 72_000_000), (
        hclk, pclk1, pclk2)
    assert hclk == value("NODE_A_HCLK_HZ")
    assert pclk1 == value("NODE_A_PCLK1_HZ") == 36_000_000
    assert pclk2 == value("NODE_A_PCLK2_HZ") == 72_000_000

    # RM0008: an APB1 prescaler other than one doubles the APB1 timer clock.
    timer_hz = pclk1 if ppre1 == 0 else pclk1 * 2
    assert timer_hz == value("NODE_A_APB1_TIMER_HZ") == 72_000_000

    # Two FLASH wait states cover 48 MHz < HCLK <= 72 MHz on STM32F103.
    assert "FLASH_LATENCY_2" in DEFINES["NODE_A_FLASH_LATENCY"]
    assert value("FLASH_LATENCY_2") == value("NODE_A_FLASH_WAIT_STATES") == 2
    assert 48_000_000 < hclk <= 72_000_000
    return f"sysclk={sysclk // 1000000}MHz hclk={hclk // 1000000}MHz " \
           f"pclk1={pclk1 // 1000000}MHz pclk2={pclk2 // 1000000}MHz"


def check_systick():
    """Model the HAL millisecond tick before and after the clock switch."""
    tick_hz = 1000 // value("HAL_TICK_FREQ_DEFAULT")
    assert tick_hz == value("NODE_A_HAL_TICK_HZ") == 1000
    assert "HAL_SYSTICK_Config(SystemCoreClock / (1000U / uwTickFreq))" in HAL_C, (
        "the HAL tick no longer derives its reload from SystemCoreClock")
    assert re.search(r"SysTick->LOAD\s*=\s*\(uint32_t\)\(ticks\s*-\s*1", CORE_CM3_TEXT), (
        "SysTick_Config no longer programs LOAD = ticks - 1")

    boot_clock = int(re.search(r"uint32_t SystemCoreClock\s*=\s*(\d+)",
                               SYSTEM).group(1))
    assert boot_clock == 8_000_000, (
        "SystemCoreClock must still start at the 8 MHz HSI boot clock")
    boot_reload = boot_clock // tick_hz - 1
    assert boot_reload == 7999, boot_reload
    reload = 72_000_000 // tick_hz - 1
    assert reload == value("NODE_A_SYSTICK_RELOAD") == 71_999

    # HAL_RCC_ClockConfig updates SystemCoreClock and re-runs HAL_InitTick after
    # the switch, so the main loop must not keep running on the boot tick.
    assert re.search(
        r"SystemCoreClock = HAL_RCC_GetSysClockFreq\(\)[^;]*;\s*[^;]*?"
        r"HAL_InitTick\(uwTickPrio\);", HAL_RCC_C, re.DOTALL), (
        "HAL_RCC_ClockConfig must re-derive the tick after the switch")
    assert "HAL_Init(); SystemClock_Config();" in NODE_A, (
        "main() must initialise the HAL and switch the clock immediately")
    assert "SysTick->LOAD" in function(NODE_A, "NodeTest_ReportClock"), (
        "the bench probe must report the real SysTick reload")
    return f"systick={boot_reload}->{reload}"


def check_uart():
    """Reproduce the HAL 16x-oversampling BRR formula on the selected PCLKs."""
    div = raw_define("UART_DIV_SAMPLING16", HAL_UART)
    scale = int(re.search(r"\*\s*(\d+)U\s*\)\s*/\s*\(\s*(\d+)U", div).group(1))
    divisor = int(re.search(r"/\s*\(\s*(\d+)U", div).group(1))
    assert (scale, divisor) == (25, 4), (scale, divisor)
    mant = raw_define("UART_DIVMANT_SAMPLING16", HAL_UART)
    fraq = raw_define("UART_DIVFRAQ_SAMPLING16", HAL_UART)
    brr = raw_define("UART_BRR_SAMPLING16", HAL_UART)
    assert "/100U" in mant, mant
    assert "* 16U" in fraq and "+ 50U) / 100U" in fraq, fraq
    for token in ("<< 4U", "& 0xF0U", "& 0x0FU"):
        assert token in brr, brr

    baud = value("NODE_A_UART_BAUD")
    assert baud == 9600
    assert "UART_BRR_SAMPLING16" not in NODE_A, (
        "the firmware must set the baud and let the HAL derive BRR")
    for name, pclk, expected in (("MX_USART1_UART_Init", 72_000_000, 7500),
                                 ("MX_USART2_UART_Init", 36_000_000, 3750)):
        init = function(NODE_A, name)
        assert "Init.BaudRate = NODE_A_UART_BAUD" in init
        usartdiv100 = (pclk * scale) // (divisor * baud)
        mantissa, fraction = usartdiv100 // 100, usartdiv100 % 100
        fraction = (fraction * 16 + 50) // 100
        brr = (mantissa << 4) + (fraction & 0xF0) + (fraction & 0x0F)
        assert brr == expected, (name, brr)
        assert pclk % brr == 0, f"{name} would carry a baud error at BRR {brr}"
        assert pclk // brr == baud, (name, pclk // brr)
    assert "USART1->BRR" in function(NODE_A, "NodeTest_ReportClock")
    assert "USART2->BRR" in function(NODE_A, "NodeTest_ReportClock")
    header_asserts("NODE_A_UART_BRR(NODE_A_PCLK2_HZ) == 7500UL")
    header_asserts("NODE_A_UART_BRR(NODE_A_PCLK1_HZ) == 3750UL")
    return "uart1_brr=7500 uart2_brr=3750 error=0%"


def check_adc():
    """Derive the ADC clock, sampling time and conversion duration."""
    field = (value("RCC_ADCPCLK2_DIV6") & value("RCC_CFGR_ADCPRE")) >> value(
        "RCC_CFGR_ADCPRE_Pos")
    divider = (field + 1) * 2
    assert divider == value("NODE_A_ADC_CLOCK_DIVIDER") == 6
    adc_hz = 72_000_000 // divider
    assert adc_hz == value("NODE_A_ADC_CLOCK_HZ") == 12_000_000
    assert adc_hz <= value("NODE_A_ADC_MAX_CLOCK_HZ") <= 12_000_000

    # SMP = 0b111 selects 239.5 sampling cycles; a 12-bit conversion adds 12.5.
    smp = value("ADC_SAMPLETIME_239CYCLES_5")
    assert smp == value("NODE_A_ADC_SAMPLE_TIME_CODE") == 0x7
    sampling_cycles = [1.5, 7.5, 13.5, 28.5, 41.5, 55.5, 71.5, 239.5][smp]
    conversion_ns = int((sampling_cycles + 12.5) / adc_hz * 1e9)
    assert conversion_ns == value("NODE_A_ADC_CONVERSION_NS") == 21_000

    assert "ADC_SAMPLETIME_239CYCLES_5" in function(NODE_A, "MX_ADC1_Init")
    sample = function(NODE_A, "GasAdc_ReadRaw")
    assert "GAS_ADC_SAMPLE_COUNT" in sample
    assert "ADC_SAMPLETIME_239CYCLES_5" in sample
    assert value("GAS_ADC_SAMPLE_COUNT") == value("NODE_A_GAS_ADC_SAMPLE_COUNT") == 64
    assert "HAL_ADC_PollForConversion(&hadc1, NODE_A_GAS_ADC_POLL_TIMEOUT_MS)" in sample
    poll_ms = value("NODE_A_GAS_ADC_POLL_TIMEOUT_MS")
    assert poll_ms * 1_000_000 > conversion_ns, "the poll timeout must exceed one conversion"
    return f"adc={adc_hz // 1000000}MHz conversion={conversion_ns // 1000}us " \
           f"samples={value('NODE_A_GAS_ADC_SAMPLE_COUNT')}"


def check_fan_pwm():
    """Derive the TIM4 carrier from the registers the init function writes."""
    init = function(NODE_A, "MX_FAN1_PWM_Init")
    assert "TIM4->PSC = NODE_A_FAN_TIMER_PRESCALER" in init
    assert "TIM4->ARR = FAN_PWM_TIMER_PERIOD" in init
    # The period alias must be the contract macro verbatim; an arithmetic
    # expression here would keep the token present while changing the carrier.
    period_body = raw_define("FAN_PWM_TIMER_PERIOD", NODE_A).split()
    assert period_body == ["NODE_A_FAN_TIMER_PERIOD"], period_body
    assert "TIM_CCMR2_OC3M_1 | TIM_CCMR2_OC3M_2" in init, "TIM4 CH3 must stay PWM mode 1"
    assert "TIM_CCMR2_OC4M_1 | TIM_CCMR2_OC4M_2" in init, "TIM4 CH4 must stay PWM mode 1"
    assert "TIM4->CCER = TIM_CCER_CC3E | TIM_CCER_CC4E" in init, (
        "only the two fan channels may be enabled")

    psc = value("NODE_A_FAN_TIMER_PRESCALER")
    arr = value("NODE_A_FAN_TIMER_PERIOD")
    timer_hz = value("NODE_A_APB1_TIMER_HZ") // (psc + 1)
    pwm_hz = timer_hz // (arr + 1)
    assert (psc, arr) == (0, 2879), (psc, arr)
    assert (timer_hz, pwm_hz) == (72_000_000, 25_000), (timer_hz, pwm_hz)
    assert pwm_hz == value("NODE_A_FAN_PWM_HZ")
    assert timer_hz % (arr + 1) == 0, "the 25 kHz division must be exact"
    assert arr + 1 >= 100, "the PWM must resolve every commanded percent"
    report = function(NODE_A, "NodeTest_ReportClock")
    assert "TIM4->PSC" in report and "TIM4->ARR" in report

    # The NPN transistor inverts the pin, so the compare value is the commanded
    # off-time; the mapping must stay percent -> CCR in {2880, 1440, 0}.
    assert "transistor_on_counts = ((uint32_t)(100U - percent)" in NODE_A
    for percent, expected in ((0, arr + 1), (50, (arr + 1) // 2), (100, 0)):
        assert ((100 - percent) * (arr + 1) + 50) // 100 == expected, percent
    return f"fan_pwm={pwm_hz}Hz ccr(0/50/100)={arr + 1}/{(arr + 1) // 2}/0"


def check_tach():
    """Cover both tach RPM paths, including real uint32 counter crossings."""
    pulses_per_rev = value("FAN_TACH_PULSES_PER_REVOLUTION")
    assert pulses_per_rev == 2
    overflow = 0xFFFFFFFF

    def delta_of(previous, current):
        """The uint32_t subtraction the ISR counter and the reader perform."""
        return (current - previous) & overflow

    def rpm(delta, elapsed_ms):
        """The firmware expression: (uint64_t)delta * 60000 / (2 * elapsed)."""
        return (delta * 60000) // (pulses_per_rev * elapsed_ms)

    # Boundary table: a real 32-bit counter crossing must be modelled as a wrap,
    # not as a plain difference, or a broken implementation still looks safe.
    boundaries = [
        (100, 115, 1000, 450),                  # no crossing
        (0xFFFFFFF0, 0x0000000F, 1000, 930),    # crosses 0xFFFFFFFF: 31 pulses
        (0xFFFFFFF0, 0x0000000F, 2000, 465),    # same delta over 2 s
        (0xFFFFFFFF, 0x00000000, 1000, 30),     # saturates then rolls to zero
        (0x7FFFFFFF, 0x80000000, 1000, 30),     # crosses the signed-int boundary
        (0xFFFFFFFE, 0x00000001, 1000, 90),     # three pulses across the wrap
        (0xFFFFFF00, 0x00000064, 1000, 10_680),  # 356 pulses across the wrap
        (42, 42, 1000, 0),                      # a stationary fan
        # 200 000 RPM in a 2 s window: the fastest plausible four-wire fan.
        (0, 200_000 * pulses_per_rev * 2 // 60, 2000, 199_995),
    ]
    for name, counter in (("Fan1Tach_ReadRpm", "fan1_tach_pulses"),
                          ("Fan2Tach_ReadRpm", "fan2_tach_pulses")):
        body = function(NODE_A, name)
        assert f"pulses = {counter};" in body
        assert "__disable_irq();" in body and "__enable_irq();" in body, (
            f"{name} must latch the 32-bit counter atomically")
        last = counter.replace("pulses", "last_pulses")
        assert f"delta = pulses - {last};" in body, (
            f"{name} must subtract in uint32 so the counter wrap stays correct")
        assert re.search(r"elapsed_ms = now - fan\d_tach_last_sample_at;", body)
        assert "if ((elapsed_ms == 0U) || (g_actuator.relay_on == 0U)) return 0U;" in body
        assert "((uint64_t)delta * 60000ULL)" in body, (
            f"{name} must widen to 64 bits before multiplying")
        assert "((uint64_t)FAN_TACH_PULSES_PER_REVOLUTION * elapsed_ms)" in body
        assert "(uint32_t)(((uint64_t)delta * 60000ULL)" in body
        # The counter and both timestamps must be 32-bit so the subtraction is
        # the unsigned wrap the table above models.
        for declaration in (f"static volatile uint32_t {counter};",
                            f"static uint32_t {last};",
                            f"static uint32_t {counter.replace('pulses', 'last_sample_at')};"):
            assert declaration in NODE_A, declaration
        # Both paths must produce the same, correct RPM across the wrap.
        for previous, current, elapsed_ms, expected in boundaries:
            delta = delta_of(previous, current)
            assert 0 <= delta <= overflow, (name, delta)
            assert rpm(delta, elapsed_ms) == expected, (name, previous, current)
    # Both paths must stay identical apart from their own counter, so a fix or a
    # regression applied to only one fan cannot pass unnoticed.
    fan1 = function(NODE_A, "Fan1Tach_ReadRpm").replace("fan1", "fanN").replace(
        "Fan1", "FanN")
    fan2 = function(NODE_A, "Fan2Tach_ReadRpm").replace("fan2", "fanN").replace(
        "Fan2", "FanN")
    assert fan1 == fan2, "the two tach paths must stay identical apart from their counter"
    assert delta_of(0xFFFFFFF0, 0x0000000F) == 31, (
        "the wrap must be modelled as a masked uint32 subtraction")
    assert delta_of(0xFFFFFFF0, 0x0000000F) != 0xFFFFFFF0 - 0x0000000F, (
        "a plain subtraction would underflow instead of wrapping")
    assert rpm(delta_of(0xFFFFFFF0, 0x0000000F), 1000) == 930
    # A real fan window stays far below the uint32 cast; a full-counter delta
    # would imply a 4.29 GHz pulse rate, which no four-wire fan can produce.
    assert rpm(0xFFFFFFFF, 1000) > 2 ** 32, (
        "documented: only an impossible rate would truncate the cast")

    # The pulse window must be timestamped after the slow software-I2C reads.
    loop = function(NODE_A, "main")
    assert loop.index("tach_now = HAL_GetTick();") > loop.index("Ina226_Read(&i2c2_bus"), (
        "the tach window must start after the sensor reads it divides by")
    assert "fan_rpm = Fan1Tach_ReadRpm(tach_now);" in loop
    assert "fan2_rpm = Fan2Tach_ReadRpm(tach_now);" in loop
    return f"tach=both paths, wrap 31->930RPM, {len(boundaries)} boundaries"


def check_ws2812():
    """Derive the WS2812 waveform from the SPI divisor and the symbols."""
    init = function(NODE_A, "MX_WS2812_SPI_Init")
    # The whole CR1 word is owned by this function, so assert the exact set of
    # fields rather than the presence of the expected tokens: OR-ing in a second
    # BR bit would halve the clock while every token stayed present.
    cr1 = re.search(r"SPI2->CR1 = ([^;]+);", init)
    assert cr1, "MX_WS2812_SPI_Init must program SPI2->CR1"
    assert set(re.findall(r"\w+", cr1.group(1))) == {
        "SPI_CR1_MSTR", "SPI_CR1_SSM", "SPI_CR1_SSI", "SPI_CR1_BR_1"}, cr1.group(1)
    assert "SPI2->CR1 |= SPI_CR1_SPE;" in init, "SPI2 must be enabled"
    assert "SPI2->CR2 = 0U;" in init
    field = (value("SPI_CR1_BR_1") & value("SPI_CR1_BR")) >> value("SPI_CR1_BR_Pos")
    divider = 1 << (field + 1)
    assert field == value("NODE_A_WS2812_BR_FIELD") == 2
    assert divider == value("NODE_A_WS2812_SPI_DIVIDER") == 8
    spi_hz = 36_000_000 // divider
    assert spi_hz == value("NODE_A_WS2812_SPI_HZ") == 4_500_000
    assert "SPI2->CR1" in function(NODE_A, "NodeTest_ReportClock")

    # The symbol keeps its HIGH bits first, so each pattern follows from the
    # number of high bits instead of being an independent literal.
    bits = value("NODE_A_WS2812_BITS_PER_DATA_BIT")
    assert bits == 6
    assert re.search(r"^#define\s+NODE_A_WS2812_ZERO_PATTERN\s+\\?\s*$",
                     CONTRACT, re.MULTILINE), "the zero symbol must stay derived"
    assert "NODE_A_WS2812_PATTERN(NODE_A_WS2812_ZERO_HIGH_BITS)" in CONTRACT
    assert "NODE_A_WS2812_PATTERN(NODE_A_WS2812_ONE_HIGH_BITS)" in CONTRACT
    for name, expected in (("NODE_A_WS2812_ZERO_PATTERN", 0x30),
                           ("NODE_A_WS2812_ONE_PATTERN", 0x3C)):
        high_bits = value(name.replace("_PATTERN", "_HIGH_BITS"))
        assert ((0xFF >> (8 - bits)) & (0xFF << (bits - high_bits))) == expected, name
    assert "encoded_bit = 0x20U" in function(NODE_A, "Ws2812_EncodeByte"), (
        "the encoder must transmit the pattern MSB first")
    assert "NODE_A_WS2812_ONE_PATTERN : NODE_A_WS2812_ZERO_PATTERN" in NODE_A

    widths = (lambda n: (n * 1000000000) // spi_hz)  # multiply before dividing
    cell_ns = widths(bits)
    zero_high = widths(value("NODE_A_WS2812_ZERO_HIGH_BITS"))
    one_high = widths(value("NODE_A_WS2812_ONE_HIGH_BITS"))
    assert value("NODE_A_WS2812_BIT_NS") == widths(1)
    assert value("NODE_A_WS2812_CELL_NS") == cell_ns
    assert value("NODE_A_WS2812_ZERO_HIGH_NS") == zero_high
    assert value("NODE_A_WS2812_ONE_HIGH_NS") == one_high
    # The bench probe re-derives the same cell from the reported register.
    assert "6 * 1000000000 // 4500000" in read(
        pathlib.Path(__file__).with_name("node_a_clock_serial_probe.py"))
    assert 650 <= cell_ns <= 1850, cell_ns
    assert zero_high >= 200, zero_high
    assert 750 <= one_high <= 1050, one_high
    assert 250 <= cell_ns - one_high <= 550, cell_ns - one_high
    assert zero_high < one_high, "a one must be longer high than a zero"
    assert "Ws2812_SendEncoded" in NODE_A and "DMA1_Channel5" in NODE_A
    assert "HAL_Delay(1U); /* Low reset interval" in NODE_A
    return f"ws_spi={spi_hz}Hz cell={cell_ns}ns high={zero_high}/{one_high}ns"


def check_i2c_bounds():
    """Prove the software-I2C transfers are bounded in time and in step count."""
    delay_ms = value("NODE_A_SOFT_I2C_DELAY_MS")
    assert delay_ms == 1
    i2c_delay = function(NODE_A, "I2c_Delay")
    assert "Communication_Service();" in i2c_delay
    assert "HAL_Delay(NODE_A_SOFT_I2C_DELAY_MS);" in i2c_delay

    # Fixed delay counts per primitive, derived from the parsed bodies: the bit
    # loop runs eight times and the tail adds the acknowledge or stop edges.
    counts = {name: function(NODE_A, name).count("I2c_Delay()")
              for name in ("I2c_Start", "I2c_Stop", "I2c_WriteByte", "I2c_ReadByte")}
    assert counts == {"I2c_Start": 2, "I2c_Stop": 3, "I2c_WriteByte": 4,
                      "I2c_ReadByte": 4}, counts
    per_byte = 0
    for name in ("I2c_WriteByte", "I2c_ReadByte"):
        body = function(NODE_A, name)
        loop = re.search(r"for \(bit = 0U; bit < 8U; \+\+bit\)\s*\{", body)
        assert loop, f"{name} must keep an eight-slot bit loop"
        depth, end = 1, loop.end()
        while depth:
            depth += (body[end] == "{") - (body[end] == "}")
            end += 1
        assert body[loop.end():end].count("I2c_Delay()") * 8 + \
            body[end:].count("I2c_Delay()") == 18, name
        per_byte = 18

    # Worst case SHT30 read: a three-byte command write, the conversion delay,
    # then six read bytes inside one address/ACK sequence, plus both stops.
    sht30 = function(NODE_A, "Sht30_Read")
    assert "NODE_A_SHT30_TIMEOUT_MS" in sht30, "the SHT30 read must carry a deadline"
    assert "I2c_DeadlineReached(deadline_ms)" in sht30
    # The deadline must be in the future and the comparison must stay positive.
    assert re.search(r"deadline_ms = HAL_GetTick\(\)\s*\+\s*NODE_A_SHT30_TIMEOUT_MS",
                     sht30), "the SHT30 deadline must be now + timeout"
    deadline_fn = function(NODE_A, "I2c_DeadlineReached")
    assert re.search(r"return \(\(int32_t\)\(\(uint32_t\)HAL_GetTick\(\) - "
                     r"deadline_ms\) >= 0\) \? 1U : 0U;", deadline_fn), (
        "the deadline comparison must treat a passed deadline as expired")
    assert sht30.count("I2c_WriteByte") == 4
    assert sht30.count("I2c_ReadByte") == 1  # inside a six-iteration loop
    byte_loop = re.search(r"for \(i = 0U; i < sizeof\(response\); \+\+i\)\s*\{(.*?)\}",
                          sht30, re.DOTALL)
    assert byte_loop, "the SHT30 response must be read in a fixed six-slot loop"
    assert "I2c_DeadlineReached(deadline_ms)" in byte_loop.group(1), (
        "the deadline must be re-checked inside the byte loop, not only after it")
    assert sht30.count("I2c_DeadlineReached(deadline_ms)") >= 2
    # HAL_Delay(N) waits N + uwTickFreq ticks; the HAL adds that tick itself, so
    # every modelled delay carries it.  Assert the HAL really does add it.
    overhead = value("NODE_A_HAL_DELAY_OVERHEAD_TICKS")
    assert overhead == value("HAL_TICK_FREQ_DEFAULT") == 1
    assert re.search(r"wait \+= \(uint32_t\)\(uwTickFreq\)", HAL_C), (
        "HAL_Delay no longer adds an overhead tick; the budgets must be retuned")
    tick_cost = delay_ms + overhead

    fixed = (counts["I2c_Start"] + 3 * per_byte + counts["I2c_Stop"]
             + counts["I2c_Start"] + per_byte + 6 * per_byte + counts["I2c_Stop"])
    assert fixed == value("NODE_A_SHT30_FIXED_DELAY_COUNT") == 190, fixed
    worst_ms = (value("NODE_A_SHT30_MEASUREMENT_DELAY_MS") + overhead) + \
        fixed * tick_cost
    assert worst_ms == value("NODE_A_SHT30_WORST_CASE_MS") == 401, worst_ms
    timeout = value("NODE_A_SHT30_TIMEOUT_MS")
    assert timeout > worst_ms, (timeout, worst_ms)
    assert "DelayWithCommunication(NODE_A_SHT30_MEASUREMENT_DELAY_MS)" in sht30
    assert "I2c_Stop(bus); return 0U;" in sht30, "every abort path must release the bus"

    for name in ("I2c_ReadRegister16", "I2c_WriteRegister16"):
        assert "I2c_DeadlineReached(deadline_ms)" in function(NODE_A, name)
    # Every call site must use the result the right way round: an abort when the
    # deadline has passed, or a success return when it has not.  Checking only
    # the helper's text would let an inverted call site deny every transfer.
    region_start = NODE_A.index("omitted HAL I2C")
    assert "omitted HAL I2C" in NODE_A, "the I2C region anchor comment moved"
    region = NODE_A[region_start:NODE_A.index("static void SendTelemetry",
                                              region_start)]
    sites = re.findall(r"[^\n]*I2c_DeadlineReached\(deadline_ms\)[^\n]*", region)
    allowed = (re.compile(r"if \(I2c_DeadlineReached\(deadline_ms\) != 0U\) "
                          r"return (value|0U);"),
               re.compile(r"if \(I2c_DeadlineReached\(deadline_ms\) != 0U\) "
                          r"\{ I2c_Stop\(bus\); return 0U; \}"),
               re.compile(r"return \(I2c_DeadlineReached\(deadline_ms\) == 0U\) "
                          r"\? 1U : 0U;"))
    for site in sites:
        assert any(pattern.search(site.strip()) for pattern in allowed), (
            f"unexpected deadline call site: {site.strip()}")
    assert len(sites) == 6, f"expected six deadline call sites, found {len(sites)}"
    for name in ("I2c_WriteByte", "I2c_ReadByte"):
        assert function(NODE_A, name).count("I2c_DeadlineReached(deadline_ms)") == 1, (
            f"{name} must check the deadline inside its bit loop")

    # Only a transaction entry point may read the tick, so a helper cannot arm
    # its own (much longer) deadline in place of the caller's.
    tick_users = {name for name, body in function_bodies(strip_c_noise(region)).items()
                  if "HAL_GetTick()" in body}
    assert tick_users == {"I2c_DeadlineReached", "Sht30_Read", "Ina226_Read"}, (
        f"unexpected HAL_GetTick() user in the I2C drivers: {sorted(tick_users)}")
    # Sampling a line is the job of the two byte primitives; a new helper that
    # reads SCL or SDA would be a bus-state wait in disguise.
    readers = {name for name, body in function_bodies(strip_c_noise(region)).items()
               if "HAL_GPIO_ReadPin" in body}
    assert readers == {"I2c_WriteByte", "I2c_ReadByte"}, (
        f"unexpected line reader in the I2C drivers: {sorted(readers)}")
    # Delays that the budgets do not model would silently extend the transfers.
    delays = sorted(set(re.findall(r"HAL_Delay\(([^)]+)\)", strip_c_noise(region))))
    assert delays == ["3U", "NODE_A_SOFT_I2C_DELAY_MS"], delays
    serviced_delays = sorted(set(re.findall(
        r"DelayWithCommunication\(([^)]+)\)", strip_c_noise(region))))
    assert serviced_delays == ["INA226_SAMPLE_SETTLE_MS",
                               "NODE_A_SHT30_MEASUREMENT_DELAY_MS"], serviced_delays

    # Everything else on the bus is a fixed-count loop over eight bit slots.
    for name in ("I2c_WriteByte", "I2c_ReadByte"):
        body = function(NODE_A, name)
        assert len(re.findall(r"\bfor\s*\(", body)) == 1
        assert "bit < 8U" in body, f"{name} must keep an eight-slot bit loop"
        assert "deadline_ms" in body

    # Region-wide guard: across the whole software-I2C/sensor driver section the
    # only while loop may be the CRC's fixed countdown, and there may be no
    # unbounded loop at all, so a new helper cannot reintroduce a wait on bus
    # state unnoticed.
    stripped = strip_c_noise(region)
    bodies = function_bodies(stripped)
    waiting = {name for name, body in bodies.items() if re.search(r"\bwhile\s*\(", body)}
    assert waiting == {"Sht30_Crc"}, (
        f"unexpected while loop in the software-I2C drivers: {sorted(waiting)}")
    # The CRC loop counts down its fixed argument, it does not wait on hardware.
    assert re.search(r"while \(length-- > 0U\)", bodies["Sht30_Crc"]), (
        "Sht30_Crc may only loop over its fixed-length input")
    for pattern, label in ((r"for\s*\(\s*;\s*;\s*\)", "an empty for(;;)"),
                           (r"\bgoto\b", "a goto")):
        assert not re.search(pattern, stripped), (
            f"the software-I2C drivers must not contain {label} loop")

    ina226 = function(NODE_A, "Ina226_Read")
    assert "NODE_A_INA226_TIMEOUT_MS" in ina226
    # One deadline per transfer: the sub-functions must receive it, never create
    # their own, or the cap would multiply by the number of register accesses.
    assert re.search(r"deadline_ms = HAL_GetTick\(\)\s*\+\s*NODE_A_INA226_TIMEOUT_MS",
                     ina226), "the INA226 deadline must be now + timeout"
    assert ina226.count("HAL_GetTick()") == 1, (
        "the INA226 transfer deadline must be taken exactly once")
    for name in ("Ina226_Configure", "Ina226_ReadSamples"):
        body = function(NODE_A, name)
        assert "HAL_GetTick()" not in body, (
            f"{name} must use the transfer deadline, not a fresh one")
        calls = body.count("I2c_ReadRegister16") + body.count("I2c_WriteRegister16")
        assert calls > 0 and body.count("deadline_ms") >= calls, (
            f"every {name} register access must pass the deadline")

    # Derive the INA226 delay budget from the same primitives and call sites.
    start, stop = counts["I2c_Start"], counts["I2c_Stop"]
    per_read = start + 2 * per_byte + start + per_byte + 2 * per_byte + stop
    per_write = start + 4 * per_byte + stop
    assert (per_read, per_write) == (97, 77), (per_read, per_write)
    read_register = function(NODE_A, "I2c_ReadRegister16")
    write_register = function(NODE_A, "I2c_WriteRegister16")
    assert read_register.count("I2c_WriteByte") == 3
    assert read_register.count("I2c_ReadByte") == 2
    assert write_register.count("I2c_WriteByte") == 4
    configure = function(NODE_A, "Ina226_Configure")
    samples = function(NODE_A, "Ina226_ReadSamples")
    assert samples.count("I2c_ReadRegister16") == 4, (
        "each sample must read bus, shunt, current and power")
    assert "sample < INA226_SAMPLE_COUNT" in samples
    sample_count = value("INA226_SAMPLE_COUNT")
    pass_delays = (configure.count("I2c_ReadRegister16") * per_read
                   + configure.count("I2c_WriteRegister16") * per_write
                   + sample_count * samples.count("I2c_ReadRegister16") * per_read)

    # Settles are derived from both raw and communication-serviced delay call
    # sites: the fixed ones in Configure plus the per-sample settle that the
    # loop repeats, each carrying the HAL's own overhead tick.
    def delay_calls(body):
        return [value(match.group(1).strip())
                for match in re.finditer(
                    r"(?:HAL_Delay|DelayWithCommunication)\(([^)]+)\)",
                    body)]

    sample_settle = value("INA226_SAMPLE_SETTLE_MS")
    configure_calls = delay_calls(configure)
    configure_nominal = sum(configure_calls)
    configure_settles = configure_nominal + len(configure_calls) * overhead
    assert configure_nominal > sample_settle, (
        "Configure must keep its reset and calibration settles")
    assert "if ((sample + 1U) < INA226_SAMPLE_COUNT)" in samples, (
        "the per-sample settle must stay inside the sample loop")
    sample_calls = delay_calls(samples)
    assert len(sample_calls) == 1 and sample_calls[0] == sample_settle
    pass_settle_calls = len(configure_calls) + (sample_count - 1) * len(sample_calls)
    pass_settles = (configure_settles
                    + (sample_count - 1) * (sample_settle + overhead))

    recover = function(NODE_A, "I2c_Recover")
    assert "pulse < 9U" in recover, "the recovery sequence must stay nine pulses"
    assert len(re.findall(r"\bfor\s*\(", recover)) == 1, (
        "the recovery sequence must stay a single nine-pulse loop")
    recover_delays = recover.count("I2c_Delay()") * 9 + counts["I2c_Stop"]
    assert ina226.count("I2c_Recover(bus)") == 2, (
        "the stuck-0x03ff path must recover exactly twice, as budgeted")

    assert value("NODE_A_INA226_PASS_DELAY_COUNT") == pass_delays, pass_delays
    assert value("NODE_A_INA226_SETTLE_DELAY_MS") == configure_nominal, \
        configure_nominal
    assert value("NODE_A_INA226_SETTLE_CALL_COUNT") == pass_settle_calls, (
        pass_settle_calls)
    assert value("NODE_A_INA226_I2C_RECOVER_DELAY_COUNT") == recover_delays, \
        recover_delays
    assert value("NODE_A_INA226_FIXED_DELAY_COUNT") == 2 * pass_delays + \
        2 * recover_delays
    assert value("NODE_A_INA226_SETTLE_BUDGET_MS") == 2 * pass_settles, \
        pass_settles
    worst_ina226 = (value("NODE_A_INA226_FIXED_DELAY_COUNT") * tick_cost
                    + value("NODE_A_INA226_SETTLE_BUDGET_MS"))
    assert value("NODE_A_INA226_WORST_CASE_MS") == worst_ina226 == 8328, worst_ina226
    ina226_timeout = value("NODE_A_INA226_TIMEOUT_MS")
    assert ina226_timeout > value("NODE_A_INA226_WORST_CASE_MS"), (
        ina226_timeout, value("NODE_A_INA226_WORST_CASE_MS"))
    return f"sht30_budget={worst_ms}ms/{timeout}ms ina226_budget=" \
           f"{value('NODE_A_INA226_WORST_CASE_MS')}ms/{ina226_timeout}ms " \
           f"(delays={fixed}/{pass_delays}+recover{recover_delays}; " \
           f"tick={tick_cost}ms)"


def check_actuator_timing():
    """Pin every millisecond deadline that drives an actuator."""
    expected = {
        "TELEMETRY_INTERVAL_MS": 2000, "LED_INTERVAL_MS": 500,
        "LED_ANIM_INTERVAL_MS": 50, "BUZZER_TEST_DURATION_MS": 1000,
        "INA226_SAMPLE_SETTLE_MS": 40, "INA226_SAMPLE_COUNT": 3,
        "SMOKE_SAMPLE_INTERVAL_MS": 50, "SMOKE_STABLE_SAMPLE_COUNT": 4,
        "FLAME_SAMPLE_INTERVAL_MS": 50, "FLAME_ALARM_HOLD_MS": 12000,
        "LEVEL_SAMPLE_INTERVAL_MS": 50, "LEVEL_STABLE_SAMPLE_COUNT": 4,
        "WS2812_PIXEL_COUNT": 18,
    }
    for name, wanted in expected.items():
        assert value(name) == wanted, (name, value(name))
    assert value("LED_ANIM_INTERVAL_MS") <= value("LED_INTERVAL_MS")
    assert value("SMOKE_STABLE_SAMPLE_COUNT") >= 2
    assert value("LEVEL_STABLE_SAMPLE_COUNT") >= 2
    assert value("NODE_A_GAS_VENTILATION_HOLD_MS") == 30000
    assert value("SMOKE_SAMPLE_INTERVAL_MS") == value("FLAME_SAMPLE_INTERVAL_MS")

    # Timed actuators use the command TTL minus the time already spent, except
    # the explicit "both fans" and buzzer-test cases and the alarm holds.
    commit = function(NODE_A, "CommitActuators")
    assert "command->ttl_ms - elapsed_ms" in commit
    assert "NODE_A_ACTION_FANS_BOTH_START" in commit
    assert "? 0xFFFFFFFFUL : (command->ttl_ms - elapsed_ms)" in commit, (
        "an untimed both-fans start must hold the relay forever")
    assert "NODE_A_ACTION_BUZZER_TEST" in commit
    assert "? BUZZER_TEST_DURATION_MS : (command->ttl_ms - elapsed_ms)" in commit, (
        "the buzzer self-test must keep its fixed 1 s duration")
    assert "relay_duration_ms = duration_ms;" in NODE_A
    assert "buzzer_duration_ms = duration_ms;" in NODE_A
    assert "((now - relay_started_at) >= relay_duration_ms)" in NODE_A
    assert "((now - buzzer_started_at) >= buzzer_duration_ms)" in NODE_A
    assert "Buzzer_Start(0xFFFFFFFFUL);" in NODE_A, (
        "an active alarm must hold the buzzer until it clears")
    assert "Relay_Enable(0xFFFFFFFFUL);" in NODE_A, (
        "ventilation must hold the relay until the alarm clears")
    return f"timing={len(expected)} constants " \
           f"vent_hold={value('NODE_A_GAS_VENTILATION_HOLD_MS')}ms"


def check_pin_map():
    """Validate the complete preserved CTRL-01 pin map, port by port."""
    pins = {}
    ports = {}
    for source in (MAIN_H, NODE_A):
        for match in re.finditer(r"^#define\s+(\w+)_Pin\s+(GPIO_PIN_\d+)", source,
                                 re.MULTILINE):
            pins[match.group(1)] = match.group(2)
        for match in re.finditer(r"^#define\s+(\w+)_GPIO_Port\s+(GPIO\w+)", source,
                                 re.MULTILINE):
            ports[match.group(1)] = match.group(2)

    expected = {
        "LED": ("GPIOA", 8), "BUZZER": ("GPIOB", 0), "RELAY": ("GPIOA", 1),
        "SMOKE": ("GPIOB", 12), "FLAME": ("GPIOB", 14), "LEVEL": ("GPIOC", 0),
        "WS2812": ("GPIOB", 15), "FAN1_TACH": ("GPIOA", 6), "FAN2_TACH": ("GPIOA", 7),
        "FAN1_PWM": ("GPIOB", 8), "FAN2_PWM": ("GPIOB", 9),
    }
    actual = {name: (ports[name], pin_number(pins[name])) for name in expected}
    assert actual == expected, actual

    buses = re.findall(r"static const SoftI2cBus (\w+) = \{(GPIO\w+), (GPIO_PIN_\d+), "
                       r"(GPIO_PIN_\d+)\};", NODE_A)
    assert buses == [("i2c1_bus", "GPIOB", "GPIO_PIN_6", "GPIO_PIN_7"),
                     ("i2c2_bus", "GPIOB", "GPIO_PIN_10", "GPIO_PIN_11")], buses

    # No peripheral may claim a pin another one already owns.
    claimed = {f"{port}{number}": name for name, (port, number) in actual.items()}
    for name, port, scl, sda in buses:
        for pin in (scl, sda):
            key = f"{port}{pin_number(pin)}"
            assert key not in claimed, f"{name} collides with {claimed[key]} on {key}"
            claimed[key] = name
    for key, name in {"GPIOA9": "USART1_TX", "GPIOA10": "USART1_RX",
                      "GPIOA2": "USART2_TX", "GPIOA3": "USART2_RX",
                      "GPIOC1": "ADC_CO", "GPIOC2": "ADC_METHANE",
                      "GPIOC3": "ADC_OXYGEN"}.items():
        assert key not in claimed, f"{name} collides with {claimed[key]} on {key}"
        claimed[key] = name

    gpio = function(NODE_A, "MX_GPIO_Init")
    modes = dict(re.findall(r"gpio\.Pin = (\w+); gpio\.Mode = (\w+);", gpio))
    pulls = dict(re.findall(r"gpio\.Pin = (\w+); gpio\.Mode = \w+; gpio\.Pull = (\w+);",
                            gpio))
    for name in ("LED_Pin", "BUZZER_Pin", "RELAY_Pin"):
        assert modes[name] == "GPIO_MODE_OUTPUT_PP", (name, modes.get(name))
    for name in ("SMOKE_Pin", "FLAME_Pin", "LEVEL_Pin"):
        assert modes[name] == "GPIO_MODE_INPUT", (name, modes.get(name))
    for name in ("SMOKE_Pin", "LEVEL_Pin"):
        assert pulls[name] == "GPIO_NOPULL", (name, pulls.get(name))
    assert pulls["FLAME_Pin"] == "GPIO_PULLUP", "the flame input must keep its pull-up"
    for name in ("FAN1_TACH_Pin", "FAN2_TACH_Pin"):
        assert modes[name] == "GPIO_MODE_IT_RISING", (name, modes.get(name))
        assert pulls[name] == "GPIO_PULLUP", (name, pulls.get(name))
    assert "gpio.Pin = i2c1_bus.scl_pin | i2c1_bus.sda_pin | i2c2_bus.scl_pin | " \
           "i2c2_bus.sda_pin;" in gpio, "both software-I2C buses must stay configured"
    assert "gpio.Mode = GPIO_MODE_OUTPUT_OD" in gpio, (
        "the software-I2C buses must stay open-drain")
    # STM32F1 ignores Pull for an open-drain output, so the bus levels come from
    # the module pull-ups; a Pull field here would be misleading, not helpful.
    assert "gpio.Pull" not in gpio[gpio.index("GPIO_MODE_OUTPUT_OD") - 200:], (
        "an open-drain output cannot use the internal pull-up/down")
    assert "HAL_GPIO_WritePin(GPIOB, i2c1_bus.scl_pin | i2c1_bus.sda_pin | " \
           "i2c2_bus.scl_pin | i2c2_bus.sda_pin, GPIO_PIN_SET);" in gpio, (
        "the I2C lines must be released high before the open-drain config")

    pwm = function(NODE_A, "MX_FAN1_PWM_Init")
    assert "gpio.Pin = FAN1_PWM_Pin | FAN2_PWM_Pin;" in pwm
    assert "gpio.Mode = GPIO_MODE_AF_PP;" in pwm
    ws = function(NODE_A, "MX_WS2812_SPI_Init")
    assert "gpio.Pin = WS2812_Pin;" in ws and "GPIO_MODE_AF_PP" in ws
    assert "TIM4_REMAP" not in NODE_A and "GPIO_AFIO_REMAP_TIM4" not in NODE_A, (
        "the fan PWM pins must stay on the default TIM4 channels PB8/PB9")

    # USART and ADC pins live in the MSP.
    usart1 = MSP[MSP.index("huart->Instance == USART1"):MSP.index(
        "huart->Instance == USART2")]
    assert "GPIO_InitStruct.Pin = GPIO_PIN_9;" in usart1
    assert "GPIO_InitStruct.Pin = GPIO_PIN_10;" in usart1
    assert usart1.count("HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);") == 2
    usart2 = MSP[MSP.index("huart->Instance == USART2"):]
    assert "GPIO_InitStruct.Pin = GPIO_PIN_2;" in usart2
    assert "GPIO_InitStruct.Pin = GPIO_PIN_3;" in usart2
    adc_msp = function(MSP, "HAL_ADC_MspInit")
    assert "GPIO_InitStruct.Pin = GPIO_PIN_1 | GPIO_PIN_2 | GPIO_PIN_3;" in adc_msp
    assert "GPIO_MODE_ANALOG" in adc_msp
    for comment in ("PC1     ------> ADC1_IN11", "PC2     ------> ADC1_IN12",
                    "PC3     ------> ADC1_IN13"):
        assert comment in MSP, comment
    return f"pins={len(claimed)} buses=2 no-collisions"


def check_interrupts():
    """Validate the preserved NVIC priorities and their ordering."""
    tach = re.search(r"HAL_NVIC_SetPriority\(EXTI9_5_IRQn, (\w+), (\w+)\)", NODE_A)
    esp = re.search(r"HAL_NVIC_SetPriority\(USART2_IRQn, (\w+), (\w+)\)", MSP)
    assert tach and tach.group(1) == "NODE_A_TACH_IRQ_PRIORITY" and tach.group(2) == "0U"
    assert esp and esp.group(1) == "NODE_A_ESP_IRQ_PRIORITY" and esp.group(2) == "0"
    assert "HAL_NVIC_EnableIRQ(EXTI9_5_IRQn);" in NODE_A
    assert "HAL_NVIC_EnableIRQ(USART2_IRQn);" in MSP
    # Node B keeps its own display DMA priority inside its own adapter: SPI1 TX
    # is DMA1_Channel3 on STM32F103 (the display contract test pins the same
    # vector).  The old DMA1_Channel1 expectation predated that assignment.
    assert "HAL_NVIC_SetPriority(DMA1_Channel3_IRQn, 2U, 0U);" in NODE_B_BUS
    assert "HAL_NVIC_EnableIRQ(DMA1_Channel3_IRQn);" in NODE_B_BUS

    esp_prio = value("NODE_A_ESP_IRQ_PRIORITY")
    tach_prio = value("NODE_A_TACH_IRQ_PRIORITY")
    tick_prio = value("TICK_INT_PRIORITY")
    assert (esp_prio, tach_prio, tick_prio) == (1, 2, 15)
    assert esp_prio < tach_prio < tick_prio, "the interrupt ordering changed"
    assert "HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4)" in HAL_C, (
        "preemption-only priority grouping is required for these orderings")
    return f"nvic=esp{esp_prio}<tach{tach_prio}<tick{tick_prio}"


def check_clock_report():
    """The bench probe must read registers, not echo the test's own constants."""
    report = function(NODE_A, "NodeTest_ReportClock")
    for register in ("RCC->CR", "RCC->CFGR", "FLASH->ACR", "USART1->BRR",
                     "USART2->BRR", "TIM4->PSC", "TIM4->ARR", "SPI2->CR1",
                     "SysTick->LOAD"):
        assert register in report, f"#NODETEST CLOCK must report {register}"
    # The emitted field names live in the format string, which the noise
    # stripper removes, so read them from the raw source region.
    raw_report = NODE_A[NODE_A.index("NodeTest_ReportClock(void)"):
                        NODE_A.index("static void NodeTest_HandleLine")]
    for field in ("rcc_cr=", "rcc_cfgr=", "flash_acr=", "uart1_brr=", "uart2_brr=",
                  "tim4_psc=", "tim4_arr=", "spi2_cr1=", "systick_load="):
        assert f"{field}0x" in raw_report or f"{field}%" in raw_report, (
            f"#NODETEST CLOCK must emit {field}")
    for constant in ("NODE_A_ADC_CLOCK_HZ", "NODE_A_FAN_PWM_HZ",
                     "NODE_A_WS2812_SPI_HZ", "NODE_A_UART_BAUD"):
        assert constant not in report, (
            f"the probe must not echo the compile-time constant {constant}")
    for helper, register in (("NodeTest_AdcClock", "RCC_CFGR_ADCPRE"),
                             ("NodeTest_Apb1TimerClock", "RCC_CFGR_PPRE1")):
        assert register in function(NODE_A, helper), f"{helper} must decode {register}"

    # The register words the firmware will actually program, derived here.
    cfgr = (value("RCC_CFGR_SW_PLL") | (value("RCC_CFGR_SW_PLL") << 2)
            | (value("RCC_HCLK_DIV2") & value("RCC_CFGR_PPRE1"))
            | value("RCC_ADCPCLK2_DIV6") | value("RCC_CFGR_PLLSRC")
            | value("RCC_PLL_MUL9"))
    assert cfgr == 0x001D840A, hex(cfgr)
    assert value("FLASH_ACR_LATENCY_1") == 0x2 and value("FLASH_ACR_PRFTBE") == 0x10
    spi_cr1 = (value("SPI_CR1_MSTR") | value("SPI_CR1_SSM") | value("SPI_CR1_SSI")
               | value("SPI_CR1_BR_1") | value("SPI_CR1_SPE"))
    assert spi_cr1 == 0x354, hex(spi_cr1)
    cr_mask = value("RCC_CR_HSEON") | value("RCC_CR_PLLON")
    assert cr_mask == 0x01010000, hex(cr_mask)
    return f"cfgr={cfgr:#010x} spi2_cr1={spi_cr1:#06x} flash_acr={0x12:#06x}"


def main():
    results = [
        check_clock_tree(), check_systick(), check_uart(), check_adc(),
        check_fan_pwm(), check_tach(), check_ws2812(), check_i2c_bounds(),
        check_actuator_timing(), check_pin_map(), check_interrupts(),
        check_clock_report(),
    ]
    print("Node A clock/peripheral contract model: PASS")
    for result in results:
        print(f"  {result}")


if __name__ == "__main__":
    main()
