# Dual-Node Multi-Sensor Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect and identify all 32 physical sensors across Node A and Node B without regressing time display, fan control, screen refresh, MQTT reconnect, command acknowledgement, or debug/download access.

**Architecture:** Both STM32 nodes use one shared, table-driven sensor model and separate node-specific acquisition modules. Node A publishes its local readings through ESP-01 to `ut/v1/CTRL-01/telemetry`; Node B publishes its local readings through ESP-02 to `ut/v1/CTRL-02/telemetry` while ESP-02 continues subscribing to Node A and forwarding menu commands. Acquisition is incremental and deadline-bounded so no complete sensor sweep blocks UART, UI, or command processing.

**Tech Stack:** STM32F103RCT6, STM32 HAL C11, software I2C, ADC1 single-channel polling, GPIO digital inputs, ESP8266 Arduino/PlatformIO, PubSubClient, native C/C++ host tests, CMake/arm-none-eabi-gcc.

**Spec:** `docs/superpowers/specs/2026-09-16-dual-node-multi-sensor-expansion-design.md`

## Global Constraints

- Preserve all pin assignments and reservations in the approved spec; do not substitute pins during implementation.
- Do not connect or enable the four-relay board, and do not change the existing fan relay path.
- Every physical sensor has a unique stable asset code: `SHT-01`–`SHT-04`, `FLAME-01`–`FLAME-05`, `MQ4-01`–`MQ4-05`, `MQ2-01`–`MQ2-05`, `O2-01`–`O2-03`, `CO-01`–`CO-05`, and `LEVEL-01`–`LEVEL-05`.
- Every STM32 analog or digital input must remain within 0–3.3 V; MQ heater power comes from a separate 5 V supply with at least 30% current margin and a shared ground.
- Each analog input uses the approved divider, then 1 kΩ series resistance and 100 nF to ground at the ADC pin.
- Uncalibrated analog gas channels publish raw ADC and millivolts with `suspect` quality; they do not publish concentration values and do not drive actuators.
- Disabled or disconnected channels publish `missing` and cannot trigger safety actions.
- PC13 is a high-impedance liquid-level digital input only.
- Each SHT30 pair on one bus must contain one address `0x44` and one address `0x45`; if the modules cannot change address, stop and revise the hardware design to use TCA9548A before wiring.
- Node B menu commands remain on `ut/v1/CTRL-01/cmd/menu`; Node B local telemetry uses `ut/v1/CTRL-02/telemetry`.
- One failed sensor must not block another sensor, UI refresh, network time, UART RX/TX, MQTT reconnection, or menu-command acknowledgement.
- Commit only files belonging to the current task; preserve the existing dirty worktree changes.

---

## File Structure

- Create `Core/Inc/multi_sensor.h` and `Core/Src/multi_sensor.c`: shared sensor identity, quality, reading, debounce, filtering, and enable-state model with no HAL dependency.
- Create `Core/Inc/node_a_sensor_bank.h` and `Core/Src/node_a_sensor_bank.c`: Node A pin tables, two software-I2C buses, four SHT30 instances, seven ADC inputs, and nine digital inputs.
- Create `Core/Inc/node_b_sensor_bank.h` and `Core/Src/node_b_sensor_bank.c`: Node B pin tables, six ADC inputs, and six digital inputs.
- Create `Core/Inc/sensor_telemetry.h` and `Core/Src/sensor_telemetry.c`: bounded `ut.telemetry.v1` frame rotation for arbitrary sensor arrays.
- Modify `Core/Src/node_a.c` and `Core/Src/node_b.c`: schedule the new banks and service communication between every bounded acquisition step.
- Modify `Core/Inc/node_a_telemetry.h` and `Core/Src/node_a_telemetry.c`: preserve fan/actuator frames while delegating expanded sensor readings to `sensor_telemetry`.
- Modify `Core/Inc/screen_snapshot.h`, `Core/Src/screen_snapshot.c`, `Core/Inc/ui_model.h`, `Core/Src/ui_state.c`, and `Core/Src/ui_renderer.c`: store and render per-sensor identities, qualities, and alarm counts.
- Modify `firmware/esp8266-01s/src/main.cpp` and routing tests: allow the CTRL-02 build to publish STM32-originated local telemetry while retaining current subscriptions and menu routing.
- Create focused host tests for each module, then extend ARM build contracts and serial probes.

---

### Task 1: Shared Multi-Sensor Domain Model

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/multi_sensor.h`
- Create: `firmware/stm32f103rct6/Core/Src/multi_sensor.c`
- Create: `firmware/stm32f103rct6/tests/multi_sensor_host_test.c`
- Create: `firmware/stm32f103rct6/tests/run_multi_sensor_host.sh`
- Modify: `firmware/stm32f103rct6/CMakeLists.txt`

**Interfaces:**
- Consumes: fixed-width integer types only; no HAL symbols.
- Produces: `SensorQuality`, `SensorKind`, `SensorReading`, `DigitalDebounce`, `SensorReading_Init`, `SensorReading_SetAnalog`, `SensorReading_SetDigital`, `SensorReading_SetMissing`, and `DigitalDebounce_Update`.

- [ ] **Step 1: Write the failing model tests**

```c
#include "multi_sensor.h"
#include <assert.h>
#include <string.h>

int main(void) {
  SensorReading r;
  SensorReading_Init(&r, "MQ4-03", SENSOR_KIND_MQ4, 1U);
  assert(strcmp(r.asset_code, "MQ4-03") == 0);
  assert(r.quality == SENSOR_QUALITY_MISSING);
  SensorReading_SetAnalog(&r, 2048U, 1650403UL, 100U, SENSOR_QUALITY_SUSPECT);
  assert(r.raw == 2048U && r.microvolts == 1650403UL);
  assert(r.sampled_at_ms == 100U && r.quality == SENSOR_QUALITY_SUSPECT);

  DigitalDebounce d = {0};
  assert(DigitalDebounce_Update(&d, 1U, 3U) == 0U);
  assert(DigitalDebounce_Update(&d, 1U, 3U) == 0U);
  assert(DigitalDebounce_Update(&d, 1U, 3U) == 1U);
  assert(d.stable == 1U);
  return 0;
}
```

- [ ] **Step 2: Run the test and verify the missing header failure**

Run: `cd firmware/stm32f103rct6 && bash tests/run_multi_sensor_host.sh`

Expected: compilation fails with `multi_sensor.h: No such file or directory`.

- [ ] **Step 3: Implement the minimal shared types and pure functions**

```c
typedef enum { SENSOR_QUALITY_GOOD, SENSOR_QUALITY_SUSPECT,
               SENSOR_QUALITY_BAD, SENSOR_QUALITY_MISSING } SensorQuality;
typedef enum { SENSOR_KIND_SHT30, SENSOR_KIND_FLAME, SENSOR_KIND_MQ4,
               SENSOR_KIND_MQ2, SENSOR_KIND_O2, SENSOR_KIND_CO,
               SENSOR_KIND_LEVEL } SensorKind;
typedef struct {
  char asset_code[10];
  SensorKind kind;
  SensorQuality quality;
  uint8_t enabled, online, alarm, digital_value;
  uint16_t raw;
  uint32_t microvolts, sampled_at_ms;
  int16_t temperature_centi_c;
  uint16_t humidity_centi_rh;
} SensorReading;
typedef struct { uint8_t stable, candidate, count; } DigitalDebounce;
```

Copy asset codes with an explicit terminating NUL. `DigitalDebounce_Update` changes `stable` only after `required_count` identical candidates. `SensorReading_SetMissing` clears `online` and sets `SENSOR_QUALITY_MISSING` without fabricating a numeric measurement.

- [ ] **Step 4: Run the shared model test**

Run: `cd firmware/stm32f103rct6 && bash tests/run_multi_sensor_host.sh`

Expected: exit code 0.

- [ ] **Step 5: Link the shared source into both STM32 variants and build**

Add `Core/Src/multi_sensor.c` to the unconditional `target_sources`. Run:

```bash
cmake --preset NodeA
cmake --build --preset NodeA
cmake --preset NodeB
cmake --build --preset NodeB
```

Expected: both ELF and BIN targets build successfully.

- [ ] **Step 6: Commit the domain model**

```bash
git add firmware/stm32f103rct6/Core/Inc/multi_sensor.h firmware/stm32f103rct6/Core/Src/multi_sensor.c firmware/stm32f103rct6/tests/multi_sensor_host_test.c firmware/stm32f103rct6/tests/run_multi_sensor_host.sh firmware/stm32f103rct6/CMakeLists.txt
git commit -m "feat: add shared multi-sensor model"
```

### Task 2: Lock the Approved Pin Map in Compile-Time Tests

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/node_sensor_pin_map.h`
- Create: `firmware/stm32f103rct6/tests/node_sensor_pin_map_test.c`
- Create: `firmware/stm32f103rct6/tests/run_node_sensor_pin_map_host.sh`

**Interfaces:**
- Consumes: STM32 HAL GPIO and ADC channel constants.
- Produces: `NodeAnalogPin`, `NodeDigitalPin`, `NODE_A_ANALOG_PIN_COUNT`, `NODE_A_DIGITAL_PIN_COUNT`, `NODE_B_ANALOG_PIN_COUNT`, and `NODE_B_DIGITAL_PIN_COUNT`.

- [ ] **Step 1: Write compile-time assertions for every approved assignment**

```c
_Static_assert(NODE_A_ANALOG_PIN_COUNT == 7U, "Node A analog count");
_Static_assert(NODE_A_DIGITAL_PIN_COUNT == 9U, "Node A digital count");
_Static_assert(NODE_B_ANALOG_PIN_COUNT == 6U, "Node B analog count");
_Static_assert(NODE_B_DIGITAL_PIN_COUNT == 6U, "Node B digital count");
_Static_assert(NODE_A_CO1_ADC_CHANNEL == ADC_CHANNEL_11, "CO-01 PC1");
_Static_assert(NODE_A_MQ4_1_ADC_CHANNEL == ADC_CHANNEL_12, "MQ4-01 PC2");
_Static_assert(NODE_A_O2_1_ADC_CHANNEL == ADC_CHANNEL_13, "O2-01 PC3");
_Static_assert(NODE_B_O2_3_ADC_CHANNEL == ADC_CHANNEL_6, "O2-03 PA6");
_Static_assert(NODE_A_LEVEL3_PIN == GPIO_PIN_13, "LEVEL-03 PC13 input only");
```

The runtime portion must insert every `(port,pin)` pair into a small array and assert no duplicate exists within a node. It must also compare against explicit reserved arrays containing every display, UART, SWD, joystick, fan, buzzer, LED, WS2812, and I2C pin from the spec.

- [ ] **Step 2: Run and verify failure because the map header does not exist**

Run: `cd firmware/stm32f103rct6 && bash tests/run_node_sensor_pin_map_host.sh`

Expected: compilation fails on missing `node_sensor_pin_map.h`.

- [ ] **Step 3: Implement the exact pin tables**

Define all 13 ADC channel constants and all 15 digital `(GPIO_TypeDef*, uint16_t)` pairs exactly as approved. Define the four SHT30 descriptors as:

```c
{ "SHT-01", GPIOB, GPIO_PIN_6,  GPIOB, GPIO_PIN_7,  0x44U },
{ "SHT-02", GPIOB, GPIO_PIN_6,  GPIOB, GPIO_PIN_7,  0x45U },
{ "SHT-03", GPIOB, GPIO_PIN_10, GPIOB, GPIO_PIN_11, 0x44U },
{ "SHT-04", GPIOB, GPIO_PIN_10, GPIOB, GPIO_PIN_11, 0x45U }
```

- [ ] **Step 4: Run the pin-map test and existing Node A map test**

Run:

```bash
cd firmware/stm32f103rct6
bash tests/run_node_sensor_pin_map_host.sh
bash tests/run_node_a_contract_arm.sh
```

Expected: both pass; the existing PC1/PC2/PC3 mappings remain unchanged.

- [ ] **Step 5: Commit the locked mapping**

```bash
git add firmware/stm32f103rct6/Core/Inc/node_sensor_pin_map.h firmware/stm32f103rct6/tests/node_sensor_pin_map_test.c firmware/stm32f103rct6/tests/run_node_sensor_pin_map_host.sh
git commit -m "test: lock dual-node sensor pin map"
```

### Task 3: Node A Incremental Sensor Bank

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/node_a_sensor_bank.h`
- Create: `firmware/stm32f103rct6/Core/Src/node_a_sensor_bank.c`
- Create: `firmware/stm32f103rct6/tests/node_a_sensor_bank_host_test.c`
- Create: `firmware/stm32f103rct6/tests/run_node_a_sensor_bank_host.sh`
- Modify: `firmware/stm32f103rct6/Core/Src/stm32f1xx_hal_msp.c`
- Modify: `firmware/stm32f103rct6/Core/Src/node_a.c`
- Modify: `firmware/stm32f103rct6/CMakeLists.txt`

**Interfaces:**
- Consumes: `SensorReading`, the approved pin map, `ADC_HandleTypeDef`, `HAL_GetTick`, and a callback used to service UART/UI during bounded I2C delays.
- Produces: `NodeASensorBank_Init`, `NodeASensorBank_Tick`, `NodeASensorBank_Readings`, and `NodeASensorBank_Count`.

- [ ] **Step 1: Write a fake-HAL scheduler test**

```c
NodeASensorBank bank;
NodeASensorBank_Init(&bank, &fake_adc, service_callback, &service_count);
assert(NodeASensorBank_Count(&bank) == 20U); /* 4 SHT + 7 analog + 9 digital */
for (uint32_t now = 0; now < 2000U; ++now) NodeASensorBank_Tick(&bank, now);
assert(service_count > 0U);
assert(max_adc_conversions_per_tick == 1U);
assert(max_sht_transactions_per_tick == 1U);
assert(find_reading(&bank, "SHT-04") != 0);
assert(find_reading(&bank, "LEVEL-03") != 0);
```

Add fault cases: NACK `SHT-02` while `SHT-01` continues updating; saturate `CO-03` at 4095 and expect `bad`; disable `MQ2-03` and expect `missing` with no alarm; bounce `FLAME-02` and require the configured stable sample count.

- [ ] **Step 2: Run and verify failure on the missing bank API**

Run: `cd firmware/stm32f103rct6 && bash tests/run_node_a_sensor_bank_host.sh`

Expected: compilation fails on missing `node_a_sensor_bank.h`.

- [ ] **Step 3: Implement GPIO and ADC initialization**

In the ADC MSP path, configure Node A `PA0|PA4|PA5|PB1|PC1|PC2|PC3` as `GPIO_MODE_ANALOG`. In Node A GPIO initialization, configure `PB12|PB14|PC0|PC8|PC9|PC10|PC11|PC12|PC13` as inputs with pulls selected from measured module polarity; defaults remain disabled until that polarity has been recorded.

- [ ] **Step 4: Implement one-operation-per-tick acquisition**

Use a round-robin cursor. Each call performs at most one ADC channel conversion, one digital sample, or one bounded SHT30 state transition. Preserve the current 64-sample gas filtering across multiple ticks rather than executing 64 blocking conversions in one call. Call `service_callback` inside software-I2C waits and after every ADC poll.

- [ ] **Step 5: Run the bank test and communication budget contracts**

Run:

```bash
cd firmware/stm32f103rct6
bash tests/run_node_a_sensor_bank_host.sh
bash tests/run_node_a_clock_host.sh
python tests/node_a_comm_service_contract_test.py
```

Expected: all pass, including the pre-existing time and UART servicing budgets.

- [ ] **Step 6: Integrate the bank into `node_a.c` without changing actuator behavior**

Initialize once after safe GPIO output states are established. Call `NodeASensorBank_Tick(&sensor_bank, HAL_GetTick())` from the main loop, then copy a completed immutable bank snapshot for display/telemetry. Keep automatic ventilation driven only by the already validated MQ4 channel until later commissioning explicitly enables another source.

- [ ] **Step 7: Build Node A and commit**

```bash
cmake --preset NodeA
cmake --build --preset NodeA
git add firmware/stm32f103rct6/Core/Inc/node_a_sensor_bank.h firmware/stm32f103rct6/Core/Src/node_a_sensor_bank.c firmware/stm32f103rct6/tests/node_a_sensor_bank_host_test.c firmware/stm32f103rct6/tests/run_node_a_sensor_bank_host.sh firmware/stm32f103rct6/Core/Src/stm32f1xx_hal_msp.c firmware/stm32f103rct6/Core/Src/node_a.c firmware/stm32f103rct6/CMakeLists.txt
git commit -m "feat: acquire Node A multi-sensor bank"
```

### Task 4: Generic Bounded Sensor Telemetry

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/sensor_telemetry.h`
- Create: `firmware/stm32f103rct6/Core/Src/sensor_telemetry.c`
- Create: `firmware/stm32f103rct6/tests/sensor_telemetry_host_test.c`
- Create: `firmware/stm32f103rct6/tests/run_sensor_telemetry_host.sh`
- Modify: `firmware/stm32f103rct6/Core/Inc/node_a_telemetry.h`
- Modify: `firmware/stm32f103rct6/Core/Src/node_a_telemetry.c`
- Modify: `firmware/stm32f103rct6/CMakeLists.txt`

**Interfaces:**
- Consumes: immutable `SensorReading[]`, reading count, sequence, and maximum output buffer size.
- Produces: `SensorTelemetryCursor`, `SensorTelemetry_Init`, and `SensorTelemetry_FormatNext(const SensorReading*, uint8_t, SensorTelemetryCursor*, char*, uint16_t, uint16_t*)`.

- [ ] **Step 1: Write formatter tests covering all quality and metric forms**

```c
SensorReading readings[3];
/* SHT-01 good, MQ4-02 suspect raw/voltage, FLAME-03 missing */
SensorTelemetryCursor cursor = { .sequence = 40U, .next_index = 0U };
char frame[768]; uint16_t length = 0U;
assert(SensorTelemetry_FormatNext(readings, 3U, &cursor, frame,
                                  sizeof frame, &length) == 1U);
assert(strstr(frame, "\"assetCode\":\"SHT-01\"") != 0);
assert(strstr(frame, "\"quality\":\"good\"") != 0);
assert(length < sizeof frame);
```

Also assert: raw gas readings use `adc` and `mV`; SHT uses `degC` and `%RH`; missing values do not reuse the prior numeric value; a too-small buffer returns 0 without advancing sequence or cursor.

- [ ] **Step 2: Run and verify failure on missing formatter**

Run: `cd firmware/stm32f103rct6 && bash tests/run_sensor_telemetry_host.sh`

Expected: compilation fails on missing `sensor_telemetry.h`.

- [ ] **Step 3: Implement bounded frame rotation**

Emit only complete JSON lines ending in `\r\n`. Pack consecutive readings until adding the next reading would exceed 767 bytes, then leave that reading for the next frame. Advance the sequence only after a complete frame is formatted. Use explicit decimal formatting supported by newlib-nano; do not use `%llu`.

- [ ] **Step 4: Adapt Node A telemetry without removing fan and actuator frames**

Replace the old single-instance environment/gas fields with an immutable `const SensorReading *sensors` plus `uint8_t sensor_count` in the formatting path. Retain existing fan/actuator wire frames and queue semantics. Update host vectors to expect unique sensor asset codes.

- [ ] **Step 5: Run telemetry regression tests**

Run:

```bash
cd firmware/stm32f103rct6
bash tests/run_sensor_telemetry_host.sh
bash tests/run_node_a_telemetry_host.sh
bash tests/run_node_a_telemetry_throughput_host.sh
```

Expected: all pass; every frame is below both the 768-byte UART line limit and the 1024-byte ESP serial limit.

- [ ] **Step 6: Commit telemetry expansion**

```bash
git add firmware/stm32f103rct6/Core/Inc/sensor_telemetry.h firmware/stm32f103rct6/Core/Src/sensor_telemetry.c firmware/stm32f103rct6/tests/sensor_telemetry_host_test.c firmware/stm32f103rct6/tests/run_sensor_telemetry_host.sh firmware/stm32f103rct6/Core/Inc/node_a_telemetry.h firmware/stm32f103rct6/Core/Src/node_a_telemetry.c firmware/stm32f103rct6/tests firmware/stm32f103rct6/CMakeLists.txt
git commit -m "feat: publish per-sensor Node A telemetry"
```

### Task 5: Node B Local Sensor Bank and UART Telemetry

**Files:**
- Create: `firmware/stm32f103rct6/Core/Inc/node_b_sensor_bank.h`
- Create: `firmware/stm32f103rct6/Core/Src/node_b_sensor_bank.c`
- Create: `firmware/stm32f103rct6/tests/node_b_sensor_bank_host_test.c`
- Create: `firmware/stm32f103rct6/tests/run_node_b_sensor_bank_host.sh`
- Modify: `firmware/stm32f103rct6/Core/Src/stm32f1xx_hal_msp.c`
- Modify: `firmware/stm32f103rct6/Core/Src/node_b.c`
- Modify: `firmware/stm32f103rct6/CMakeLists.txt`

**Interfaces:**
- Consumes: shared reading model, approved Node B pin table, ADC1, UART TX queue, and generic telemetry formatter.
- Produces: `NodeBSensorBank_Init`, `NodeBSensorBank_Tick`, `NodeBSensorBank_Readings`, `NodeBSensorBank_Count`; Node B UART emits local `ut.telemetry.v1` JSON lines.

- [ ] **Step 1: Write Node B bank and scheduling tests**

Create 12 expected readings: `MQ4-03`–`MQ4-05`, `O2-03`, `CO-04`–`CO-05`, `FLAME-04`–`FLAME-05`, `MQ2-04`–`MQ2-05`, and `LEVEL-04`–`LEVEL-05`. Assert one ADC conversion or digital sample per tick, no access to joystick PC0/PC1 or PC4, and no use of screen pins PA5/PA7/PB6–PB9.

- [ ] **Step 2: Run and verify the missing module failure**

Run: `cd firmware/stm32f103rct6 && bash tests/run_node_b_sensor_bank_host.sh`

Expected: compilation fails on missing `node_b_sensor_bank.h`.

- [ ] **Step 3: Implement Node B GPIO and ADC setup**

Configure `PA0|PA1|PA4|PA6|PB0|PB1` as analog and `PC6|PC7|PC8|PC9|PC10|PC11` as inputs. Do not initialize PA6 as SPI1_MISO; the display remains transmit-only on PA5/PA7.

- [ ] **Step 4: Implement incremental acquisition and immutable snapshots**

Use the same filtering, debounce, disabled-state, saturation, and quality rules as Node A. Each tick performs one bounded operation and returns immediately. Never call a blocking full-bank scan from the UI loop.

- [ ] **Step 5: Queue one local telemetry frame at a time**

Add a local `SensorTelemetryCursor`. At the existing telemetry interval, format one frame and offer it to the nonblocking UART TX queue. Advance only when the entire line is accepted; otherwise retry the same sequence and cursor.

- [ ] **Step 6: Run Node B regressions and build**

Run:

```bash
cd firmware/stm32f103rct6
bash tests/run_node_b_sensor_bank_host.sh
python tests/node_b_uart_contract_test.py
cmake --preset NodeB
cmake --build --preset NodeB
```

Expected: all pass; existing menu command and time-sync paths remain serviced.

- [ ] **Step 7: Commit Node B acquisition**

```bash
git add firmware/stm32f103rct6/Core/Inc/node_b_sensor_bank.h firmware/stm32f103rct6/Core/Src/node_b_sensor_bank.c firmware/stm32f103rct6/tests/node_b_sensor_bank_host_test.c firmware/stm32f103rct6/tests/run_node_b_sensor_bank_host.sh firmware/stm32f103rct6/Core/Src/stm32f1xx_hal_msp.c firmware/stm32f103rct6/Core/Src/node_b.c firmware/stm32f103rct6/CMakeLists.txt
git commit -m "feat: acquire and queue Node B sensor telemetry"
```

### Task 6: ESP-02 Publishes Node B Local Telemetry

**Files:**
- Modify: `firmware/esp8266-01s/src/main.cpp`
- Modify: `firmware/esp8266-01s/include/screen_routing.h`
- Modify: `firmware/esp8266-01s/src/screen_routing.cpp`
- Modify: `firmware/esp8266-01s/test/test_screen_routing/test_main.cpp`

**Interfaces:**
- Consumes: Node B UART JSON lines using schema `ut.telemetry.v1`.
- Produces: MQTT publications to `ut/v1/CTRL-02/telemetry`; preserves CTRL-02 subscriptions to Node A telemetry and command acknowledgements and publication of menu commands to `ut/v1/CTRL-01/cmd/menu`.

- [ ] **Step 1: Add a failing CTRL-02 routing test**

```cpp
RouteOutput output{};
const char local[] =
  "{\"schema\":\"ut.telemetry.v1\",\"seq\":1,\"readings\":["
  "{\"assetCode\":\"MQ4-03\",\"metric\":\"raw\",\"value\":321,"
  "\"unit\":\"adc\",\"quality\":\"suspect\"}]}";
CHECK_EQ(RouteResult::Publish,
         RouteSerialLine(Role::Ctrl02, local, strlen(local), &output));
CHECK_TRUE(strcmp(output.topic, "ut/v1/CTRL-02/telemetry") == 0);
```

Also assert that CTRL-02 still rejects command-ack payloads as local telemetry and still routes menu commands to CTRL-01.

- [ ] **Step 2: Run and confirm the routing test fails**

Run: `cd firmware/esp8266-01s && pio test -e native`

Expected: the new assertion fails because CTRL-02 does not currently publish local telemetry.

- [ ] **Step 3: Implement role-aware local telemetry routing**

Create the telemetry topic for both roles from `BUILD_DEVICE_ID`. For a CTRL-02 serial JSON line with `ut.telemetry.v1`, queue `PendingKind::Telemetry` to `ut/v1/CTRL-02/telemetry`. Keep MQTT callback routing separate so a subscribed CTRL-01 telemetry frame is forwarded to Node B's STM32 and is never re-published as CTRL-02 telemetry.

- [ ] **Step 4: Run native tests and build both ESP images**

Run:

```bash
cd firmware/esp8266-01s
pio test -e native
pio run -e esp01_ctrl01
pio run -e esp01_ctrl02
```

Expected: all tests pass and both firmware binaries build.

- [ ] **Step 5: Commit ESP-02 publishing**

```bash
git add firmware/esp8266-01s/src/main.cpp firmware/esp8266-01s/include/screen_routing.h firmware/esp8266-01s/src/screen_routing.cpp firmware/esp8266-01s/test/test_screen_routing/test_main.cpp
git commit -m "feat: publish CTRL-02 local telemetry"
```

### Task 7: Per-Sensor Dual-Node Screen Model and Rendering

**Files:**
- Modify: `firmware/stm32f103rct6/Core/Inc/screen_snapshot.h`
- Modify: `firmware/stm32f103rct6/Core/Src/screen_snapshot.c`
- Modify: `firmware/stm32f103rct6/Core/Inc/ui_model.h`
- Modify: `firmware/stm32f103rct6/Core/Src/ui_state.c`
- Modify: `firmware/stm32f103rct6/Core/Src/ui_renderer.c`
- Modify: `firmware/stm32f103rct6/Core/Inc/node_a_status_screen.h`
- Modify: `firmware/stm32f103rct6/Core/Src/node_a_status_screen.c`
- Modify: relevant tests under `firmware/stm32f103rct6/tests/`
- Modify: `firmware/esp8266-01s/include/screen_protocol.h`
- Modify: `firmware/esp8266-01s/src/screen_protocol.cpp`
- Modify: `firmware/esp8266-01s/src/screen_routing.cpp`
- Modify: ESP native protocol/routing tests.

**Interfaces:**
- Consumes: per-sensor telemetry from CTRL-01 and CTRL-02.
- Produces: a bounded screen snapshot with sensor identifier, kind, value, quality, alarm, source node, and sample time; summary counts and detail-page selection.

- [ ] **Step 1: Add failing snapshot/protocol tests**

Build a snapshot containing `FLAME-04` alarm from CTRL-02, `MQ4-01` good from CTRL-01, and `SHT-03` missing. Assert round-trip preservation of identifiers and source nodes, summary alarm count 1, worst quality `missing`, and alarm label `FLAME-04`.

- [ ] **Step 2: Run both protocol and UI tests to see the expected failures**

Run:

```bash
cd firmware/esp8266-01s && pio test -e native
cd ../stm32f103rct6 && bash tests/run_task8_host.sh && bash tests/run_ui_renderer_host.sh && bash tests/run_node_a_status_host.sh
```

Expected: new per-sensor assertions fail because the existing snapshot only stores category aggregates.

- [ ] **Step 3: Extend the bounded snapshot contract**

Define `SCREEN_SENSOR_CAPACITY 32U` and a compact `ScreenSensorReading` containing fixed asset code, kind, signed value, scale, quality, alarm, source, and `updated_at_ms`. Reject duplicate asset codes in one payload and replace readings by asset code when merging rotations. Expire an individual reading to `missing` after the existing freshness window instead of expiring unrelated readings.

- [ ] **Step 4: Implement summary and detail navigation**

Home pages show, per kind, the worst severity and abnormal count. Detail pages iterate stable asset-code order. Render missing as `OFF` or `--`. The alarm overlay uses the exact asset code (`FLAME-04`), not only the type name.

- [ ] **Step 5: Preserve time and command responsiveness in renderer tests**

Extend tests so an incoming snapshot update changes only dirty sensor rows, while the clock region continues updating and menu command state remains visible. Keep rendering incremental; do not redraw the entire display for each sensor sample.

- [ ] **Step 6: Run all screen regressions**

Run:

```bash
cd firmware/esp8266-01s && pio test -e native
cd ../stm32f103rct6
bash tests/run_task8_host.sh
bash tests/run_ui_renderer_host.sh
bash tests/run_node_a_status_host.sh
python tests/node_a_display_contract_test.py
```

Expected: all pass.

- [ ] **Step 7: Commit screen support**

```bash
git add firmware/esp8266-01s/include/screen_protocol.h firmware/esp8266-01s/src/screen_protocol.cpp firmware/esp8266-01s/src/screen_routing.cpp firmware/esp8266-01s/test firmware/stm32f103rct6/Core/Inc/screen_snapshot.h firmware/stm32f103rct6/Core/Src/screen_snapshot.c firmware/stm32f103rct6/Core/Inc/ui_model.h firmware/stm32f103rct6/Core/Src/ui_state.c firmware/stm32f103rct6/Core/Src/ui_renderer.c firmware/stm32f103rct6/Core/Inc/node_a_status_screen.h firmware/stm32f103rct6/Core/Src/node_a_status_screen.c firmware/stm32f103rct6/tests
git commit -m "feat: show identified sensors from both nodes"
```

### Task 8: Safety Gating and Fault Isolation

**Files:**
- Modify: `firmware/stm32f103rct6/Core/Inc/node_a_sensor_map.h`
- Modify: `firmware/stm32f103rct6/Core/Src/node_a.c`
- Modify: `firmware/stm32f103rct6/Core/Src/node_a_sensor_bank.c`
- Modify: `firmware/stm32f103rct6/Core/Src/node_b_sensor_bank.c`
- Create: `firmware/stm32f103rct6/tests/multi_sensor_safety_host_test.c`
- Create: `firmware/stm32f103rct6/tests/run_multi_sensor_safety_host.sh`

**Interfaces:**
- Consumes: enabled state, calibration state, quality, alarm, and source asset code from every reading.
- Produces: `SensorSafety_Evaluate` result containing `alarm_active`, `source_count`, and ordered source asset codes; only explicitly commissioned channels participate.

- [ ] **Step 1: Write safety tests before changing actuator logic**

```c
/* MQ4-01 commissioned alarm -> ventilation; CO-02 suspect -> telemetry only;
   disabled FLAME-03 active level -> ignored; FLAME-04 good/alarm -> audible alarm. */
SensorSafetyResult result = SensorSafety_Evaluate(readings, count);
assert(result.ventilation_required == 1U);
assert(result.audible_required == 1U);
assert(has_source(&result, "MQ4-01"));
assert(has_source(&result, "FLAME-04"));
assert(!has_source(&result, "CO-02"));
assert(!has_source(&result, "FLAME-03"));
```

Add startup tests proving floating/unconfigured inputs do not activate relay, fan, or buzzer before stable sampling completes.

- [ ] **Step 2: Run and verify failure on missing safety evaluator**

Run: `cd firmware/stm32f103rct6 && bash tests/run_multi_sensor_safety_host.sh`

Expected: compile failure on undefined `SensorSafety_Evaluate`.

- [ ] **Step 3: Implement explicit per-channel commissioning flags**

Default all newly added channels to disabled. Keep the previously validated methane/MQ4 input commissioned. Require `enabled && online && quality == GOOD && commissioned_for_alarm` before a digital channel can trigger an action; analog channels additionally require `calibrated`.

- [ ] **Step 4: Integrate the evaluator while preserving manual fan control**

Automatic ventilation ORs only qualified gas/flame policy outputs with the existing cooldown policy. Manual fan commands and their acknowledgements continue to use the current command state machine and must not be overwritten by an unqualified sensor.

- [ ] **Step 5: Run safety, command, and timing tests**

Run:

```bash
cd firmware/stm32f103rct6
bash tests/run_multi_sensor_safety_host.sh
bash tests/run_node_a_command_host.sh
bash tests/run_node_a_clock_host.sh
```

Expected: all pass.

- [ ] **Step 6: Commit safety gating**

```bash
git add firmware/stm32f103rct6/Core/Inc/node_a_sensor_map.h firmware/stm32f103rct6/Core/Src/node_a.c firmware/stm32f103rct6/Core/Src/node_a_sensor_bank.c firmware/stm32f103rct6/Core/Src/node_b_sensor_bank.c firmware/stm32f103rct6/tests/multi_sensor_safety_host_test.c firmware/stm32f103rct6/tests/run_multi_sensor_safety_host.sh
git commit -m "feat: gate multi-sensor safety actions"
```

### Task 9: Full Build, Wiring Checklist, and Bench Commissioning

**Files:**
- Create: `docs/hardware/dual-node-sensor-wiring-checklist.md`
- Create: `docs/hardware/dual-node-sensor-commissioning-log.md`
- Modify: `firmware/stm32f103rct6/README.md`
- Modify: `firmware/esp8266-01s/README.md` if present; otherwise document ESP commands in the hardware checklist.

**Interfaces:**
- Consumes: completed firmware and the approved design spec.
- Produces: reproducible binaries, pin-by-pin wiring checklist, measured voltage/polarity record, and pass/fail evidence for all 32 sensors.

- [ ] **Step 1: Write the exact pre-power checklist**

The checklist must contain one row per sensor with node, asset code, MCU pin(s), module pin, supply voltage, expected maximum AO/DO voltage, divider resistor values, enabled flag, active polarity/address, and an empty measured-value field. Include separate checks for common ground, MQ heater supply current margin, PC8–PC13 physical header availability, and SWD/USART bootloader accessibility.

- [ ] **Step 2: Run every host and native test**

Run:

```bash
cd firmware/stm32f103rct6
bash tests/run_multi_sensor_host.sh
bash tests/run_node_sensor_pin_map_host.sh
bash tests/run_node_a_sensor_bank_host.sh
bash tests/run_node_b_sensor_bank_host.sh
bash tests/run_sensor_telemetry_host.sh
bash tests/run_multi_sensor_safety_host.sh
bash tests/run_node_a_command_host.sh
bash tests/run_node_a_telemetry_host.sh
bash tests/run_node_a_telemetry_throughput_host.sh
bash tests/run_node_a_status_host.sh
bash tests/run_task8_host.sh
bash tests/run_uart_tx_queue_host.sh
bash tests/run_ui_renderer_host.sh
python tests/node_a_clock_host_test.py
python tests/node_a_display_contract_test.py
python tests/node_b_uart_contract_test.py
cd ../../esp8266-01s && pio test -e native
```

Expected: every command exits 0.

- [ ] **Step 3: Build all four deployable images**

Run:

```bash
cd firmware/stm32f103rct6
cmake --preset NodeA && cmake --build --preset NodeA
cmake --preset NodeB && cmake --build --preset NodeB
cd ../esp8266-01s
pio run -e esp01_ctrl01
pio run -e esp01_ctrl02
```

Expected: Node A and Node B `.bin` files plus both ESP `.bin` files are generated without warnings indicating overflow.

- [ ] **Step 4: Commission hardware one channel at a time**

With STM32 inputs disconnected, power each module and record its supply, AO maximum, DO high level, DO active polarity, and SHT30 address. Add the divider/level shifter before any output above 3.3 V touches an STM32. Connect and enable in this order: four SHT30s; Node A analog; Node B analog; Node A digital; Node B digital. After each connection, verify only that asset code changes and unplugging it changes only that asset to `missing`.

- [ ] **Step 5: Flash in a controlled order and capture serial/MQTT evidence**

Flash ESP-01 (`esp01_ctrl01`), ESP-02 (`esp01_ctrl02`), Node A, then Node B using the already established USB-ISP process and the confirmed COM ports at execution time. Do not assume COM numbers remain stable. Capture boot logs, `ut/v1/CTRL-01/telemetry`, `ut/v1/CTRL-02/telemetry`, command acknowledgements, and one disconnect/reconnect cycle for each node.

- [ ] **Step 6: Run system acceptance checks**

Verify all 32 unique asset codes, individual disconnect detection, SHT address stability, analog 0–3.3 V limits, Node B menu command acknowledgement inside the existing timeout, Beijing time on both screens, fan start/stop/duty control, screen refresh, MQTT reconnect, and exact alarm source rendering. Leave uncalibrated analog channels as `suspect` and disabled for automatic action.

- [ ] **Step 7: Record evidence and commit documentation**

```bash
git add docs/hardware/dual-node-sensor-wiring-checklist.md docs/hardware/dual-node-sensor-commissioning-log.md firmware/stm32f103rct6/README.md firmware/esp8266-01s/README.md
git commit -m "docs: record multi-sensor commissioning"
```

If `firmware/esp8266-01s/README.md` does not exist, omit it from `git add`; do not create a second document duplicating the hardware checklist.

---

## Completion Gate

Do not mark the expansion complete until all of the following evidence exists:

- The pin-map test proves no duplicate or reserved pin is used.
- All 32 asset codes appear on the correct node topic.
- Every newly connected input has a recorded measured voltage or digital high level below or equal to 3.3 V.
- Disconnecting any one sensor affects only that asset and changes it to `missing` within the documented freshness window.
- Both screens continue showing Beijing time and refresh while all sensor banks run.
- Start, stop, and duty commands for both fans still receive acknowledgements and change physical fan behavior.
- MQTT reconnect is demonstrated for CTRL-01 and CTRL-02.
- Alarm overlays identify the exact asset code.
- No uncalibrated analog channel drives an actuator or reports a fabricated concentration.
