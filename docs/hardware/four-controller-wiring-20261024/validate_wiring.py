"""Validate the proposed resource map; does not connect, power or flash hardware."""
from pathlib import Path
import collections
import json
import re
import sys

ROOT = Path(__file__).resolve().parent
PLAN_PATH = ROOT / "wiring-plan.json"
REPORT_PATH = ROOT / "validation-report.json"
plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
errors = []
warnings = [
    "This is a static planning check, not native ERC, a firmware build or hardware validation.",
    "Board variant, relay interfaces and power capacity remain unverified; 3.3V sensor signal levels are user-confirmed, not measured in this run.",
    "AO-02 bare sensors are user-directed direct-to-ADC; millivolt resolution and accuracy remain unvalidated.",
    "Disconnect all old fan control wires before connecting each new PB8/PA7/PA1 set; CTRL-01 PC10 stays unused.",
    "Selected automatic-direction RS485 modules require timing and reset/recovery tests.",
]
adc_pins = {"PA0":0, "PA1":1, "PA2":2, "PA3":3, "PA4":4, "PA5":5,
            "PA6":6, "PA7":7, "PB0":8, "PB1":9, "PC0":10, "PC1":11,
            "PC2":12, "PC3":13, "PC4":14, "PC5":15}
af_pins = {
    "USART2_TX":"PA2", "USART2_RX":"PA3",
    "SPI3_SCK":"PB3", "SPI3_MOSI":"PB5",
    "SPI1_SCK":"PA5", "SPI1_MOSI":"PA7",
    "SPI2_MOSI":"PB15", "TIM4_CH3":"PB8", "TIM4_CH4":"PB9",
    "EXTI6":"PA6", "EXTI7":"PA7",
}
nodes = {"CTRL-01", "CTRL-02", "CTRL-03", "CTRL-04"}
claims = {node:{} for node in nodes}
def check(ok, msg):
    if not ok:
        errors.append(msg)

def claim(node, pin, owner, mode):
    check(node in nodes, f"Unknown MCU node: {node}")
    if node not in nodes:
        return
    check(bool(re.fullmatch(r"P[ABC](?:[0-9]|1[0-5])", pin)), f"Invalid or unverified package pin {node}/{pin}")
    reserved = dict(plan["reservedPins"])
    reserved.update(plan["nodeSpecificReserved"].get(node, {}))
    check(pin not in reserved, f"Reserved pin claimed {node}/{pin}: {owner}")
    if pin in claims[node]:
        errors.append(f"Pin collision {node}/{pin}: {claims[node][pin]['owner']} vs {owner}")
    else:
        claims[node][pin] = {"owner":owner, "mode":mode}
    if mode in af_pins:
        check(af_pins[mode] == pin, f"AF mismatch {node}/{owner}/{mode}/{pin}")
    if mode.startswith("ADC1_IN"):
        channel = int(mode.removeprefix("ADC1_IN"))
        check(adc_pins.get(pin) == channel, f"ADC mismatch {node}/{pin}/{mode}")

sensors = plan["sensors"]
tags = [s["physicalTag"] for s in sensors]
check(len(tags) == 31 and len(set(tags)) == 31, "Expected exactly 31 unique external sensors")
check("LEVEL-05" not in tags, "Removed LEVEL-05 must not be active")
expected_counts = {"MQ2":5, "MQ4":5, "CO":5, "FLAME":5, "SHT":4, "LEVEL":4, "O2":3}
counts = dict(collections.Counter(s["category"] for s in sensors))
check(counts == expected_counts, f"Category count mismatch: {counts}")
by_node = dict(collections.Counter(s["node"] for s in sensors))
check(by_node == plan["allocation"], f"Allocation mismatch: {by_node}")

bus_by_node = {b["node"]:b for b in plan["buses"]}
check(len(bus_by_node) == 4, "Expected four separate local I2C buses")
for bus in plan["buses"]:
    addresses = [d["address"] for d in bus["devices"]]
    check(len(addresses) == len(set(addresses)), f"I2C address collision on {bus['node']}")
    check(bus["pullupRail"] == "3V3", "I2C pull-up target must be 3.3V")
    claim(bus["node"], bus["scl"], "I2C-LOCAL:SCL(shared)", "SOFTWARE_I2C_OPEN_DRAIN")
    claim(bus["node"], bus["sda"], "I2C-LOCAL:SDA(shared)", "SOFTWARE_I2C_OPEN_DRAIN")

for sensor in sensors:
    check(sensor["old"] is not None, f"Missing migration origin for {sensor['physicalTag']}")
    check(sensor["mcuSignalDomain"] == "0_TO_3V3", "Unexpected MCU signal-voltage target")
    if sensor["interface"] == "I2C_SOFTWARE":
        bus = bus_by_node[sensor["node"]]
        check(sensor["pins"] == [bus["scl"],bus["sda"]], f"I2C pins mismatch {sensor['physicalTag']}")
        matches = [d for d in bus["devices"] if d["id"] == sensor["physicalTag"]]
        check(len(matches) == 1 and matches[0]["address"] == sensor["i2cAddress"],
              f"I2C address mismatch {sensor['physicalTag']}")
    else:
        check(len(sensor["pins"]) == 1, "Expected one data pin per scalar sensor")
        mode = f"ADC1_IN{sensor['adcChannel']}" if sensor["interface"] == "ADC" else "GPIO_INPUT"
        claim(sensor["node"], sensor["pins"][0], sensor["physicalTag"], mode)
    if sensor["category"] == "O2":
        check(sensor["powerDomain"] == "PASSIVE_ELECTRODE_NO_EXTERNAL_POWER",
              "AO-02 electrodes must not receive an external supply")
        check(sensor["conditioning"] == "DIRECT_ADC_USER_SELECTED_RAW_MILLIVOLT_ACCURACY_UNVALIDATED",
              "AO-02 direct ADC decision must retain raw-millivolt/accuracy limitations")

for station, config in plan["layout"]["stations"].items():
    group = [s for s in sensors if s["station"] == station]
    check(len(group) == 4 and {s["category"] for s in group} == {"MQ2","MQ4","CO","FLAME"},
          f"Station membership invalid: {station}")
    check(all(s["node"] == config["node"] for s in group), f"Station controller mismatch: {station}")
    check(all(int(s["physicalTag"].split("-")[1]) == int(station[1:]) for s in group),
          f"Station tag suffix mismatch: {station}")

for device in plan["devices"]:
    for signal in device["signals"]:
        claim(device["node"], signal["pin"], device["id"]+":"+signal["name"], signal["mode"])
for node in nodes:
    serial = [d for d in plan["devices"] if d["node"] == node and d["id"] == "RS485"]
    check(len(serial) == 1, f"Expected one RS485 interface on {node}")

for node, fan_id, relay_id in [("CTRL-01","FAN-01","RELAY-01"),("CTRL-04","FAN-02","RELAY-02")]:
    fan = next(d for d in plan["devices"] if d["node"] == node and d["id"] == fan_id)
    check([(s["pin"],s["mode"]) for s in fan["signals"]] == [("PB8","TIM4_CH3"),("PA7","EXTI7")],
          f"Unified fan PWM/TACH mapping mismatch on {node}")
    relay = next(d for d in plan["devices"] if d["node"] == node and d["id"] == relay_id)
    check(relay["signals"][0]["pin"] == "PA1", f"Unified relay mapping mismatch on {node}")

check(plan["rs485"]["route"] == ["GW-01","CTRL-01","CTRL-02","CTRL-04","CTRL-03"],
      "Unexpected open-chain routing")
check(plan["rs485"]["terminations"] == [plan["rs485"]["route"][0],plan["rs485"]["route"][-1]],
      "Only physical endpoints may have 120-ohm termination")
check([plan["rs485"]["gateway"]["txGpio"], plan["rs485"]["gateway"]["rxGpio"]] == [17,18],
      "Gateway UART candidate changed without re-review")
check(plan["layout"]["sizeMm"] == [700,700,300], "Wrong physical envelope")

# Independent peripheral ownership constraints from legacy firmware and RM0008.
dma_proposal = {
    "CTRL-01":{"DMA2_CH2":"SPI3_TX", "DMA1_CH1":"ADC1"},
    "CTRL-02":{"DMA1_CH3":"SPI1_TX", "DMA1_CH5":"SPI2_TX", "DMA1_CH1":"ADC1"},
    "CTRL-03":{"DMA1_CH1":"ADC1"},
    "CTRL-04":{"DMA1_CH1":"ADC1"},
}
# USART1 remains polled/interrupt-driven; do not allocate its RX to DMA1_CH5 on CTRL-02.
warnings.append("CTRL-01 PB3 requires disabling JTAG while retaining SWD.")
warnings.append("Keep USART1 interrupt/poll driven on CTRL-02 while WS2812 uses SPI2_TX DMA1_CH5; local I2C remains software-driven without DMA.")
warnings.append("Digital sensor inputs are polled/latched; EXTI lines are not allocated to every input.")
mq = plan["powerBudget"]["mqModuleCounts"]
check(mq == {n:sum(s["category"] in {"MQ2","MQ4","CO"} for s in sensors if s["node"]==n) for n in nodes},
      "MQ power count does not match wiring")
mq_a = round(sum(mq.values()) * plan["powerBudget"]["mqBudgetPerModuleA5V"], 3)
led_a = round(plan["powerBudget"]["ledCount"] * plan["powerBudget"]["ledBudgetAPerPixel5V"],3)
fan_w = round(2 * plan["powerBudget"]["fanNominalV"] * plan["powerBudget"]["fanNominalAEach"],3)
resource_summary = {}
for node in sorted(nodes):
    resource_summary[node] = {
        "external_sensor_count":by_node[node],
        "external_adc_channels":sum(s["interface"]=="ADC" for s in sensors if s["node"]==node),
        "digital_sensor_inputs":sum(s["interface"]=="DIGITAL_INPUT" for s in sensors if s["node"]==node),
        "allocated_gpio_count_including_shared_buses":len(claims[node]),
    }
report = {
    "date":plan["date"], "static_resource_check":"PASS" if not errors else "FAIL",
    "energization_release":"BLOCKED_PENDING_INTERFACE_AND_POWER_MEASUREMENTS",
    "firmware_built":False, "hardware_verified":False, "native_erc_run":False,
    "counts":counts, "allocation":by_node, "resource_summary":resource_summary,
    "gpio_claims":{n:dict(sorted(claims[n].items())) for n in sorted(nodes)},
    "dma_proposal_not_implemented":dma_proposal,
    "partial_power_targets":{"mq_total_a_at_5v":mq_a,"mq_total_w":round(5*mq_a,3),
      "led_a_at_5v":led_a,"led_w":round(5*led_a,3),"fan_old_nominal_w_not_startup":fan_w,
      "incomplete_total_do_not_size_psu_from_this":True},
    "errors":errors,"warnings":warnings,
}
REPORT_PATH.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"static_resource_check":report["static_resource_check"],
                  "external_sensors":len(sensors),"allocation":by_node,
                  "resource_summary":resource_summary,
                  "energization_release":report["energization_release"],
                  "errors":errors},ensure_ascii=False))
sys.exit(0 if not errors else 1)
