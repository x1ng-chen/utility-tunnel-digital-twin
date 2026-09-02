#include "main.h"

#include <stdio.h>
#include <string.h>

#define NODE_ID                         "node-a"
#define TELEMETRY_INTERVAL_MS           2000U
#define LED_INTERVAL_MS                  500U
#define SHT30_COMMAND_HIGH_REPEATABLE    0x2400U
#define SHT30_ADDRESS_44                 0x44U
#define SHT30_ADDRESS_45                 0x45U
#define ESP_RX_LINE_SIZE                  384U
#define ESP_RX_QUEUE_CAPACITY             4U
#define COMMAND_ID_MAX                    40U
#define COMMAND_ACTION_MAX                24U
#define COMMAND_DEDUP_CAPACITY            8U
#define COMMAND_TTL_MAX_MS                30000U
#define BUZZER_Pin                         GPIO_PIN_0
#define BUZZER_GPIO_Port                   GPIOB
#define RELAY_Pin                          GPIO_PIN_1
#define RELAY_GPIO_Port                    GPIOA
#define WS2812_Pin                         GPIO_PIN_15
#define WS2812_GPIO_Port                   GPIOB
#define WS2812_PIXEL_COUNT                 9U
#define WS2812_TEST_BRIGHTNESS             32U

typedef struct
{
  GPIO_TypeDef *port;
  uint16_t scl_pin;
  uint16_t sda_pin;
} SoftI2cBus;

typedef struct
{
  uint8_t online;
  int16_t temperature_centi_c;
  uint16_t humidity_centi_rh;
} Sht30Reading;

static const SoftI2cBus i2c1_bus = {GPIOB, GPIO_PIN_6, GPIO_PIN_7};
static const SoftI2cBus i2c2_bus = {GPIOB, GPIO_PIN_10, GPIO_PIN_11};
UART_HandleTypeDef huart2;
UART_HandleTypeDef huart1;
static uint8_t esp_rx_character;
static volatile char esp_rx_lines[ESP_RX_QUEUE_CAPACITY][ESP_RX_LINE_SIZE];
static volatile uint16_t esp_rx_length;
static volatile uint8_t esp_rx_discarding;
static volatile uint16_t esp_rx_lengths[ESP_RX_QUEUE_CAPACITY];
static volatile uint32_t esp_rx_received_at[ESP_RX_QUEUE_CAPACITY];
static volatile uint8_t esp_rx_head;
static volatile uint8_t esp_rx_tail;
static volatile uint8_t esp_rx_count;
static char recent_command_ids[COMMAND_DEDUP_CAPACITY][COMMAND_ID_MAX + 1U];
static uint8_t recent_command_next;
static uint8_t buzzer_active;
static uint32_t buzzer_started_at;
static uint32_t buzzer_duration_ms;
static uint8_t relay_active;
static uint32_t relay_started_at;
static uint32_t relay_duration_ms;
static uint8_t ws2812_encoded[WS2812_PIXEL_COUNT * 15U];

void SystemClock_Config(void);
void Error_Handler(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_USART1_UART_Init(void);
static uint8_t Sht30_Read(const SoftI2cBus *bus, uint8_t address, Sht30Reading *reading);
static void SendTelemetry(const Sht30Reading readings[3]);
static void Command_Poll(void);
static void Buzzer_Silence(void);
static void Buzzer_Start(uint32_t duration_ms);
static void Relay_Disable(void);
static void Relay_Enable(uint32_t duration_ms);
static void MX_WS2812_SPI_Init(void);
static void Ws2812_Show(uint8_t red, uint8_t green, uint8_t blue);
static void Ws2812_Off(void);

/* The existing Cube package omitted HAL I2C. These deliberately slow,
 * open-drain routines are sufficient for initial SHT30 bring-up at 500 Hz. */
static void I2c_Delay(void) { HAL_Delay(1U); }
static void I2c_Sda(const SoftI2cBus *bus, GPIO_PinState state)
{
  HAL_GPIO_WritePin(bus->port, bus->sda_pin, state);
}
static void I2c_Scl(const SoftI2cBus *bus, GPIO_PinState state)
{
  HAL_GPIO_WritePin(bus->port, bus->scl_pin, state);
}
static void I2c_Start(const SoftI2cBus *bus)
{
  I2c_Sda(bus, GPIO_PIN_SET); I2c_Scl(bus, GPIO_PIN_SET); I2c_Delay();
  I2c_Sda(bus, GPIO_PIN_RESET); I2c_Delay(); I2c_Scl(bus, GPIO_PIN_RESET);
}
static void I2c_Stop(const SoftI2cBus *bus)
{
  I2c_Sda(bus, GPIO_PIN_RESET); I2c_Delay(); I2c_Scl(bus, GPIO_PIN_SET);
  I2c_Delay(); I2c_Sda(bus, GPIO_PIN_SET); I2c_Delay();
}
static uint8_t I2c_WriteByte(const SoftI2cBus *bus, uint8_t value)
{
  uint8_t bit;
  for (bit = 0U; bit < 8U; ++bit)
  {
    I2c_Sda(bus, (value & 0x80U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    I2c_Delay(); I2c_Scl(bus, GPIO_PIN_SET); I2c_Delay(); I2c_Scl(bus, GPIO_PIN_RESET);
    value <<= 1U;
  }
  I2c_Sda(bus, GPIO_PIN_SET); I2c_Delay(); I2c_Scl(bus, GPIO_PIN_SET); I2c_Delay();
  bit = (HAL_GPIO_ReadPin(bus->port, bus->sda_pin) == GPIO_PIN_RESET) ? 1U : 0U;
  I2c_Scl(bus, GPIO_PIN_RESET);
  return bit;
}
static uint8_t I2c_ReadByte(const SoftI2cBus *bus, uint8_t acknowledge)
{
  uint8_t bit;
  uint8_t value = 0U;
  I2c_Sda(bus, GPIO_PIN_SET);
  for (bit = 0U; bit < 8U; ++bit)
  {
    value <<= 1U;
    I2c_Delay(); I2c_Scl(bus, GPIO_PIN_SET); I2c_Delay();
    if (HAL_GPIO_ReadPin(bus->port, bus->sda_pin) == GPIO_PIN_SET) value |= 1U;
    I2c_Scl(bus, GPIO_PIN_RESET);
  }
  I2c_Sda(bus, acknowledge ? GPIO_PIN_RESET : GPIO_PIN_SET);
  I2c_Delay(); I2c_Scl(bus, GPIO_PIN_SET); I2c_Delay(); I2c_Scl(bus, GPIO_PIN_RESET);
  I2c_Sda(bus, GPIO_PIN_SET);
  return value;
}
static uint8_t Sht30_Crc(const uint8_t *data, uint8_t length)
{
  uint8_t crc = 0xFFU;
  uint8_t i;
  while (length-- > 0U)
  {
    crc ^= *data++;
    for (i = 0U; i < 8U; ++i)
      crc = (crc & 0x80U) ? (uint8_t)((crc << 1U) ^ 0x31U) : (uint8_t)(crc << 1U);
  }
  return crc;
}
static uint8_t Sht30_Read(const SoftI2cBus *bus, uint8_t address, Sht30Reading *reading)
{
  uint8_t response[6];
  uint8_t i;
  uint16_t raw_temperature;
  uint16_t raw_humidity;

  reading->online = 0U;
  I2c_Start(bus);
  if (!I2c_WriteByte(bus, (uint8_t)(address << 1U)) ||
      !I2c_WriteByte(bus, (uint8_t)(SHT30_COMMAND_HIGH_REPEATABLE >> 8U)) ||
      !I2c_WriteByte(bus, (uint8_t)SHT30_COMMAND_HIGH_REPEATABLE))
  {
    I2c_Stop(bus); return 0U;
  }
  I2c_Stop(bus); HAL_Delay(20U); I2c_Start(bus);
  if (!I2c_WriteByte(bus, (uint8_t)((address << 1U) | 1U)))
  {
    I2c_Stop(bus); return 0U;
  }
  for (i = 0U; i < sizeof(response); ++i)
    response[i] = I2c_ReadByte(bus, i < (sizeof(response) - 1U));
  I2c_Stop(bus);
  if (Sht30_Crc(response, 2U) != response[2] || Sht30_Crc(&response[3], 2U) != response[5]) return 0U;
  raw_temperature = (uint16_t)((response[0] << 8U) | response[1]);
  raw_humidity = (uint16_t)((response[3] << 8U) | response[4]);
  reading->temperature_centi_c = (int16_t)(((int32_t)17500 * raw_temperature) / 65535 - 4500);
  reading->humidity_centi_rh = (uint16_t)(((uint32_t)10000 * raw_humidity) / 65535U);
  reading->online = 1U;
  return 1U;
}
static void SendTelemetry(const Sht30Reading readings[3])
{
  char message[420];
  static uint32_t sequence = 0U;
  int32_t temperature_abs;
  const char *temperature_sign;
  const char *quality;
  int length;

  /* Slot 1 is the physically installed environmental sensor.  Report only
   * that truthful source in the platform contract; Slots 2/3 are reserved
   * buses and must not create fabricated zero-value readings. */
  sequence++;
  temperature_abs = readings[0].temperature_centi_c;
  temperature_sign = "";
  if (temperature_abs < 0)
  {
    temperature_sign = "-";
    temperature_abs = -temperature_abs;
  }
  quality = readings[0].online ? "good" : "missing";
  length = snprintf(message, sizeof(message),
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
    "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":%s%ld.%02ld,\"unit\":\"degC\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"ENV-01\",\"metric\":\"humidity\",\"value\":%lu.%02lu,\"unit\":\"%%RH\",\"quality\":\"%s\"}]}\r\n",
    (unsigned long)sequence,
    temperature_sign, (long)(temperature_abs / 100), (long)(temperature_abs % 100), quality,
    (unsigned long)(readings[0].humidity_centi_rh / 100U),
    (unsigned long)(readings[0].humidity_centi_rh % 100U), quality);
  if (length > 0 && length < (int)sizeof(message))
  {
    (void)HAL_UART_Transmit(&huart2, (uint8_t *)message, (uint16_t)length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message, (uint16_t)length, 1000U);
  }
}

static uint8_t Json_ReadString(const char *json, const char *key,
                               char *destination, size_t destination_size)
{
  char needle[32];
  const char *cursor;
  size_t length = 0U;

  if ((snprintf(needle, sizeof(needle), "\"%s\"", key) <= 0) ||
      (destination_size == 0U)) return 0U;
  cursor = strstr(json, needle);
  if (cursor == NULL) return 0U;
  cursor += strlen(needle);
  while ((*cursor == ' ') || (*cursor == '\t')) ++cursor;
  if (*cursor++ != ':') return 0U;
  while ((*cursor == ' ') || (*cursor == '\t')) ++cursor;
  if (*cursor++ != '"') return 0U;
  while ((*cursor != '\0') && (*cursor != '"'))
  {
    if ((*cursor == '\\') || ((unsigned char)*cursor < 0x20U) ||
        (length >= (destination_size - 1U))) return 0U;
    destination[length++] = *cursor++;
  }
  if ((*cursor != '"') || (length == 0U)) return 0U;
  destination[length] = '\0';
  return 1U;
}

static uint8_t Json_ReadUnsigned(const char *json, const char *key, uint32_t *value)
{
  char needle[32];
  const char *cursor;
  uint32_t parsed = 0U;
  uint8_t digits = 0U;

  if (snprintf(needle, sizeof(needle), "\"%s\"", key) <= 0) return 0U;
  cursor = strstr(json, needle);
  if (cursor == NULL) return 0U;
  cursor += strlen(needle);
  while ((*cursor == ' ') || (*cursor == '\t')) ++cursor;
  if (*cursor++ != ':') return 0U;
  while ((*cursor == ' ') || (*cursor == '\t')) ++cursor;
  while ((*cursor >= '0') && (*cursor <= '9'))
  {
    if ((parsed > 429496729U) || ((parsed == 429496729U) && (*cursor > '5'))) return 0U;
    parsed = (parsed * 10U) + (uint32_t)(*cursor++ - '0');
    ++digits;
  }
  if (digits == 0U) return 0U;
  *value = parsed;
  return 1U;
}

static uint8_t CommandId_IsSafe(const char *command_id)
{
  size_t index;
  const size_t length = strlen(command_id);
  if ((length == 0U) || (length > COMMAND_ID_MAX)) return 0U;
  for (index = 0U; index < length; ++index)
  {
    const char value = command_id[index];
    if (!(((value >= 'a') && (value <= 'z')) || ((value >= 'A') && (value <= 'Z')) ||
          ((value >= '0') && (value <= '9')) || (value == '-') || (value == '_'))) return 0U;
  }
  return 1U;
}

static uint8_t CommandId_IsDuplicate(const char *command_id)
{
  uint8_t index;
  for (index = 0U; index < COMMAND_DEDUP_CAPACITY; ++index)
    if (strcmp(recent_command_ids[index], command_id) == 0) return 1U;
  return 0U;
}

static void CommandId_Remember(const char *command_id)
{
  (void)snprintf(recent_command_ids[recent_command_next], COMMAND_ID_MAX + 1U, "%s", command_id);
  recent_command_next = (uint8_t)((recent_command_next + 1U) % COMMAND_DEDUP_CAPACITY);
}

static void Command_SendAck(const char *command_id, const char *status, const char *reason)
{
  char json[220];
  const int length = snprintf(json, sizeof(json),
    "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"%s\",\"status\":\"%s\",\"reason\":\"%s\"}\r\n",
    command_id, status, reason);
  if ((length > 0) && (length < (int)sizeof(json)))
  {
    (void)HAL_UART_Transmit(&huart2, (uint8_t *)json, (uint16_t)length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)json, (uint16_t)length, 1000U);
  }
}

/* MH-FMG is a high-level-triggered active buzzer.  PB0 is deliberately
 * dedicated to it and starts low so a reset cannot leave the buzzer sounding. */
static void Buzzer_Silence(void)
{
  HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_RESET);
  buzzer_active = 0U;
}

static void Buzzer_Start(uint32_t duration_ms)
{
  HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_SET);
  buzzer_started_at = HAL_GetTick();
  buzzer_duration_ms = duration_ms;
  buzzer_active = 1U;
}

/* The installed relay module is set to high-level trigger.  PA1 is held low
 * before it is configured as an output, so power-up, timeout and safe-state are off. */
static void Relay_Disable(void)
{
  HAL_GPIO_WritePin(RELAY_GPIO_Port, RELAY_Pin, GPIO_PIN_RESET);
  relay_active = 0U;
}

static void Relay_Enable(uint32_t duration_ms)
{
  HAL_GPIO_WritePin(RELAY_GPIO_Port, RELAY_Pin, GPIO_PIN_SET);
  relay_started_at = HAL_GetTick();
  relay_duration_ms = duration_ms;
  relay_active = 1U;
}

/* SPI2 on PB15 runs at 4 MHz from the 8 MHz APB1 clock.  Each WS2812 bit is
 * encoded as five SPI bits: 0=10000 and 1=11100, giving a 1.25 us cell. */
static uint8_t *Ws2812_EncodeByte(uint8_t value, uint8_t *output,
                                  uint8_t *pending, uint8_t *pending_bits)
{
  uint8_t source_bit;
  for (source_bit = 0x80U; source_bit != 0U; source_bit >>= 1U)
  {
    uint8_t encoded = ((value & source_bit) != 0U) ? 0x1CU : 0x10U;
    uint8_t encoded_bit;
    for (encoded_bit = 0x10U; encoded_bit != 0U; encoded_bit >>= 1U)
    {
      *pending = (uint8_t)((*pending << 1U) | (((encoded & encoded_bit) != 0U) ? 1U : 0U));
      if (++(*pending_bits) == 8U)
      {
        *output++ = *pending;
        *pending = 0U;
        *pending_bits = 0U;
      }
    }
  }
  return output;
}

static void MX_WS2812_SPI_Init(void)
{
  GPIO_InitTypeDef gpio = {0};
  __HAL_RCC_DMA1_CLK_ENABLE();
  __HAL_RCC_SPI2_CLK_ENABLE();
  gpio.Pin = WS2812_Pin;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(WS2812_GPIO_Port, &gpio);
  SPI2->CR1 = SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI;
  SPI2->CR2 = 0U;
  SPI2->CR1 |= SPI_CR1_SPE;
}

static void Ws2812_SendEncoded(uint16_t length)
{
  /* Keep MOSI low for one complete SPI byte before DMA begins.  This prevents
   * the first WS2812 high pulse from inheriting the SPI start half-cycle. */
  while ((SPI2->SR & SPI_SR_TXE) == 0U) { }
  *(__IO uint8_t *)&SPI2->DR = 0U;
  while ((SPI2->SR & SPI_SR_BSY) != 0U) { }
  (void)SPI2->DR;
  (void)SPI2->SR;

  DMA1_Channel5->CCR = 0U;
  DMA1_Channel5->CNDTR = length;
  DMA1_Channel5->CPAR = (uint32_t)&SPI2->DR;
  DMA1_Channel5->CMAR = (uint32_t)ws2812_encoded;
  DMA1_Channel5->CCR = DMA_CCR_DIR | DMA_CCR_MINC | DMA_CCR_PL_1;
  SPI2->CR2 |= SPI_CR2_TXDMAEN;
  DMA1_Channel5->CCR |= DMA_CCR_EN;
  while (DMA1_Channel5->CNDTR != 0U) { }
  while ((SPI2->SR & SPI_SR_BSY) != 0U) { }
  DMA1_Channel5->CCR = 0U;
  SPI2->CR2 &= ~SPI_CR2_TXDMAEN;
  (void)SPI2->DR;
  (void)SPI2->SR;
}

static void Ws2812_Show(uint8_t red, uint8_t green, uint8_t blue)
{
  uint8_t *output = ws2812_encoded;
  uint8_t pending = 0U;
  uint8_t pending_bits = 0U;
  uint8_t pixel;

  for (pixel = 0U; pixel < WS2812_PIXEL_COUNT; ++pixel)
  {
    output = Ws2812_EncodeByte(green, output, &pending, &pending_bits); /* WS2812B serial order is GRB. */
    output = Ws2812_EncodeByte(red, output, &pending, &pending_bits);
    output = Ws2812_EncodeByte(blue, output, &pending, &pending_bits);
  }
  Ws2812_SendEncoded((uint16_t)(output - ws2812_encoded));
  HAL_Delay(1U); /* Low reset interval exceeds the WS2812B latch requirement. */
}

static void Ws2812_Off(void) { Ws2812_Show(0U, 0U, 0U); }

static uint8_t Command_IsForThisController(const char *topic)
{
  static const char command_topic[] = "ut/v1/CTRL-01/cmd";
  const size_t length = sizeof(command_topic) - 1U;
  return (strncmp(topic, command_topic, length) == 0) &&
         ((topic[length] == '\0') || (topic[length] == '/'));
}

static void Command_HandleLine(char *line, uint32_t received_at)
{
  char *topic;
  char *payload;
  char command_id[COMMAND_ID_MAX + 1U];
  char action[COMMAND_ACTION_MAX + 1U];
  uint32_t ttl_ms;

  if (strncmp(line, "MQTT|", 5U) != 0) return;
  topic = line + 5U;
  payload = strchr(topic, '|');
  if (payload == NULL) return;
  *payload++ = '\0';
  if (!Command_IsForThisController(topic)) return;
  if (!Json_ReadString(payload, "schema", action, sizeof(action)) ||
      (strcmp(action, "ut.command.v1") != 0) ||
      !Json_ReadString(payload, "cmdId", command_id, sizeof(command_id)) ||
      !CommandId_IsSafe(command_id))
  {
    Command_SendAck("unknown", "rejected", "invalid_command");
    return;
  }
  if (CommandId_IsDuplicate(command_id))
  {
    Command_SendAck(command_id, "duplicate", "cmdId_seen");
    return;
  }
  if (!Json_ReadString(payload, "action", action, sizeof(action)) ||
      !Json_ReadUnsigned(payload, "ttlMs", &ttl_ms) || (ttl_ms == 0U) ||
      (ttl_ms > COMMAND_TTL_MAX_MS))
  {
    CommandId_Remember(command_id);
    Command_SendAck(command_id, "rejected", "invalid_or_missing_ttl");
    return;
  }
  if ((HAL_GetTick() - received_at) >= ttl_ms)
  {
    CommandId_Remember(command_id);
    Command_SendAck(command_id, "expired", "ttl_elapsed");
    return;
  }

  CommandId_Remember(command_id);
  if (strcmp(action, "status") == 0)
    Command_SendAck(command_id, "accepted", "controller_online");
  else if (strcmp(action, "safe_state") == 0)
  {
    Buzzer_Silence();
    Relay_Disable();
    Ws2812_Off();
    Command_SendAck(command_id, "accepted", "safe_state_applied");
  }
  else if (strcmp(action, "buzzer_off") == 0)
  {
    Buzzer_Silence();
    Command_SendAck(command_id, "accepted", "buzzer_silent");
  }
  else if (strcmp(action, "buzzer_on") == 0)
  {
    const uint32_t elapsed_ms = HAL_GetTick() - received_at;
    Buzzer_Start(ttl_ms - elapsed_ms);
    Command_SendAck(command_id, "accepted", "buzzer_active");
  }
  else if (strcmp(action, "relay_off") == 0)
  {
    Relay_Disable();
    Command_SendAck(command_id, "accepted", "relay_off");
  }
  else if (strcmp(action, "relay_on") == 0)
  {
    const uint32_t elapsed_ms = HAL_GetTick() - received_at;
    Relay_Enable(ttl_ms - elapsed_ms);
    Command_SendAck(command_id, "accepted", "relay_active");
  }
  else if (strcmp(action, "led_off") == 0)
  {
    Ws2812_Off();
    Command_SendAck(command_id, "accepted", "led_off");
  }
  else if (strcmp(action, "led_red") == 0)
  {
    Ws2812_Show(WS2812_TEST_BRIGHTNESS, 0U, 0U);
    Command_SendAck(command_id, "accepted", "led_red");
  }
  else if (strcmp(action, "led_green") == 0)
  {
    Ws2812_Show(0U, WS2812_TEST_BRIGHTNESS, 0U);
    Command_SendAck(command_id, "accepted", "led_green");
  }
  else if (strcmp(action, "led_blue") == 0)
  {
    Ws2812_Show(0U, 0U, WS2812_TEST_BRIGHTNESS);
    Command_SendAck(command_id, "accepted", "led_blue");
  }
  else
    Command_SendAck(command_id, "rejected", "actuator_unmapped");
}

static void Command_Poll(void)
{
  char line[ESP_RX_LINE_SIZE];
  uint16_t length;
  uint32_t received_at;

  if (esp_rx_count == 0U) return;
  __disable_irq();
  length = esp_rx_lengths[esp_rx_head];
  if (length >= sizeof(line)) length = sizeof(line) - 1U;
  (void)memcpy(line, (const void *)esp_rx_lines[esp_rx_head], length);
  line[length] = '\0';
  received_at = esp_rx_received_at[esp_rx_head];
  esp_rx_head = (uint8_t)((esp_rx_head + 1U) % ESP_RX_QUEUE_CAPACITY);
  --esp_rx_count;
  __enable_irq();
  Command_HandleLine(line, received_at);
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
  if (uart->Instance != USART2) return;
  if (esp_rx_character == '\n')
  {
    if ((esp_rx_discarding == 0U) && (esp_rx_length > 0U) &&
        (esp_rx_count < ESP_RX_QUEUE_CAPACITY))
    {
      esp_rx_lengths[esp_rx_tail] = esp_rx_length;
      esp_rx_received_at[esp_rx_tail] = HAL_GetTick();
      esp_rx_tail = (uint8_t)((esp_rx_tail + 1U) % ESP_RX_QUEUE_CAPACITY);
      ++esp_rx_count;
    }
    esp_rx_length = 0U;
    esp_rx_discarding = 0U;
  }
  else if ((esp_rx_character != '\r') && (esp_rx_discarding == 0U))
  {
    if (esp_rx_count >= ESP_RX_QUEUE_CAPACITY) esp_rx_discarding = 1U;
    else if (esp_rx_length < (ESP_RX_LINE_SIZE - 1U))
      esp_rx_lines[esp_rx_tail][esp_rx_length++] = (char)esp_rx_character;
    else { esp_rx_length = 0U; esp_rx_discarding = 1U; }
  }
  (void)HAL_UART_Receive_IT(&huart2, &esp_rx_character, 1U);
}
int main(void)
{
  Sht30Reading readings[3] = {0};
  uint32_t last_telemetry = HAL_MAX_DELAY;
  uint32_t last_led = HAL_MAX_DELAY;
  HAL_Init(); SystemClock_Config(); MX_GPIO_Init(); MX_WS2812_SPI_Init();
  Ws2812_Off();
  MX_USART1_UART_Init(); MX_USART2_UART_Init();
  if (HAL_UART_Receive_IT(&huart2, &esp_rx_character, 1U) != HAL_OK) Error_Handler();
  (void)HAL_UART_Transmit(&huart1, (uint8_t *)"#NODE node-a boot\r\n", 19U, 1000U);
  for (;;)
  {
    Command_Poll();
    /* A command may start a timed actuator. Read the clock afterwards so a
     * just-written start timestamp can never appear to be in the future. */
    uint32_t now = HAL_GetTick();
    if ((buzzer_active != 0U) && ((now - buzzer_started_at) >= buzzer_duration_ms))
      Buzzer_Silence();
    if ((relay_active != 0U) && ((now - relay_started_at) >= relay_duration_ms))
      Relay_Disable();
    if ((now - last_telemetry) >= TELEMETRY_INTERVAL_MS)
    {
      (void)Sht30_Read(&i2c1_bus, SHT30_ADDRESS_44, &readings[0]);
      (void)Sht30_Read(&i2c1_bus, SHT30_ADDRESS_45, &readings[1]);
      (void)Sht30_Read(&i2c2_bus, SHT30_ADDRESS_44, &readings[2]);
      SendTelemetry(readings); last_telemetry = now;
    }
    if ((now - last_led) >= LED_INTERVAL_MS)
    {
      HAL_GPIO_TogglePin(LED_GPIO_Port, LED_Pin); last_led = now;
    }
  }
}
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef oscillator = {0};
  RCC_ClkInitTypeDef clock = {0};
  oscillator.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  oscillator.HSIState = RCC_HSI_ON;
  oscillator.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  oscillator.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&oscillator) != HAL_OK) Error_Handler();
  clock.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  clock.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  clock.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clock.APB1CLKDivider = RCC_HCLK_DIV1;
  clock.APB2CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_0) != HAL_OK) Error_Handler();
}
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef gpio = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOB_CLK_ENABLE();
  HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(RELAY_GPIO_Port, RELAY_Pin, GPIO_PIN_RESET);
  gpio.Pin = LED_Pin; gpio.Mode = GPIO_MODE_OUTPUT_PP; gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LED_GPIO_Port, &gpio);
  gpio.Pin = BUZZER_Pin; gpio.Mode = GPIO_MODE_OUTPUT_PP; gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(BUZZER_GPIO_Port, &gpio);
  gpio.Pin = RELAY_Pin; gpio.Mode = GPIO_MODE_OUTPUT_PP; gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(RELAY_GPIO_Port, &gpio);
  HAL_GPIO_WritePin(GPIOB, i2c1_bus.scl_pin | i2c1_bus.sda_pin | i2c2_bus.scl_pin | i2c2_bus.sda_pin, GPIO_PIN_SET);
  gpio.Pin = i2c1_bus.scl_pin | i2c1_bus.sda_pin | i2c2_bus.scl_pin | i2c2_bus.sda_pin;
  gpio.Mode = GPIO_MODE_OUTPUT_OD; gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &gpio);
}
static void MX_USART2_UART_Init(void)
{
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 9600;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK) Error_Handler();
}
static void MX_USART1_UART_Init(void)
{
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 9600;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK) Error_Handler();
}
void Error_Handler(void)
{
  __disable_irq();
  while (1) { }
}
