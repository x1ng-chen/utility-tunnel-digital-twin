# Circuit review — dual-node bench sensor wiring

- Project: utility-tunnel-digital-twin, Node A/B STM32F103RCT6 bench wiring
- Revision: 2026-09-24 planning review; no native schematic or PCB changed
- Status: `USER_REVIEW` — physical sensor module variants, connector labels, rail capacity and signal maxima are not yet proven
- Electrical source of truth: current firmware pin ownership plus 2026-09-24 fan bench evidence; the new `docs/hardware/2026-09-24-双节点最新接线与传感器引脚规划.md` is the wiring plan, not an as-built netlist
- Reviewed evidence: `Core/Inc/node_sensor_pin_map.h`, `Core/Src/node_a.c`, `Core/Src/node_a_sensor_bank.c`, `Core/Src/node_b.c`, `Core/Src/node_b_sensor_bank.c`, `docs/hardware/双屏与摇杆接线.md`, `docs/hardware/dual-node-sensor-wiring-checklist.md`, `docs/acceptance/2026-09-24-双风机继电器台架记录.md`, Sensirion SHT3x-DIS datasheet (December 2022)

## Operating principle

Node A reads two software-I²C buses and local analog/digital sensors, controls two 12 V fans, and reports via ESP-01S. Node B owns menu/screen/joystick and a separate planned sensor bank. Existing fan wiring must not be reassigned to sensors.

## Functional blocks and component roles

| Block | Role | Evidence limit |
|---|---|---|
| SHT30 ×4 | RH/T, two devices per bus at 0x44/0x45 | AD/AL user-reported; board-level AD solder ties unverified; SHT-04 not yet sampled in Node A loop |
| INA226 ×2 | Fan voltage/current, one at 0x40 on each bus | R010 user-confirmed, but current accuracy and FAN1 identity fault unresolved |
| CO/O2/MQ4 analog bank | ADC telemetry | Exact board type, supply, AO range and calibration unresolved |
| MQ2/flame/level digital bank | Alarm/level inputs | Exact output levels/polarities require physical tests; some Node A alarm channels already enabled |
| Fans/relay/PWM/TACH | Existing actuators and feedback | Short functional test only; preserve PA1/PA15, PB8/PB9, PA6/PA7 |

## Power tree and budget

3.3 V domain: STM32, ESP (separately capable supply), SHT30, INA226, LCD and I²C pull-ups. External 5 V domain: candidate MQ heaters and some digital modules; 5 V aggregate capacity and startup current are `[TBD-MEASURE]`. Fan power is 12 V behind separate relays. All grounds share a tested reference; sensor power must not back-feed unpowered MCU through SDA/SCL/AO/DO.

## Voltage domains and interfaces

| Interface | Requirement | Status |
|---|---|---|
| Software I²C PB6/PB7, PB10/PB11 | 3.3 V pull-up; addresses 0x40, 0x44, 0x45 per bus; no duplicate | Planned; bus idle/high, pull-up parallel loading and physical address straps `[TBD-MEASURE]` |
| ADC analog inputs | 0–3.3 V at MCU input during all states | Not measured for unconnected modules; series 1 kΩ alone is not overvoltage protection |
| 5 V digital DO | Logic-low and logic-high must meet 3.3 V input limits/threshold after translation | Not measured for unconnected modules |
| SHT30 AD / AL | AD tied low or high; AL floating if unused | Datasheet-supported; breakout implementation unverified |

## Operating states, reset, and ownership

At reset, PA1/PA15 external pulldowns keep fan relays off. Node A owns both SHT/INA buses; Node B owns screen/joystick and its sensor GPIO. During partial power, signal lines must not power an unpowered board. SHT-04 lacks a current read path; Node B sensor-bank entries initialize disabled. SWD and boot/UART pins remain reserved.

## Timing and signal integrity

`[SPEC]` Node A software-I²C transfers have firmware deadlines; clock stretching is unsupported by this implementation. `[TARGET]` Keep two I²C bus harnesses separate, short and with common returns. `[TBD-MEASURE]` Bus idle levels, rise time with all module pull-ups in parallel, and update behavior with INA226 fault present. Analog harnesses require measured filtering/source impedance before calibration.

## Protection, thermal, and mechanics

`[TBD-MEASURE]` MQ heater rail load/thermal behavior and supply margin; STM32 input conditioning under 5 V module outputs; PC8–PC13 header availability; strain relief for temporary bench jumpers. Do not use real flame/combustible gas as an initial input stimulus.

## Layout handoff constraints

`[SPEC]` Preserve Node A PA1/PA15 relay, PB8/PB9 PWM, PA6/PA7 TACH, PB6/PB7 and PB10/PB11 I²C; preserve Node B LCD, joystick, UART and SWD assignments. `[TARGET]` Route I²C with nearby GND return and avoid fan switching leads. `[TBD-MEASURE]` Actual cable length, rise time and rail decoupling on the physical breakout modules.

## Findings

| ID | Severity | Evidence | Consequence | Action | Gate | Status |
|---|---|---|---|---|---|---|
| C-01 | Major | Node A loop reads SHT-01..03, no SHT-04 call | Fourth physically wired sensor will not report | Add read path and enable/telemetry test before claiming complete | Firmware | Open |
| C-02 | Major | Node B bank init sets all sensors disabled | Connecting Node B channels alone yields no readings | Enable each after hardware voltage check and test | Firmware | Open |
| C-03 | Major | Exact CO/O2/MQ4 modules and AO maxima unavailable | Potential STM32 ADC overvoltage or false units | Measure module supply/AO; design division/buffer from measured max; calibrate separately | Power/analog | Open |
| C-04 | Major | User reports SHT30 AD/AL pins; breakout straps uninspected | AD may already tie low, creating conflict if directly tied high | Power-off continuity check before AD→3.3 V on 02/04 | I²C power-up | Open |
| C-05 | Information | Older display doc lists one relay and both INA on bus 2 | Misleading wiring instruction | Added legacy notices and new consolidated table | Documentation | Addressed |

## Approved design decisions and waivers

None. This review does not approve quantitative gas alarms or PCB fabrication.

## Verification and unresolved evidence

Pin ownership compared against current firmware definitions and bench record; no native schematic/netlist or KiCad ERC was run because this request only changes bench wiring documentation. No physical continuity, voltage, I²C scan, load-current or long-duration verification was performed in this documentation turn.
