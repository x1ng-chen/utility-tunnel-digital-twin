"""Execute actual portable firmware headers, natively or as ARM machine code.

No serial connection, flashing, GPIO, HAL peripherals, or paid model calls.
ARM mode needs arm-none-eabi-gcc/g++, pyelftools, and unicorn. The ELF loader
initializes PT_LOAD segments and calls test_entry directly; it is not a full
STM32/system timing simulation.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def run(command, log):
    result = subprocess.run([str(x) for x in command], cwd=ROOT, text=True, capture_output=True)
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}), see {log}: {result.stderr[-3000:]}")
    return result.stdout


def emulate(path):
    from elftools.elf.elffile import ELFFile
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
    from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(0x8000, 0x1000)
    uc.mem_map(0x10000, 0x100000)
    uc.mem_map(0x20000000, 0x80000)
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        for segment in elf.iter_segments():
            if segment["p_type"] == "PT_LOAD":
                uc.mem_write(int(segment["p_vaddr"]), segment.data())
        symbols = elf.get_section_by_name(".symtab")
        entry = int(symbols.get_symbol_by_name("test_entry")[0]["st_value"])
        result_address = int(symbols.get_symbol_by_name("ut_test_results")[0]["st_value"])
        fixtures = symbols.get_symbol_by_name("ut_fixture_json")
    uc.reg_write(UC_ARM_REG_SP, 0x2007FFF0)
    uc.reg_write(UC_ARM_REG_LR, 0x8001)
    uc.emu_start(entry | 1, 0x8000, count=100_000_000)
    checks, failures, first, groups, done = struct.unpack("<5I", uc.mem_read(result_address, 20))
    if done != 0x5554 or uc.reg_read(UC_ARM_REG_PC) != 0x8000:
        raise RuntimeError("ARM test did not finish inside the instruction budget.")
    if fixtures:
        address = int(fixtures[0]["st_value"])
        frames = [json.loads(bytes(uc.mem_read(address + i * 4096, 4096)).split(b"\0")[0]) for i in range(4)]
        (path.parent / "gateway-fixtures.json").write_text(json.dumps(frames, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"checks": checks, "failures": failures, "firstLine": first, "groups": groups}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--native", action="store_true")
    mode.add_argument("--arm-emulated", action="store_true")
    parser.add_argument("--json-include", type=Path, default=ROOT / "firmware/four-controller/gateway/.pio/libdeps/s3_four_gateway/ArduinoJson/src")
    parser.add_argument("--dependency-dir", type=Path, default=ROOT / ".agent-eval/firmware-native-tools")
    parser.add_argument("--output", type=Path, default=ROOT / ".agent-eval/firmware-fix/core-test-results.json")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.json_include = args.json_include.resolve()
    if not (args.json_include / "ArduinoJson.h").exists():
        raise RuntimeError("ArduinoJson header not found; build the pinned gateway environment first.")
    if args.arm_emulated:
        sys.path.insert(0, str(args.dependency_dir.resolve()))
    records = []
    for name, filename, language in (("core", "test_core.c", "c"), ("command_json", "test_command_json.cpp", "c++"), ("telemetry", "test_telemetry.cpp", "c++")):
        compiler_name = ("arm-none-eabi-" if args.arm_emulated else "") + ("g++" if language == "c++" else "gcc")
        compiler = shutil.which(compiler_name)
        if not compiler:
            raise RuntimeError(f"{compiler_name} is unavailable.")
        target = args.output.parent / (name + (".elf" if args.arm_emulated else (".exe" if sys.platform == "win32" else ".native")))
        command = [compiler, "-std=" + ("c++17" if language == "c++" else "c11"), "-Os", "-g", "-Wall", "-Wextra", "-Werror",
                   "-ffunction-sections", "-fdata-sections", "-I", args.json_include, HERE / filename, "-o", target]
        if language == "c++":
            command += ["-fno-exceptions", "-fno-rtti", "-DARDUINOJSON_ENABLE_STD_STRING=0", "-DARDUINOJSON_ENABLE_STD_STREAM=0"]
        if args.arm_emulated:
            command += ["-mcpu=cortex-m3", "-mthumb", "-DUT_TEST_EMULATED=1", "-nostartfiles",
                        "--specs=nano.specs", "--specs=nosys.specs", "-Wl,--gc-sections", "-Wl,-T," + str(HERE / "arm-test.ld")]
        run(command, args.output.parent / f"compile-{name}.log")
        result = emulate(target) if args.arm_emulated else json.loads(run([target], args.output.parent / f"run-{name}.log"))
        result.update(suite=name, executable=str(target.relative_to(ROOT)), sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        records.append(result)
        print(json.dumps(result))
    source_paths = [
        HERE / "test_core.c", HERE / "test_command_json.cpp", HERE / "test_telemetry.cpp", HERE / "test_support.h",
        HERE.parent / "common/protocol.h", HERE.parent / "common/interaction.h",
        HERE.parent / "common/digital.h", HERE.parent / "common/measurements.h", HERE.parent / "common/snapshot.h",
        HERE.parent / "gateway/include/command_json.h", HERE.parent / "gateway/include/command_ledger.h", HERE.parent / "gateway/include/telemetry_encode.h", HERE.parent / "gateway/include/device_map.h",
    ]
    report = {
        "mode": "ARM machine-code emulation (portable logic only)" if args.arm_emulated else "native machine code",
        "executedAt": datetime.now(timezone.utc).isoformat(),
        "hardwareExecuted": False,
        "suites": records,
        "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
        "limitations": ["No HAL peripheral execution or electrical/timing proof.", "Synthetic sampled input cannot recover an unobserved pulse."],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return int(any(r["failures"] for r in records))


if __name__ == "__main__":
    raise SystemExit(main())
