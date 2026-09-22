from pathlib import Path


source = Path("src/index.js").read_text(encoding="utf-8")

assert "AbortSignal.timeout(config.API_TIMEOUT_MS)" in source
assert "SERIAL_QUEUE_MAX" in source
assert "port.on('close'" in source
assert "scheduleOpen();" in source
assert "COM10 is not ready" not in source

print("Serial gateway reliability contract: PASS")
