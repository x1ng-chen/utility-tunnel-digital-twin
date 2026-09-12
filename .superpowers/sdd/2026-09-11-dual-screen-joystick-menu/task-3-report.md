# Task 3 report — 72 MHz clock and SPI1 DMA display transport

## Delivered

- Node B now selects the 8 MHz HSE, PLL x9, 72 MHz SYSCLK, AHB /1,
  APB1 /2, APB2 /1, Flash latency 2, and ADC PCLK2 /6. USART1 and USART2
  remain configured for 9600 baud.
- Node B drives the ST7735 through SPI1 mode 0 at PCLK2 /4 (18 MHz): PA5 is
  SCK, PA7 is MOSI, and PA6 is unused. PB6/PB7/PB8/PB9 remain RES/DC/CS/BLK.
- `St7735Bus_*` owns DMA1 Channel 3 as an 8-bit, memory-increment,
  memory-to-peripheral transport with transfer-complete and transfer-error
  interrupts. DMA1 Channel 1 flags/configuration are never cleared or changed
  by the display transport.
- The rasterizer uses two 256-byte line buffers. It converts RGB565 to
  controller byte order into one buffer while DMA retains the other; it never
  allocates a full framebuffer.
- `ST7735_WritePixels`, clipped `ST7735_FillRect`, clipped
  `ST7735_BlitRgb565`, glyphs, and characters use bulk pixel runs. The software
  SPI implementation remains compiled for Node A.
- Foreground waits keep interrupts enabled and are bounded by SysTick plus DWT
  cycle counting. Timeout or DMA error aborts Channel 3, deselects the panel,
  resets SPI1, records a counter, and permits a later fresh transaction.
- `#DISPLAYTEST` reports `sysclk`, `spi_hz`, `dma_frames`, `dma_timeouts`,
  `worst_frame_us`, and `dma_errors`. `#DISPLAYTEST RUN` schedules exactly 1000
  alternating eight-row transfers followed by a three-color full-screen cycle,
  one primitive per main-loop iteration.
- Existing `#UITEST` and `#JOYTEST` parsing remains in the shared UART1 line
  handler. TIM3 continues to trigger the ADC1 two-rank scan at 200 Hz (5 ms),
  with circular halfword DMA on DMA1 Channel 1 and its higher-priority IRQ.

## TDD and audit evidence

The interrupted worker left the Task 3 production and host-test files together
as an uncommitted test-first diff. The inherited raster harness covers clipping,
RGB565 big-endian output, source-stride preservation, two-buffer ownership,
full-screen chunking, and aborted-frame accounting. The inherited real-register
bus harness covers DMA bounds, Channel 1 isolation, Channel 3 IRQ ownership,
DMA/SPI stuck states, DWT fallback, error recovery, and a usable transaction
after recovery.

During takeover, the clock contract was strengthened to execute the exact
Node B clock/UART functions, the real joystick module, and the exact ADC MSP
function. Its expectations independently assert PLL x9, all bus dividers,
Flash latency, both UART BRRs and modes, ADC /6, ADC channels/ranks/sample time,
DMA1 Channel 1 direction/width/circular mode/linkage/IRQ priority, and the TIM3
200 Hz trigger.

The strengthened contract can load the pre-Task-3 source directly from Git.
That recovers a valid RED result without modifying the inherited implementation:

```text
wsl.exe sh -lc "cd .../firmware/stm32f103rct6 && python3 tests/display_clock_host_test.py --node-b-revision HEAD"
clock_test: <stdin>:171: main: Assertion
  `osc.OscillatorType == RCC_OSCILLATORTYPE_HSE && osc.HSEState == RCC_HSE_ON'
  failed.
exit 1 (expected RED: HEAD still selected the 8 MHz HSI)
```

The current worktree then supplies GREEN:

```text
wsl.exe sh -lc "cd .../firmware/stm32f103rct6 && sh tests/run_display_host.sh"
Display raster test: PASS
Display bus test: PASS
Display clock/UART/joystick contract test: PASS
```

## Fresh verification

All commands below were rerun on the final code immediately before this report.

```text
wsl.exe sh -lc "cd .../firmware/stm32f103rct6 && sh tests/run_display_host.sh && <Task 1/2 host commands> && python3 -m py_compile tests/display_clock_host_test.py tests/display_serial_probe.py"
Display raster test: PASS
Display bus test: PASS
Display clock/UART/joystick contract test: PASS
UiState host test: PASS
Joystick host test: PASS
exit 0
```

The raster and bus harnesses were also compiled independently with
`-Wall -Wextra -Werror` (plus the established host-only CMSIS
`-Wno-int-to-pointer-cast` suppression):

```text
Display raster test: PASS
Display bus test: PASS
exit 0
```

```text
cmake --preset NodeB --fresh
cmake --build --preset NodeB
exit 0
RAM: 3328 B / 48 KB (6.77%)
FLASH: 33360 B / 256 KB (12.73%)
stm32_controller.bin generated
```

```text
cmake --preset NodeA --fresh
cmake --build --preset NodeA
exit 0
RAM: 4312 B / 48 KB (8.77%)
FLASH: 30016 B / 256 KB (11.45%)
stm32_controller.bin generated
```

## Physical verification status

`[System.IO.Ports.SerialPort]::GetPortNames()` and the present Ports-class PnP
query both returned no devices. No firmware was flashed in this environment.
Accordingly, the following remain explicitly unverified on hardware:

- HSE/PLL SYSCLK and SPI waveforms at 72 MHz and 18 MHz;
- physical USART1/USART2 baud rate at 9600;
- ADC input acquisition and TIM3 trigger cadence on the board;
- 1000 dirty-row transfers with zero physical-bus timeouts;
- the three-color full-screen cycle at or below 22 ms.

Run `python tests/display_serial_probe.py --port COMx --run` after flashing the
Node B binary. The host tests validate the configured registers, byte stream,
bounds, and recovery behavior, but do not substitute for electrical or panel
timing measurements.

## Self-review and scope

- Reviewed the complete Task 3 diff against the brief and checked the required
  APIs, pin map, bus clocks, DMA register setup, buffer size, timeout paths,
  interrupt ownership, diagnostics, and Node A conditional fallback.
- No production behavior defect was found during takeover. The only production
  edit made after the inherited implementation was correcting the header's
  pin-map comment to distinguish Node A from Node B.
- Task 3 necessarily includes CMake source registration and deterministic host
  tests in addition to the six production files named in the brief. No unrelated
  tracked or untracked files are included.
