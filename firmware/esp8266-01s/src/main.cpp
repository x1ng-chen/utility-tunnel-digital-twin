#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#define WIFI_SSID "replace-me"
#define WIFI_PASSWORD "replace-me"
#define MQTT_HOST "192.168.1.10"
#define MQTT_PORT 1883
#define MQTT_USERNAME ""
#define MQTT_PASSWORD ""
#define DEVICE_ID "CTRL-01"
#endif

namespace {
// Match the STM32 USART2 configuration in led_blink.ioc.
constexpr uint32_t kSerialBaud = 9600;
constexpr uint32_t kReconnectIntervalMs = 5000;
constexpr size_t kMaxSerialFrame = 768;
constexpr uint8_t kLedPin = 2;

WiFiClient networkClient;
PubSubClient mqtt(networkClient);
String serialFrame;
String telemetryTopic;
String commandTopic;
uint32_t lastWiFiAttempt = 0;
uint32_t lastMqttAttempt = 0;

void printStatus() {
  Serial.printf("#STATUS wifi=%s ip=%s rssi=%d mqtt=%s heap=%u\r\n",
                WiFi.status() == WL_CONNECTED ? "up" : "down",
                WiFi.localIP().toString().c_str(), WiFi.RSSI(),
                mqtt.connected() ? "up" : "down", ESP.getFreeHeap());
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
  if (WiFi.status() == WL_CONNECTED || millis() - lastWiFiAttempt < kReconnectIntervalMs) return;
  lastWiFiAttempt = millis();
  if (strcmp(WIFI_SSID, "replace-me") == 0) {
    Serial.println("#ERROR create include/secrets.h before deployment");
    return;
  }
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.println("#WIFI connecting");
}

void connectMqtt() {
  if (WiFi.status() != WL_CONNECTED || mqtt.connected() ||
      millis() - lastMqttAttempt < kReconnectIntervalMs) return;
  lastMqttAttempt = millis();
  const bool connected = strlen(MQTT_USERNAME) == 0
                             ? mqtt.connect(DEVICE_ID)
                             : mqtt.connect(DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD);
  if (!connected) {
    Serial.printf("#MQTT connect_failed state=%d\r\n", mqtt.state());
    return;
  }
  mqtt.subscribe(commandTopic.c_str(), 1);
  Serial.println("#MQTT connected");
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
  if (!mqtt.connected()) {
    Serial.println("#ERROR mqtt_offline");
    return;
  }
  if (mqtt.publish(telemetryTopic.c_str(), line.c_str(), false)) {
    Serial.println("#PUBLISHED");
  } else {
    Serial.println("#ERROR publish_failed");
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
  telemetryTopic = String("ut/v1/") + DEVICE_ID + "/telemetry";
  commandTopic = String("ut/v1/") + DEVICE_ID + "/cmd/#";
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  mqtt.setBufferSize(1024);
  mqtt.setKeepAlive(30);
  Serial.println("#BOOT esp8266-01s mqtt-uart-bridge v1");
  connectWiFi();
}

void loop() {
  connectWiFi();
  connectMqtt();
  if (mqtt.connected()) mqtt.loop();
  readSerial();
  digitalWrite(kLedPin, mqtt.connected() ? LOW : HIGH);
  delay(1);
}
