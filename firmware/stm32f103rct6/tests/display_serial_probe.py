"""Bench probe: python tests/display_serial_probe.py --port COM6 [--run]."""
import argparse
import re
import time
import serial

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
        assert int(fields['sysclk']) == 72000000, line
        assert int(fields['spi_hz']) == 18000000, line
        assert int(fields['dma_timeouts']) == 0, line
        if args.run:
            assert int(fields['dma_frames']) >= 1003, line
            assert 0 < int(fields['worst_frame_us']) <= 22000, line
        break
    else:
        raise AssertionError('No #DISPLAYTEST response (command absent or board unavailable)')
