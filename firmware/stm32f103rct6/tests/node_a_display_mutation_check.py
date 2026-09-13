"""Mutation check for the CTRL-01 secondary display suites.

The display tests are only as good as the defects they catch, so this tool
copies the firmware tree to a temporary directory, injects one realistic defect
at a time into the copy, runs tests/run_node_a_status_host.sh against it and
reports whether the suite failed.  The working tree is never modified.

    python3 tests/node_a_display_mutation_check.py      (needs gcc + python3)

Every seeded defect below would be a real firmware problem (a carousel that
skips or stretches a page, an alarm that waits for a dwell, a display that
takes over a fan PWM pin, a wrong SPI divider or DMA channel, a lost frame
bound), so a MISSED line means the suite has a hole worth closing.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

SOURCE = pathlib.Path(__file__).resolve().parent.parent
RUNNER = "tests/run_node_a_status_host.sh"

# (description, file, exact text to replace, replacement)
MUTATIONS = [
    # Page model: dwell, order, takeover and recovery.
    ("dwell shortened to four seconds",
     "Core/Inc/node_a_status_screen.h", "#define NODE_A_STATUS_DWELL_MS        5000U",
     "#define NODE_A_STATUS_DWELL_MS        4000U"),
    ("carousel phase shifted by one page",
     "Core/Src/node_a_status_screen.c", "           NODE_A_STATUS_DWELL_MS) % NODE_A_STATUS_CAROUSEL_PAGES;",
     "           NODE_A_STATUS_DWELL_MS + 1U) % NODE_A_STATUS_CAROUSEL_PAGES;"),
    ("alarm takeover branch loses its early return",
     "Core/Src/node_a_status_screen.c",
     "      model->page = NODE_A_STATUS_PAGE_ALARM;\n    model->alarm_active = 1U;\n    return;\n",
     "      model->page = NODE_A_STATUS_PAGE_ALARM;\n    model->alarm_active = 1U;\n"),
    ("carousel resumes mid-dwell instead of restarting on recovery",
     "Core/Src/node_a_status_screen.c", "    model->carousel_epoch_ms = now_ms;\n  }",
     "    model->carousel_epoch_ms = now_ms - NODE_A_STATUS_DWELL_MS;\n  }"),
    ("alarm page painted in the normal background colour",
     "Core/Src/node_a_status_screen.c", "  ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_DANGER);",
     "  ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);"),
    ("time placeholder replaced with a fabricated 00:00",
     "Core/Src/node_a_status_screen.c", '    (void)snprintf(output, size, "--:--");\n    return;',
     '    (void)snprintf(output, size, "00:00");\n    return;'),
    ("periodic refresh dropped so a stopped sensor never repaints",
     "Core/Src/node_a_status_screen.c",
     "  if ((page_changed == 0U) && (data_changed == 0U) && (refresh_due == 0U)) return;",
     "  (void)refresh_due;\n"
     "  if ((page_changed == 0U) && (data_changed == 0U)) return;"),
    # Bus adapter: clock, channel, pin map and bounded waits.
    ("SPI3 divider widened to /4 (9 MHz)",
     "Core/Src/st7735_bus_node_a.c", "    SPI3->CR1 = SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI |",
     "    SPI3->CR1 = SPI_CR1_MSTR | SPI_CR1_BR_0 | SPI_CR1_SSM | SPI_CR1_SSI |"),
    ("display moved onto DMA2 Channel1 (SPI3 RX channel)",
     "Core/Src/st7735_bus_node_a.c", "    DMA2_Channel2->CCR = DMA_CCR_DIR | DMA_CCR_MINC | DMA_CCR_TCIE | DMA_CCR_TEIE;",
     "    DMA2_Channel1->CCR = DMA_CCR_DIR | DMA_CCR_MINC | DMA_CCR_TCIE | DMA_CCR_TEIE;"),
    # The cycle budget is shrunk rather than deleted on purpose: a defect that
    # removes the bound entirely would hang the suite instead of failing it.
    ("DWT cycle budget shrunk to one cycle",
     "Core/Src/st7735_bus_node_a.c",
     "            ((uint32_t)(St7735Bus_Cycles() - cycles) >=\n"
     "             (SystemCoreClock / 1000U) * ST7735_BUS_TIMEOUT_MS)) {",
     "            ((uint32_t)(St7735Bus_Cycles() - cycles) >= 1U)) {"),
    ("CS moved onto PB8, the TIM4 fan PWM pin",
     "Core/Inc/st7735.h", "#define LCD_CS_PIN      GPIO_PIN_6    /* CS  */",
     "#define LCD_CS_PIN      GPIO_PIN_8    /* CS  */"),
    ("SPI3 remapped away from its default pins",
     "Core/Src/stm32f1xx_hal_msp.c", "  __HAL_AFIO_REMAP_SWJ_NOJTAG();",
     "  __HAL_AFIO_REMAP_SWJ_NOJTAG();\n  __HAL_AFIO_REMAP_SPI3_ENABLE();"),
    ("JTAG released without keeping SWD",
     "Core/Src/stm32f1xx_hal_msp.c", "  __HAL_AFIO_REMAP_SWJ_NOJTAG();",
     "  __HAL_AFIO_REMAP_SWJ_ENABLE();"),
    ("display DMA raised above the fan tachometer",
     "Core/Inc/node_a_clock_contract.h", "#define NODE_A_DISPLAY_IRQ_PRIORITY                   3U",
     "#define NODE_A_DISPLAY_IRQ_PRIORITY                   1U"),
    ("Node A stops consuming the ESP-01 time sync",
     "Core/Src/node_a.c", "    EspTime_Poll();\n", ""),
    ("main loop stops ticking the secondary screen",
     "Core/Src/node_a.c", "    Status_Tick(now);\n", ""),
    ("panel never initialised at boot",
     "Core/Src/node_a.c", "  ST7735_Init();\n", ""),
]


def run_suite(tree):
    # A seeded defect must fail the suite, not wedge it: bound the run so a
    # mutated busy-wait is reported rather than hanging the gate.
    try:
        result = subprocess.run(["sh", RUNNER], cwd=str(tree), capture_output=True,
                                text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, ["the suite did not finish within 120 s"]
    return result.returncode == 0, (result.stdout + result.stderr).strip().splitlines()


def main():
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="node_a_display_mutation_"))
    tree = scratch / SOURCE.name
    shutil.copytree(SOURCE, tree,
                    ignore=shutil.ignore_patterns("build*", "__pycache__"))
    print(f"scratch copy: {tree}")

    clean, output = run_suite(tree)
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
        still_passes, output = run_suite(tree)
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
