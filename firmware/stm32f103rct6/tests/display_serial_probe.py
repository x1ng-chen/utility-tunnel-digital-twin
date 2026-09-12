"""Bench probe: python tests/display_serial_probe.py --port COM6 [--run]."""
import argparse
import re
import time
import serial


def validate_display_stats(fields, run):
    assert int(fields['sysclk']) == 72000000
    assert int(fields['spi_hz']) == 18000000
    assert int(fields['dma_timeouts']) == 0
    assert int(fields['dma_errors']) == 0
    if run:
        assert int(fields['dma_frames']) == 1003
        assert 0 < int(fields['worst_frame_us']) <= 22000


parser = argparse.ArgumentParser()
parser.add_argument('--port', required=True)
parser.add_argument('--run', action='store_true')
args = parser.parse_args()
with serial.Serial(args.port, 9600, timeout=0.2) as port:
    port.reset_input_buffer()
    port.write(b'#DISPLAYTEST RUN\n' if args.run else b'#DISPLAYTEST\n')
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        line = port.readline().decode('ascii', errors='replace').strip()
        if not line.startswith('#DISPLAY '):
            continue
        print(line)
        fields = dict(re.findall(r'(\w+)=(\d+)', line))
        try:
            validate_display_stats(fields, args.run)
        except (AssertionError, KeyError, ValueError) as error:
            raise AssertionError(line) from error
        break
    else:
        raise AssertionError('No #DISPLAYTEST response (command absent or board unavailable)')
