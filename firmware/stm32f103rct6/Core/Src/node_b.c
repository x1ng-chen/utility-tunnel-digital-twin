#include "main.h"
#include "st7735.h"

#include <stdio.h>
#include <string.h>

#define NODE_ID "node-b"
#define ESP_HEARTBEAT_INTERVAL_MS 2000U
#define LED_INTERVAL_MS 500U
#define ESP_RX_LINE_SIZE 256U

typedef struct
{
  uint8_t online;
  int16_t temperature_centi_c;
  uint16_t humidity_centi_rh;
} PeerReading;

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;
static uint8_t esp_rx_character;
static volatile char esp_rx_line[ESP_RX_LINE_SIZE];
static volatile uint16_t esp_rx_length;
static volatile uint8_t esp_rx_line_ready;

void SystemClock_Config(void);
void Error_Handler(void);
static void MX_GPIO_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_USART2_UART_Init(void);
static void DrawStatus(uint32_t received_count, const PeerReading *peer);
static void UpdatePeerDisplay(uint32_t received_count, const PeerReading *peer);
static void SendHeartbeat(void);
static void PollEsp(uint32_t *received_count, PeerReading *peer);

static void DrawStatus(uint32_t received_count, const PeerReading *peer)
{
  ST7735_Clear(LCD_BLACK);
  ST7735_DrawString(24, 10, "NODE B", LCD_GREEN, LCD_BLACK);
  ST7735_DrawString(8, 80, "ESP: CTRL-02", LCD_WHITE, LCD_BLACK);
  UpdatePeerDisplay(received_count, peer);
}

/* A full 128x128 software-SPI redraw blocks UART polling too long. Keep the
 * fixed labels and update only the three changing text rows on each message. */
static void UpdatePeerDisplay(uint32_t received_count, const PeerReading *peer)
{
  char line[24];
  long temperature;

  ST7735_FillRect(0, 30, LCD_WIDTH, 22, LCD_BLACK);
  ST7735_FillRect(0, 52, LCD_WIDTH, 22, LCD_BLACK);
  ST7735_FillRect(0, 100, LCD_WIDTH, 22, LCD_BLACK);
  if (peer->online)
  {
    temperature = peer->temperature_centi_c;
    (void)snprintf(line, sizeof(line), "A T:%ld.%02ldC", temperature / 100L,
                   (temperature < 0L ? -temperature : temperature) % 100L);
    ST7735_DrawString(4, 34, line, LCD_CYAN, LCD_BLACK);
    (void)snprintf(line, sizeof(line), "A H:%u.%02u%%", peer->humidity_centi_rh / 100U,
                   peer->humidity_centi_rh % 100U);
    ST7735_DrawString(4, 56, line, LCD_WHITE, LCD_BLACK);
  }
  else
  {
    ST7735_DrawString(8, 38, "A: WAIT DATA", LCD_YELLOW, LCD_BLACK);
  }
  (void)snprintf(line, sizeof(line), "RX: %lu", (unsigned long)received_count);
  ST7735_DrawString(8, 104, line, LCD_GREEN, LCD_BLACK);
}

static uint8_t DecodePeerReading(const char *line, PeerReading *peer)
{
  const char *payload = strchr(line, '|');
  int online;
  int temperature;
  unsigned int humidity;

  if (payload == NULL) return 0U;
  payload = strchr(payload + 1, '|');
  if ((payload == NULL) || (strstr(payload, "\"schema\":\"ut.node-b.peer.v1\"") == NULL)) return 0U;
  if (sscanf(payload, "|{\"schema\":\"ut.node-b.peer.v1\",\"source\":\"node-a\",\"online\":%d,\"temperatureCentiC\":%d,\"humidityCentiRH\":%u}",
             &online, &temperature, &humidity) != 3) return 0U;
  if ((temperature < -4500) || (temperature > 13000) || (humidity > 10000U)) return 0U;
  peer->online = online ? 1U : 0U;
  peer->temperature_centi_c = (int16_t)temperature;
  peer->humidity_centi_rh = (uint16_t)humidity;
  return 1U;
}

static void SendHeartbeat(void)
{
  char message[128];
  static uint32_t sequence;
  const int length = snprintf(message, sizeof(message),
    "{\"schema\":\"ut.node-b.status.v1\",\"nodeId\":\"%s\",\"seq\":%lu,\"display\":\"online\"}\r\n",
    NODE_ID, (unsigned long)++sequence);

  if ((length > 0) && (length < (int)sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart2, (uint8_t *)message, (uint16_t)length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message, (uint16_t)length, 1000U);
  }
}

static void PollEsp(uint32_t *received_count, PeerReading *peer)
{
  char line[ESP_RX_LINE_SIZE];
  uint16_t length;

  if (esp_rx_line_ready == 0U) return;
  __disable_irq();
  length = esp_rx_length;
  if (length >= sizeof(line)) length = sizeof(line) - 1U;
  (void)memcpy(line, (const void *)esp_rx_line, length);
  line[length] = '\0';
  esp_rx_line_ready = 0U;
  esp_rx_length = 0U;
  __enable_irq();

  if (length > 0U)
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)"#ESP ", 5U, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)line, length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)"\r\n", 2U, 1000U);
    if ((strncmp(line, "MQTT|", 5U) == 0) && DecodePeerReading(line, peer))
    {
      ++*received_count;
      UpdatePeerDisplay(*received_count, peer);
    }
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
  if (uart->Instance != USART2) return;
  if (esp_rx_character == '\n')
  {
    if ((esp_rx_line_ready == 0U) && (esp_rx_length > 0U)) esp_rx_line_ready = 1U;
  }
  else if ((esp_rx_character != '\r') && (esp_rx_line_ready == 0U) &&
           (esp_rx_length < (ESP_RX_LINE_SIZE - 1U)))
  {
    esp_rx_line[esp_rx_length++] = (char)esp_rx_character;
  }
  (void)HAL_UART_Receive_IT(&huart2, &esp_rx_character, 1U);
}

int main(void)
{
  uint32_t last_heartbeat = HAL_MAX_DELAY;
  uint32_t last_led = HAL_MAX_DELAY;
  uint32_t received_count = 0U;
  PeerReading peer = {0};

  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
  MX_USART1_UART_Init();
  MX_USART2_UART_Init();
  if (HAL_UART_Receive_IT(&huart2, &esp_rx_character, 1U) != HAL_OK) Error_Handler();
  ST7735_Init();
  DrawStatus(received_count, &peer);
  (void)HAL_UART_Transmit(&huart1, (uint8_t *)"#NODE node-b boot\r\n", 19U, 1000U);

  for (;;)
  {
    const uint32_t now = HAL_GetTick();
    PollEsp(&received_count, &peer);
    if ((now - last_heartbeat) >= ESP_HEARTBEAT_INTERVAL_MS)
    {
      SendHeartbeat();
      last_heartbeat = now;
    }
    if ((now - last_led) >= LED_INTERVAL_MS)
    {
      HAL_GPIO_TogglePin(LED_GPIO_Port, LED_Pin);
      last_led = now;
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
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin, GPIO_PIN_RESET);
  gpio.Pin = LED_Pin;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LED_GPIO_Port, &gpio);

  /* PA5/PA7 are configured as SPI1 SCK/MOSI by ST7735_Init(). */
  gpio.Pin = TFT_RES_Pin | TFT_DC_Pin | TFT_CS_Pin | TFT_BLK_Pin;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(GPIOB, &gpio);
  HAL_GPIO_WritePin(GPIOB, gpio.Pin, GPIO_PIN_RESET);
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

void Error_Handler(void)
{
  __disable_irq();
  while (1) { }
}
