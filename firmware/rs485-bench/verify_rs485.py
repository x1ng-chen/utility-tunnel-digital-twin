"""Read the S3 diagnostic log and summarise per-slave RS485_OK/FAIL counts.

Examples:
    python firmware/rs485-bench/verify_rs485.py --port COM8 --seconds 30
    python firmware/rs485-bench/verify_rs485.py --port COM8 --seconds 30 --expect 4
    python firmware/rs485-bench/verify_rs485.py --port COM8 --seconds 30 --expect 4,3

--expect lists the slaves that should answer in the current topology. Slaves not
listed are reported but do not affect the exit status. Exit code 0 means every
expected slave reached --min-ok successes with zero failures.
"""
import argparse
import re
import sys
import time

import serial


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', required=True)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--min-ok', type=int, default=30)
    parser.add_argument('--expect', default='',
                        help='Comma-separated slave numbers that must pass, e.g. 4 or 4,3')
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        parser.error('Use 1 to 600 seconds.')

    expected = {int(x) for x in args.expect.split(',') if x.strip()}
    stats = {}
    opened = serial.Serial()
    opened.port = args.port
    opened.baudrate = 115200
    opened.timeout = 0.2
    opened.dtr = False   # Never reset the ESP32 just by opening the port.
    opened.rts = False
    opened.open()

    buffer = ''
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline:
            data = opened.read(512)
            if data:
                buffer += data.decode('utf-8', errors='replace')
    finally:
        opened.close()

    lines = 0
    for line in buffer.splitlines():
        match = re.search(r'RS485_(OK|FAIL) poll=(\d+) slave=(\d+)', line)
        if not match:
            continue
        lines += 1
        slave = int(match.group(3))
        entry = stats.setdefault(slave, {'ok': 0, 'fail': 0, 'timeout': 0, 'malformed': 0})
        if match.group(1) == 'OK':
            entry['ok'] += 1
        else:
            entry['fail'] += 1
            if 'rx_bytes=0' in line:
                entry['timeout'] += 1
            else:
                entry['malformed'] += 1

    print(f'Captured {lines} poll results in {args.seconds:g}s on {args.port}')
    if not stats:
        print('No RS485_OK/RS485_FAIL lines found. Check the port, baud rate and that the S3 is running.')
        return 2

    for slave in sorted(stats):
        entry = stats[slave]
        flag = ''
        if slave in expected:
            flag = '  PASS' if entry['ok'] >= args.min_ok and entry['fail'] == 0 else '  FAIL'
        print(f"slave {slave}: OK={entry['ok']:3d}  FAIL={entry['fail']:3d}  "
              f"timeout={entry['timeout']:3d}  malformed={entry['malformed']:3d}{flag}")

    if not expected:
        print('No --expect given; reporting only, no pass/fail decision.')
        return 0

    failures = []
    for slave in sorted(expected):
        entry = stats.get(slave)
        if entry is None:
            failures.append(f'slave {slave}: no data')
        elif entry['fail']:
            failures.append(f"slave {slave}: {entry['fail']} failures")
        elif entry['ok'] < args.min_ok:
            failures.append(f"slave {slave}: only {entry['ok']} successes, need {args.min_ok}")
    if failures:
        print('RESULT: FAIL')
        for item in failures:
            print('  -', item)
        return 1
    print('RESULT: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
