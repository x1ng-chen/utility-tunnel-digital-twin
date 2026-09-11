# Dual-Screen Joystick Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 60 FPS joystick-controlled primary menu on CTRL-02, route its commands through MQTT with acknowledgements from CTRL-01, and add an automatic status display to CTRL-01.

**Architecture:** Keep menu state, joystick decoding, display transport, snapshots, commands, and time synchronization as separate modules. CTRL-02 owns interaction and publishes commands through ESP-02; CTRL-01 owns sensors, safety policy, actuators, acknowledgements, and the read-only secondary screen. Both displays use 18 MHz SPI DMA at a 72 MHz MCU clock and redraw only dirty regions.

**Tech Stack:** STM32F103RCT6 HAL/C11, ST7735 RGB565, SPI/DMA, ADC, ESP8266 Arduino/PlatformIO, PubSubClient MQTT, NTP/Unix time, Node.js 22 test runner, Python/pyserial hardware probes, CMake/Ninja/Arm GNU Toolchain.

**Spec:** `docs/superpowers/specs/2026-09-11-dual-screen-joystick-menu-design.md`

## Global Constraints

- Preserve all existing Node A sensor, fan, relay, WS2812, buzzer, INA226, USART, and safety behavior.
- CTRL-02 is the only interactive screen; CTRL-01 is read-only and auto-rotates every 5 seconds.
- Manual menu commands never override an active validated safety alarm.
- Oxygen and CO remain telemetry-only until their physical front ends are calibrated.
- A command is successful only after a matching `ut.command.ack.v1` carrying the same `cmdId` arrives.
- MQTT loss locks the menu control pages; local CTRL-01 safety logic continues operating.
- Do not store Huawei Cloud credentials on either STM32 or ESP8266.
- Preserve unrelated dirty-worktree changes; stage only files belonging to the current task.

---

## Milestone 1 — CTRL-02 Local 60 FPS Menu

### Task 1: Pure menu state machine

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/ui_model.h`
- Create: `firmware/stm32f103rct6/Core/Inc/ui_state.h`
- Create: `firmware/stm32f103rct6/Core/Src/ui_state.c`
- Create: `firmware/stm32f103rct6/tests/ui_state_serial_probe.py`
- Modify: `firmware/stm32f103rct6/CMakeLists.txt`

**Interfaces:**
- Produces: `void UiState_Init(UiState *state)`, `UiEffect UiState_Handle(UiState *state, UiInputEvent event, uint32_t now_ms)`, `void UiState_Tick(UiState *state, uint32_t now_ms)`.
- Produces the shared, HAL-free `UiSnapshot` display model used by the renderer and later populated by the snapshot parser. It includes sensor quality/timestamps, alarms, both fan target/actual values, actuator states, connectivity, and last-command result.
- `UiState` exposes page, selected row, dialog, animation start/end, and command phase; it contains no HAL types.

- [ ] **Step 1: Write a failing serial behavior probe**

```python
# tests/ui_state_serial_probe.py
send('#UITEST RESET\n')
assert read_line() == '#UI page=home row=0 dialog=none command=idle'
send('#UITEST DOWN\n')
assert 'row=1' in read_line()
send('#UITEST LONG_PRESS\n')
assert 'page=home row=0' in read_line()
```

- [ ] **Step 2: Run the probe against the current Node B firmware**

Run: `python tests/ui_state_serial_probe.py --port COM6 --baud 9600`

Expected: FAIL because `#UITEST` is not recognized.

- [ ] **Step 3: Implement the minimal deterministic state machine**

```c
typedef enum { UI_HOME, UI_OVERVIEW, UI_MONITOR, UI_ALERTS, UI_FANS,
               UI_LIGHT_SOUND, UI_NETWORK, UI_SETTINGS } UiPage;
typedef enum { UI_EVT_NONE, UI_EVT_UP, UI_EVT_DOWN, UI_EVT_LEFT,
               UI_EVT_RIGHT, UI_EVT_PRESS, UI_EVT_LONG_PRESS } UiInputEvent;
typedef enum { UI_CMD_IDLE, UI_CMD_CONFIRM, UI_CMD_SENDING,
               UI_CMD_ACCEPTED, UI_CMD_REJECTED, UI_CMD_TIMEOUT } UiCommandPhase;
typedef enum { UI_EFFECT_NONE, UI_EFFECT_DIRTY, UI_EFFECT_OPEN_CONFIRM,
               UI_EFFECT_SEND_COMMAND, UI_EFFECT_GO_HOME } UiEffectKind;
typedef struct {
    UiEffectKind kind;
    uint8_t action;
    uint8_t value;
} UiEffect;
```

Implement wraparound navigation only on pages that declare it, left/back semantics, short-press confirm, long-press home, critical-action confirmation, and a 5000 ms command timeout.

- [ ] **Step 4: Add a Node B-only `#UITEST` UART1 adapter and rerun**

Run: `cmake --preset NodeB --fresh && cmake --build --preset NodeB`

Flash `build/NodeB/stm32_controller.bin`, then run the probe. Expected: PASS for reset, navigation, dialog, and timeout cases.

- [ ] **Step 5: Commit**

```powershell
git add firmware/stm32f103rct6/Core/Inc/ui_model.h firmware/stm32f103rct6/Core/Inc/ui_state.h firmware/stm32f103rct6/Core/Src/ui_state.c firmware/stm32f103rct6/tests/ui_state_serial_probe.py firmware/stm32f103rct6/CMakeLists.txt
git commit -m "feat(firmware): add deterministic display menu state"
```

### Task 2: Joystick calibration and event decoder

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/joystick.h`
- Create: `firmware/stm32f103rct6/Core/Src/joystick.c`
- Create: `firmware/stm32f103rct6/tests/joystick_serial_probe.py`
- Modify: `firmware/stm32f103rct6/Core/Src/node_b.c`

**Interfaces:**
- Consumes: `UiInputEvent` from `ui_state.h`.
- Produces: `Joystick_Init()`, `Joystick_Calibrate()`, and `UiInputEvent Joystick_Poll(uint32_t now_ms)`.

- [ ] **Step 1: Add failing synthetic ADC cases**

```python
cases = [
    ('#JOYTEST 2048 2048 1 0\n', 'NONE'),
    ('#JOYTEST 3600 2048 1 10\n', 'RIGHT'),
    ('#JOYTEST 2048 400 1 20\n', 'UP'),
    ('#JOYTEST 2048 2048 0 30\n', 'PRESS'),
]
```

Expected initial result: FAIL because `#JOYTEST` is absent.

- [ ] **Step 2: Implement input filtering**

Use 16-sample center calibration, a default ±500 ADC dead zone, 100-count hysteresis, 25 ms switch debounce, 1000 ms long press, 350 ms repeat delay, and 100 ms repeat period. Emit at most one event per poll.

- [ ] **Step 3: Configure Node B ADC/GPIO without pin conflicts**

Configure PC0/ADC1_IN10 for VRx, PC1/ADC1_IN11 for VRy, PC4 input pull-up for SW, ADC clock at 12 MHz or less, and an acquisition cadence of 5 ms. Power the joystick from 3.3 V despite its `+5V` label.

- [ ] **Step 4: Build, flash, and verify synthetic plus physical input**

Run the synthetic probe, then leave the joystick untouched for 60 seconds. Expected: no spontaneous event. Exercise every direction, short press, long press, and held-repeat once.

- [ ] **Step 5: Commit**

```powershell
git add firmware/stm32f103rct6/Core/Inc/joystick.h firmware/stm32f103rct6/Core/Src/joystick.c firmware/stm32f103rct6/Core/Src/node_b.c firmware/stm32f103rct6/tests/joystick_serial_probe.py
git commit -m "feat(firmware): add calibrated Node B joystick input"
```

### Task 3: 72 MHz clock and SPI1 DMA display transport

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/st7735_bus.h`
- Create: `firmware/stm32f103rct6/Core/Src/st7735_bus_node_b.c`
- Modify: `firmware/stm32f103rct6/Core/Src/st7735.c`
- Modify: `firmware/stm32f103rct6/Core/Inc/st7735.h`
- Modify: `firmware/stm32f103rct6/Core/Src/node_b.c`
- Modify: `firmware/stm32f103rct6/Core/Src/stm32f1xx_it.c`

**Interfaces:**
- Produces: `St7735Bus_Init()`, `St7735Bus_BeginData()`, `St7735Bus_WriteAsync(const uint8_t *, uint16_t)`, `St7735Bus_IsBusy()`, and `St7735Bus_Recover()`.
- Display mapping: PA5=SCK, PA7=MOSI, PB6=RES, PB7=DC, PB8=CS, PB9=BLK; PA6 is unused.

- [ ] **Step 1: Add a failing display timing probe**

Add `#DISPLAYTEST` output containing `sysclk`, `spi_hz`, `dma_frames`, `dma_timeouts`, and worst frame microseconds. Expected before implementation: command absent or `sysclk=8000000 spi_hz=2000000`.

- [ ] **Step 2: Configure the clock tree and SPI1 DMA**

Use HSE + PLL×9 for 72 MHz SYSCLK, APB1÷2, APB2÷1, Flash latency 2, ADC÷6, and SPI1÷4 for 18 MHz. Preserve USART1/USART2 at 9600 baud and the joystick's 5 ms acquisition cadence. Configure DMA1 Channel3 memory-to-peripheral, 8-bit, memory increment, and transfer-complete interrupt. Use two 256-byte line buffers; never allocate a full framebuffer.

- [ ] **Step 3: Convert drawing primitives to bulk transfers**

```c
void ST7735_WritePixels(const uint16_t *pixels, uint32_t count);
void ST7735_FillRect(int x, int y, int w, int h, uint16_t color);
void ST7735_BlitRgb565(int x, int y, int w, int h, const uint16_t *pixels);
```

Set DC once for a pixel run, fill alternating line buffers while DMA transmits, and time out/recover without blocking UART or joystick tasks indefinitely.

- [ ] **Step 4: Build, flash, and measure**

Run: `cmake --preset NodeB --fresh && cmake --build --preset NodeB`

Expected: build passes; `#DISPLAYTEST` reports 72 MHz and 18 MHz; ADC is at or below 12 MHz; both UARTs measure 9600 baud; 1000 alternating dirty-row transfers have zero timeouts; a full-screen color cycle is no slower than 22 ms on the bench.

- [ ] **Step 5: Commit**

```powershell
git add firmware/stm32f103rct6/Core/Inc/st7735_bus.h firmware/stm32f103rct6/Core/Src/st7735_bus_node_b.c firmware/stm32f103rct6/Core/Inc/st7735.h firmware/stm32f103rct6/Core/Src/st7735.c firmware/stm32f103rct6/Core/Src/node_b.c firmware/stm32f103rct6/Core/Src/stm32f1xx_it.c
git commit -m "perf(firmware): drive Node B display with SPI DMA"
```

### Task 4: Industrial renderer and local menu acceptance

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/ui_renderer.h`
- Create: `firmware/stm32f103rct6/Core/Src/ui_renderer.c`
- Modify: `firmware/stm32f103rct6/Core/Src/ui_menu.c`
- Modify: `firmware/stm32f103rct6/Core/Inc/ui_menu.h`
- Modify: `firmware/stm32f103rct6/Core/Inc/hmi_zh_font.h`
- Modify: `firmware/stm32f103rct6/Core/Src/node_b.c`

**Interfaces:**
- Consumes: immutable `UiState` plus `UiSnapshot` view data.
- Produces: `UiRenderer_Init()`, `UiRenderer_RenderFrame(..., uint32_t now_ms)`, and dirty rectangle statistics.

- [ ] **Step 1: Add failing screenshot-state serial checks**

For every page, inject `#UITEST GOTO <page>` and assert the diagnostic layout contains the required title, row count, selected item, time field, MQTT state, and dialog state.

- [ ] **Step 2: Implement the confirmed B/C visual design**

Use the industrial dark palette, vertical highlight bar, fixed status header, safety overview, classified detail pages, critical-action modal, and footer hints. Add only glyphs used by these screens.

- [ ] **Step 3: Implement animations and dirty redraw**

Advance animation at a 16/17 ms cadence. Interpolate the selected row over 140 ms and page offset over 180 ms. Redraw only old/new highlight bounds, moving page strips, changed metric rows, time digits, and command overlays.

- [ ] **Step 4: Verify Milestone 1 on hardware**

Expected: all menu pages navigate by joystick; 60-second neutral test has no drift; selected-row updates remain at 60 Hz; the screen has no full-screen white flash; UART2 continues receiving while animations run.

- [ ] **Step 5: Commit**

```powershell
git add firmware/stm32f103rct6/Core/Inc/ui_renderer.h firmware/stm32f103rct6/Core/Src/ui_renderer.c firmware/stm32f103rct6/Core/Src/ui_menu.c firmware/stm32f103rct6/Core/Inc/ui_menu.h firmware/stm32f103rct6/Core/Inc/hmi_zh_font.h firmware/stm32f103rct6/Core/Src/node_b.c
git commit -m "feat(firmware): add 60 fps industrial joystick menu"
```

---

## Milestone 2 — Time, Snapshot, and Command Closed Loop

### Task 5: Versioned screen protocol helpers

**Files:**
- Create: `firmware/esp8266-01s/include/screen_protocol.h`
- Create: `firmware/esp8266-01s/src/screen_protocol.cpp`
- Create: `firmware/esp8266-01s/test/test_screen_protocol/test_main.cpp`
- Modify: `firmware/esp8266-01s/platformio.ini`

**Interfaces:**
- Produces: builders/parsers for `ut.screen.snapshot.v1`, `ut.menu.command.v1`, `ut.command.ack.v1`, and `ut.time.sync.v1`.

- [ ] **Step 1: Write failing native PlatformIO tests**

Test complete snapshots, missing fields, value bounds, stale timestamps, `cmdId` preservation, target `CTRL-01`, and NTP epoch validity.

- [ ] **Step 2: Run RED**

Run: `pio test -e native -f test_screen_protocol`

Expected: FAIL because protocol helpers do not exist.

- [ ] **Step 3: Implement bounded JSON helpers**

Reject messages above the UART line limit, unknown schema versions, absent identifiers, invalid fan duties, and epochs before 2024-01-01. Do not allocate unbounded queues.

- [ ] **Step 4: Run GREEN and both ESP builds**

Run: `pio test -e native -f test_screen_protocol`, then `pio run -e esp01_ctrl01` and `pio run -e esp01_ctrl02`.

- [ ] **Step 5: Commit**

```powershell
git add firmware/esp8266-01s/include/screen_protocol.h firmware/esp8266-01s/src/screen_protocol.cpp firmware/esp8266-01s/test/test_screen_protocol/test_main.cpp firmware/esp8266-01s/platformio.ini
git commit -m "feat(esp): add versioned screen bridge protocol"
```

### Task 6: ESP-02 subscriptions, NTP, and menu command publishing

**Files:**
- Modify: `firmware/esp8266-01s/src/main.cpp`
- Create: `firmware/esp8266-01s/test/test_screen_routing/test_main.cpp`

**Interfaces:**
- Consumes menu lines from CTRL-02 USART.
- Publishes `ut/v1/CTRL-01/cmd/menu` and subscribes to `ut/v1/CTRL-01/telemetry` plus `ut/v1/CTRL-01/cmd_ack` only in the `CTRL-02` build.
- Sends snapshots and acknowledgements to CTRL-02, and sends NTP time-sync lines to the local STM32 in both CTRL-01 and CTRL-02 builds.
- In the `CTRL-01` build, normalizes `ut.menu.command.v1` from `cmd/menu` into the same bounded `ut.command.v1` UART command accepted from Web/IoTDA while preserving `cmdId`, target, TTL, action, and value.

- [ ] **Step 1: Add failing routing-table tests**

Assert CTRL-01 and CTRL-02 builds receive different subscription sets, that a menu command is never published on CTRL-02 telemetry, and that CTRL-01 normalization preserves the identifier and rejects missing/expired fields.

- [ ] **Step 2: Implement routing and NTP sync**

Configure NTP after Wi-Fi association, emit time to each role's local STM32 immediately after first valid sync and every 10 minutes, convert CTRL-01 telemetry to a bounded screen snapshot, forward matching acknowledgements unchanged, and normalize menu commands only in the CTRL-01 role before writing them to its STM32 UART.

- [ ] **Step 3: Verify native tests and both ESP builds**

Expected: no compiled MQTT host/IP, no secrets in binaries or logs, bounded queues retained, and both firmware images build.

- [ ] **Step 4: Flash ESP-02 and inspect serial/MQTT**

Expected topics: subscriptions for CTRL-01 telemetry/ack and publish to `ut/v1/CTRL-01/cmd/menu`. Expected UART: valid time line and snapshot after MQTT reconnect.

- [ ] **Step 5: Commit**

```powershell
git add firmware/esp8266-01s/src/main.cpp firmware/esp8266-01s/test/test_screen_routing/test_main.cpp
git commit -m "feat(esp): bridge Node B menu and network time"
```

### Task 7: CTRL-01 expanded command execution and truthful telemetry

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/node_a_command.h`
- Create: `firmware/stm32f103rct6/Core/Src/node_a_command.c`
- Modify: `firmware/stm32f103rct6/Core/Src/node_a.c`
- Create: `firmware/stm32f103rct6/tests/node_a_command_serial_probe.py`

**Interfaces:**
- Consumes existing `ut.command.v1` actions from Web/IoTDA plus menu-originated commands normalized by ESP-01.
- Produces actual actuator state in telemetry and `ut.command.ack.v1` with `cmdId`, `status`, `reason`, and applied value.

- [ ] **Step 1: Write failing command/ack hardware cases**

Cover fan1/fan2 30/60/100, both start, all stop, LED color/mode/brightness, buzzer test/mute/restore, invalid values, expired TTL, duplicate `cmdId`, and active-safety rejection.

- [ ] **Step 2: Extract and implement one command dispatcher**

```c
NodeACommandResult NodeACommand_Apply(const NodeACommand *command,
                                      const NodeASafetyState *safety,
                                      NodeAActuatorState *actual);
```

Web, IoTDA, and menu inputs must call this same function. Preserve the current safety priority and make a new alarm invalidate buzzer mute.

- [ ] **Step 3: Extend telemetry with actual state**

Include both fan target/actual RPM, voltage/current, relay state, LED mode/brightness, buzzer state, gas/water/fire values, data quality, and monotonic sequence without removing existing fields.

- [ ] **Step 4: Build, flash CTRL-01, and run probe**

Expected: every accepted action changes hardware and returns matching actual state; every rejected action leaves hardware unchanged and returns an explicit reason.

- [ ] **Step 5: Commit**

```powershell
git add firmware/stm32f103rct6/Core/Inc/node_a_command.h firmware/stm32f103rct6/Core/Src/node_a_command.c firmware/stm32f103rct6/Core/Src/node_a.c firmware/stm32f103rct6/tests/node_a_command_serial_probe.py
git commit -m "feat(firmware): unify Node A command execution and feedback"
```

### Task 8: CTRL-02 real snapshot, time, and command state integration

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/screen_snapshot.h`
- Create: `firmware/stm32f103rct6/Core/Src/screen_snapshot.c`
- Create: `firmware/stm32f103rct6/Core/Inc/network_time.h`
- Create: `firmware/stm32f103rct6/Core/Src/network_time.c`
- Create: `firmware/stm32f103rct6/Core/Inc/menu_command.h`
- Create: `firmware/stm32f103rct6/Core/Src/menu_command.c`
- Modify: `firmware/stm32f103rct6/Core/Src/node_b.c`
- Modify: `firmware/stm32f103rct6/Core/Src/ui_renderer.c`

**Interfaces:**
- Populates the shared `UiSnapshot` declared in `ui_model.h`; produces monotonic `UiClock` and command lifecycle events for `UiState`.

- [ ] **Step 1: Add failing UART injection tests**

Inject valid/invalid/old snapshots, valid/invalid time sync, matching/mismatching/late acknowledgements, and MQTT up/down events. Assert the diagnostic UI model rather than pixels.

- [ ] **Step 2: Implement strict parsers and staleness**

Parse into a temporary structure and publish atomically only after full validation. Mark data stale at 5000 ms. Continue clock holdover after sync and render `--:--` before first sync.

- [ ] **Step 3: Wire confirmed menu actions to commands**

Generate unique `menu-CTRL-02-<boot>-<seq>` identifiers, apply a 10000 ms TTL, send one bounded UART line, start the 5000 ms UI timeout, and accept only a matching acknowledgement.

- [ ] **Step 4: Verify Milestone 2 end to end**

Flash both ESPs and both current STM32 images. Exercise all controls from the screen, verify actual hardware, matching screen acknowledgement, MQTT messages, Django/Frontend state convergence, NTP display, stale-data gray state, and offline control lock.

- [ ] **Step 5: Commit**

```powershell
git add firmware/stm32f103rct6/Core/Inc/screen_snapshot.h firmware/stm32f103rct6/Core/Src/screen_snapshot.c firmware/stm32f103rct6/Core/Inc/network_time.h firmware/stm32f103rct6/Core/Src/network_time.c firmware/stm32f103rct6/Core/Inc/menu_command.h firmware/stm32f103rct6/Core/Src/menu_command.c firmware/stm32f103rct6/Core/Src/node_b.c firmware/stm32f103rct6/Core/Src/ui_renderer.c
git commit -m "feat(firmware): connect menu to live state and commands"
```

---

## Milestone 3 — CTRL-01 Read-Only Secondary Screen

### Task 9: Retune CTRL-01 for 72 MHz without peripheral regressions

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/node_a_clock_contract.h`
- Modify: `firmware/stm32f103rct6/Core/Src/node_a.c`
- Modify: `firmware/stm32f103rct6/Core/Src/stm32f1xx_hal_msp.c`
- Modify: `firmware/stm32f103rct6/tests/node_a_sensor_map_test.c`
- Create: `firmware/stm32f103rct6/tests/node_a_clock_serial_probe.py`

**Interfaces:**
- Produces fixed contracts for 72 MHz SYSCLK, 36 MHz APB1, 72 MHz APB2, ADC ≤12 MHz, 25 kHz fan PWM, 9600-baud UARTs, SHT30 timing, and valid WS2812 waveform.

- [ ] **Step 1: Record failing pre-change clock diagnostics**

Expected current diagnostic: 8 MHz SYSCLK. Add assertions for all target frequencies before changing the clock.

- [ ] **Step 2: Apply the clock tree and retune peripherals**

Use HSE + PLL×9, APB1÷2, APB2÷1, ADC÷6. Recompute timer prescalers/periods for 25 kHz fan PWM, software-I2C delays, and timeouts. Change WS2812 SPI2 encoding to a divisor/pattern combination that remains within the LED timing window at 36 MHz PCLK1.

- [ ] **Step 3: Build and bench-test every existing Node A peripheral**

Verify SHT30, INA226 buses, gas ADC, liquid, smoke, flame, both fan tach/PWM, relay, buzzer, WS2812, USART1, and ESP USART2 before adding the screen.

- [ ] **Step 4: Run a 30-minute regression soak**

Expected: no false alarms, no lost ESP connection, stable fan PWM/RPM, stable sensor cadence, and no WS2812 corruption.

- [ ] **Step 5: Commit**

```powershell
git add firmware/stm32f103rct6/Core/Inc/node_a_clock_contract.h firmware/stm32f103rct6/Core/Src/node_a.c firmware/stm32f103rct6/Core/Src/stm32f1xx_hal_msp.c firmware/stm32f103rct6/tests/node_a_sensor_map_test.c firmware/stm32f103rct6/tests/node_a_clock_serial_probe.py
git commit -m "perf(firmware): retune Node A for 72 mhz"
```

### Task 10: SPI3 DMA secondary display and alarm takeover

**Files:**
- Create: `firmware/stm32f103rct6/Core/Src/st7735_bus_node_a.c`
- Create: `firmware/stm32f103rct6/Core/Inc/node_a_status_screen.h`
- Create: `firmware/stm32f103rct6/Core/Src/node_a_status_screen.c`
- Modify: `firmware/stm32f103rct6/Core/Src/node_a.c`
- Modify: `firmware/stm32f103rct6/Core/Src/stm32f1xx_it.c`
- Modify: `firmware/stm32f103rct6/CMakeLists.txt`

**Interfaces:**
- Consumes Node A's actual local sensor/safety/actuator state directly.
- Consumes `ut.time.sync.v1` from ESP-01 through the shared `network_time` module and shows `--:--` until the first valid sync.
- Produces a read-only 5-second carousel and immediate alarm page.
- Mapping: PB3=SPI3_SCK, PB5=SPI3_MOSI, PC4=RES, PC5=DC, PB8=CS, PB9=BLK.

- [ ] **Step 1: Add failing secondary-screen diagnostics**

Assert page sequence `environment → gas → fans`, 5000 ms dwell, immediate alarm takeover, and return to carousel only after alarm clears.

- [ ] **Step 2: Configure SPI3 and DMA2 Channel2**

Disable JTAG while retaining SWD, configure 18 MHz SPI3 Mode 0, and reuse the transport API from Task 3 through the Node A adapter. Confirm PB6/PB7 SHT30 and PA7 fan2 tach remain untouched.

- [ ] **Step 3: Implement read-only pages**

Render local values from one atomic state snapshot. Do not parse MQTT or accept joystick/control input on Node A.

- [ ] **Step 4: Build, flash, and run final dual-screen soak**

Run NodeA and NodeB builds, flash both boards, then run 30 minutes with live telemetry. Trigger methane, smoke, and flame alarms one at a time. Expected: both screens show the same alarm; Node A screen takeover is immediate; safety actions occur even with MQTT disconnected.

- [ ] **Step 5: Commit**

```powershell
git add firmware/stm32f103rct6/Core/Src/st7735_bus_node_a.c firmware/stm32f103rct6/Core/Inc/node_a_status_screen.h firmware/stm32f103rct6/Core/Src/node_a_status_screen.c firmware/stm32f103rct6/Core/Src/node_a.c firmware/stm32f103rct6/Core/Src/stm32f1xx_it.c firmware/stm32f103rct6/CMakeLists.txt
git commit -m "feat(firmware): add Node A status display"
```

### Task 11: Documentation and release evidence

**Files:**
- Modify: `firmware/stm32f103rct6/README.md`
- Modify: `docs/项目实施日志.md`
- Create: `docs/hardware/双屏与摇杆接线.md`
- Create: `docs/acceptance/双屏菜单实机验收.md`

**Interfaces:**
- Produces the authoritative pin map, build/flash instructions, final SPI divisors, measured frame timing, command topics, and signed-off hardware observations.

- [ ] **Step 1: Replace obsolete display wiring and capability text**

Document both screen pin maps, joystick 3.3 V warning, BOOT/SWD preservation, ESP UARTs, and every retained Node A connection.

- [ ] **Step 2: Record exact verification commands and evidence**

Include NodeA/NodeB CMake output, both PlatformIO builds/tests, gateway tests, serial diagnostic output, final stable SPI frequency, 30-minute soak result, alarm tests, and command acknowledgement samples with secrets removed.

- [ ] **Step 3: Run the complete release gate**

```powershell
cmake --preset NodeA --fresh
cmake --build --preset NodeA
cmake --preset NodeB --fresh
cmake --build --preset NodeB
cd ..\..\esp8266-01s
pio test -e native
pio run -e esp01_ctrl01
pio run -e esp01_ctrl02
cd ..\..\services\iotda-gateway
npm test
```

Expected: every command exits 0. Then perform the documented physical checklist; do not mark unobserved items as passed.

- [ ] **Step 4: Commit**

```powershell
git add firmware/stm32f103rct6/README.md docs/项目实施日志.md docs/hardware/双屏与摇杆接线.md docs/acceptance/双屏菜单实机验收.md
git commit -m "docs: record dual-screen menu integration"
```

## Execution Checkpoints

- Stop after Task 4 for user review of local menu feel before changing ESP/MQTT behavior.
- Stop after Task 8 for user review of real command execution before changing Node A clock/peripheral timing.
- Stop after Task 9 if any existing Node A peripheral regresses; do not connect the second screen until the regression is resolved.
- Final completion requires both automated gates and the physical acceptance checklist; build success alone is insufficient.
