/*
 * 四主控 RS-485 网关（第二版）
 *
 * 轮询 4→3→2→1 号 STM32，读取 52 个输入寄存器（功能码 04），
 * 校验签名 0x5554、板号与 CRC 后：
 *   - 通过串口打印一行 JSON；
 *   - 若配置了 secrets.h，则连接 Wi-Fi/MQTT 并发布到 ut/v1/gateway/telemetry；
 *   - 订阅 ut/v1/gateway/cmd，把命令转换为 Modbus 06 写保持寄存器。
 *
 * 命令格式：
 *   {"board":4,"cmd":"fan","value":100}
 *   cmd = fan / relay / buzzer / led
 */
#include <Arduino.h>

#if __has_include("secrets.h")
#include "secrets.h"
#define HAVE_NET 1
#include <WiFi.h>
#include <PubSubClient.h>
#else
#define HAVE_NET 0
#endif

#define SLAVE_COUNT      4U
#define REGISTER_COUNT   52U
#define RESPONSE_BYTES   (3U + REGISTER_COUNT * 2U + 2U)   /* 109 */
#define POLL_TIMEOUT_MS  300U
#define POLL_INTERVAL_MS 500U
#define MODBUS_SIGNATURE 0x5554U

static HardwareSerial bus(1);
static const uint8_t scan_order[SLAVE_COUNT] = {4U, 3U, 2U, 1U};
static uint8_t scan_index;
static uint32_t polls;

#if HAVE_NET
static WiFiClient net;
static PubSubClient mqtt(net);
static const char *TELEMETRY_TOPIC = "ut/v1/gateway/telemetry";
static const char *COMMAND_TOPIC = "ut/v1/gateway/cmd";
static uint32_t last_net_attempt;
#endif

static uint16_t modbus_crc(const uint8_t *bytes, size_t count)
{
  uint16_t crc = 0xFFFFU;
  for (size_t i = 0; i < count; ++i)
  {
    crc ^= bytes[i];
    for (uint8_t bit = 0; bit < 8; ++bit)
      crc = (crc & 1U) ? (uint16_t)((crc >> 1U) ^ 0xA001U) : (uint16_t)(crc >> 1U);
  }
  return crc;
}

static void add_crc(uint8_t *frame, size_t size_without_crc)
{
  uint16_t crc = modbus_crc(frame, size_without_crc);
  frame[size_without_crc] = (uint8_t)crc;
  frame[size_without_crc + 1U] = (uint8_t)(crc >> 8U);
}

static uint16_t read_u16(const uint8_t *p)
{
  return (uint16_t)(((uint16_t)p[0] << 8U) | p[1]);
}

static uint8_t next_address(void)
{
  uint8_t address = scan_order[scan_index];
  scan_index = (uint8_t)((scan_index + 1U) % SLAVE_COUNT);
  return address;
}

/* ---------- Modbus 写单个寄存器（功能码 06） ---------- */

static bool write_register(uint8_t address, uint16_t reg, uint16_t value)
{
  uint8_t request[8] = {address, 0x06U, (uint8_t)(reg >> 8U), (uint8_t)reg,
                        (uint8_t)(value >> 8U), (uint8_t)value};
  add_crc(request, 6U);

  while (bus.available()) (void)bus.read();
  bus.write(request, sizeof request);
  bus.flush();

  uint8_t incoming[16];
  size_t used = 0;
  uint32_t start = millis();
  while ((uint32_t)(millis() - start) < POLL_TIMEOUT_MS)
  {
    while (bus.available())
    {
      int byte = bus.read();
      if (used < sizeof incoming) incoming[used++] = (uint8_t)byte;
    }
    if (used >= 8U) break;
    delay(1);
  }
  return used >= 8U && modbus_crc(incoming, 8U) == 0U && incoming[0] == address;
}

static bool apply_command(uint8_t board, const char *command, int value)
{
  uint16_t code;
  if (strcmp(command, "fan") == 0) code = 1U;
  else if (strcmp(command, "relay") == 0) code = 2U;
  else if (strcmp(command, "buzzer") == 0) code = 3U;
  else if (strcmp(command, "led") == 0) code = 4U;
  else return false;

  if (!write_register(board, 0U, code)) return false;
  if (!write_register(board, 1U, (uint16_t)value)) return false;
  return write_register(board, 2U, 1U);
}

#if HAVE_NET
static int json_int(const char *text, const char *key, int fallback)
{
  const char *found = strstr(text, key);
  if (found == nullptr) return fallback;
  return atoi(found + strlen(key));
}

static bool json_string(const char *text, const char *key, char *out, size_t size)
{
  const char *found = strstr(text, key);
  if (found == nullptr) return false;
  found += strlen(key);
  size_t i = 0;
  while (found[i] != '\0' && found[i] != '"' && i + 1U < size)
  {
    out[i] = found[i];
    ++i;
  }
  out[i] = '\0';
  return i > 0U;
}

static void on_command(char *topic, uint8_t *payload, unsigned int length)
{
  (void)topic;
  char text[256];
  char command[16];
  if (length >= sizeof text) return;
  memcpy(text, payload, length);
  text[length] = '\0';

  int board = json_int(text, "\"board\":", 0);
  int value = json_int(text, "\"value\":", 0);
  if (board < 1 || board > 4) return;
  if (!json_string(text, "\"cmd\":\"", command, sizeof command)) return;

  bool ok = apply_command((uint8_t)board, command, value);
  char ack[96];
  snprintf(ack, sizeof ack, "{\"board\":%d,\"cmd\":\"%s\",\"value\":%d,\"ok\":%s}",
           board, command, value, ok ? "true" : "false");
  mqtt.publish("ut/v1/gateway/cmd_ack", ack, false);
  Serial.println(ack);
}

static void net_loop(void)
{
  uint32_t now = millis();
  if (WiFi.status() != WL_CONNECTED)
  {
    if ((uint32_t)(now - last_net_attempt) >= 5000U)
    {
      last_net_attempt = now;
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      Serial.println("{\"net\":\"wifi_connecting\"}");
    }
    return;
  }
  if (!mqtt.connected())
  {
    if ((uint32_t)(now - last_net_attempt) >= 5000U)
    {
      last_net_attempt = now;
      bool connected = (strlen(MQTT_USERNAME) == 0)
        ? mqtt.connect("four-gateway")
        : mqtt.connect("four-gateway", MQTT_USERNAME, MQTT_PASSWORD);
      if (connected)
      {
        mqtt.subscribe(COMMAND_TOPIC, 1);
        mqtt.publish("ut/v1/gateway/status", "online", true);
        Serial.println("{\"net\":\"mqtt_connected\"}");
      }
    }
    return;
  }
  mqtt.loop();
}

static void publish(const char *json)
{
  if (mqtt.connected()) (void)mqtt.publish(TELEMETRY_TOPIC, json, false);
}
#else
static void net_loop(void) { }
static void publish(const char *json) { (void)json; }
#endif

/* ---------- 轮询与解析 ---------- */

static bool response_ok(const uint8_t *frame, uint8_t address)
{
  return modbus_crc(frame, RESPONSE_BYTES) == 0U &&
         frame[0] == address &&
         frame[1] == 0x04U &&
         frame[2] == (uint8_t)(REGISTER_COUNT * 2U) &&
         read_u16(frame + 3U) == MODBUS_SIGNATURE &&
         read_u16(frame + 5U) == address;
}

static void emit_slots(const uint8_t *frame, uint8_t address, uint32_t uptime_s, uint16_t seq)
{
  char json[640];
  size_t used = 0;
  used += snprintf(json + used, sizeof json - used,
                   "{\"board\":%u,\"seq\":%u,\"uptime_s\":%lu,\"slots\":[",
                   address, seq, (unsigned long)uptime_s);
  bool first = true;
  for (uint16_t i = 0; i < 11U; ++i)
  {
    uint16_t base = (uint16_t)(3U + (8U + i * 4U) * 2U);
    uint16_t id = read_u16(frame + base);
    if (id == 0xFFFFU) continue;
    if (used + 64U >= sizeof json) break;
    used += snprintf(json + used, sizeof json - used,
                     "%s{\"id\":%u,\"v\":%u,\"a\":%u,\"s\":%u}",
                     first ? "" : ",", id,
                     read_u16(frame + base + 2U),
                     read_u16(frame + base + 4U),
                     read_u16(frame + base + 6U));
    first = false;
  }
  snprintf(json + used, sizeof json - used, "]}");
  Serial.println(json);
  publish(json);
}

static void poll_slave(uint8_t address)
{
  uint8_t request[8] = {address, 0x04U, 0x00U, 0x00U,
                        (uint8_t)(REGISTER_COUNT >> 8U), (uint8_t)REGISTER_COUNT};
  add_crc(request, 6U);

  while (bus.available()) (void)bus.read();
  ++polls;
  bus.write(request, sizeof request);
  bus.flush();

  uint8_t incoming[192];
  size_t used = 0;
  bool overflow = false;
  uint32_t start = millis();
  uint32_t last_byte = start;
  while ((uint32_t)(millis() - start) < POLL_TIMEOUT_MS)
  {
    while (bus.available())
    {
      int value = bus.read();
      if (used < sizeof incoming) incoming[used++] = (uint8_t)value;
      else overflow = true;
      last_byte = millis();
    }
    if (used >= RESPONSE_BYTES && (uint32_t)(millis() - last_byte) >= 10U) break;
    delay(1);
  }

  if (!overflow)
  {
    for (size_t offset = 0; offset + RESPONSE_BYTES <= used; ++offset)
    {
      const uint8_t *reply = incoming + offset;
      if (!response_ok(reply, address)) continue;
      uint32_t uptime = ((uint32_t)read_u16(reply + 3U + 4U * 2U) << 16U) |
                        read_u16(reply + 3U + 5U * 2U);
      uint16_t seq = read_u16(reply + 3U + 6U * 2U);
      emit_slots(reply, address, uptime, seq);
      return;
    }
  }

  char error[96];
  snprintf(error, sizeof error, "{\"board\":%u,\"error\":\"%s\",\"rx\":%u}",
           address, used ? "malformed" : "timeout", (unsigned)used);
  Serial.println(error);
}

void setup()
{
  Serial.begin(115200);
  delay(300);
  bus.setRxBufferSize(256);
  bus.begin(19200, SERIAL_8E1, 18, 17);
  delay(300);
  Serial.println("FOUR_GATEWAY_V2 1-4 19200-8E1 READ_WRITE");

#if HAVE_NET
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  last_net_attempt = millis() - 5000U;
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(on_command);
  mqtt.setBufferSize(1024);
  mqtt.setKeepAlive(30);
#endif
}

void loop()
{
  static uint32_t last_poll;
  net_loop();
  if ((uint32_t)(millis() - last_poll) >= POLL_INTERVAL_MS)
  {
    last_poll = millis();
    poll_slave(next_address());
  }
  delay(1);
}
