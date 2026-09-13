"""Reproducible pre-retune clock baseline for CTRL-01.

Task 9 Step 1 asks for the earlier 8 MHz configuration as evidence that the
clock tree was retuned from a known state.  This script *derives* that state
from the sources at a given revision; it does not report, and must never be
presented as, a measurement taken on hardware.

    python3 tests/node_a_clock_baseline.py --rev 998e29e
    python3 tests/node_a_clock_baseline.py --check tests/node_a_clock_baseline.txt

The stored artifact is the derived baseline for the last revision before the
retune.  `--check` regenerates it from git history and fails loudly if the
values move or if the revision is unavailable (a shallow clone must fetch it
rather than silently skip the check).
"""
import argparse
import os
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKTREE = ROOT.parents[1]
DEFAULTS = {
    "HSE_VALUE": 8_000_000,
    "HSI_VALUE": 8_000_000,
    "TIMER_ARR": 319,
    "TIMER_PSC": 0,
}


def git_dir_args():
    """Resolve the worktree's git directory, translating a Windows path when
    the script runs under WSL (a linked worktree stores an absolute path)."""
    marker = WORKTREE / ".git"
    if marker.is_dir():
        return []
    text = marker.read_text(encoding="utf-8").strip()
    if not text.startswith("gitdir:"):
        return []
    path = text.split(":", 1)[1].strip()
    drive = re.match(r"^([A-Za-z]):[/\\](.*)$", path)
    if drive and os.name != "nt":
        path = f"/mnt/{drive.group(1).lower()}/{drive.group(2)}"
    return [f"--git-dir={path}"]


def source_at(rev, path, required=True):
    result = subprocess.run(
        ["git", *git_dir_args(), "show", f"{rev}:{path}"],
        cwd=str(WORKTREE), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        assert not required, f"{path} is missing at {rev}"
        return ""
    return result.stdout


def resolve_define(sources, name):
    """Follow a #define chain (possibly across files) to its numeric value."""
    if re.fullmatch(r"\d+[uUlL]*", str(name)):
        return int(re.match(r"\d+", str(name)).group(0))
    for _ in range(8):
        body = None
        for source in sources:
            match = re.search(rf"^#define\s+{re.escape(name)}\s+([^/\r\n]+)", source,
                              re.MULTILINE)
            if match:
                body = match.group(1).strip()
                break
        if body is None:
            return None
        literal = re.fullmatch(r"(\d+)[uUlL]*", body)
        if literal:
            return int(literal.group(1))
        name = body
    return None


def function(source, name):
    text = re.sub(r"/\*.*?\*/|//[^\n]*", " ", source, flags=re.DOTALL)
    match = re.search(rf"\b{re.escape(name)}\s*\([^{{;]*?\)\s*\{{", text, re.DOTALL)
    assert match, f"function {name} not found at this revision"
    depth, end = 1, match.end()
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[match.start():end]


def derive(source, hal_conf, contract=""):
    """Derive the clock tree the sources at this revision actually select."""
    clock = function(source, "SystemClock_Config")
    hse = int(re.search(r"#define\s+HSE_VALUE\s+(\d+)", hal_conf).group(1))
    hsi = int(re.search(r"#define\s+HSI_VALUE\s+(\d+)", hal_conf).group(1))

    if "RCC_OSCILLATORTYPE_HSE" in clock and "RCC_PLL_MUL9" in clock:
        system = "HSE"
        pll_multiplier = 9
        sysclk = hse * pll_multiplier
        hse_state = "on"
    elif "RCC_OSCILLATORTYPE_HSI" in clock:
        system = "HSI"
        pll_multiplier = 0
        sysclk = hsi
        hse_state = "off (HSI is the system clock)"
    else:
        raise AssertionError("unrecognised SystemClock_Config at this revision")

    ahb_divider = int(re.search(r"AHBCLKDivider = RCC_SYSCLK_DIV(\d+)", clock).group(1))
    apb1_divider = int(re.search(r"APB1CLKDivider = RCC_HCLK_DIV(\d+)", clock).group(1))
    apb2_divider = int(re.search(r"APB2CLKDivider = RCC_HCLK_DIV(\d+)", clock).group(1))
    latency = int(re.search(r"HAL_RCC_ClockConfig\(&clock, FLASH_LATENCY_(\d+)\)",
                            clock).group(1))
    if "AdcClockSelection" in clock:
        adc_divider = int(re.search(r"AdcClockSelection = RCC_ADCPCLK2_DIV(\d+)",
                                    clock).group(1))
        adc_source = f"RCC_ADCPCLK2_DIV{adc_divider}"
    else:
        # No ADC clock is selected, so RCC_CFGR.ADCPRE keeps its reset value
        # 0b00, which is PCLK2 / 2 (RM0008 reset value 0x0000_0000).
        adc_divider = 2
        adc_source = "reset default ADCPRE = /2 (never configured by this revision)"

    hclk = sysclk // ahb_divider
    pclk1 = hclk // apb1_divider
    pclk2 = hclk // apb2_divider
    # An APB1 prescaler other than one doubles the APB1 timer clock.
    timer_hz = pclk1 if apb1_divider == 1 else pclk1 * 2

    pwm = function(source, "MX_FAN1_PWM_Init")
    psc = re.search(r"TIM4->PSC = (\d+)U?", pwm)
    arr = re.search(r"TIM4->ARR = (\w+)", pwm)
    prescaler = int(psc.group(1)) if psc else DEFAULTS["TIMER_PSC"]
    period = resolve_define([source, contract], arr.group(1))
    assert period is not None, f"cannot resolve the fan timer period {arr.group(1)}"

    baud_name = re.search(r"Init\.BaudRate = (\w+);", source).group(1)
    baud = resolve_define([source, contract], baud_name)
    assert baud is not None, f"cannot resolve the baud rate {baud_name}"
    # HAL 16x-oversampling BRR: USARTDIV x100, then the fraction in sixteenths.
    usartdiv100 = pclk2 * 25 // (4 * baud)
    fraction = (usartdiv100 % 100) * 16 + 50
    brr = ((usartdiv100 // 100) << 4) + (fraction // 100 & 0xF0) + (fraction // 100 & 0x0F)
    actual_baud = pclk2 / brr
    return {
        "system_clock_source": system,
        "hse_state": hse_state,
        "hse_hz": hse,
        "hsi_hz": hsi,
        "pll_multiplier": pll_multiplier,
        "sysclk_hz": sysclk,
        "hclk_hz": hclk,
        "pclk1_hz": pclk1,
        "pclk2_hz": pclk2,
        "apb1_timer_hz": timer_hz,
        "flash_wait_states": latency,
        "adc_source": adc_source,
        "adc_divider": adc_divider,
        "adc_hz": pclk2 // adc_divider,
        "timer_prescaler": prescaler,
        "timer_period": period,
        "fan_pwm_hz": timer_hz // ((prescaler + 1) * (period + 1)),
        "uart_baud": baud,
        "usart1_brr": brr,
        "usart1_actual_baud": round(actual_baud, 2),
        "usart1_baud_error_ppm": round((actual_baud - baud) / baud * 1e6),
        "systick_reload": hclk // 1000 - 1,
    }


def model(rev):
    """Derived baseline for one revision, without any physical claim."""
    source = source_at(rev, "firmware/stm32f103rct6/Core/Src/node_a.c")
    hal_conf = source_at(rev, "firmware/stm32f103rct6/Core/Inc/stm32f1xx_hal_conf.h")
    contract = source_at(rev, "firmware/stm32f103rct6/Core/Inc/node_a_clock_contract.h",
                         required=False)
    return derive(source, hal_conf, contract)


def record(rev, derived):
    """The stored form: the revision plus every derived field."""
    return "\n".join([f"revision={rev}"] +
                     [f"{key}={value if value is not None else 'n/a'}"
                      for key, value in derived.items()])


def check(artifact):
    raw = pathlib.Path(artifact).read_text(encoding="utf-8").splitlines()
    # The provenance label must survive: this is a source model, never a
    # measurement, and the artifact must say so.
    assert raw and "NOT a hardware measurement" in raw[0], (
        f"{artifact} must keep its 'source model, NOT a hardware measurement' label")
    stored = [line for line in raw if line and not line.startswith("#")]
    header = dict(line.split("=", 1) for line in stored if "=" in line)
    rev = header.get("revision")
    assert rev, f"{artifact} must record the revision it was derived from"
    regenerated = record(rev, model(rev))
    assert "\n".join(stored) == regenerated, (
        f"{artifact} no longer matches revision {rev}:\n"
        f"--- stored ---\n" + "\n".join(stored) +
        "\n--- regenerated ---\n" + regenerated)
    print(f"Node A clock baseline artifact matches revision {rev}: PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rev", help="git revision whose node_a.c is to be modelled")
    parser.add_argument("--check", metavar="ARTIFACT",
                        help="re-derive the stored baseline and compare")
    args = parser.parse_args()
    assert args.rev or args.check, "pass --rev or --check"

    if args.check:
        check(args.check)
        return
    print(f"# Node A clock baseline derived from {args.rev} "
          f"(source model, NOT a hardware measurement)")
    print(record(args.rev, model(args.rev)))


if __name__ == "__main__":
    main()
