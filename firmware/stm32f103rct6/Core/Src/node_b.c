#include "main.h"
#include "joystick.h"
#include "st7735.h"
#include "st7735_bus.h"
#include "ui_state.h"

#include <stdio.h>
#include <string.h>

#define NODE_ID "node-b"
#define ESP_HEARTBEAT_INTERVAL_MS 2000U
#define LED_INTERVAL_MS 500U
#define ESP_RX_LINE_SIZE 256U
#define UI_TEST_LINE_SIZE 48U
#define DISPLAY_TEST_DIRTY_COUNT 1000U
#define DISPLAY_TEST_COLOR_COUNT 3U
#define DISPLAY_TEST_PRIMITIVE_COUNT (DISPLAY_TEST_DIRTY_COUNT + DISPLAY_TEST_COLOR_COUNT)

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
static UiState ui_test_state;
static char ui_test_line[UI_TEST_LINE_SIZE];
static uint8_t ui_test_length;
static uint16_t display_test_completed;
static uint8_t display_test_active;

void SystemClock_Config(void);
void Error_Handler(void);
static void MX_GPIO_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_USART2_UART_Init(void);
static void DrawStatus(uint32_t received_count, const PeerReading *peer);
static void UpdatePeerDisplay(uint32_t received_count, const PeerReading *peer);
static void SendHeartbeat(void);
static void PollEsp(uint32_t *received_count, PeerReading *peer);
static void PollUiTest(void);

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

static const char *UiTest_PageName(UiPage page)
{
  static const char *const names[] = {
    "home", "overview", "monitor", "alerts", "fans", "light_sound", "network", "settings",
  };
  return ((uint8_t)page < (sizeof(names) / sizeof(names[0]))) ? names[page] : "unknown";
}

static const char *UiTest_DialogName(UiDialog dialog)
{
  return (dialog == UI_DIALOG_CONFIRM) ? "confirm" : "none";
}

static const char *UiTest_CommandName(UiCommandPhase phase)
{
  static const char *const names[] = {
    "idle", "confirm", "sending", "accepted", "rejected", "timeout",
  };
  return ((uint8_t)phase < (sizeof(names) / sizeof(names[0]))) ? names[phase] : "unknown";
}

static const char *Joystick_EventName(UiInputEvent event)
{
  static const char *const names[] = {
    "NONE", "UP", "DOWN", "LEFT", "RIGHT", "PRESS", "LONG_PRESS",
  };
  return ((uint8_t)event < (sizeof(names) / sizeof(names[0]))) ? names[event] : "NONE";
}

static void JoystickTest_Report(UiInputEvent event)
{
  char message[32];
  const int length = snprintf(message, sizeof(message), "#JOY %s\r\n", Joystick_EventName(event));

  if ((length > 0) && (length < (int)sizeof(message))) {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message, (uint16_t)length, 1000U);
  }
}

static void UiTest_Report(void)
{
  char message[96];
  const int length = snprintf(message, sizeof(message),
    "#UI page=%s row=%u dialog=%s command=%s\r\n",
    UiTest_PageName(ui_test_state.page), (unsigned int)ui_test_state.selected_row,
    UiTest_DialogName(ui_test_state.dialog), UiTest_CommandName(ui_test_state.command_phase));

  if ((length > 0) && (length < (int)sizeof(message))) {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message, (uint16_t)length, 1000U);
  }
}

static void DisplayTest_Report(void)
{
  St7735BusStats stats;
  char message[180];
  St7735Bus_GetStats(&stats);
  const int length = snprintf(message, sizeof(message),
    "#DISPLAY sysclk=%lu spi_hz=%lu dma_frames=%lu dma_timeouts=%lu worst_frame_us=%lu dma_errors=%lu\r\n",
    (unsigned long)HAL_RCC_GetSysClockFreq(), (unsigned long)stats.spi_hz,
    (unsigned long)stats.dma_frames, (unsigned long)stats.dma_timeouts,
    (unsigned long)stats.worst_frame_us, (unsigned long)stats.dma_errors);
  if (length > 0 && length < (int)sizeof(message))
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message, (uint16_t)length, 1000U);
}

static void DisplayTest_BeginRun(void)
{
  St7735Bus_ResetStats();
  display_test_completed = 0U;
  display_test_active = 1U;
}

/* Return true when this run is complete or has failed. Only an exact one-frame
 * transition with no new transport fault earns progress. */
static uint8_t DisplayTest_RecordPrimitive(const St7735BusStats *before,
                                           const St7735BusStats *after)
{
  const uint8_t succeeded =
    ((uint32_t)(after->dma_frames - before->dma_frames) == 1U) &&
    ((uint32_t)(after->dma_timeouts - before->dma_timeouts) == 0U) &&
    ((uint32_t)(after->dma_errors - before->dma_errors) == 0U);

  if (succeeded) ++display_test_completed;
  if (!succeeded || (display_test_completed == DISPLAY_TEST_PRIMITIVE_COUNT)) {
    display_test_active = 0U;
    return 1U;
  }
  return 0U;
}

static void UiTest_HandleLine(void)
{
  UiInputEvent event = UI_EVT_NONE;
  unsigned long elapsed_ms;
  unsigned int enabled;
  unsigned int x;
  unsigned int y;
  unsigned int switch_released;
  unsigned long now_ms;
  char command_id[40];
  char acknowledgement[16];

  if (strcmp(ui_test_line, "#DISPLAYTEST RUN") == 0) {
    DisplayTest_BeginRun();
    return;
  } else if (strcmp(ui_test_line, "#DISPLAYTEST") == 0) {
    DisplayTest_Report();
    return;
  } else if (strcmp(ui_test_line, "#JOYTEST RESET") == 0) {
    Joystick_TestReset(2048U, 2048U);
    JoystickTest_Report(UI_EVT_NONE);
    return;
  } else if (sscanf(ui_test_line, "#JOYTEST %u %u %u %lu", &x, &y, &switch_released, &now_ms) == 4) {
    if ((x > 4095U) || (y > 4095U) || (switch_released > 1U)) return;
    JoystickTest_Report(Joystick_TestProcessSample((uint16_t)x, (uint16_t)y,
                                                   (uint8_t)switch_released, (uint32_t)now_ms));
    return;
  } else if (strcmp(ui_test_line, "#UITEST RESET") == 0) {
    UiState_Init(&ui_test_state);
  } else if (sscanf(ui_test_line, "#UITEST TICK %lu", &elapsed_ms) == 1) {
    /* TICK is a deterministic elapsed interval for the diagnostic adapter. */
    UiState_Tick(&ui_test_state, ui_test_state.command_started_ms + (uint32_t)elapsed_ms);
  } else if (sscanf(ui_test_line, "#UITEST BIND %39s", command_id) == 1) {
    (void)UiState_CommandDispatched(&ui_test_state, command_id);
  } else if (sscanf(ui_test_line, "#UITEST ACK %39s %15s", command_id, acknowledgement) == 2) {
    if (strcmp(acknowledgement, "ACCEPT") == 0) {
      (void)UiState_HandleAcknowledgement(&ui_test_state, command_id, 1U);
    } else if (strcmp(acknowledgement, "REJECT") == 0) {
      (void)UiState_HandleAcknowledgement(&ui_test_state, command_id, 0U);
    }
  } else if (sscanf(ui_test_line, "#UITEST MQTT %u", &enabled) == 1) {
    UiState_SetControlAvailability(&ui_test_state, enabled ? 1U : 0U, ui_test_state.control.safety_locked);
  } else if (sscanf(ui_test_line, "#UITEST SAFETY %u", &enabled) == 1) {
    UiState_SetControlAvailability(&ui_test_state, ui_test_state.control.mqtt_online, enabled ? 1U : 0U);
  } else if (strcmp(ui_test_line, "#UITEST UP") == 0) {
    event = UI_EVT_UP;
  } else if (strcmp(ui_test_line, "#UITEST DOWN") == 0) {
    event = UI_EVT_DOWN;
  } else if (strcmp(ui_test_line, "#UITEST LEFT") == 0) {
    event = UI_EVT_LEFT;
  } else if (strcmp(ui_test_line, "#UITEST RIGHT") == 0) {
    event = UI_EVT_RIGHT;
  } else if (strcmp(ui_test_line, "#UITEST PRESS") == 0) {
    event = UI_EVT_PRESS;
  } else if (strcmp(ui_test_line, "#UITEST LONG_PRESS") == 0) {
    event = UI_EVT_LONG_PRESS;
  } else {
    return;
  }

  if (event != UI_EVT_NONE) (void)UiState_Handle(&ui_test_state, event, HAL_GetTick());
  UiTest_Report();
}

static void PollUiTest(void)
{
  uint8_t character;

  while (HAL_UART_Receive(&huart1, &character, 1U, 0U) == HAL_OK) {
    if (character == '\n') {
      ui_test_line[ui_test_length] = '\0';
      UiTest_HandleLine();
      ui_test_length = 0U;
    } else if (character != '\r') {
      if (ui_test_length < (UI_TEST_LINE_SIZE - 1U)) ui_test_line[ui_test_length++] = (char)character;
      else ui_test_length = 0U;
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
  UiState_Init(&ui_test_state);
  Joystick_Init();
  if (HAL_UART_Receive_IT(&huart2, &esp_rx_character, 1U) != HAL_OK) Error_Handler();
  ST7735_Init();
  DrawStatus(received_count, &peer);
  (void)HAL_UART_Transmit(&huart1, (uint8_t *)"#NODE node-b boot\r\n", 19U, 1000U);

  for (;;)
  {
    const uint32_t now = HAL_GetTick();
    UiInputEvent event;
    event = Joystick_Poll(now);
    if (event != UI_EVT_NONE) (void)UiState_Handle(&ui_test_state, event, now);
    PollUiTest();
    PollEsp(&received_count, &peer);
    UiState_Tick(&ui_test_state, now);
    /* One diagnostic transfer per loop keeps input and ESP polling scheduled. */
    if (display_test_active) {
      St7735BusStats before;
      St7735BusStats after;
      St7735Bus_GetStats(&before);
      if (display_test_completed < DISPLAY_TEST_DIRTY_COUNT) {
        ST7735_FillRect(0, 32, LCD_WIDTH, 8,
                       (display_test_completed & 1U) ? LCD_BLUE : LCD_RED);
      } else {
        static const uint16_t colors[] = {LCD_BLUE, LCD_GREEN, LCD_RED};
        ST7735_Clear(colors[display_test_completed - DISPLAY_TEST_DIRTY_COUNT]);
      }
      St7735Bus_GetStats(&after);
      if (DisplayTest_RecordPrimitive(&before, &after)) {
        DisplayTest_Report();
        DrawStatus(received_count, &peer);
      }
    }
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
  RCC_PeriphCLKInitTypeDef peripheral_clock = {0};
  oscillator.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  oscillator.HSEState = RCC_HSE_ON;
  oscillator.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  oscillator.HSIState = RCC_HSI_ON;
  oscillator.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  oscillator.PLL.PLLState = RCC_PLL_ON;
  oscillator.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  oscillator.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&oscillator) != HAL_OK) Error_Handler();
  clock.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  clock.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  clock.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clock.APB1CLKDivider = RCC_HCLK_DIV2;
  clock.APB2CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_2) != HAL_OK) Error_Handler();
  peripheral_clock.PeriphClockSelection = RCC_PERIPHCLK_ADC;
  peripheral_clock.AdcClockSelection = RCC_ADCPCLK2_DIV6;
  if (HAL_RCCEx_PeriphCLKConfig(&peripheral_clock) != HAL_OK) Error_Handler();
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

  /* PA5/PA7 are configured by the SPI1 bus; PA6 remains unused. */
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
