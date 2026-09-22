# Embedded Link Reliability Implementation Plan

**Spec:** `docs/superpowers/specs/2026-09-21-embedded-link-reliability-design.md`

## Global constraints

- Preserve unrelated worktree changes.
- Use regression tests before implementation changes.
- Do not flash hardware until all applicable builds and tests pass.
- Never commit deployment secrets.

## Task 1: Make MQTT discovery V2 interoperable

Update gateway tests to require a keyed V2 packet and rejection of missing keys. Implement HMAC packet generation, configuration validation, documentation, and matching ESP vectors. Verify gateway tests and both ESP builds.

## Task 2: Make ESP UART bridging non-blocking and priority aware

Add tests for queued CTRL-01 downlinks and schema parsing independent of JSON spacing/order. Route callbacks only into bounded queues and report drops. Verify native routing tests and both ESP builds.

## Task 3: Bound link-state staleness on Node B

Add a contract test for a six-second authoritative lease. Make display state and control availability expire together while retaining positive-heartbeat renewal. Verify Node B contracts and build.

## Task 4: Keep Node A gas safety responsive

Add a contract test proving gas service is called from cooperative waits as well as the main loop. Enable the commissioned methane channel only; keep uncalibrated channels explicit. Verify safety tests and Node A build.

## Task 5: Prevent gateway poison-item and reconnect stalls

Add Node tests for bounded permanent-error retries, HTTP timeout behavior, serial close/error reconnect, and bounded queueing. Implement the minimum state-machine changes and run both gateway suites.

## Task 6: Whole-chain verification and cleanup

Run all relevant host tests, Node tests, frontend targeted tests, ESP builds, STM32 builds, and `git diff --check`. Review the final diff for protocol mismatches, unsafe defaults, blocking callbacks, and stale connectivity semantics.
