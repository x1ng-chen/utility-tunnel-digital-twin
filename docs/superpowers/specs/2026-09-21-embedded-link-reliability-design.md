# Embedded Link Reliability Design

## Goal

Restore a coherent, fail-safe chain from the local gateway through both ESP8266 bridges to STM32 Node A/Node B, while keeping the display responsive and making reported connectivity match command availability.

## Protocol and security

MQTT discovery uses only `UT-MQTT-DISCOVERY/2`. The gateway signs the exact ASCII prefix through the final separator with HMAC-SHA256; the ESP verifies it in constant work before accepting the sender address. Discovery is enabled only when the same non-empty deployment key is configured on both sides. Persisted unsigned endpoints remain invalidated by storage version 2.

## Scheduling and safety

Node A gas safety sampling runs every 200 ms independently of the slow SHT30 and INA226 telemetry path. Cooperative wait loops service the gas sampler as well as communications. MQ-4 methane protection is enabled for the commissioned prototype channel; oxygen and CO remain telemetry-only until calibrated, and this state is explicit in configuration.

## Queues and connectivity

Both ESP roles enqueue MQTT downlinks and drain UART in bounded chunks outside MQTT callbacks. Command acknowledgements have priority over state and telemetry. Telemetry is latest-value data and may be replaced under pressure; command or acknowledgement frames are not silently overwritten.

Node B derives the displayed link state and command availability from the same six-second heartbeat lease. Negative evidence expires the lease instead of leaving controls active for sixty seconds.

## Gateway failure handling

The serial gateway reconnects after close/error, applies request timeouts, and bounds its work queue. The Django forwarding lane dead-letters permanent failures and items that exceed a retry-count or age budget so one poison item cannot block the queue forever.

## Verification

Cross-language discovery vectors, ESP routing/queue tests, STM32 contract and host tests, Node gateway tests, and production firmware builds must pass before any firmware is offered for flashing.
