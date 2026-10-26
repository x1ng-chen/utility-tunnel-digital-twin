"""Static review of the 2026-10-26 physical numbering and local resource map."""
from pathlib import Path
import collections
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parent
EXPECTED_POSITIONS = {'CTRL-01': 'LOWER_LEFT', 'CTRL-02': 'LOWER_RIGHT',
                      'CTRL-03': 'UPPER_RIGHT', 'CTRL-04': 'UPPER_LEFT'}
EXPECTED_STATIONS = {'P1': 'CTRL-04', 'P2': 'CTRL-03', 'P3': 'CTRL-01',
                     'P4': 'CTRL-02', 'P5': 'CTRL-01'}
EXPECTED_COUNTS = {'CTRL-01': 11, 'CTRL-02': 7, 'CTRL-03': 6, 'CTRL-04': 7}
EXPECTED_CATEGORIES = {'MQ2': 5, 'MQ4': 5, 'CO': 5, 'FLAME': 5, 'SHT': 4, 'LEVEL': 4, 'O2': 3}
ADC = {f'PA{i}': i for i in range(8)} | {'PB0': 8, 'PB1': 9} | {f'PC{i}': i + 10 for i in range(6)}
AF = {'USART2_TX': 'PA2', 'USART2_RX': 'PA3', 'SPI3_SCK': 'PB3', 'SPI3_MOSI': 'PB5',
      'SPI2_MOSI': 'PB15', 'TIM4_CH3': 'PB8', 'EXTI7': 'PA7'}
SCREEN = {'SCL': ('PB3', 'SPI3_SCK'), 'SDA': ('PB5', 'SPI3_MOSI'),
          'RES': ('PB6', 'GPIO_OUT'), 'DC': ('PB7', 'GPIO_OUT'),
          'CS': ('PB9', 'GPIO_OUT'), 'BLK': ('PC12', 'GPIO_OUT')}
# Independent requirements from board observations, package/AF maps and the user layout.
RESERVED = {'PA0', 'PA8', 'PA9', 'PA10', 'PA11', 'PA12', 'PA13', 'PA14', 'PA15',
            'PB2', 'PB4', 'PC8', 'PC9', 'PC14', 'PC15'}
ANCHORS = {'SCREEN-STATUS': 'CTRL-01', 'SCREEN-MAIN': 'CTRL-02', 'JOYSTICK': 'CTRL-02',
           'FAN-01': 'CTRL-04', 'RELAY-01': 'CTRL-04',
           'FAN-02': 'CTRL-02', 'RELAY-02': 'CTRL-02', 'BUZZER': 'CTRL-03', 'LED-01': 'CTRL-03'}


def validate(p):
    errors = []
    claims = {n: {} for n in EXPECTED_POSITIONS}

    def check(ok, message):
        if not ok:
            errors.append(message)

    def claim(node, pin, owner, mode):
        check(node in claims, f'Unknown MCU: {node}')
        if node not in claims:
            return
        check(bool(re.fullmatch(r'P[ABC](?:[0-9]|1[0-5])', pin)), f'Unverified package pin: {node}/{pin}')
        check(pin not in RESERVED and not (node == 'CTRL-04' and pin == 'PC10'),
              f'Reserved pin: {node}/{pin} for {owner}')
        check(pin not in claims[node], f'Pin collision: {node}/{pin}: {owner} vs {claims[node].get(pin)}')
        claims[node][pin] = {'owner': owner, 'mode': mode}
        if mode.startswith('ADC1_IN'):
            check(ADC.get(pin) == int(mode[7:]), f'ADC channel mismatch: {node}/{pin}/{mode}')
        elif mode in AF:
            check(AF[mode] == pin, f'AF mismatch: {node}/{pin}/{mode}')
        else:
            check(mode in {'GPIO_INPUT_POLL', 'GPIO_OUT', 'GPIO_IN_PULLUP', 'SOFTWARE_I2C_OPEN_DRAIN'},
                  f'Unreviewed peripheral mode: {node}/{pin}/{mode}')

    check(p['layout']['controllerPositions'] == EXPECTED_POSITIONS, 'Physical numbering differs from user image')
    check(p['layout']['sizeMm'] == [700, 700, 300], 'Envelope changed')
    check({k: v['node'] for k, v in p['layout']['stations'].items()} == EXPECTED_STATIONS, 'Station ownership changed')
    check(p['allocation'] == EXPECTED_COUNTS, 'Declared sensor allocation changed')
    sensors = p['sensors']
    tags = [s['physicalTag'] for s in sensors]
    expected_tags = {f'{c}-{i:02}' for c, count in EXPECTED_CATEGORIES.items() for i in range(1, count + 1)}
    check(len(tags) == 31 and set(tags) == expected_tags, 'Expected 31 unique physical sensor tags; no LEVEL-05')
    check(dict(collections.Counter(s['category'] for s in sensors)) == EXPECTED_CATEGORIES, 'Category count differs')
    counts = dict(collections.Counter(s['node'] for s in sensors))
    check(counts == EXPECTED_COUNTS, f'Actual sensor allocation differs: {counts}')

    baseline_path = ROOT.parent / 'four-controller-wiring-20261024' / 'wiring-plan.json'
    raw = baseline_path.read_bytes()
    check(hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest() == p['source']['sha256'], 'Historical baseline hash changed')
    baseline = json.loads(raw)
    original = {s['physicalTag']: s for s in baseline['sensors']}
    old_to_new = {'CTRL-01': 'CTRL-04', 'CTRL-02': 'CTRL-03', 'CTRL-03': 'CTRL-01', 'CTRL-04': 'CTRL-02'}
    buses = {b['node']: b for b in p['buses']}
    check(len(p['buses']) == 4 and set(buses) == set(claims), 'Need one local I2C bus on each MCU')
    for bus in p['buses']:
        check(bus['pullupRail'] == '3V3', f'Wrong pullup rail: {bus["node"]}')
        check(len({d['address'] for d in bus['devices']}) == len(bus['devices']), f'I2C address collision: {bus["node"]}')
        check(len({d['id'] for d in bus['devices']}) == len(bus['devices']), f'Duplicate I2C identity: {bus["node"]}')
        claim(bus['node'], bus['scl'], 'LOCAL-I2C:SCL(shared)', 'SOFTWARE_I2C_OPEN_DRAIN')
        claim(bus['node'], bus['sda'], 'LOCAL-I2C:SDA(shared)', 'SOFTWARE_I2C_OPEN_DRAIN')
    for s in sensors:
        old = original.get(s['physicalTag'])
        check(old is not None, f'Unknown historical sensor: {s["physicalTag"]}')
        if old:
            check(s['node'] == old_to_new[old['node']], f'Cross-zone sensor: {s["physicalTag"]}')
            check(s['pins'] == old['pins'] and s['old'] == old['old'], f'Local pin/provenance changed: {s["physicalTag"]}')
        check(s['localZone'] == EXPECTED_POSITIONS.get(s['node']), f'Wrong zone: {s["physicalTag"]}')
        check(s['mcuSignalDomain'] == '0_TO_3V3', f'Wrong signal domain: {s["physicalTag"]}')
        if s['station']:
            check(s['node'] == EXPECTED_STATIONS.get(s['station']), f'Station crosses zone: {s["physicalTag"]}')
            check(int(s['physicalTag'].split('-')[1]) == int(s['station'][1:]), f'Station/tag renamed: {s["physicalTag"]}')
        if s['interface'] == 'I2C_SOFTWARE':
            bus = buses.get(s['node'])
            check(bus is not None, f'No local I2C for {s["physicalTag"]}')
            if bus:
                check(s['pins'] == [bus['scl'], bus['sda']], f'Wrong shared bus pins: {s["physicalTag"]}')
                check({'id': s['physicalTag'], 'address': s['i2cAddress']} in bus['devices'], f'Wrong I2C identity/address: {s["physicalTag"]}')
        else:
            check(len(s['pins']) == 1, f'Expected scalar signal: {s["physicalTag"]}')
            mode = f'ADC1_IN{s["adcChannel"]}' if s['interface'] == 'ADC' else 'GPIO_INPUT_POLL'
            claim(s['node'], s['pins'][0], s['physicalTag'], mode)
        if s['category'] == 'O2':
            check(s['powerDomain'] == 'PASSIVE_ELECTRODE_NO_EXTERNAL_POWER', 'Do not power bare AO-02')
            check(s['quality'] == 'RAW_ONLY_NOT_VALIDATED_OXYGEN_CONCENTRATION', 'AO-02 quality boundary lost')
    for station in EXPECTED_STATIONS:
        check({s['category'] for s in sensors if s['station'] == station} == {'MQ2', 'MQ4', 'CO', 'FLAME'},
              f'Incomplete four-sensor station: {station}')
    for node, ina_id in [('CTRL-04', 'INA226-FAN1'), ('CTRL-02', 'INA226-FAN2')]:
        check({'id': ina_id, 'address': 64} in buses[node]['devices'], f'INA crosses zone or wrong address: {ina_id}')
    all_bus_ids = [d['id'] for b in p['buses'] for d in b['devices']]
    check(len(all_bus_ids) == 6 and len(set(all_bus_ids)) == 6, 'Expected four SHT and two INA I2C devices')

    devices = p['devices']
    ids = [d['id'] for d in devices if d['id'] != 'RS485']
    check(len(ids) == len(ANCHORS) and set(ids) == set(ANCHORS), 'Device inventory differs')
    for d in devices:
        check(d['localZone'] == EXPECTED_POSITIONS.get(d['node']), f'Wrong device zone: {d["id"]}')
        if d['id'] in ANCHORS:
            check(d['node'] == ANCHORS[d['id']], f'Cross-zone device: {d["id"]}')
        for s in d['signals']:
            claim(d['node'], s['pin'], d['id'] + ':' + s['name'], s['mode'])
        if d['id'].startswith('SCREEN-'):
            check({s['name']: (s['pin'], s['mode']) for s in d['signals']} == SCREEN, f'Nonuniform screen: {d["id"]}')
            check('DISABLE_JTAG_RETAIN_SWD' in d['spiSetup'], 'Screen JTAG/SWD setup omitted')
    for node in claims:
        check(sum(d['id'] == 'RS485' and d['node'] == node for d in devices) == 1, f'Wrong RS485 count: {node}')
    for fan_id in ['FAN-01', 'FAN-02']:
        fan = next(d for d in devices if d['id'] == fan_id)
        check([(s['pin'], s['mode']) for s in fan['signals']] == [('PB8', 'TIM4_CH3'), ('PA7', 'EXTI7')], f'Fan pins changed: {fan_id}')
    for relay in [d for d in devices if d['id'].startswith('RELAY-')]:
        check([(s['pin'], s['mode']) for s in relay['signals']] == [('PA1', 'GPIO_OUT')], 'Relay pins changed')
    joystick = next(d for d in devices if d['id'] == 'JOYSTICK')
    check({s['name']: (s['pin'], s['mode']) for s in joystick['signals']} ==
          {'VRx': ('PC0', 'ADC1_IN10'), 'VRy': ('PC1', 'ADC1_IN11'), 'SW': ('PC4', 'GPIO_IN_PULLUP')}, 'Joystick mapping changed')
    dma_seen = set()
    dma_map = {'ADC1': 'DMA1_CH1', 'SPI3_TX': 'DMA2_CH2', 'SPI2_TX': 'DMA1_CH5'}
    expected_dma = {(n, 'ADC1') for n in claims} | {('CTRL-01', 'SPI3_TX'), ('CTRL-02', 'SPI3_TX'), ('CTRL-03', 'SPI2_TX')}
    check({(d['node'], d['request']) for d in p['dmaProposal']} == expected_dma, 'Missing/extra DMA request')
    for d in p['dmaProposal']:
        key = (d['node'], d['channel'])
        check(key not in dma_seen, f'DMA channel collision: {key}')
        check(d['channel'] == dma_map.get(d['request']), f'DMA map mismatch: {d}')
        dma_seen.add(key)
    check(p['rs485']['route'] == ['GW-01', 'CTRL-04', 'CTRL-03', 'CTRL-02', 'CTRL-01'], 'Wrong physical trunk route')
    check(p['rs485']['terminations'] == ['GW-01', 'CTRL-01'], 'Only actual endpoints may be terminated')
    check([p['rs485']['gateway'][k] for k in ('txGpio', 'rxGpio')] == [17, 18], 'Gateway UART candidates changed')
    check(p['powerBudget']['mqModuleCounts'] == {n: sum(s['category'] in {'MQ2', 'MQ4', 'CO'} for s in sensors if s['node'] == n) for n in claims}, 'Zone MQ power count differs')
    return {'date': p['date'], 'revision': p['revision'], 'static_resource_check': 'FAIL' if errors else 'PASS',
            'physical_modules': len(sensors), 'allocation': dict(sorted(counts.items())),
            'gpio_claims': {n: dict(sorted(v.items())) for n, v in sorted(claims.items())},
            'resource_summary': {n: {'allocated_gpio': len(claims[n]),
                'external_adc_channels': sum(s['node'] == n and s['interface'] == 'ADC' for s in sensors),
                'joystick_adc_channels': 2 if n == 'CTRL-02' else 0} for n in sorted(claims)},
            'errors': errors, 'firmware_built': False, 'hardware_verified': False,
            'locality': 'PASS_PHYSICAL_ZONE_OWNERSHIP_NOT_MEASURED_CABLE_LENGTHS' if not errors else 'NOT_PASSED',
            'warnings': [
                'Static design only; board variants, actual module pin labels, supply margins and electrical interfaces require bench checks.',
                'SCREEN-STATUS on CTRL-01 and SCREEN-MAIN on CTRL-02 require SPI3 and JTAG disabled with SWD retained.',
                'AO-02 remains unpowered raw-millivolt ADC; calibrated oxygen concentration is not validated.',
                'A shared two-channel relay PCB may require one longer harness; no new hardware has been assumed.',
                'USART1 interrupt/polling; USART2 interrupt initially; software I2C; digital sensor DO polling to avoid EXTI aliasing.',
                'The previous live database/model/MQTT identities have not been migrated; four-node firmware is not implemented.',
                'Local protection of P3/P5 cannot operate remote fans/buzzer when gateway coordination is absent.'
            ]}


def main():
    path = ROOT / 'wiring-plan.json'
    p = json.loads(path.read_text(encoding='utf-8'))
    report = validate(p)
    report['plan_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    (ROOT / 'validation-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: report[k] for k in ('static_resource_check', 'physical_modules', 'allocation', 'resource_summary', 'errors')}, ensure_ascii=False))
    return 0 if not report['errors'] else 1


if __name__ == '__main__':
    sys.exit(main())
