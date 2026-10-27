"""显示指定控制器的网关遥测；兼容新版 readings 与旧 slots。

用法：
    python firmware/four-controller/verify_sensors.py --port COM8 --board 1

脚本只读取 S3 网关的 USB 串口，不占用 485 总线；按 Ctrl+C 退出。
"""
import argparse
import json
import sys
import time


TAGS = {
    1: "MQ2-01", 2: "MQ4-01", 3: "CO-01", 4: "FLAME-01",
    5: "MQ2-02", 6: "MQ4-02", 7: "CO-02", 8: "FLAME-02",
    9: "MQ2-03", 10: "MQ4-03", 11: "CO-03", 12: "FLAME-03",
    13: "MQ2-04", 14: "MQ4-04", 15: "CO-04", 16: "FLAME-04",
    17: "MQ2-05", 18: "MQ4-05", 19: "CO-05", 20: "FLAME-05",
    21: "SHT-01", 22: "SHT-02", 23: "SHT-03", 24: "SHT-04",
    25: "LEVEL-01", 26: "LEVEL-02", 27: "LEVEL-03", 28: "LEVEL-04",
    29: "O2-01", 30: "O2-02", 31: "O2-03",
}

STATUS = {0: "ok", 1: "missing", 2: "suspect", 3: "observed-event-held"}


def summarize(event, board):
    if not isinstance(event, dict):
        return None
    if event.get('schema') == 'ut.telemetry.v1':
        if event.get('controllerId') != f'CTRL-0{board}':
            return None
        rows = event.get('readings')
        if not isinstance(rows, list):
            return None
        parts = []
        for row in rows:
            if not isinstance(row, dict):
                return None
            value = row.get('value') if row.get('quality') != 'missing' else '--'
            kind = ' [OBSERVED EVENT, NOT CURRENT LEVEL]' if row.get('eventLatched') else ''
            parts.append(f"{row.get('assetCode')}/{row.get('metric')}={value}{row.get('unit')} [{row.get('quality')}] age={row.get('sampleAgeMs')}ms{kind}")
        return f"seq={event.get('seq')} source={event.get('clockSource')}  " + '  '.join(parts)
    if event.get('board') != board:
        return None
    if 'error' in event:
        return f"board {board} error: {event['error']}"
    if 'slots' not in event:
        return None
    parts = []
    for slot in event.get('slots', []):
        sid = slot['id'];status = STATUS.get(slot['s'], str(slot['s']))
        extra = f"/{slot['a']}" if slot['a'] else ''
        parts.append(f"{TAGS.get(sid, f'ID{sid}')}={slot['v']}{extra}[{status}]")
    return f"seq={event.get('seq')} legacy slots  " + '  '.join(parts)



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--board", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--seconds", type=float, default=0,
                        help="采集时长；0 表示一直运行到 Ctrl+C")
    args = parser.parse_args()

    import serial  # Optional dependency is only needed for the explicitly requested port.
    stream = serial.Serial()
    stream.port = args.port
    stream.baudrate = 115200
    stream.timeout = 0.3
    stream.dtr = False
    stream.rts = False
    stream.open()

    deadline = time.monotonic() + args.seconds if args.seconds > 0 else None
    buffer = ""
    print(f"Listening on {args.port}, board {args.board} only. Ctrl+C to stop.\n")
    try:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                break
            data = stream.read(512)
            if not data:
                continue
            buffer += data.decode("utf-8", errors="replace")
            if len(buffer) > 16384:  # Reset an unterminated/noisy diagnostic line.
                buffer = ""
                continue
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = summarize(event, args.board)
                if text:
                    print(f"[{time.strftime('%H:%M:%S')}] {text}")
    except KeyboardInterrupt:
        pass
    finally:
        stream.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
