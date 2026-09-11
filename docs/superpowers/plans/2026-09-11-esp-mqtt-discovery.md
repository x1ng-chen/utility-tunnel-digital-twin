# ESP MQTT Endpoint Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let CTRL-01 and CTRL-02 automatically discover and remember the laptop MQTT endpoint after hotspot address changes.

**Architecture:** The IoTDA gateway periodically emits a versioned UDP announcement. Each ESP validates the packet, uses its sender IP as the broker host, and persists the last successfully connected endpoint in EEPROM with a CRC.

**Tech Stack:** Node.js 22 `dgram`, Node test runner, ESP8266 Arduino/PlatformIO, `WiFiUDP`, `EEPROM`, PubSubClient.

**Spec:** `docs/superpowers/specs/2026-09-11-esp-mqtt-discovery-design.md`

## Global Constraints

- Advertise MQTT port `1884` and listen for discovery on UDP `4210`.
- Do not store Wi-Fi, MQTT, Huawei IAM, or IoTDA device secrets in tracked files.
- Preserve the existing telemetry queue and command topics.
- Build both `esp01_ctrl01` and `esp01_ctrl02`.

---

### Task 1: Gateway UDP broadcaster

**Files:**
- Create: `services/iotda-gateway/src/discovery.js`
- Create: `services/iotda-gateway/test/discovery.test.js`
- Modify: `services/iotda-gateway/src/index.js`
- Modify: `services/iotda-gateway/src/config.js` if configuration extraction is needed

**Interfaces:**
- Produces: `buildDiscoveryPacket({ serviceName, mqttPort })` and `startDiscoveryBroadcaster(options)`.
- Consumes: validated MQTT public port and optional injected network/socket functions for deterministic tests.

- [ ] Write failing tests for exact packet encoding, invalid ports, directed broadcast addresses, periodic send, and close.
- [ ] Run `node --test test/discovery.test.js` and confirm failures are caused by the missing implementation.
- [ ] Implement the minimal broadcaster using `dgram` and `os.networkInterfaces()`.
- [ ] Start it from `src/index.js` and close it in the existing shutdown path.
- [ ] Run `npm test` and require zero failures.

### Task 2: ESP discovery protocol and persistent endpoint

**Files:**
- Create: `firmware/esp8266-01s/include/mqtt_discovery.h`
- Create: `firmware/esp8266-01s/test/test_mqtt_discovery/test_main.cpp`
- Modify: `firmware/esp8266-01s/src/main.cpp`
- Modify: `firmware/esp8266-01s/include/secrets.example.h`

**Interfaces:**
- Produces: packet parser, CRC-validated `BrokerEndpoint`, EEPROM load/save helpers, and runtime endpoint switching.
- Consumes: UDP sender IPv4 address plus `UT-MQTT-DISCOVERY/1|utility-tunnel|PORT` payload.

- [ ] Write failing native tests for valid packets, wrong versions/services, malformed ports, CRC rejection, and unchanged-endpoint detection.
- [ ] Run the focused PlatformIO native test and confirm the expected failure.
- [ ] Implement the pure parser/config helpers without Wi-Fi dependencies.
- [ ] Integrate `WiFiUDP` listener, saved-endpoint startup, successful-connect persistence, and endpoint switching in `main.cpp`.
- [ ] Remove `MQTT_HOST` from the example and local untracked secrets contract.
- [ ] Run the focused tests and build both ESP environments.

### Task 3: End-to-end bench verification

**Files:**
- Modify: `services/local-mqtt/README.md`
- Modify: `firmware/esp8266-01s/README.md` if present

**Interfaces:**
- Consumes: discovery broadcaster and compiled CTRL-01 image.
- Produces: reproducible start/flash/status instructions.

- [ ] Start Mosquitto and the gateway, then verify UDP announcements on the current hotspot interface.
- [ ] Flash CTRL-01 and restore normal boot.
- [ ] Verify serial reports the discovered current laptop IP, `mqtt=up`, and command subscription.
- [ ] Publish a status command and require an STM32 command ACK.
- [ ] Document startup and recovery behavior, then run the full gateway tests and both ESP builds again.

