#include <Arduino.h>
#include <cstring>
#include <EEPROM.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <WiFiUdp.h>
#include <sys/time.h>
#include <time.h>

#include "mqtt_discovery.h"
#include "network_client_config.h"
#include "screen_routing.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#define WIFI_SSID "replace-me"
#define WIFI_PASSWORD "replace-me"
#define MQTT_USERNAME ""
#define MQTT_PASSWORD ""
#endif

/* Discovery advertisements are only trusted when they carry a valid HMAC for
 * this deployment's key.  An empty key disables discovery entirely (the saved
 * broker endpoint still works) instead of silently accepting unsigned packets. */
#ifndef DISCOVERY_HMAC_KEY
#define DISCOVERY_HMAC_KEY ""
#endif

#ifndef BUILD_DEVICE_ID
#define BUILD_DEVICE_ID "CTRL-01"
#endif

namespace {
// Match the STM32 USART2 configuration in led_blink.ioc.
constexpr uint32_t kSerialBaud = 9600;
constexpr uint32_t kReconnectIntervalMs = 2000;
constexpr uint32_t kWiFiConnectTimeoutMs = 30000;
constexpr uint32_t kWiFiTransientGraceMs = 10000;
constexpr uint32_t kWiFiHardRecoveryMs = 60000;
constexpr uint32_t kLinkHeartbeatIntervalMs = 2000;
// Preserve the bench-tested long telemetry path. Screen protocol frames remain
// independently capped at screen_protocol::kUartLineLimit (768 bytes).
constexpr size_t kMaxSerialFrame = 1024;
constexpr uint16_t kMqttBufferSize = 1280;
constexpr uint8_t kPendingFrameCapacity = 8;
constexpr uint8_t kLedPin = 2;
constexpr uint16_t kDiscoveryPort = 4210;
/* v2 layout: "UT-MQTT-DISCOVERY/2|utility-tunnel|" (35) + port digits (<=5)
 * + '|' + 64 hex signature characters. */
constexpr size_t kMaxDiscoveryPacket = 112;
/* Node A's ESP_RX_LINE_SIZE is 384 bytes including the line's NUL terminator,
 * so the longest bridge-to-Node-A line is 383 characters: "MQTT|" + topic +
 * '|' + payload.  Enforcing it here keeps a lawful MQTT payload from being
 * silently truncated mid-frame by the STM32 receive ISR. */
#if !defined(BUILD_ROLE_CTRL02)
constexpr size_t kMaxDownlinkLine = 383U;
#endif

WiFiClient networkClient;
WiFiUDP discoveryUdp;
PubSubClient mqtt(networkClient);
char serialFrame[kMaxSerialFrame + 1U] = {};
size_t serialFrameLength = 0U;
/* An oversized frame must die whole.  Resetting only the length (the old
 * behaviour) let the bytes past the cap masquerade as a fresh line once a '\n'
 * arrived; while this flag is set, everything up to the next newline is
 * dropped instead of parsed. */
bool serialFrameDiscarding = false;
String statusTopic;
String telemetryTopic;
#if !defined(BUILD_ROLE_CTRL02)
String commandAckTopic;
#endif
char pendingFrames[kPendingFrameCapacity][kMaxSerialFrame + 1] = {};
enum class PendingKind : uint8_t { Telemetry = 0, CommandAck, MenuCommand };
PendingKind pendingFrameKinds[kPendingFrameCapacity] = {};
uint8_t pendingHead = 0;
uint8_t pendingCount = 0;
uint32_t lastWiFiAttempt = 0;
uint32_t lastMqttAttempt = 0;
uint32_t wifiDownSinceMs = 0;
uint32_t lastWiFiHardRecoveryMs = 0;
bool wifiStarted = false;
bool missingSecretsReported = false;
BrokerEndpoint brokerEndpoint{};
BrokerEndpoint savedBrokerEndpoint{};
bool brokerAvailable = false;
bool savedBrokerAvailable = false;
bool discoveryListening = false;
screen_routing::TelemetryAccumulator screenTelemetry{};
screen_routing::TimeSyncSchedule timeSyncSchedule{};
screen_routing::NtpAssociationState ntpAssociation{};
screen_routing::MqttLinkStatusState mqttLinkStatus{};
screen_routing::UartTxQueue uartTxQueue{};
/* PubSubClient invokes its callback while servicing the ESP8266 network path.
 * RouteOutput is larger than 800 bytes, so allocating it in that callback can
 * exhaust the small system stack while a telemetry frame is being parsed. */
screen_routing::RouteOutput mqttRouteOutput{};
bool ntpConfigureAttempted = false;
#if defined(BUILD_ROLE_CTRL02)
uint32_t lastLinkHeartbeatMs = 0U;
bool nodeAStatusKnown = false;
bool nodeAOnline = false;
#endif

#if defined(BUILD_ROLE_CTRL02)
constexpr screen_routing::Role kBuildRole = screen_routing::Role::Ctrl02;
#else
constexpr screen_routing::Role kBuildRole = screen_routing::Role::Ctrl01;
#endif

IPAddress brokerIp() {
  return IPAddress(brokerEndpoint.address[0], brokerEndpoint.address[1],
                   brokerEndpoint.address[2], brokerEndpoint.address[3]);
}

void selectBroker(const BrokerEndpoint& endpoint) {
  if (brokerAvailable && endpointEquals(endpoint, brokerEndpoint)) return;
  /* Discovery may be broadcast by more than one local interface or broker.
   * Never tear down a healthy MQTT session just because another valid
   * advertisement arrived; consider a new endpoint only after the active
   * connection has actually failed. */
  if (mqtt.connected()) return;
  brokerEndpoint = endpoint;
  brokerAvailable = true;
  mqtt.setServer(brokerIp(), brokerEndpoint.port);
  lastMqttAttempt = millis() - kReconnectIntervalMs;
  Serial.printf("#DISCOVERY broker=%s:%u\r\n", brokerIp().toString().c_str(), brokerEndpoint.port);
}

void persistBrokerAfterSuccessfulConnection() {
  if (!brokerAvailable || (savedBrokerAvailable && endpointEquals(brokerEndpoint, savedBrokerEndpoint))) return;
  const StoredBrokerEndpoint stored = makeStoredEndpoint(brokerEndpoint);
  EEPROM.put(0, stored);
  if (!EEPROM.commit()) {
    Serial.println("#ERROR broker_persist_failed");
    return;
  }
  savedBrokerEndpoint = brokerEndpoint;
  savedBrokerAvailable = true;
  Serial.println("#DISCOVERY broker_saved");
}

void handleDiscovery() {
  /* No key configured: refuse to act on any advertisement rather than accept
   * unsigned ones.  The EEPROM-restored broker endpoint remains usable. */
  const size_t hmacKeyLength = std::strlen(DISCOVERY_HMAC_KEY);
  if (hmacKeyLength == 0U) return;
  if (WiFi.status() != WL_CONNECTED) {
    if (discoveryListening) {
      discoveryUdp.stop();
      discoveryListening = false;
    }
    return;
  }
  if (!discoveryListening) {
    if (!discoveryUdp.begin(kDiscoveryPort)) {
      Serial.println("#ERROR discovery_listen_failed");
      return;
    }
    discoveryListening = true;
    Serial.printf("#DISCOVERY listening udp=%u\r\n", kDiscoveryPort);
  }

  const int packetSize = discoveryUdp.parsePacket();
  if (packetSize <= 0) return;
  char packet[kMaxDiscoveryPacket];
  const int bytesRead = discoveryUdp.read(packet, sizeof(packet));
  if (bytesRead <= 0 || packetSize > static_cast<int>(sizeof(packet))) return;
  const IPAddress sender = discoveryUdp.remoteIP();
  const uint8_t senderAddress[] = {sender[0], sender[1], sender[2], sender[3]};
  BrokerEndpoint discovered{};
  if (parseDiscoveryPacket(packet, static_cast<size_t>(bytesRead), senderAddress,
                           DISCOVERY_HMAC_KEY, hmacKeyLength, &discovered)) {
    selectBroker(discovered);
  } else {
    Serial.println("#ERROR discovery_packet_rejected");
  }
}

void printStatus() {
  const String broker = brokerAvailable
                            ? brokerIp().toString() + ":" + String(brokerEndpoint.port)
                            : "unknown";
  Serial.printf("#STATUS wifi=%s wifi_code=%d ip=%s rssi=%d mqtt=%s broker=%s queued=%u heap=%u\r\n",
                WiFi.status() == WL_CONNECTED ? "up" : "down",
                static_cast<int>(WiFi.status()), WiFi.localIP().toString().c_str(), WiFi.RSSI(),
                mqtt.connected() ? "up" : "down", broker.c_str(), pendingCount, ESP.getFreeHeap());
}

uint64_t currentEpochMilliseconds() {
  struct timeval now{};
  if (gettimeofday(&now, nullptr) != 0) return 0ULL;
  // EpochMillisecondsFromUnixParts returns 0 when the clock is not yet
  // synchronized (pre-2024 or post-2099), preserving rejection of future or
  // expired commands until NTP has produced a valid time.
  return screen_routing::EpochMillisecondsFromUnixParts(
      static_cast<int64_t>(now.tv_sec), static_cast<int32_t>(now.tv_usec));
}

#if !defined(BUILD_ROLE_CTRL02)
bool isCtrl01CommandTopic(const char* topic) {
  constexpr char prefix[] = "ut/v1/CTRL-01/cmd";
  constexpr size_t prefixLength = sizeof(prefix) - 1U;
  return std::strncmp(topic, prefix, prefixLength) == 0 &&
         (topic[prefixLength] == '\0' || topic[prefixLength] == '/');
}
#endif

#if !defined(BUILD_ROLE_CTRL02)
/* Broker-controlled bytes reach Node A's line parser verbatim, so a payload or
 * topic carrying CR/LF/NUL could terminate the frame early and inject a second
 * forged line (an #ACK, a LINK frame, ...).  Reject the whole command instead. */
bool uartTextIsSafe(const char* text, size_t length) {
  for (size_t i = 0U; i < length; ++i) {
    const char c = text[i];
    if (c == '\r' || c == '\n' || c == '\0') return false;
  }
  return true;
}

/* The single guarded downlink writer for CTRL-01: both MQTT command paths emit
 * "MQTT|<topic>|<payload>" through here so the control-character and length
 * rules cannot drift between them. */
bool writeUartCommand(const char* topic, const char* payload, size_t length) {
  const size_t topicLength = std::strlen(topic);
  if (!uartTextIsSafe(topic, topicLength) || !uartTextIsSafe(payload, length)) {
    Serial.println("#ERROR mqtt_downlink_control_chars");
    return false;
  }
  /* 6 = "MQTT|" plus the separating '|'. */
  const size_t frameLength = 6U + topicLength + length;
  if (frameLength > kMaxDownlinkLine) {
    Serial.println("#ERROR mqtt_downlink_too_large");
    return false;
  }
  char frame[kMaxDownlinkLine + 1U];
  std::memcpy(frame, "MQTT|", 5U);
  std::memcpy(frame + 5U, topic, topicLength);
  frame[5U + topicLength] = '|';
  std::memcpy(frame + 6U + topicLength, payload, length);
  frame[frameLength] = '\0';
  const screen_routing::UartTxEnqueueResult result =
      screen_routing::EnqueueUartTxLine(
          &uartTxQueue, screen_routing::UartTxFrameKind::Acknowledgement,
          frame, frameLength);
  if (result != screen_routing::UartTxEnqueueResult::Queued) {
    Serial.printf("#ERROR mqtt_downlink_queue=%u\r\n",
                  static_cast<unsigned int>(result));
    return false;
  }
  return true;
}
#endif

// Drain pending UART frames in bounded chunks without blocking. Each frame,
// including its CRLF terminator, is written whole by UartTxPeek/UartTxConsume,
// so frames never interleave. The chunk count caps per-loop work regardless of
// how much room Serial.availableForWrite() reports.
void pumpUartTxQueue() {
  constexpr size_t kMaxChunksPerPump = 16U;  // 16 * 64 = 1024 bytes max.
  for (size_t chunks = 0U;
       chunks < kMaxChunksPerPump &&
       screen_routing::UartTxQueuedFrameCount(&uartTxQueue) != 0U;
       ++chunks) {
    const int available = Serial.availableForWrite();
    if (available <= 0) return;
    const uint8_t* bytes = nullptr;
    const size_t count = screen_routing::UartTxPeek(
        &uartTxQueue, static_cast<size_t>(available), &bytes);
    if (count == 0U || bytes == nullptr) return;
    Serial.write(bytes, count);
    screen_routing::UartTxConsume(&uartTxQueue, count);
  }
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  if (length > kMaxSerialFrame) {
    Serial.println("#ERROR mqtt_payload_too_large");
    return;
  }
#if defined(BUILD_ROLE_CTRL02)
  /* Node A presence must not be inferred from whichever telemetry fragment
   * happens to survive a busy UART interval.  Its retained MQTT status gives
   * ESP-02 an immediate, explicit source after every reconnect. */
  if (std::strcmp(topic, "ut/v1/CTRL-01/status") == 0) {
    const bool online = length == 6U &&
                        std::memcmp(payload, "online", 6U) == 0;
    nodeAStatusKnown = true;
    nodeAOnline = online;
    const char* line = online ? "NODEA|1" : "NODEA|0";
    screen_routing::EnqueueUartTxLine(
        &uartTxQueue, screen_routing::UartTxFrameKind::Diagnostic,
        line, 7U);
    return;
  }
  const screen_routing::RouteResult result = screen_routing::RouteMqttMessage(
      kBuildRole, topic, reinterpret_cast<const char*>(payload), length,
      currentEpochMilliseconds(), &screenTelemetry, &mqttRouteOutput);
  if (result == screen_routing::RouteResult::Ok &&
      mqttRouteOutput.kind == screen_routing::OutputKind::UartLine) {
    // Enqueue rather than synchronously writing a full snapshot/ack frame from
    // the MQTT callback; loop() drains it in bounded chunks.
    const screen_routing::UartTxFrameKind kind =
        std::strcmp(topic, "ut/v1/CTRL-01/cmd_ack") == 0
            ? screen_routing::UartTxFrameKind::Acknowledgement
            : screen_routing::UartTxFrameKind::Snapshot;
    screen_routing::EnqueueUartTxLine(&uartTxQueue, kind,
                                      mqttRouteOutput.payload,
                                      mqttRouteOutput.payload_length);
  } else if (result != screen_routing::RouteResult::WrongTopic) {
    Serial.printf("#ERROR screen_route=%u\r\n",
                  static_cast<unsigned int>(result));
  }
#else
  if (std::strcmp(topic, "ut/v1/CTRL-01/cmd/menu") == 0) {
    const screen_routing::RouteResult result = screen_routing::RouteMqttMessage(
        kBuildRole, topic, reinterpret_cast<const char*>(payload), length,
        currentEpochMilliseconds(), &screenTelemetry, &mqttRouteOutput);
    if (result != screen_routing::RouteResult::Ok ||
        mqttRouteOutput.kind != screen_routing::OutputKind::UartCommand) {
      Serial.printf("#ERROR menu_command_rejected=%u\r\n",
                    static_cast<unsigned int>(result));
      return;
    }
    (void)writeUartCommand(topic, mqttRouteOutput.payload,
                           mqttRouteOutput.payload_length);
    return;
  }
  if (!isCtrl01CommandTopic(topic)) return;
  // Preserve the existing Web/IoTDA command bridge byte-for-byte, now behind
  // the shared control-character and length guard.
  (void)writeUartCommand(topic, reinterpret_cast<const char*>(payload), length);
#endif
}

void connectWiFi() {
  const uint32_t now = millis();
  if (WiFi.status() == WL_CONNECTED) {
    wifiDownSinceMs = 0U;
    return;
  }
  if (strcmp(WIFI_SSID, "replace-me") == 0) {
    if (!missingSecretsReported) {
      Serial.println("#ERROR create include/secrets.h before deployment");
      missingSecretsReported = true;
    }
    return;
  }
  if (!wifiStarted) {
    WiFi.mode(WIFI_STA);
    WiFi.persistent(false);
    WiFi.setAutoReconnect(true);
    WiFi.setSleepMode(WIFI_NONE_SLEEP);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    wifiStarted = true;
    lastWiFiAttempt = now;
    wifiDownSinceMs = now;
    Serial.println("#WIFI connecting");
    return;
  }
  /* ESP8266 can briefly report IDLE/DISCONNECTED during a beacon miss or DHCP
   * renewal.  Calling begin() at that instant tears down an otherwise healthy
   * association and was the source of the MQTT online/offline oscillation. */
  if (wifiDownSinceMs == 0U) {
    wifiDownSinceMs = now;
    return;
  }
  if (static_cast<uint32_t>(now - wifiDownSinceMs) < kWiFiTransientGraceMs ||
      static_cast<uint32_t>(now - lastWiFiAttempt) < kWiFiConnectTimeoutMs) {
    return;
  }
  lastWiFiAttempt = now;
  /* WiFi.reconnect() is intentionally the first recovery step because it does
   * not tear down a transiently recoverable association.  The ESP8266 driver
   * can, however, remain indefinitely in WL_DISCONNECTED after an AP restart.
   * Escalate once per minute to a fresh begin() so a node cannot stay offline
   * forever while its peer on the same supply and SSID remains healthy. */
  if (static_cast<uint32_t>(now - wifiDownSinceMs) >= kWiFiHardRecoveryMs &&
      static_cast<uint32_t>(now - lastWiFiHardRecoveryMs) >=
          kWiFiHardRecoveryMs) {
    lastWiFiHardRecoveryMs = now;
    wifiDownSinceMs = now;
    WiFi.disconnect(false);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.printf("#WIFI hard_recovery status=%d\r\n",
                  static_cast<int>(WiFi.status()));
    return;
  }
  WiFi.reconnect();
  Serial.printf("#WIFI reconnect status=%d\r\n", static_cast<int>(WiFi.status()));
}

void handleNetworkTime() {
  const bool connected = WiFi.status() == WL_CONNECTED;
  const uint32_t nowMs = millis();
  const bool associated =
      screen_routing::ShouldConfigureNtp(&ntpAssociation, connected);
  if (associated || (connected && !ntpConfigureAttempted)) {
    // configTime() starts the SNTP client and returns immediately.
    // Multiple geographically diverse names make hotspot/DNS restrictions
    // much less likely to leave both displays at the unsynchronised marker.
    configTime(0, 0, "ntp.aliyun.com", "time1.cloud.tencent.com",
               "pool.ntp.org");
    ntpConfigureAttempted = true;
    Serial.println("#NTP configured");
  }
  if (!connected) return;
  const time_t epoch = time(nullptr);
  char line[screen_protocol::kUartLineLimit + 1U]{};
  size_t written = 0U;
  const screen_routing::TimeEmitResult result =
      screen_routing::BuildDueTimeSync(
          &timeSyncSchedule, nowMs,
          epoch > 0 ? static_cast<uint64_t>(epoch) : 0ULL, line,
          sizeof(line), &written);
  if (result == screen_routing::TimeEmitResult::Emitted) {
    screen_routing::EnqueueUartTxLine(
        &uartTxQueue, screen_routing::UartTxFrameKind::TimeSync, line, written);
  }
}

void handleMqttLinkStatus() {
  char line[16]{};
  size_t written = 0U;
  if (screen_routing::BuildMqttLinkStatus(
          &mqttLinkStatus, mqtt.connected(), line, sizeof(line), &written) ==
      screen_routing::MqttLinkStatusResult::Emitted) {
    screen_routing::EnqueueUartTxLine(
        &uartTxQueue, screen_routing::UartTxFrameKind::Diagnostic, line,
        written);
  }
}

void handleLinkHeartbeat() {
#if defined(BUILD_ROLE_CTRL02)
  const uint32_t now = millis();
  if (static_cast<uint32_t>(now - lastLinkHeartbeatMs) < kLinkHeartbeatIntervalMs) return;
  char line[24]{};
  const int length = snprintf(line, sizeof(line), "LINK|%u|%u|%u",
                              WiFi.status() == WL_CONNECTED ? 1U : 0U,
                              mqtt.connected() ? 1U : 0U,
                              (nodeAStatusKnown && nodeAOnline) ? 1U : 0U);
  if (length > 0 && static_cast<size_t>(length) < sizeof(line)) {
    screen_routing::EnqueueUartTxLine(
        &uartTxQueue, screen_routing::UartTxFrameKind::Diagnostic,
        line, static_cast<size_t>(length));
  }
  lastLinkHeartbeatMs = now;
#endif
}

void connectMqtt() {
  if (WiFi.status() != WL_CONNECTED || !brokerAvailable || mqtt.connected() ||
      millis() - lastMqttAttempt < kReconnectIntervalMs) return;
  lastMqttAttempt = millis();
  const bool connected = strlen(MQTT_USERNAME) == 0
                             ? mqtt.connect(BUILD_DEVICE_ID, statusTopic.c_str(), 1, true, "offline")
                             : mqtt.connect(BUILD_DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD,
                                            statusTopic.c_str(), 1, true, "offline", true);
  if (!connected) {
    Serial.printf("#MQTT connect_failed state=%d\r\n", mqtt.state());
    return;
  }
  /* WiFiClient::keepAlive() dereferences its internal ClientContext without a
   * null check.  Apply socket options only after PubSubClient has established
   * the TCP connection. */
  (void)network_client_config::ConfigureConnectedClient(networkClient);
  const screen_routing::RouteTopics& topics =
      screen_routing::TopicsForRole(kBuildRole);
  for (size_t index = 0U; index < topics.subscription_count; ++index) {
    if (!mqtt.subscribe(topics.subscriptions[index], 1)) {
      Serial.println("#MQTT subscribe_failed");
      mqtt.disconnect();
      return;
    }
  }
#if defined(BUILD_ROLE_CTRL02)
  if (!mqtt.subscribe("ut/v1/CTRL-01/status", 1)) {
    Serial.println("#MQTT peer_status_subscribe_failed");
    mqtt.disconnect();
    return;
  }
#endif
  mqtt.publish(statusTopic.c_str(), "online", true);
  persistBrokerAfterSuccessfulConnection();
  Serial.println("#MQTT connected");
}

const char* topicForPending(PendingKind kind) {
#if defined(BUILD_ROLE_CTRL02)
  if (kind == PendingKind::Telemetry) return telemetryTopic.c_str();
  return screen_routing::TopicsForRole(kBuildRole).serial_publish_topic;
#else
  if (kind == PendingKind::CommandAck) return commandAckTopic.c_str();
  return telemetryTopic.c_str();
#endif
}

void enqueueFrame(const char* line, size_t length, PendingKind kind) {
  if (line == nullptr || length > kMaxSerialFrame) return;
  int telemetryLogicalIndex = -1;
  for (uint8_t logical = 0U; logical < pendingCount; ++logical) {
    const uint8_t candidate =
        static_cast<uint8_t>((pendingHead + logical) % kPendingFrameCapacity);
    if (pendingFrameKinds[candidate] == PendingKind::Telemetry) {
      telemetryLogicalIndex = static_cast<int>(logical);
    }
  }
  if (pendingCount == kPendingFrameCapacity) {
    if (kind == PendingKind::Telemetry && telemetryLogicalIndex >= 0) {
      const uint8_t index = static_cast<uint8_t>(
          (pendingHead + telemetryLogicalIndex) % kPendingFrameCapacity);
      std::memcpy(pendingFrames[index], line, length);
      pendingFrames[index][length] = '\0';
      Serial.println("#QUEUED telemetry_coalesced");
      return;
    }
    if (telemetryLogicalIndex < 0) {
      Serial.println("#ERROR mqtt_buffer_full_priority_frame_preserved");
      return;
    }
    /* A command/ACK may evict stale telemetry, but never another accepted
     * command/ACK. Shift logical entries inside the small fixed ring. */
    for (uint8_t logical = static_cast<uint8_t>(telemetryLogicalIndex);
         logical + 1U < pendingCount; ++logical) {
      const uint8_t target =
          static_cast<uint8_t>((pendingHead + logical) % kPendingFrameCapacity);
      const uint8_t source = static_cast<uint8_t>(
          (pendingHead + logical + 1U) % kPendingFrameCapacity);
      std::memcpy(pendingFrames[target], pendingFrames[source],
                  sizeof(pendingFrames[target]));
      pendingFrameKinds[target] = pendingFrameKinds[source];
    }
    --pendingCount;
    Serial.println("#ERROR mqtt_buffer_telemetry_evicted");
  }
  const uint8_t index = (pendingHead + pendingCount) % kPendingFrameCapacity;
  std::memcpy(pendingFrames[index], line, length);
  pendingFrames[index][length] = '\0';
  pendingFrameKinds[index] = kind;
  pendingCount++;
  Serial.printf("#QUEUED count=%u\r\n", pendingCount);
}

void flushPendingFrame() {
  if (!mqtt.connected() || pendingCount == 0) return;
  const PendingKind kind = pendingFrameKinds[pendingHead];
  const char* topic = topicForPending(kind);
  if (!mqtt.publish(topic, pendingFrames[pendingHead], false)) return;
  pendingFrames[pendingHead][0] = '\0';
  pendingFrameKinds[pendingHead] = PendingKind::Telemetry;
  pendingHead = (pendingHead + 1U) % kPendingFrameCapacity;
  pendingCount--;
  Serial.printf("#PUBLISHED queued=%u\r\n", pendingCount);
}

void handleSerialLine(const char* line, size_t length) {
  while (length != 0U &&
         (*line == ' ' || *line == '\t' || *line == '\r' || *line == '\n')) {
    ++line;
    --length;
  }
  while (length != 0U &&
         (line[length - 1U] == ' ' || line[length - 1U] == '\t' ||
          line[length - 1U] == '\r' || line[length - 1U] == '\n')) {
    --length;
  }
  if (length == 0U) return;
  if ((length == 6U && std::memcmp(line, "STATUS", 6U) == 0) ||
      (length == 2U && std::memcmp(line, "AT", 2U) == 0)) {
    printStatus();
    return;
  }
  if (line[0] != '{') {
    Serial.println("#ERROR expected JSON, STATUS, or AT");
    return;
  }
#if defined(BUILD_ROLE_CTRL02)
  if (screen_routing::IsCtrl02StatusHeartbeat(line, length)) {
    /* Node B can reboot independently after a firmware update.  Its heartbeat
     * is the readiness handshake that makes ESP-02 replay the current link and
     * clock instead of leaving the display stale for up to ten minutes. */
    screen_routing::RequestMqttLinkStatus(&mqttLinkStatus);
    screen_routing::RequestTimeSync(&timeSyncSchedule);
    return;
  }
  const screen_routing::RouteResult result = screen_routing::RouteSerialLine(
      kBuildRole, line, length, currentEpochMilliseconds(), &mqttRouteOutput);
  if (result != screen_routing::RouteResult::Ok ||
      mqttRouteOutput.kind != screen_routing::OutputKind::MqttPublish) {
    Serial.printf("#ERROR menu_serial_rejected=%u\r\n",
                  static_cast<unsigned int>(result));
    return;
  }
  const bool isTelemetry =
      std::strcmp(mqttRouteOutput.topic, telemetryTopic.c_str()) == 0;
  const PendingKind kind = isTelemetry ? PendingKind::Telemetry
                                       : PendingKind::MenuCommand;
  if (!mqtt.connected()) {
    enqueueFrame(mqttRouteOutput.payload, mqttRouteOutput.payload_length, kind);
    return;
  }
  if (mqtt.publish(mqttRouteOutput.topic, mqttRouteOutput.payload, false)) {
    Serial.println(isTelemetry ? "#PUBLISHED" : "#MENU_PUBLISHED");
  } else {
    enqueueFrame(mqttRouteOutput.payload, mqttRouteOutput.payload_length, kind);
  }
#else
  screen_protocol::CommandAck parsedAck{};
  const bool isCommandAck =
      screen_protocol::ParseCommandAck(line, length, &parsedAck) ==
      screen_protocol::Result::Ok;
  const PendingKind kind = isCommandAck ? PendingKind::CommandAck
                                        : PendingKind::Telemetry;
  const char* topic = topicForPending(kind);
  if (!mqtt.connected()) {
    enqueueFrame(line, length, kind);
    return;
  }
  if (mqtt.publish(topic, reinterpret_cast<const uint8_t*>(line), length,
                   false)) {
    Serial.println(isCommandAck ? "#ACK_PUBLISHED" : "#PUBLISHED");
  } else {
    enqueueFrame(line, length, kind);
  }
#endif
}

void readSerial() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\n') {
      if (serialFrameDiscarding) {
        serialFrameDiscarding = false;
        Serial.println("#ERROR serial_frame_dropped");
      } else {
        serialFrame[serialFrameLength] = '\0';
        handleSerialLine(serialFrame, serialFrameLength);
      }
      serialFrameLength = 0U;
      serialFrame[0] = '\0';
    } else if (c != '\r') {
      if (serialFrameDiscarding) continue;
      if (serialFrameLength >= kMaxSerialFrame) {
        serialFrameLength = 0U;
        serialFrame[0] = '\0';
        serialFrameDiscarding = true;
        Serial.println("#ERROR serial_frame_too_large");
      } else {
        serialFrame[serialFrameLength++] = c;
      }
    }
  }
}
}  // namespace

void setup() {
  pinMode(kLedPin, OUTPUT);
  digitalWrite(kLedPin, HIGH);
  Serial.begin(kSerialBaud);
  Serial.setTimeout(50);
  telemetryTopic = String("ut/v1/") + BUILD_DEVICE_ID + "/telemetry";
#if !defined(BUILD_ROLE_CTRL02)
  commandAckTopic = String("ut/v1/") + BUILD_DEVICE_ID + "/cmd_ack";
#endif
  statusTopic = String("ut/v1/") + BUILD_DEVICE_ID + "/status";
  mqtt.setCallback(onMqttMessage);
  /* PubSubClient silently keeps its 256-byte default when the larger buffer
   * cannot be allocated; that would break every telemetry frame at runtime,
   * so surface the failure at boot instead. */
  if (!mqtt.setBufferSize(kMqttBufferSize)) {
    Serial.println("#ERROR mqtt_buffer_alloc_failed");
  }
  mqtt.setKeepAlive(15);
  mqtt.setSocketTimeout(4);
  screen_routing::InitTelemetryAccumulator(&screenTelemetry);
  screen_routing::InitTimeSyncSchedule(&timeSyncSchedule);
  screen_routing::InitNtpAssociationState(&ntpAssociation);
  screen_routing::InitMqttLinkStatusState(&mqttLinkStatus);
  screen_routing::InitUartTxQueue(&uartTxQueue);
  EEPROM.begin(sizeof(StoredBrokerEndpoint));
  StoredBrokerEndpoint stored{};
  EEPROM.get(0, stored);
  if (loadStoredEndpoint(stored, &savedBrokerEndpoint)) {
    savedBrokerAvailable = true;
    selectBroker(savedBrokerEndpoint);
    Serial.println("#DISCOVERY restored_saved_broker");
  }
  Serial.printf("#BOOT esp8266-01s mqtt-uart-bridge v3 device=%s\r\n", BUILD_DEVICE_ID);
  if (std::strlen(DISCOVERY_HMAC_KEY) == 0U) {
    Serial.println("#ERROR discovery_disabled_missing_hmac_key");
  }
  connectWiFi();
}

void loop() {
  connectWiFi();
  /* Service MQTT before DNS, discovery and UART work.  A second call later in
   * the iteration drains packets that arrived while those handlers ran. */
  if (mqtt.connected()) mqtt.loop();
  handleDiscovery();
  handleNetworkTime();
  connectMqtt();
  handleMqttLinkStatus();
  handleLinkHeartbeat();
  if (mqtt.connected()) {
    mqtt.loop();
    flushPendingFrame();
  }
  pumpUartTxQueue();
  readSerial();
  digitalWrite(kLedPin, mqtt.connected() ? LOW : HIGH);
  delay(1);
}
