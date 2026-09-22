# Dual-Node 32-Sensor Carrier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a manufacturable KiCad 10 carrier-board project for two STM32F103RCT6 development boards, two ESP-01S modules, all 32 confirmed sensors, displays, joystick, fans and actuators, together with verified fabrication and assembly outputs.

**Architecture:** One PCB carries two independent logic nodes. A protected 12 V input feeds separate 5 V / 3 A logic and 5 V / 5 A MQ-heater converters; each ESP has its own 3.3 V regulator. Thirteen analog and fifteen digital sensor signals connect directly to the two STM32 boards, while four SHT30 modules use two Node A I2C buses.

**Tech Stack:** KiCad 10.0.5 (`D:\KiCad\bin\kicad-cli.exe`), KiCad schematic/PCB/jobset formats, PowerShell, Python standard library, CSV, Markdown, Git.

**Spec:** `docs/superpowers/specs/2026-09-22-dual-node-32-sensor-carrier-design.md`

## Global Constraints

- Sensor population is fixed at 32: SHT30 ×4, FS-IR02 ×5, MQ-2 ×5, MQ-4 ×5, MQ-7 ×5, oxygen modules ×3 and flame modules ×5.
- Both existing STM32F103RCT6 development boards and both ESP-01S modules remain removable.
- Keep the current Node A / Node B firmware pin mapping, dual MQTT identity, SWD, USART1, BOOT and reset access.
- Use 12 V input, independent `5V_LOGIC / 3 A` and `5V_MQ / 5 A` converters, and independent ESP 3.3 V regulators rated at least 600 mA each.
- The two fans are each 12 V / 0.2 A and require independent branch protection.
- Do not connect the 24 V pump; expose only a clearly labelled low-voltage expansion control interface.
- DHT11, vibration, K210 and voice modules receive no dedicated connector.
- Treat 160 mm × 100 mm as an exploration envelope only; final board dimensions require measured enclosure and development-board geometry.
- Never guess module output voltage, heater current, shunt value, connector pin order, mounting dimensions or safety-critical fuse values.
- Do not release Gerbers until all evidence gates in the spec are satisfied.

## Review Focus

- A 5 V sensor output or accidental 5 V application must not expose an STM32 ADC/GPIO above its safe range; Task 5 includes worst-case divider and fault-current checks.
- Fifteen simultaneous MQ heaters plus Wi-Fi transmission and fan startup must not reset either controller; Tasks 3 and 11 include budget and staged-load tests.
- Duplicate SHT30 addresses or excessive parallel pull-ups must be detected before assembly; Tasks 2 and 5 include address and pull-up checks.
- USB connection to either development board must not back-feed the carrier 5 V rail; Tasks 2 and 4 require a measured power-direction decision and schematic isolation.
- Reversed or mismatched board connectors must be discoverable before power-up; Tasks 6 and 11 include pin-1, voltage-domain and continuity inspections.

---

## File Map

- `hardware/carrier32/carrier32.kicad_pro` — KiCad project settings.
- `hardware/carrier32/carrier32.kicad_sch` — hierarchical top-level schematic.
- `hardware/carrier32/carrier32.kicad_pcb` — PCB source.
- `hardware/carrier32/carrier32.kicad_jobset` — reproducible ERC, DRC, plotting and fabrication jobs.
- `hardware/carrier32/sheets/*.kicad_sch` — power, Node A, Node B, sensors and actuator sheets.
- `hardware/carrier32/lib/carrier32.kicad_sym` — project-only symbols for the two development boards and confirmed modules.
- `hardware/carrier32/lib/carrier32.pretty/*.kicad_mod` — measured project-only footprints.
- `hardware/carrier32/config/design-inputs.csv` — measured electrical and mechanical release evidence.
- `hardware/carrier32/config/net-contract.csv` — authoritative connector-to-node pin contract.
- `hardware/carrier32/scripts/check_design_inputs.py` — blocks fabrication when required evidence is absent.
- `hardware/carrier32/scripts/check_net_contract.py` — compares exported netlist against the pin contract.
- `hardware/carrier32/scripts/check_fabrication_bundle.py` — validates Gerber, drill, BOM and CPL completeness.
- `hardware/carrier32/output/review/` — schematic PDF and PCB review plots.
- `hardware/carrier32/output/fabrication/` — release Gerbers, drill and job file.
- `hardware/carrier32/output/assembly/` — BOM and CPL.
- `hardware/carrier32/ASSEMBLY.md` — connector, jumper and staged power-up instructions.

### Task 1: Establish the KiCad Project and Reproducible Checks

**Files:**
- Create: `hardware/carrier32/carrier32.kicad_pro`
- Create: `hardware/carrier32/carrier32.kicad_jobset`
- Create: `hardware/carrier32/README.md`
- Create: `hardware/carrier32/scripts/run_checks.ps1`
- Modify: `hardware/README.md`

**Interfaces:**
- Consumes: KiCad CLI at `D:\KiCad\bin\kicad-cli.exe`.
- Produces: one command that runs project validation and writes logs under `hardware/carrier32/output/review/`.

- [ ] **Step 1: Verify the toolchain**

Run:

```powershell
& 'D:\KiCad\bin\kicad-cli.exe' version
python --version
```

Expected: KiCad reports `10.0.5`; Python reports an available Python 3 interpreter.

- [ ] **Step 2: Install the KiCad workflow skills**

Use the `skill-installer` workflow to install `Keitark/pcba-design-skills`, `mash/kicad-skills`, and `aklofas/kicad-happy`. Report each installed skill and restart/reload requirement before using it. If a repository does not contain a valid Codex skill, record that result in `hardware/carrier32/README.md` and continue with KiCad 10 CLI plus manual review.

- [ ] **Step 3: Create the KiCad project and jobset**

Create an empty KiCad 10 project named `carrier32`, with project-local symbol and footprint library tables. Configure the jobset to run schematic ERC, PCB DRC, schematic PDF export, PCB Gerber export, drill export and position-file export.

- [ ] **Step 4: Add the check runner**

`run_checks.ps1` must resolve its own directory, call the fixed KiCad CLI path, run the three Python validators created later, and stop on the first non-zero exit code. It must never delete prior evidence outside `hardware/carrier32/output/`.

- [ ] **Step 5: Verify the empty project opens and the jobset parses**

Run:

```powershell
& 'D:\KiCad\bin\kicad-cli.exe' jobset run --file 'hardware\carrier32\carrier32.kicad_jobset' 'hardware\carrier32\carrier32.kicad_pro'
```

Expected: project and jobset parse successfully; schematic/PCB-dependent jobs may report that their source files do not exist yet.

- [ ] **Step 6: Commit**

```powershell
git add hardware/carrier32 hardware/README.md
git commit -m "chore: scaffold carrier32 kicad project"
```

### Task 2: Capture Release Evidence and Pin Contracts

**Files:**
- Create: `hardware/carrier32/config/design-inputs.csv`
- Create: `hardware/carrier32/config/net-contract.csv`
- Create: `hardware/carrier32/scripts/check_design_inputs.py`
- Create: `hardware/carrier32/scripts/check_net_contract.py`
- Test: `hardware/carrier32/scripts/test_checks.py`

**Interfaces:**
- Consumes: the approved spec and current firmware pin macros.
- Produces: machine-readable evidence status and an exact connector/net/pin mapping used by every later task.

- [ ] **Step 1: Write failing standard-library tests**

Tests must assert that the evidence checker rejects a required row whose `status` is not `verified`, accepts evidence rows with a value, unit, source and date, reports duplicate reference designators, and verifies exactly 32 sensor asset codes. The net-contract test must assert the frozen Node A and Node B pins from the spec and reject a conflicting duplicate MCU pin.

- [ ] **Step 2: Run tests and confirm failure**

```powershell
python -m unittest hardware.carrier32.scripts.test_checks -v
```

Expected: failure because the checker modules do not yet exist.

- [ ] **Step 3: Implement the evidence and contract checkers**

`check_design_inputs.py` must parse CSV with `id,status,value,unit,source,date,notes`, require `verified` for fabrication-critical rows, and print every blocking row before returning exit code 1. `check_net_contract.py` must parse `asset_code,node,connector_pin,mcu_pin,signal_type,voltage_domain,active_level`, enforce unique asset codes and connector pins, and enforce the 32-sensor count.

- [ ] **Step 4: Populate known facts and explicit measurement gates**

Record the two fan ratings as verified from the project owner. Record each unknown mechanical/electrical item with status `measurement_required`; this is a deliberate release state, not a guessed value. Populate all 32 sensor asset codes and the approved MCU pins.

- [ ] **Step 5: Run tests**

```powershell
python -m unittest hardware.carrier32.scripts.test_checks -v
python hardware/carrier32/scripts/check_design_inputs.py --phase schematic hardware/carrier32/config/design-inputs.csv
python hardware/carrier32/scripts/check_net_contract.py hardware/carrier32/config/net-contract.csv
```

Expected: unit tests pass; schematic-phase evidence passes; the fabrication phase remains blocked until physical measurements are recorded.

- [ ] **Step 6: Commit**

```powershell
git add hardware/carrier32/config hardware/carrier32/scripts
git commit -m "test: codify carrier evidence and net contracts"
```

### Task 3: Design the Protected Power Tree

**Files:**
- Create: `hardware/carrier32/sheets/power.kicad_sch`
- Create: `hardware/carrier32/docs/power-budget.csv`
- Create: `hardware/carrier32/docs/power-review.md`
- Modify: `hardware/carrier32/carrier32.kicad_sch`

**Interfaces:**
- Consumes: `12V_IN`, verified fan rating, 32-sensor population.
- Produces: `12V_PROTECTED`, `5V_LOGIC`, `5V_MQ`, `3V3_ESP_A`, `3V3_ESP_B` and protected branch nets.

- [ ] **Step 1: Calculate the documented power budget**

Use 1 W per MQ sensor as the design ceiling, 18 × 60 mA as the WS2812 full-white ceiling, 0.2 A per fan, and measured or manufacturer-backed values for every other row. Keep unmeasured loads as separately identified release gates; do not replace them with invented current values.

- [ ] **Step 2: Select parts from primary datasheets and available supply channels**

Select a 12 V protection MOSFET, TVS, two buck converters, and two ESP regulators. The logic buck must provide at least 3 A, the MQ buck at least 5 A, and each ESP regulator at least 600 mA. Capture manufacturer, exact orderable part, input/output limits, package, thermal requirements and approved alternate in `power-review.md`.

- [ ] **Step 3: Draw the input protection and branch protection schematic**

Place terminal, replaceable total fuse, reverse-polarity MOSFET, gate protection, TVS, input bulk/high-frequency capacitors, and independent fan branch fuse positions. Mark fuse values as selected-by-test fields in the BOM and block fabrication until evidence supplies those values.

- [ ] **Step 4: Draw independent logic and MQ regulators**

Copy each selected regulator's manufacturer reference design, including compensation, inductor, bootstrap and capacitor requirements. Keep the two switch nodes and feedback networks electrically independent.

- [ ] **Step 5: Draw the two ESP regulator branches**

Add independent input/output capacitors, local bulk capacitor, current-measurement link, power test point and LED-disable solder bridge for each ESP.

- [ ] **Step 6: Review startup and single-fault behavior**

Document expected behavior for reverse input, TVS conduction, one fan short, one MQ group short, one ESP short and USB insertion. No fault in a board-external branch may rely only on a thin PCB trace to clear.

- [ ] **Step 7: Export and inspect the power-sheet PDF**

Run the KiCad schematic PDF export and visually check net labels, fuse order, regulator feedback, polarity and test points.

- [ ] **Step 8: Commit**

```powershell
git add hardware/carrier32
git commit -m "feat: design carrier power and protection"
```

### Task 4: Add the Two Controller and ESP Sockets

**Files:**
- Create: `hardware/carrier32/sheets/node_a.kicad_sch`
- Create: `hardware/carrier32/sheets/node_b.kicad_sch`
- Modify: `hardware/carrier32/lib/carrier32.kicad_sym`
- Modify: `hardware/carrier32/carrier32.kicad_sch`

**Interfaces:**
- Consumes: protected logic rails and the net contract.
- Produces: Node A/Node B MCU nets, dual ESP UARTs, dual screens, joystick, SWD, USART1, BOOT and reset access.

- [ ] **Step 1: Create controller symbols from photographed and measured headers**

Use pin names matching the development-board silk and MCU port names. Mark 5 V, 3.3 V and GND as power pins; do not assign a footprint until header count and row spacing are measured.

- [ ] **Step 2: Add power-direction control**

Implement the measured USB/carrier 5 V behavior using either a documented selection jumper or isolation component. The schematic must make USB and carrier simultaneous connection behavior explicit.

- [ ] **Step 3: Add ESP sockets and boot networks**

Connect PA2/PA3 to RX/TX with series-resistor positions. Add EN, RST, GPIO0 and GPIO2 networks, programming jumper, reset access and independent power test points.

- [ ] **Step 4: Add both displays and the joystick**

Node A display uses PB3/PB5 and PC4-PC7. Node B display uses PA5/PA7 and PB6-PB9. The joystick uses Node B PC0, PC1 and PC4 and receives only 3.3 V.

- [ ] **Step 5: Add SWD, USART1, BOOT and reset headers**

Provide separate node-labelled interfaces. SWD pin order is `3V3, SWDIO, SWCLK, NRST, GND`; debug UART exposes `3V3, TX, RX, GND` and silk later states the adapter crossing direction.

- [ ] **Step 6: Run net-contract checks and schematic ERC**

Export the netlist, compare every frozen signal using `check_net_contract.py`, and run KiCad ERC. Expected: no pin collision, no unresolved power-driver error and no cross-node same-name net connection.

- [ ] **Step 7: Commit**

```powershell
git add hardware/carrier32
git commit -m "feat: add dual controller and esp interfaces"
```

### Task 5: Add All 32 Sensor Interfaces

**Files:**
- Create: `hardware/carrier32/sheets/sensors_a.kicad_sch`
- Create: `hardware/carrier32/sheets/sensors_b.kicad_sch`
- Create: `hardware/carrier32/docs/input-protection-calculations.csv`
- Modify: `hardware/carrier32/carrier32.kicad_sch`

**Interfaces:**
- Consumes: the 32-row net contract and protected power domains.
- Produces: 4 I2C, 13 protected analog and 15 protected digital sensor connectors.

- [ ] **Step 1: Add four SHT30 connectors**

Place two sensors on PB6/PB7 and two on PB10/PB11, with one 0x44 and one 0x45 per bus. Add configurable bus pull-ups and record the maximum allowed equivalent pull-up before module population.

- [ ] **Step 2: Add thirteen analog front ends**

Each channel receives connector-side test point, series limit resistor, selectable unity/divider population, RC filter, low-leakage rail protection and ADC-side test point. Calculate divider output, Thevenin resistance, clamp current and RC cutoff for both 3.3 V and 5 V source configurations in the CSV.

- [ ] **Step 3: Add fifteen digital front ends**

Each channel receives series resistance, configurable pull-up/pull-down, divider or level-shifter position and ESD position. Populate the FS-IR02 path for 5 V module operation; leave flame and MQ-2 population determined by recorded output-structure measurements.

- [ ] **Step 4: Partition MQ power connectors**

Place five MQ-2, five MQ-4 and five MQ-7 connectors on separately disconnectable `5V_MQ` branches. Each connector carries the exact module pins verified from the purchased hardware; a generic guessed `VCC/GND/AO/DO` order is not acceptable.

- [ ] **Step 5: Add MQ-7 limitation and test provisions**

Mark MQ-7 readings as raw/qualitative unless the module exposes independent heater control and the approved high/low heater cycle is implemented. Add accessible AO and supply test points for every MQ-7 channel.

- [ ] **Step 6: Verify all sensor counts and pin voltage calculations**

Run the contract checker and independently count 4 SHT30, 5 level, 5 MQ-2, 5 MQ-4, 5 MQ-7, 3 O2 and 5 flame connectors. Expected: exactly 32 unique asset codes and no MCU pin collision.

- [ ] **Step 7: Run ERC and inspect PDFs**

Expected: zero unreviewed ERC errors. Any intentional unconnected module output receives an explicit no-connect marker and design note.

- [ ] **Step 8: Commit**

```powershell
git add hardware/carrier32
git commit -m "feat: add thirty-two protected sensor interfaces"
```

### Task 6: Add Fans, INA226, Relay, Buzzer, WS2812 and Expansion

**Files:**
- Create: `hardware/carrier32/sheets/actuators.kicad_sch`
- Create: `hardware/carrier32/sheets/expansion.kicad_sch`
- Modify: `hardware/carrier32/carrier32.kicad_sch`

**Interfaces:**
- Consumes: Node A actuator pins and protected rails.
- Produces: two four-wire fan interfaces, two INA226 sockets, relay, buzzer, HW-221/WS2812 and generic expansion headers.

- [ ] **Step 1: Add both four-wire fan interfaces**

Use Node A PB8/PB9 through inverting open-drain drivers for 25 kHz PWM. Use PA6/PA7 for TACH with external 10 kOhm pull-ups to 3.3 V and series protection. Label connector order only after wire-color/pin-order continuity testing.

- [ ] **Step 2: Add INA226 module sockets**

Power logic from 3.3 V and connect the approved Node A I2C bus. Make shunt direction and fan association unambiguous; do not encode current range until module shunt values are measured.

- [ ] **Step 3: Add relay and buzzer drivers**

Use buffered or transistor drivers so PA1/PB0 never source the load. Match the measured active levels while preserving the firmware's high-level logical commands.

- [ ] **Step 4: Add HW-221 and WS2812 interface**

Use PB15 through a 74AHCT-family 3.3 V-to-5 V buffer, output damping resistor, independent branch protection and connector-side bulk capacitance.

- [ ] **Step 5: Add generic expansion headers**

Separate Node A and Node B, ADC and digital signals, 3.3 V and 5 V. Do not name DHT11, vibration, K210 or voice modules on the schematic or silk.

- [ ] **Step 6: Run ERC and safe-default review**

Check that reset and unpowered states leave fans, relay and buzzer safe and do not back-feed MCU pins. Export PDFs and inspect every connector's voltage and active-level annotation.

- [ ] **Step 7: Commit**

```powershell
git add hardware/carrier32
git commit -m "feat: add carrier actuator and expansion interfaces"
```

### Task 7: Complete Schematic Review and Freeze the BOM Basis

**Files:**
- Create: `hardware/carrier32/output/review/carrier32-schematic.pdf`
- Create: `hardware/carrier32/output/review/erc-report.txt`
- Create: `hardware/carrier32/docs/schematic-review.md`
- Create: `hardware/carrier32/output/assembly/carrier32-bom.csv`

**Interfaces:**
- Consumes: all schematic sheets.
- Produces: an ERC-clean reviewed schematic and exact preliminary BOM.

- [ ] **Step 1: Annotate and assign footprints**

Use stable references grouped by function. Only measured modules receive project footprints; unmeasured mechanical parts keep fabrication blocked rather than receiving guessed footprints.

- [ ] **Step 2: Generate BOM and audit lifecycle/availability**

Each fitted row includes reference, quantity, manufacturer, MPN, description, package, voltage/current rating, population status and approved alternate. Safety-critical protection parts may not use unspecified marketplace substitutions.

- [ ] **Step 3: Run ERC and net-contract checks**

```powershell
& 'D:\KiCad\bin\kicad-cli.exe' sch erc --exit-code-violations --output 'hardware\carrier32\output\review\erc-report.txt' 'hardware\carrier32\carrier32.kicad_sch'
python hardware/carrier32/scripts/check_net_contract.py hardware/carrier32/config/net-contract.csv
```

Expected: exit code 0 and no unreviewed violations.

- [ ] **Step 4: Perform manual schematic review**

Review power polarity, protection order, every connector pin, cross-sheet labels, ESP boot states, fan inversion, ADC protection, SHT30 addresses, unused logic inputs and all no-connect markers. Record reviewer/date/evidence for each item.

- [ ] **Step 5: Commit**

```powershell
git add hardware/carrier32
git commit -m "docs: freeze reviewed carrier schematic"
```

### Task 8: Create and Verify Measured Footprints

**Files:**
- Modify: `hardware/carrier32/lib/carrier32.pretty/*.kicad_mod`
- Create: `hardware/carrier32/docs/footprint-inspection.md`

**Interfaces:**
- Consumes: verified physical measurements in `design-inputs.csv`.
- Produces: exact sockets, connector courtyards, mounting holes and antenna keep-outs.

- [ ] **Step 1: Record physical measurements**

Measure both STM32 boards, header row spacing, pin count, board thickness, underside height, mounting holes, USB protrusion, ESP modules, connector bodies and enclosure interior. Attach photo/caliper evidence paths to the CSV.

- [ ] **Step 2: Create project footprints**

Create footprints with explicit pin 1, fab outline, courtyard, assembly name and orientation. The ESP footprint includes copper/track/via/component keep-outs under and in front of the antenna.

- [ ] **Step 3: Print a 1:1 fit sheet**

Export footprint drawings at 1:1 scale, print without scaling, place physical modules/connectors over them and record pass/fail results.

- [ ] **Step 4: Validate footprint libraries**

```powershell
& 'D:\KiCad\bin\kicad-cli.exe' fp upgrade 'hardware\carrier32\lib\carrier32.pretty'
```

Expected: every footprint parses as KiCad 10 and retains measured pad coordinates.

- [ ] **Step 5: Commit**

```powershell
git add hardware/carrier32/lib hardware/carrier32/config hardware/carrier32/docs
git commit -m "feat: add measured carrier footprints"
```

### Task 9: Place the PCB and Freeze the Mechanical Outline

**Files:**
- Create: `hardware/carrier32/carrier32.kicad_pcb`
- Create: `hardware/carrier32/docs/placement-review.md`

**Interfaces:**
- Consumes: ERC-clean schematic, measured footprints and enclosure dimensions.
- Produces: final board outline, mounting holes, zones, keep-outs and reviewed placement.

- [ ] **Step 1: Import the schematic into PCB Editor**

Confirm every annotated symbol has exactly one footprint and no orphan footprint exists.

- [ ] **Step 2: Draw the measured board outline and mounting holes**

Do not retain 160 mm × 100 mm unless the enclosure measurements explicitly approve it. Set board-edge clearance and mounting-hole keep-outs.

- [ ] **Step 3: Place functional zones**

Place 12 V protection and converters together, MQ connectors near `5V_MQ`, fans and WS2812 near the power edge, analog inputs near their MCU ADC pins, and both ESP antennas at clear board edges.

- [ ] **Step 4: Review serviceability**

Confirm USB, SWD, UART, BOOT, reset, fuses, jumpers, test points and all removable modules remain accessible after enclosure installation.

- [ ] **Step 5: Generate placement review images**

Export front/back SVG or high-resolution plots and a 3D screenshot. Mark antenna keep-outs, high-current regions and analog regions in `placement-review.md`.

- [ ] **Step 6: Commit**

```powershell
git add hardware/carrier32
git commit -m "feat: place carrier pcb from measured geometry"
```

### Task 10: Route Power, Signals and Planes

**Files:**
- Modify: `hardware/carrier32/carrier32.kicad_pcb`
- Create: `hardware/carrier32/docs/routing-calculations.csv`

**Interfaces:**
- Consumes: approved placement and measured load currents.
- Produces: fully routed PCB with continuous ground and current-rated copper.

- [ ] **Step 1: Define net classes**

Create classes for 12 V input, fan branches, `5V_MQ`, `5V_LOGIC`, ESP supplies, ordinary digital, I2C/UART/SPI and analog inputs. Calculate width/via requirements from copper weight, current, layer use and accepted temperature rise.

- [ ] **Step 2: Route both switch-mode converters first**

Follow manufacturer placement and loop-area requirements. Keep SW copper compact and away from ADC, I2C and antennas.

- [ ] **Step 3: Route high-current branches**

Use pours or appropriately wide tracks with via arrays. Each fan and MQ group must return directly to the power-entry region without sharing a narrow sensor return.

- [ ] **Step 4: Route analog and communication signals**

Keep ADC traces short and separated from PWM, relay, WS2812 and switch nodes. Avoid routing under ESP antennas. Keep each I2C bus compact and preserve its own pull-up domain.

- [ ] **Step 5: Pour continuous ground planes and inspect return paths**

Do not split GND. Remove islands, stitch around board edges and converters where useful, and ensure no signal crosses a void in its reference plane.

- [ ] **Step 6: Add final silk and assembly markings**

Mark every connector reference, signal order, voltage, node, pin 1, fuse function, jumper state and warning. Keep silk out of pads and exposed antenna areas.

- [ ] **Step 7: Run DRC and inspect every remaining marker**

```powershell
& 'D:\KiCad\bin\kicad-cli.exe' pcb drc --exit-code-violations --output 'hardware\carrier32\output\review\drc-report.txt' 'hardware\carrier32\carrier32.kicad_pcb'
```

Expected: exit code 0 and zero unreviewed violations.

- [ ] **Step 8: Commit**

```powershell
git add hardware/carrier32
git commit -m "feat: route carrier pcb and power planes"
```

### Task 11: Prototype Bring-Up and Load Verification

**Files:**
- Create: `hardware/carrier32/docs/bring-up-record.md`
- Modify: `hardware/carrier32/config/design-inputs.csv`
- Modify: `hardware/carrier32/docs/power-budget.csv`

**Interfaces:**
- Consumes: assembled prototype and test firmware.
- Produces: measured evidence required to finalize fuses, filters, bulk capacitors and population options.

- [ ] **Step 1: Inspect the unpowered board**

Check polarity, shorts, connector pin order, fuse paths, module orientation and resistance between every rail and GND.

- [ ] **Step 2: Bring up rails without controllers or sensors**

Use a current-limited 12 V supply. Record 12 V protected, 5 V logic, 5 V MQ and both ESP 3.3 V rails, switching ripple and regulator temperature.

- [ ] **Step 3: Add loads in the specified order**

Add both ESPs, both STM32 boards, displays/joystick, one MQ, three MQ groups, digital sensors, analog sensors, fans and WS2812. Record current, minimum rail voltage and temperature at each step.

- [ ] **Step 4: Exercise review-focus faults**

Test fan simultaneous startup, both ESPs transmitting, WS2812 full-white command, one unplugged sensor per class, SHT30 address conflict detection, USB insertion and each external branch short through a protected test fixture.

- [ ] **Step 5: Freeze protection and filter values**

Update fuse ratings, TVS selection, bulk capacitors, ADC filters and population options only from recorded measurements and part limits. Re-run ERC/DRC after every schematic/PCB change.

- [ ] **Step 6: Commit**

```powershell
git add hardware/carrier32
git commit -m "test: record carrier prototype bring-up"
```

### Task 12: Generate and Validate Manufacturing Deliverables

**Files:**
- Create: `hardware/carrier32/scripts/check_fabrication_bundle.py`
- Test: `hardware/carrier32/scripts/test_fabrication_bundle.py`
- Create: `hardware/carrier32/output/fabrication/*`
- Create: `hardware/carrier32/output/assembly/carrier32-bom.csv`
- Create: `hardware/carrier32/output/assembly/carrier32-cpl.csv`
- Create: `hardware/carrier32/ASSEMBLY.md`

**Interfaces:**
- Consumes: fabrication-cleared evidence, ERC-clean schematic, DRC-clean PCB and prototype-approved values.
- Produces: complete factory and assembly package.

- [ ] **Step 1: Write failing fabrication-bundle tests**

Tests must reject a missing copper layer, missing solder mask, absent edge cuts, absent plated/non-plated drill data, duplicate BOM references, CPL references absent from the BOM, unverified design-input rows, and non-zero ERC/DRC violations.

- [ ] **Step 2: Implement the bundle validator and pass its tests**

```powershell
python -m unittest hardware.carrier32.scripts.test_fabrication_bundle -v
```

Expected: all validator tests pass.

- [ ] **Step 3: Run the fabrication evidence gate**

```powershell
python hardware/carrier32/scripts/check_design_inputs.py --phase fabrication hardware/carrier32/config/design-inputs.csv
```

Expected: exit code 0. A non-zero result stops release.

- [ ] **Step 4: Run final ERC, DRC and schematic-PCB consistency checks**

Run `run_checks.ps1`. Expected: all commands exit 0 and reports contain no unreviewed violations.

- [ ] **Step 5: Generate fabrication and assembly outputs from the jobset**

Use the KiCad jobset to create Gerbers, drill files, Gerber job file, BOM, CPL, schematic PDF and front/back review plots. Do not hand-edit generated Gerbers or CPL coordinates.

- [ ] **Step 6: Validate and visually inspect outputs**

Run `check_fabrication_bundle.py`; then open the Gerbers in KiCad Gerber Viewer and inspect outline, holes, masks, silk, copper, polarity marks and connector orientation. Render PCB and schematic review images for human inspection.

- [ ] **Step 7: Write assembly and wiring instructions**

Document module orientation, jumper defaults, fuse installation, first-power sequence, Node A/Node B programming headers, every connector pinout and all do-not-fit options.

- [ ] **Step 8: Commit**

```powershell
git add hardware/carrier32
git commit -m "build: generate verified carrier manufacturing package"
```

### Task 13: Final Cross-Discipline Review

**Files:**
- Create: `hardware/carrier32/output/review/final-review.md`

**Interfaces:**
- Consumes: the complete KiCad project and manufacturing bundle.
- Produces: signed release decision or an exact blocking list.

- [ ] **Step 1: Review schematic against firmware**

Compare all Node A/Node B pins against current source macros and persistent pin-contract tests. Confirm no firmware change since the contract export invalidated the design.

- [ ] **Step 2: Review PCB against schematic and mechanical evidence**

Check footprint pin numbering, module orientation, board outline, enclosure clearance, antenna zones, current paths, thermal paths and service access.

- [ ] **Step 3: Review outputs against the source revision**

Record Git commit, KiCad version, jobset hash, ERC/DRC report hashes and fabrication bundle hashes in `final-review.md`.

- [ ] **Step 4: Run the full verification command**

```powershell
powershell -ExecutionPolicy Bypass -File hardware/carrier32/scripts/run_checks.ps1
git status --short
```

Expected: all checks pass; generated outputs correspond to the reviewed source; no unintended source change remains.

- [ ] **Step 5: Commit**

```powershell
git add hardware/carrier32/output/review/final-review.md
git commit -m "docs: approve carrier32 manufacturing release"
```
