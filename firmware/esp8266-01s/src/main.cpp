#include <Arduino.h>
#include <EEPROM.h>
#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <PubSubClient.h>

#include "mqtt_discovery.h"

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
constexpr size_t kMaxSerialFrame = 1024;
constexpr uint16_t kMqttBufferSize = 1280;
constexpr uint8_t kPendingFrameCapacity = 8;
constexpr uint8_t kLedPin = 2;
constexpr uint16_t kDiscoveryPort = 4210;
constexpr size_t kMaxDiscoveryPacket = 96;

WiFiClient networkClient;
WiFiUDP discoveryUdp;
PubSubClient mqtt(networkClient);
String serialFrame;
String telemetryTopic;
String commandTopic;
String statusTopic;
String commandAckTopic;
char pendingFrames[kPendingFrameCapacity][kMaxSerialFrame + 1] = {};
bool pendingFrameIsCommandAck[kPendingFrameCapacity] = {};
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

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  // The STM32 receives cloud/local commands as one framed UART line.
  Serial.print("MQTT|");
  Serial.print(topic);
  Serial.print('|');
  Serial.write(payload, length);
  Serial.print("\r\n");
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
  mqtt.subscribe(commandTopic.c_str(), 1);
  mqtt.publish(statusTopic.c_str(), "online", true);
  persistBrokerAfterSuccessfulConnection();
  Serial.println("#MQTT connected");
}

void enqueueFrame(const String& line, bool isCommandAck) {
  if (pendingCount == kPendingFrameCapacity) {
    pendingHead = (pendingHead + 1U) % kPendingFrameCapacity;
    pendingCount--;
    Serial.println("#ERROR telemetry_buffer_overflow_oldest_removed");
  }
  const uint8_t index = (pendingHead + pendingCount) % kPendingFrameCapacity;
  line.toCharArray(pendingFrames[index], kMaxSerialFrame + 1);
  pendingFrameIsCommandAck[index] = isCommandAck;
  pendingCount++;
  Serial.printf("#QUEUED count=%u\r\n", pendingCount);
}

void flushPendingFrame() {
  if (!mqtt.connected() || pendingCount == 0) return;
  const char* topic = pendingFrameIsCommandAck[pendingHead] ? commandAckTopic.c_str() : telemetryTopic.c_str();
  if (!mqtt.publish(topic, pendingFrames[pendingHead], false)) return;
  pendingFrames[pendingHead][0] = '\0';
  pendingFrameIsCommandAck[pendingHead] = false;
  pendingHead = (pendingHead + 1U) % kPendingFrameCapacity;
  pendingCount--;
  Serial.printf("#PUBLISHED queued=%u\r\n", pendingCount);
}

void handleSerialLine(String line) {
  line.trim();
  if (line.isEmpty()) return;
  if (line == "STATUS" || line == "AT") {
    printStatus();
    return;
  }
  if (line[0] != '{') {
    Serial.println("#ERROR expected JSON, STATUS, or AT");
    return;
  }
  const bool isCommandAck = line.indexOf("\"schema\":\"ut.command.ack.v1\"") >= 0;
  const char* topic = isCommandAck ? commandAckTopic.c_str() : telemetryTopic.c_str();
  if (!mqtt.connected()) {
    enqueueFrame(line, isCommandAck);
    return;
  }
  if (mqtt.publish(topic, line.c_str(), false)) {
    Serial.println(isCommandAck ? "#ACK_PUBLISHED" : "#PUBLISHED");
  } else {
    enqueueFrame(line, isCommandAck);
  }
}

void readSerial() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\n') {
      handleSerialLine(serialFrame);
      serialFrame = "";
    } else if (c != '\r') {
      if (serialFrame.length() >= kMaxSerialFrame) {
        serialFrame = "";
        Serial.println("#ERROR serial_frame_too_large");
      } else {
        serialFrame += c;
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
  serialFrame.reserve(kMaxSerialFrame);
  telemetryTopic = String("ut/v1/") + BUILD_DEVICE_ID + "/telemetry";
  commandTopic = String("ut/v1/") + BUILD_DEVICE_ID + "/cmd/#";
  commandAckTopic = String("ut/v1/") + BUILD_DEVICE_ID + "/cmd_ack";
  statusTopic = String("ut/v1/") + BUILD_DEVICE_ID + "/status";
  mqtt.setCallback(onMqttMessage);
  mqtt.setBufferSize(kMqttBufferSize);
  mqtt.setKeepAlive(30);
  EEPROM.begin(sizeof(StoredBrokerEndpoint));
  StoredBrokerEndpoint stored{};
  EEPROM.get(0, stored);
  if (loadStoredEndpoint(stored, &savedBrokerEndpoint)) {
    savedBrokerAvailable = true;
    selectBroker(savedBrokerEndpoint);
    Serial.println("#DISCOVERY restored_saved_broker");
  }
  Serial.printf("#BOOT esp8266-01s mqtt-uart-bridge v2 device=%s\r\n", BUILD_DEVICE_ID);
  connectWiFi();
}

void loop() {
  connectWiFi();
  handleDiscovery();
  connectMqtt();
  if (mqtt.connected()) {
    mqtt.loop();
    flushPendingFrame();
  }
  readSerial();
  digitalWrite(kLedPin, mqtt.connected() ? LOW : HIGH);
  delay(1);
}
