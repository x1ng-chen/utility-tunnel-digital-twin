#include "stm32f1xx_hal.h"
#include "actuators.h"
#include "board_config.h"
#include "board_io.h"
#include "joystick.h"
#include "modbus_slave.h"
#include "screen.h"
#include <stdio.h>

#define SAMPLE_INTERVAL_MS 2000U
#define LOG_INTERVAL_MS    5000U

static UART_HandleTypeDef huart1;
static uint16_t sequence;
static uint32_t last_sample_at;
static uint32_t last_log_at;

void Error_Handler(void)
{
  __disable_irq();
  for (;;) { }
}

void SysTick_Handler(void)
{
  HAL_IncTick();
}

void NMI_Handler(void) { Error_Handler(); }
void HardFault_Handler(void) { Error_Handler(); }
void MemManage_Handler(void) { Error_Handler(); }
void BusFault_Handler(void) { Error_Handler(); }
void UsageFault_Handler(void) { Error_Handler(); }

static void SystemClock_Config(void)
{
  RCC_OscInitTypeDef osc = {0};
  RCC_ClkInitTypeDef clk = {0};

  osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  osc.HSIState = RCC_HSI_ON;
  osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  osc.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&osc) != HAL_OK) Error_Handler();

  clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                  RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  clk.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clk.APB1CLKDivider = RCC_HCLK_DIV1;
  clk.APB2CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_0) != HAL_OK) Error_Handler();
}

/* USART1 = PA9/PA10，115200 8N1，仅作调试日志。 */
static void DebugUart_Init(void)
{
  GPIO_InitTypeDef gpio = {0};

  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_USART1_CLK_ENABLE();

  gpio.Pin = GPIO_PIN_9;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(GPIOA, &gpio);
  gpio.Pin = GPIO_PIN_10;
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOA, &gpio);

  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200U;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK) Error_Handler();
}

static void Log_Status(void)
{
  char line[128];
  int size = snprintf(line, sizeof line,
    "FOUR_CTRL CTRL-0%u board=%u sensors=%u seq=%u uptime_s=%lu\r\n",
    (unsigned)board_config.id, (unsigned)board_config.id,
    (unsigned)BoardIo_SampleCount(), (unsigned)sequence,
    (unsigned long)(HAL_GetTick() / 1000U));
  if (size > 0 && (size_t)size < sizeof line)
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)line, (uint16_t)size, 50U);
}

int main(void)
{
  HAL_Init();
  SystemClock_Config();
  DebugUart_Init();

#ifdef ONLY_MODBUS
  {
    const char ready[] = "ONLY_MODBUS\r\n";
    uint32_t last_ping = HAL_GetTick();
    Modbus_Init(BOARD_ID);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)ready, sizeof ready - 1U, 100U);
    for (;;)
    {
      Modbus_Poll();
      if ((uint32_t)(HAL_GetTick() - last_ping) >= 2000U)
      {
        last_ping = HAL_GetTick();
        Modbus_DebugPing();
      }
    }
  }
#endif
  BoardIo_Init();
  Actuators_Init();
  /* 先启动 485，屏幕初始化较慢，不能挡在通信前面。 */
  Modbus_Init(BOARD_ID);
#ifndef MINIMAL_485
  if (board_config.has_screen) Screen_Init();
  if (board_config.has_joystick) Joystick_Init();
#endif

  {
    char banner[96];
    int size = snprintf(banner, sizeof banner,
      "FOUR_CTRL CTRL-0%u BOOT sensors=%u bus=PA2/PA3 19200-8E1\r\n",
      (unsigned)BOARD_ID, (unsigned)BoardIo_SampleCount());
    if (size > 0 && (size_t)size < sizeof banner)
      (void)HAL_UART_Transmit(&huart1, (uint8_t *)banner, (uint16_t)size, 50U);
  }

  last_sample_at = HAL_GetTick() - SAMPLE_INTERVAL_MS;
  last_log_at = HAL_GetTick();

  for (;;)
  {
    uint32_t now = HAL_GetTick();

    Modbus_Poll();
    Actuators_Poll(now);

    if ((uint32_t)(now - last_sample_at) >= SAMPLE_INTERVAL_MS)
    {
      ++sequence;
      BoardIo_SampleAll();
      Modbus_SetSamples(BoardIo_Samples(), BoardIo_SampleCount(),
                        now / 1000U, sequence);

      /* 本板本地安全联动，不依赖网关：烟雾/火焰触发本板执行器。 */
      {
        uint8_t alarm = BoardIo_AlarmActive();
        if (board_config.has_buzzer) Actuators_SetBuzzer(alarm);
        if (board_config.has_led) Actuators_SetLedColor(alarm ? 255U : 0U, 0U, 0U);
        if (board_config.has_fan)
        {
          Actuators_SetFanPercent(alarm ? 100U : 0U);
          Actuators_SetRelay(alarm ? 1U : 0U);
        }
      }
      /* 软件 SPI 刷屏较慢，先按 10 秒节奏，避免挡住 Modbus 应答。 */
      {
        static uint32_t last_screen;
        static uint8_t screen_first = 1U;
        if (board_config.has_screen &&
            (screen_first || ((uint32_t)(now - last_screen) >= 10000U)))
        {
          Screen_Update(board_config.id, sequence, now / 1000U,
                        BoardIo_AlarmActive(), BoardIo_Samples(),
                        BoardIo_SampleCount());
          last_screen = now;
          screen_first = 0U;
        }
      }
      last_sample_at = now;
    }

    if ((uint32_t)(now - last_log_at) >= LOG_INTERVAL_MS)
    {
      Log_Status();
      last_log_at = now;
    }
  }
}
