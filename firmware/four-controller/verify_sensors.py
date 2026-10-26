"""实时显示四主控网关输出中某一板的 11 路传感器。

用法：
    python firmware/four-controller/verify_sensors.py --port COM8 --board 1

脚本只读取 S3 网关的 USB 串口，不占用 485 总线；按 Ctrl+C 退出。
"""
import argparse
import json
import re
import sys
import time

import serial

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

STATUS = {0: "ok", 1: "missing", 2: "suspect"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--board", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--seconds", type=float, default=0,
                        help="采集时长；0 表示一直运行到 Ctrl+C")
    args = parser.parse_args()

    stream = serial.Serial()
    stream.port = args.port
    stream.baudrate = 115200
    stream.timeout = 0.3
    stream.dtr = False
    stream.rts = False
    stream.open()

    deadline = time.time() + args.seconds if args.seconds > 0 else None
    buffer = ""
    print(f"Listening on {args.port}, board {args.board} only. Ctrl+C to stop.\n")
    try:
        while True:
            if deadline is not None and time.time() >= deadline:
                break
            data = stream.read(512)
            if not data:
                continue
            buffer += data.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("board") != args.board:
                    continue
                if "error" in event:
                    print(f"[{time.strftime('%H:%M:%S')}] board {args.board} error: {event['error']}")
                    continue
                parts = []
                for slot in event.get("slots", []):
                    sid = slot["id"]
                    tag = TAGS.get(sid, f"ID{sid}")
                    status = STATUS.get(slot["s"], str(slot["s"]))
                    extra = f"/{slot['a']}" if slot["a"] else ""
                    mark = "" if slot["s"] == 0 else f"[{status}]"
                    parts.append(f"{tag}={slot['v']}{extra}{mark}")
                print(f"[{time.strftime('%H:%M:%S')}] seq={event.get('seq')}  " + "  ".join(parts))
    except KeyboardInterrupt:
        pass
    finally:
        stream.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
