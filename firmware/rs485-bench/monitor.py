"""Bounded read-only UART log capture; disables DTR/RTS before opening."""
import argparse
from pathlib import Path
import time
import serial

parser = argparse.ArgumentParser()
parser.add_argument('--port', required=True)
parser.add_argument('--seconds', type=float, default=15)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--stop-file', type=Path, help='Stop cleanly when this marker file appears.')
args = parser.parse_args()
if not 1 <= args.seconds <= 600:
    parser.error('Use a capture duration from 1 to 600 seconds; commands should yield while capturing.')
if args.output.exists():
    parser.error('Existing evidence retained; choose another output file.')
stream = serial.Serial(port=None, baudrate=115200, timeout=0.25)
stream.dtr = False
stream.rts = False
stream.port = args.port
with args.output.open('xb') as out:
    stream.open()
    try:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            if args.stop_file is not None and args.stop_file.exists():
                break
            data = stream.read(512)
            if data:
                out.write(data)
                out.flush()
                print(data.decode('utf-8', errors='replace'), end='', flush=True)
    finally:
        stream.close()
