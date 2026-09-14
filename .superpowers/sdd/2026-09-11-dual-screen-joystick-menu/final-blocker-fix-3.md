# Final blocker fix 3 — transactional telemetry rotation and ACK reserve

This report covers the final telemetry blockers found after commit `6da4b58`
on `feature/dual-screen-joystick-menu`.  The changes are intentionally limited
to the Node A telemetry/diagnostic path, the shared bounded UART queue, and the
host/probe contracts that exercise those paths.  Nothing was pushed, merged, or
flashed.  All verification below is host/build verification; no physical or
bench result is claimed.

## Root causes and fixes

### Critical: a refused ESP frame advanced the rotation

`NodeATelemetry_FormatFrame` used to take `uint32_t *sequence` and increment it
before `Telemetry_EmitOneFrame` attempted `UartTx_Enqueue(&esp_tx_queue, ...)`.
When the bounded queue refused the frame, the caller returned without restoring
the cursor.  The next interval therefore emitted the following slot and the
state-carrying frame was skipped.  The old throughput test copied the cursor to
`candidate_sequence`; that made the test pass while avoiding the production
failure mode.

The API now separates formatting from committing transport state:

* `NodeATelemetry_FormatFrame(sequence, ...)` is pure and formats the fixed slot
  `(sequence - 1) % NODE_A_TELEMETRY_FRAME_COUNT`.
* `NodeATelemetry_QueueNext` formats `*sequence + 1`, calls a bounded enqueue
  callback, and writes the cursor only when that callback returns accepted.
* `NodeATelemetry_QueueFullRotation` is a retryable six-slot request; it stops
  at the first refusal and leaves the cursor parked there.
* Node A's `Telemetry_EnqueueBoth` enqueues ESP first.  ESP is the commit point;
  the debug mirror is best-effort and cannot move the cursor or block the loop.
  Queue and state refusal counters remain observable.

`Telemetry_EmitOneFrame` and `SendTelemetryFullRotation` both use this helper.
The throughput test now calls `NodeATelemetry_QueueNext` with the queue callback
instead of reproducing candidate/copy/commit logic.  Its refusal test fills the
real queue, captures the refused bytes, checks that the cursor is unchanged,
then retries through the same helper and compares the accepted bytes.

### Important 1: `#NODETEST TELEMETRY` consumed the wrong unit

The command used to set `test_telemetry_burst` to six even though one call to
`SendTelemetryFullRotation` already attempted six frames.  The main loop then
decremented the value once per call, including after a partial failure.  A
failed request could therefore consume the test while leaving a partial
rotation.

The command now arms exactly one complete rotation request (`1U`).  The main
loop decrements it and updates `last_telemetry` only when
`SendTelemetryFullRotation` reports that all six frames were accepted.  A
refusal leaves the request armed and the cursor at the refused slot for a
non-blocking retry on the next loop pass.  The new
`test_full_rotation_is_retryable_as_one_request` test covers a later-slot
refusal and a complete retry.

### Important 2: ACK reserve was only a static assertion

`NODE_A_UART_ACK_RESERVE_BYTES` was asserted against the physical capacity but
ordinary output could still fill all 3072 bytes.  ACK and diagnostic enqueue
returns were also discarded.

`UartTx_InitWithReserve` now records a runtime reserve.  Ordinary
`UartTx_Enqueue` admission is capped at `capacity - reserved_bytes`; it can
never consume the reserve.  `UartTx_EnqueuePriority` is still whole-frame and
non-blocking, but may use the physical capacity including the reserve.  Priority
refusals are counted separately (`priority_dropped_*`).  Node A initializes both
UART queues with the 350-byte reserve, routes command ACKs through the priority
path, and exposes ACK/state/ESP/debug enqueue failures in `#STATE` diagnostics.
The authoritative ESP ACK result is checked immediately; no retry loop or
infinite wait was introduced.

`test_dual_queue_ack_and_diagnostics_compete` exercises both queues together:
the production-shaped telemetry callback commits only after ESP acceptance,
normal diagnostics fill only the ordinary portion, the next telemetry frame is
refused with the sequence unchanged, and a priority ACK still fits in each
reserve.  `uart_tx_queue_host_test` separately proves ordinary admission and
bounded priority refusal accounting.

### Important 3: the probe waited for a line Node A did not emit

After `#NODETEST CMD`, the probe read an ACK and then waited for `#STATE`, but
the firmware command branch returned after `Command_ProcessPayload` and emitted
no state line.  The branch now reports state after every accepted, rejected,
expired, malformed, or duplicate command, so the serial contract is explicit
and consistent.  The state report remains an ordinary bounded diagnostic line;
its enqueue failure is counted rather than allowed to block command handling.

### Important 4: the probe accepted skipped/mislabelled rotations

The probe previously checked only distinct sorted sequence values and a handful
of aggregate readings.  It now requires six integer sequences in exact
contiguous order and checks the complete fixed `(assetCode, metric)` signature
for the slot selected by each sequence:

```
1 ENV/GAS environment       2 FAN-01 electrical/diagnostic
3 FAN-02 electrical/diagnostic
4 gas alarm/status           5 gas raw evidence
6 CTRL-01 LED/buzzer
```

The host validator fixtures reject a sequence gap, out-of-order frame, wrong
asset/metric mapping, shared sequence, missing slot, and duplicate reading.

### Important 5: the throughput model ignored its `blocked_ms` argument

`test_a_tighter_interval_still_delivers_exactly` set `blocked_ms = 800`, but
`run_cycles` hard-coded the old 400 ms value.  The scheduler helper now accepts
and uses the duration supplied by each test.  The virtual drain also caps each
batch by the bytes remaining in the current interval, so a batch cannot charge
wire time beyond the interval boundary.  A dedicated boundary test catches a
1300 ms block that leaves fewer bytes than the widest frame.

## Strict TDD record

Each new production-path assertion was made to fail before its implementation
was added, then the smallest implementation was applied and the same command
was rerun.  The following are the recorded RED/GREEN checkpoints (all commands
were run from `firmware/stm32f103rct6` in this worktree).

| Checkpoint | RED command and failure | GREEN command and result |
|---|---|---|
| Transactional `QueueNext` path and real refusal | `bash tests/run_node_a_telemetry_throughput_host.sh` after the host test called the not-yet-existing helper: compile failed on the missing `NodeATelemetry_QueueNext` API (the old candidate-copy path was still present). | `bash tests/run_node_a_telemetry_throughput_host.sh` — `node_a_telemetry_throughput_host_test: ok`. |
| Retryable full rotation | The same throughput command after adding the six-frame request test: compile failed because `NodeATelemetry_QueueFullRotation` did not yet exist. | The same command — `ok`; a later-slot refusal parks at sequence 5 and the retry completes at sequence 11. |
| Runtime reserve and priority enqueue | `bash tests/run_uart_tx_queue_host.sh` after adding reserve/priority tests: compile failed because `UartTxQueue` had no reserve/counters and the new init/priority APIs were absent. | `bash tests/run_uart_tx_queue_host.sh` — `uart_tx_queue_host_test: ok`. |
| `blocked_ms` reaches the scheduler | `bash tests/run_node_a_telemetry_throughput_host.sh` after wiring the 800 ms argument but before interval-boundary capping: the 1300 ms boundary assertion failed because a fixed drain batch overshot the remaining interval. | The same command — `ok`; the drain is capped by remaining wire time. |
| Dual-queue reserve/diagnostic competition | `bash tests/run_node_a_telemetry_throughput_host.sh` with the new two-queue reserve test against the old queue semantics: ordinary diagnostics consumed bytes from the ACK space / priority admission was unavailable, so the reserve assertions failed. | The same command — `ok`; ordinary output stops at the ordinary limit, telemetry refusal leaves sequence unchanged, and priority ACKs fit. |
| Probe contiguous sequence and slot mapping | `bash tests/run_node_a_command_probe_host.sh` after adding rejected gap/mapping fixtures but before validator changes: it failed with `accepted a rotation with a sequence gap`. | The same command — `Node A command probe validator: PASS`. |
| `#NODETEST TELEMETRY` and `#STATE` source contract | `bash tests/run_node_a_command_probe_host.sh` after adding the source assertions against the old firmware: assertions failed because the command still armed six, did not gate decrement on full-rotation success, omitted runtime reserve setup, and returned without `NodeTest_ReportState`. | The same command — `PASS`; the forced request is one success-gated rotation and CMD is ACK + state. |

The former throughput test's `candidate_sequence` copy was removed rather than
updated; all refusal/commit assertions now drive `NodeATelemetry_QueueNext`, the
same helper used by production.

## Verification

The final verification was run after the implementation and report edits.  The
STM32 host scripts all passed, including the original regression and mutation
gates:

```
bash ./tests/run_display_host.sh
bash ./tests/run_node_a_clock_host.sh
bash ./tests/run_node_a_command_host.sh
bash ./tests/run_node_a_command_probe_host.sh
bash ./tests/run_node_a_display_mutation_check.sh       # 18/18 caught
bash ./tests/run_node_a_mutation_check.sh                # 34/34 caught
bash ./tests/run_node_a_status_host.sh
bash ./tests/run_node_a_telemetry_host.sh
bash ./tests/run_node_a_telemetry_throughput_host.sh
bash ./tests/run_task8_host.sh
bash ./tests/run_uart_tx_queue_host.sh
bash ./tests/run_ui_renderer_host.sh
```

The unchanged regression suites cover the previously fixed contracts, including
0..100 telemetry values (fan duty 45 and LED brightness 60), the strict menu
ladder, and C1-C3/I1-I5 display/clock/safety behavior.

The strict ARM contract passed with the installed ARM GNU toolchain:

```
bash -c 'export ARM_GCC="/mnt/c/Program Files (x86)/Arm GNU Toolchain arm-none-eabi/12.2 mpacbti-rel1/bin/arm-none-eabi-gcc.exe"; exec ./tests/run_node_a_contract_arm.sh'
Node A ARM clock/pin contract test: PASS
```

Both STM32 firmware variants configured and linked successfully:

```
cmake --preset NodeA --fresh
cmake --build --preset NodeA
# RAM 11984 B / 49152 B; FLASH 55636 B / 262144 B

cmake --preset NodeB --fresh
cmake --build --preset NodeB
# RAM 11296 B / 49152 B; FLASH 69552 B / 262144 B
```

The ESP suites and PlatformIO images also passed:

```
cd firmware/esp8266-01s
bash ./test/run_native_host_tests.sh
# screen_protocol tests passed; screen_routing tests passed; native host suites: ok
python -m platformio run -e esp01_ctrl01 -e esp01_ctrl02
# 2 succeeded
```

Finally, `git diff --check` reported no whitespace errors.  Host-script
temporary directories were self-cleaned; the generated Python `__pycache__`
was removed.  The only remaining ignored build directories are normal CMake/
PlatformIO build outputs and do not enter the commit.

## Commit and validation boundary

The final change is one focused commit on `feature/dual-screen-joystick-menu`:

```
the branch tip containing this report (the exact hash is returned in the task
hand-off)
```

No push, merge, or flash was performed.  This report does not claim that a
serial probe was run against a physical Node A, that a display/ESP/STM32 board
was powered, or that any bench behavior was verified.  Those remain separate
physical validation steps.
