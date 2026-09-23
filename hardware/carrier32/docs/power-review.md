# Carrier32 power design review — work in progress

Date: 2026-09-23. This is a design review input, not a fabrication approval.

## Rail targets and known load

| Rail | Target | Known load | Unknown load |
| --- | ---: | ---: | --- |
| `12V_PROTECTED` | external 12 V, adapter target ≥5 A | two fans 0.4 A / 4.8 W | converter input and transients |
| `5V_MQ` | 5 A regulator capability | 15 MQ modules, 3 A / 15 W design ceiling | module electronics above the 1 W cap, if any |
| `5V_LOGIC` | 3 A minimum regulator capability | 18 WS2812, 1.08 A / 5.4 W full white | both MCUs, displays, relay, buzzer, sensors, ESP LDO input |
| `3V3_ESP_A`, `3V3_ESP_B` | independent LDOs, ≥600 mA device rating each | no measured module current | startup and Wi-Fi peak current, temperature |

Known ceiling is 25.2 W across separate rails, excluding every unmeasured item. The 12 V / 5 A input is an initial adapter target, not a proved worst-case requirement. See [power-budget.csv](power-budget.csv).

## Proposed components

| Function | Exact intended part | Evidence and conditions | Release status |
| --- | --- | --- | --- |
| Reverse polarity MOSFET | Alpha & Omega AO4443 | Manufacturer lists full production, P-channel −40 V, −6 A at 25 °C, SO8, 42 mΩ max at −10 V gate drive. Drain at fused input, source at protected rail, gate pull-down with gate-source zener. At 5 A, 42 mΩ implies 1.05 W conduction loss before thermal derating. Copper area and prototype temperature are gates. [Manufacturer](https://www.aosmd.com/products/mosfets/p-channel-mosfets-8v-60v/ao4443) | THERMAL_GATE |
| Input TVS | Littelfuse SMBJ18CA | Bidirectional, 18 V standoff, 20.0–22.1 V breakdown, 29.2 V peak clamp, 600 W 10/1000 µs waveform. Verify fuse coordination under the actual supply source. [Manufacturer series data](https://www.littelfuse.com/assetdocs/tvs-diodes-smbj-series-datasheet?assetguid=ba555e99-a12d-4f72-a0b6-86b06c67171e) | COORDINATION_GATE |
| Logic buck | TI LMR51450FSQDRRRQ1 | 4–36 V input, 5 A rating, WSON-12, FPWM. This single stocked family is used for both 5 V rails; 5 A capability exceeds the 3 A logic minimum. The exact device is listed active by TI. [TI part](https://www.ti.com/product/LMR51450-Q1/part-details/LMR51450FSQDRRRQ1) | SYMBOL_FOOTPRINT_GATE |
| MQ buck | TI LMR51450FSQDRRRQ1 | Independent instance, switch node, bootstrap, input and feedback from the logic buck. At 440 kHz, TI's 5 V / 5 A reference calls for 4.7 µH, two 33 µF ceramic output capacitors after derating, 100 kΩ/19.1 kΩ divider, 33 pF feed-forward and 1 kΩ feed-forward resistor. Input uses two 4.7 µF 50 V X7R plus 0.1 µF close to VIN. Inductor requirement: 6 A RMS and 10 A saturation in TI's design example. [TI data sheet](https://www.ti.com/lit/ds/symlink/lmr51450-q1.pdf) | SYMBOL_FOOTPRINT_GATE |
| ESP LDOs | Diodes Incorporated AP2112K-3.3TRG1 ×2 | Guaranteed 600 mA continuous device rating and fixed 3.3 V output, SOT-23-5. Two separate branches with local input/output and bulk capacitors. Each 5 V→3.3 V LDO could dissipate 1.02 W at 600 mA; prototype temperature and actual current must be measured before declaring continuous operation. [Manufacturer](https://www.diodes.com/part/view/AP2112) | THERMAL_GATE |
| Logic buck alternative | TI LMR51430XFDDCR | 4.5–36 V, 3 A, 500 kHz FPWM, SOT-23-6. This is an architectural alternate, not pin compatible; requires a new circuit and footprint review. [TI data sheet](https://www.ti.com/lit/ds/symlink/lmr51430.pdf) | NOT_APPROVED_FOR_DROP_IN |

No footprint or electrical substitution is approved merely by sharing a nominal rating. The buck instances use a project-local 13-pin electrical symbol from TI's pin table. Their PCB footprint fields are intentionally blank. Before fabrication, attach a verified WSON-12 exposed-pad land pattern and re-run netlist pin and ERC checks. AO4443 now has a project-local 8-pin model with SOIC-8 footprint, based on the manufacturer's pin diagram; confirm pad mapping once more during PCB layout review.

## Protection and startup behavior

- `F1` is the replaceable input fuse. `F2` and `F3` are independent fan branch fuse positions. `F4` isolates the MQ regulator input branch. `F5`–`F7` split the 5 V MQ output into MQ-2, MQ-4 and MQ-7 groups. `F8`–`F10` isolate the external WS2812, sensor and relay 5 V branches. Values remain `SELECT_BY_TEST` until startup surge, fan stall, MQ heater cold resistance, wiring gauge, and adapter current limit are measured. External branches cannot rely on a PCB trace as a fuse.
- Reverse input: the P-channel MOSFET body diode is reverse-biased with drain at the fused input and source at the load, and the gate pull-down does not turn it on. Verify with the exact AO4443 pin mapping and the prototype.
- Excess positive input: the TVS diverts surge current after F1; F1/TVS coordination and allowed energy must be tested. A sustained overvoltage is outside the TVS pulse rating.
- One fan short: its own fuse position should clear or current-limit independently; choose rating after the actual fan stall profile is known.
- MQ short: `F4` protects its input branch; the buck also has cycle-by-cycle current limit, hiccup short-circuit handling and thermal shutdown per TI. Other rails should stay alive during this single fault in prototype testing.
- One ESP short: the affected AP2112 branch has current limit/thermal protection; the other ESP has a separate LDO. The shared 5 V logic input must be checked for sag.
- USB insertion into either removable STM32 board: the board's USB 5 V direction is not yet measured. The later controller sheet must implement measured isolation or an explicit selection jumper before powering the carrier and USB at once.

## Open design defects / evidence gates

1. Buck WSON footprints require mechanical review; these footprint fields are deliberately omitted. AO4443's 8-pad mapping remains a PCB review item.
2. F1 must be a field-replaceable fuse and holder. Its holder footprint is blank until enclosure and service-clearance measurements are available.
3. The 2026-09-23 PDF inspection found overlapping values/net labels around both buck converters and ESP branches, plus the inherited `API Series 500 (EDA 306)` title block. Although the netlist maps 80 checked pins correctly and ERC has zero errors, the drawing fails the visual-review gate. Re-layout into functional sheets, replace the title block, export a fresh PDF, and reinspect before claiming circuit freeze.
4. Fuse ratings, inductor MPN/footprint and derated ceramic capacitor MPNs are unselected. The generic 1210 inductor footprint was removed because it cannot establish the required 6 A RMS / 10 A saturation capability; use the selected inductor manufacturer's land pattern only after sourcing review. The schematic generator also inherited a 10×10 electrolytic footprint on the four ceramic output capacitors; those inherited footprints were cleared and are now checked as an explicit invariant.
5. AO4443 SO8 thermal margin, TVS/fuse coordination and each ESP LDO thermal margin need prototype evidence.
6. All module current measurements and physical pinout photographs remain outstanding. The PCB outline cannot be frozen before mechanical measurements.

This review keeps the circuit and manufacturing stages blocked until those findings are resolved.
