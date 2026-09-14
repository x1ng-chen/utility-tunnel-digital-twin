#include <Arduino.h>
#include <cstring>
#include <EEPROM.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <WiFiUdp.h>
#include <sys/time.h>
#include <time.h>

#include "mqtt_discovery.h"
#include "screen_routing.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#define WIFI_SSID "replace-me"
#define WIFI_PASSWORD "replace-me"
#define MQTT_USERNAME ""
#define MQTT_PASSWORD ""
#endif

#ifndef BUILD_DEVICE_ID
#define BUILD_DEVICE_ID "CTRL-01"
#endif

namespace {
// Match the STM32 USART2 configuration in led_blink.ioc.
constexpr uint32_t kSerialBaud = 9600;
constexpr uint32_t kReconnectIntervalMs = 5000;
constexpr uint32_t kWiFiConnectTimeoutMs = 30000;
constexpr uint32_t kNtpRetryIntervalMs = 30000;
// Preserve the bench-tested long telemetry path. Screen protocol frames remain
// independently capped at screen_protocol::kUartLineLimit (768 bytes).
constexpr size_t kMaxSerialFrame = 1024;
constexpr uint16_t kMqttBufferSize = 1280;
constexpr uint8_t kPendingFrameCapacity = 8;
constexpr uint8_t kLedPin = 2;
constexpr uint16_t kDiscoveryPort = 4210;
constexpr size_t kMaxDiscoveryPacket = 96;

WiFiClient networkClient;
WiFiUDP discoveryUdp;
PubSubClient mqtt(networkClient);
char serialFrame[kMaxSerialFrame + 1U] = {};
size_t serialFrameLength = 0U;
String statusTopic;
#if !defined(BUILD_ROLE_CTRL02)
String telemetryTopic;
String commandAckTopic;
#endif
char pendingFrames[kPendingFrameCapacity][kMaxSerialFrame + 1] = {};
enum class PendingKind : uint8_t { Telemetry = 0, CommandAck, MenuCommand };
PendingKind pendingFrameKinds[kPendingFrameCapacity] = {};
uint8_t pendingHead = 0;
uint8_t pendingCount = 0;
uint32_t lastWiFiAttempt = 0;
uint32_t lastMqttAttempt = 0;
bool wifiAttemptActive = false;
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
uint32_t lastNtpConfigureMs = 0U;
bool ntpConfigureAttempted = false;

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
  if (mqtt.connected()) mqtt.disconnect();
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
  if (parseDiscoveryPacket(packet, static_cast<size_t>(bytesRead), senderAddress, &discovered)) {
    selectBroker(discovered);
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
void writeUartLine(const char* payload, size_t length) {
  Serial.write(reinterpret_cast<const uint8_t*>(payload), length);
  Serial.print("\r\n");
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
  screen_routing::RouteOutput routed{};
  const screen_routing::RouteResult result = screen_routing::RouteMqttMessage(
      kBuildRole, topic, reinterpret_cast<const char*>(payload), length,
      currentEpochMilliseconds(), &screenTelemetry, &routed);
  if (result == screen_routing::RouteResult::Ok &&
      routed.kind == screen_routing::OutputKind::UartLine) {
    // Enqueue rather than synchronously writing a full snapshot/ack frame from
    // the MQTT callback; loop() drains it in bounded chunks.
    const screen_routing::UartTxFrameKind kind =
        std::strcmp(topic, "ut/v1/CTRL-01/cmd_ack") == 0
            ? screen_routing::UartTxFrameKind::Acknowledgement
            : screen_routing::UartTxFrameKind::Snapshot;
    screen_routing::EnqueueUartTxLine(&uartTxQueue, kind, routed.payload,
                                      routed.payload_length);
  } else if (result != screen_routing::RouteResult::WrongTopic) {
    Serial.printf("#ERROR screen_route=%u\r\n",
                  static_cast<unsigned int>(result));
  }
#else
  if (std::strcmp(topic, "ut/v1/CTRL-01/cmd/menu") == 0) {
    screen_routing::RouteOutput routed{};
    const screen_routing::RouteResult result = screen_routing::RouteMqttMessage(
        kBuildRole, topic, reinterpret_cast<const char*>(payload), length,
        currentEpochMilliseconds(), &screenTelemetry, &routed);
    if (result != screen_routing::RouteResult::Ok ||
        routed.kind != screen_routing::OutputKind::UartCommand) {
      Serial.printf("#ERROR menu_command_rejected=%u\r\n",
                    static_cast<unsigned int>(result));
      return;
    }
    Serial.print("MQTT|");
    Serial.print(topic);
    Serial.print('|');
    writeUartLine(routed.payload, routed.payload_length);
    return;
  }
  if (!isCtrl01CommandTopic(topic)) return;
  // Preserve the existing Web/IoTDA command bridge byte-for-byte.
  Serial.print("MQTT|");
  Serial.print(topic);
  Serial.print('|');
  writeUartLine(reinterpret_cast<const char*>(payload), length);
#endif
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    wifiAttemptActive = false;
    return;
  }
  if (wifiAttemptActive && millis() - lastWiFiAttempt < kWiFiConnectTimeoutMs) return;
  if (wifiAttemptActive) {
    Serial.printf("#WIFI retry status=%d\r\n", static_cast<int>(WiFi.status()));
    WiFi.disconnect(false);
  }
  lastWiFiAttempt = millis();
  if (strcmp(WIFI_SSID, "replace-me") == 0) {
    Serial.println("#ERROR create include/secrets.h before deployment");
    return;
  }
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  wifiAttemptActive = true;
  Serial.println("#WIFI connecting");
}

void handleNetworkTime() {
  const bool connected = WiFi.status() == WL_CONNECTED;
  const uint32_t nowMs = millis();
  const uint64_t epochMs = currentEpochMilliseconds();
  const bool associated =
      screen_routing::ShouldConfigureNtp(&ntpAssociation, connected);
  const bool retryDue = connected && epochMs == 0ULL &&
      (!ntpConfigureAttempted ||
       static_cast<uint32_t>(nowMs - lastNtpConfigureMs) >=
           kNtpRetryIntervalMs);
  if (associated || retryDue) {
    // configTime() starts the SNTP client and returns immediately.
    // Multiple geographically diverse names make hotspot/DNS restrictions
    // much less likely to leave both displays at the unsynchronised marker.
    configTime(0, 0, "ntp.aliyun.com", "time1.cloud.tencent.com",
               "pool.ntp.org");
    lastNtpConfigureMs = nowMs;
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
  const screen_routing::RouteTopics& topics =
      screen_routing::TopicsForRole(kBuildRole);
  for (size_t index = 0U; index < topics.subscription_count; ++index) {
    if (!mqtt.subscribe(topics.subscriptions[index], 1)) {
      Serial.println("#MQTT subscribe_failed");
      mqtt.disconnect();
      return;
    }
  }
  mqtt.publish(statusTopic.c_str(), "online", true);
  persistBrokerAfterSuccessfulConnection();
  Serial.println("#MQTT connected");
}

const char* topicForPending(PendingKind kind) {
#if defined(BUILD_ROLE_CTRL02)
  (void)kind;
  return screen_routing::TopicsForRole(kBuildRole).serial_publish_topic;
#else
  if (kind == PendingKind::CommandAck) return commandAckTopic.c_str();
  return telemetryTopic.c_str();
#endif
}

void enqueueFrame(const char* line, size_t length, PendingKind kind) {
  if (line == nullptr || length > kMaxSerialFrame) return;
  if (pendingCount == kPendingFrameCapacity) {
    pendingHead = (pendingHead + 1U) % kPendingFrameCapacity;
    pendingCount--;
    Serial.println("#ERROR mqtt_buffer_overflow_oldest_removed");
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
  screen_routing::RouteOutput routed{};
  const screen_routing::RouteResult result = screen_routing::RouteSerialLine(
      kBuildRole, line, length, currentEpochMilliseconds(), &routed);
  if (result != screen_routing::RouteResult::Ok ||
      routed.kind != screen_routing::OutputKind::MqttPublish) {
    Serial.printf("#ERROR menu_serial_rejected=%u\r\n",
                  static_cast<unsigned int>(result));
    return;
  }
  if (!mqtt.connected()) {
    enqueueFrame(routed.payload, routed.payload_length,
                 PendingKind::MenuCommand);
    return;
  }
  if (mqtt.publish(routed.topic, routed.payload, false)) {
    Serial.println("#MENU_PUBLISHED");
  } else {
    enqueueFrame(routed.payload, routed.payload_length,
                 PendingKind::MenuCommand);
  }
#else
  const bool isCommandAck =
      std::strstr(line, "\"schema\":\"ut.command.ack.v1\"") != nullptr;
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
      serialFrame[serialFrameLength] = '\0';
      handleSerialLine(serialFrame, serialFrameLength);
      serialFrameLength = 0U;
      serialFrame[0] = '\0';
    } else if (c != '\r') {
      if (serialFrameLength >= kMaxSerialFrame) {
        serialFrameLength = 0U;
        serialFrame[0] = '\0';
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
#if !defined(BUILD_ROLE_CTRL02)
  telemetryTopic = String("ut/v1/") + BUILD_DEVICE_ID + "/telemetry";
  commandAckTopic = String("ut/v1/") + BUILD_DEVICE_ID + "/cmd_ack";
#endif
  statusTopic = String("ut/v1/") + BUILD_DEVICE_ID + "/status";
  mqtt.setCallback(onMqttMessage);
  mqtt.setBufferSize(kMqttBufferSize);
  mqtt.setKeepAlive(30);
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
  connectWiFi();
}

void loop() {
  connectWiFi();
  handleDiscovery();
  handleNetworkTime();
  connectMqtt();
  handleMqttLinkStatus();
  if (mqtt.connected()) {
    mqtt.loop();
    flushPendingFrame();
  }
  pumpUartTxQueue();
  readSerial();
  digitalWrite(kLedPin, mqtt.connected() ? LOW : HIGH);
  delay(1);
}
