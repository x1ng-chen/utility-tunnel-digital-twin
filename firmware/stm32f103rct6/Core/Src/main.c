/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "st7735.h"

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define WATER_ALARM_THRESHOLD  1000U
#define WATER_SAMPLE_COUNT     8U
#define VIBRATION_HOLD_MS      5000U
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
ADC_HandleTypeDef hadc1;

TIM_HandleTypeDef htim2;

/* USER CODE BEGIN PV */
static volatile uint32_t vibration_alarm_until = 0U;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM2_Init(void);
static void MX_ADC1_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
static void DHT11_DelayUs(uint16_t us)
{
  __HAL_TIM_SET_COUNTER(&htim2, 0);
  while (__HAL_TIM_GET_COUNTER(&htim2) < us) {}
}

static void DHT11_SetOutput(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  GPIO_InitStruct.Pin = GPIO_PIN_1;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_OD;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
}

static void DHT11_SetInput(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  GPIO_InitStruct.Pin = GPIO_PIN_1;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
}

static uint8_t DHT11_WaitFor(GPIO_PinState state, uint16_t timeout_us)
{
  __HAL_TIM_SET_COUNTER(&htim2, 0);

  while (HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_1) != state)
  {
    if (__HAL_TIM_GET_COUNTER(&htim2) >= timeout_us)
    {
      return 0;
    }
  }
  return 1;
}

static uint8_t DHT11_Read(uint8_t *temperature, uint8_t *humidity)
{
  uint8_t data[5] = {0};
  uint8_t i, j;

  DHT11_SetOutput();
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, GPIO_PIN_RESET);
  HAL_Delay(20);
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, GPIO_PIN_SET);
  DHT11_DelayUs(30);
  DHT11_SetInput();

  if (!DHT11_WaitFor(GPIO_PIN_RESET, 150)) return 0;
  if (!DHT11_WaitFor(GPIO_PIN_SET,   150)) return 0;
  if (!DHT11_WaitFor(GPIO_PIN_RESET, 150)) return 0;

  for (i = 0; i < 5; i++)
  {
    for (j = 0; j < 8; j++)
    {
      if (!DHT11_WaitFor(GPIO_PIN_SET, 100)) return 0;

      DHT11_DelayUs(40);
      if (HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_1) == GPIO_PIN_SET)
      {
        data[i] |= (1 << (7 - j));
      }

      if (!DHT11_WaitFor(GPIO_PIN_RESET, 100)) return 0;
    }
  }

  if (data[4] != (uint8_t)(data[0] + data[1] + data[2] + data[3]))
  {
    return 0;
  }

  *humidity = data[0];
  *temperature = data[2];
  return 1;
}

static uint16_t Water_ReadRaw(void)
{
  uint32_t sum = 0;
  uint8_t valid_samples = 0;
  uint8_t i;

  for (i = 0; i < WATER_SAMPLE_COUNT; i++)
  {
    if (HAL_ADC_Start(&hadc1) != HAL_OK)
    {
      continue;
    }

    if (HAL_ADC_PollForConversion(&hadc1, 10) == HAL_OK)
    {
      sum += HAL_ADC_GetValue(&hadc1);
      valid_samples++;
    }

    HAL_ADC_Stop(&hadc1);
  }

  return (valid_samples > 0U) ? (uint16_t)(sum / valid_samples) : 0U;
}

#if 0
/* Previous local TFT implementation kept here temporarily for comparison.
 * The active implementation is the verified external st7735.c driver. */
/* 1.44-inch 128x128 TFT (ST7735S, board OLED/TFT socket)
 * Socket mapping: SCL=PB4, SDA=PB5, RES=PB6, DC=PB7, CS=PB8, BLK=PB9.
 * These are not SPI2 pins, therefore the display uses software SPI here. */
#define TFT_CS_LOW()   HAL_GPIO_WritePin(GPIOB, GPIO_PIN_8, GPIO_PIN_RESET)
#define TFT_CS_HIGH()  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_8, GPIO_PIN_SET)
#define TFT_DC_LOW()   HAL_GPIO_WritePin(GPIOB, GPIO_PIN_7, GPIO_PIN_RESET)
#define TFT_DC_HIGH()  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_7, GPIO_PIN_SET)
#define TFT_RST_LOW()  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_6, GPIO_PIN_RESET)
#define TFT_RST_HIGH() HAL_GPIO_WritePin(GPIOB, GPIO_PIN_6, GPIO_PIN_SET)
#define TFT_BLK_HIGH() HAL_GPIO_WritePin(GPIOB, GPIO_PIN_9, GPIO_PIN_SET)

#define TFT_BLACK  0x0000
#define TFT_WHITE  0xFFFF
#define TFT_GREEN  0x07E0
#define TFT_RED    0xF800
#define TFT_CYAN   0x07FF

static void TFT_WriteByte(uint8_t value)
{
  uint8_t bit;

  for (bit = 0; bit < 8; bit++)
  {
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_5,
                      (value & 0x80U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    value <<= 1;
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_4, GPIO_PIN_SET);
  }
}

static void TFT_WriteCommand(uint8_t command)
{
  TFT_DC_LOW();
  TFT_WriteByte(command);
}

static void TFT_WriteData(const uint8_t *data, uint16_t length)
{
  TFT_DC_HIGH();
  while (length--)
  {
    TFT_WriteByte(*data++);
  }
}

static void TFT_SetAddressWindow(uint8_t x0, uint8_t y0, uint8_t x1, uint8_t y1)
{
  uint8_t data[4];

  TFT_WriteCommand(0x2A);
  data[0] = 0; data[1] = x0 + 2; data[2] = 0; data[3] = x1 + 2;
  TFT_WriteData(data, 4);

  TFT_WriteCommand(0x2B);
  data[0] = 0; data[1] = y0 + 3; data[2] = 0; data[3] = y1 + 3;
  TFT_WriteData(data, 4);
  TFT_WriteCommand(0x2C);
}

static void TFT_FillScreen(uint16_t color)
{
  uint8_t data[64];
  uint16_t i;

  for (i = 0; i < sizeof(data); i += 2)
  {
    data[i] = color >> 8;
    data[i + 1] = color & 0xFF;
  }

  TFT_SetAddressWindow(0, 0, 127, 127);
  TFT_DC_HIGH();
  for (i = 0; i < 512; i++)
  {
    uint8_t j;
    for (j = 0; j < sizeof(data); j++) TFT_WriteByte(data[j]);
  }
}

static uint8_t TFT_Glyph(char ch, uint8_t column)
{
  static const uint8_t digits[10][5] = {
    {0x3E, 0x51, 0x49, 0x45, 0x3E}, {0x00, 0x42, 0x7F, 0x40, 0x00},
    {0x42, 0x61, 0x51, 0x49, 0x46}, {0x21, 0x41, 0x45, 0x4B, 0x31},
    {0x18, 0x14, 0x12, 0x7F, 0x10}, {0x27, 0x45, 0x45, 0x45, 0x39},
    {0x3C, 0x4A, 0x49, 0x49, 0x30}, {0x01, 0x71, 0x09, 0x05, 0x03},
    {0x36, 0x49, 0x49, 0x49, 0x36}, {0x06, 0x49, 0x49, 0x29, 0x1E}
  };
  static const uint8_t t[5] = {0x01, 0x01, 0x7F, 0x01, 0x01};
  static const uint8_t h[5] = {0x7F, 0x08, 0x04, 0x04, 0x78};
  static const uint8_t c[5] = {0x3E, 0x41, 0x41, 0x41, 0x22};
  static const uint8_t e[5] = {0x38, 0x54, 0x54, 0x54, 0x18};
  static const uint8_t r[5] = {0x7C, 0x08, 0x04, 0x04, 0x08};
  static const uint8_t percent[5] = {0x62, 0x64, 0x08, 0x13, 0x23};
  static const uint8_t colon[5] = {0x00, 0x36, 0x36, 0x00, 0x00};
  static const uint8_t space[5] = {0, 0, 0, 0, 0};

  if (ch >= '0' && ch <= '9') return digits[ch - '0'][column];
  if (ch == 'T') return t[column];
  if (ch == 'H') return h[column];
  if (ch == 'C') return c[column];
  if (ch == 'E') return e[column];
  if (ch == 'R') return r[column];
  if (ch == '%') return percent[column];
  if (ch == ':') return colon[column];
  return space[column];
}

static void TFT_DrawChar(uint8_t x, uint8_t y, char ch, uint16_t color, uint8_t scale)
{
  uint8_t column, row, dx, dy, pixel[2];

  pixel[0] = color >> 8;
  pixel[1] = color & 0xFF;
  for (column = 0; column < 5; column++)
  {
    uint8_t bits = TFT_Glyph(ch, column);
    for (row = 0; row < 7; row++)
    {
      if ((bits >> row) & 1U)
      {
        TFT_SetAddressWindow(x + column * scale, y + row * scale,
                             x + column * scale + scale - 1, y + row * scale + scale - 1);
        TFT_DC_HIGH();
        for (dx = 0; dx < scale; dx++)
          for (dy = 0; dy < scale; dy++)
          {
            TFT_WriteByte(pixel[0]);
            TFT_WriteByte(pixel[1]);
          }
      }
    }
  }
}

static void TFT_Print(uint8_t x, uint8_t y, const char *text, uint16_t color, uint8_t scale)
{
  while (*text != '\0')
  {
    TFT_DrawChar(x, y, *text++, color, scale);
    x += 6 * scale;
  }
}

static void TFT_Init(void)
{
  static const uint8_t frmctr[] = {0x01, 0x2C, 0x2D};
  static const uint8_t frmctr3[] = {0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D};
  static const uint8_t pwctr1[] = {0xA2, 0x02, 0x84};
  static const uint8_t pwctr3[] = {0x0A, 0x00};
  static const uint8_t pwctr4[] = {0x8A, 0x2A};
  static const uint8_t pwctr5[] = {0x8A, 0xEE};
  static const uint8_t value_07[] = {0x07};
  static const uint8_t value_c5[] = {0xC5};
  static const uint8_t value_0e[] = {0x0E};
  static const uint8_t madctl[] = {0xC8};
  static const uint8_t color_mode[] = {0x05};

  /* The verified board driver keeps CS asserted for the whole session. */
  TFT_CS_LOW();
  TFT_DC_HIGH();
  TFT_BLK_HIGH();
  TFT_RST_LOW();  HAL_Delay(20);
  TFT_RST_HIGH(); HAL_Delay(120);
  TFT_WriteCommand(0x01); HAL_Delay(150);       /* SWRESET */
  TFT_WriteCommand(0x11); HAL_Delay(120);       /* SLPOUT  */
  TFT_WriteCommand(0xB1); TFT_WriteData(frmctr, 3);
  TFT_WriteCommand(0xB2); TFT_WriteData(frmctr, 3);
  TFT_WriteCommand(0xB3); TFT_WriteData(frmctr3, 6);
  TFT_WriteCommand(0xB4); TFT_WriteData(value_07, 1);
  TFT_WriteCommand(0xC0); TFT_WriteData(pwctr1, 3);
  TFT_WriteCommand(0xC1); TFT_WriteData(value_c5, 1);
  TFT_WriteCommand(0xC2); TFT_WriteData(pwctr3, 2);
  TFT_WriteCommand(0xC3); TFT_WriteData(pwctr4, 2);
  TFT_WriteCommand(0xC4); TFT_WriteData(pwctr5, 2);
  TFT_WriteCommand(0xC5); TFT_WriteData(value_0e, 1);
  TFT_WriteCommand(0x20);                         /* INVOFF */
  TFT_WriteCommand(0x36); TFT_WriteData(madctl, 1);
  TFT_WriteCommand(0x3A); TFT_WriteData(color_mode, 1);
  TFT_WriteCommand(0x13);                         /* NORON  */
  TFT_WriteCommand(0x29); HAL_Delay(100);         /* DISPON */
}

static void TFT_ShowValues(uint8_t temperature, uint8_t humidity)
{
  char temperature_text[] = {'T', ':', '0' + temperature / 10,
                             '0' + temperature % 10, 'C', '\0'};
  char humidity_text[] = {'H', ':', '0' + humidity / 10,
                          '0' + humidity % 10, '%', '\0'};

  TFT_FillScreen(TFT_BLACK);
  TFT_Print(16, 30, temperature_text, TFT_GREEN, 3);
  TFT_Print(16, 75, humidity_text, TFT_CYAN, 3);
}

/* Visual wiring check: the backlight must blink three times after reset. */
static void TFT_BacklightTest(void)
{
  uint8_t i;
  for (i = 0; i < 3; i++)
  {
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_9, GPIO_PIN_SET);
    HAL_Delay(300);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_9, GPIO_PIN_RESET);
    HAL_Delay(300);
  }
  TFT_BLK_HIGH();
}
#endif

static void LCD_ShowValues(uint8_t temperature, uint8_t humidity,
                           uint16_t water_raw, uint8_t dht_ok,
                           uint8_t vibration_alarm)
{
  char temperature_text[] = {'T', ':', '0' + temperature / 10,
                             '0' + temperature % 10, 'C', ' ', ' ', ' ',
                             ' ', ' ', ' ', '\0'};
  char humidity_text[] = {'H', ':', '0' + humidity / 10,
                          '0' + humidity % 10, '%', ' ', ' ', ' ',
                          ' ', ' ', ' ', '\0'};
  char water_text[] = {'W', ':',
                       '0' + (water_raw / 1000U) % 10U,
                       '0' + (water_raw / 100U) % 10U,
                       '0' + (water_raw / 10U) % 10U,
                       '0' + water_raw % 10U, ' ', ' ', ' ', ' ', ' ', '\0'};

  if (dht_ok)
  {
    ST7735_DrawString(8, 16, temperature_text, LCD_GREEN, LCD_BLACK);
    ST7735_DrawString(8, 40, humidity_text, LCD_CYAN, LCD_BLACK);
  }
  else
  {
    ST7735_DrawString(8, 16, "DHT ERR    ", LCD_RED, LCD_BLACK);
    ST7735_DrawString(8, 40, "           ", LCD_BLACK, LCD_BLACK);
  }

  ST7735_DrawString(8, 64, water_text, LCD_WHITE, LCD_BLACK);
  if (water_raw >= WATER_ALARM_THRESHOLD)
  {
    ST7735_DrawString(8, 88, "WATER ALARM", LCD_RED, LCD_BLACK);
  }
  else
  {
    ST7735_DrawString(8, 88, "WATER OK   ", LCD_GREEN, LCD_BLACK);
  }

  if (vibration_alarm)
  {
    ST7735_DrawString(8, 108, "VIB ALARM  ", LCD_RED, LCD_BLACK);
  }
  else
  {
    ST7735_DrawString(8, 108, "VIB OK     ", LCD_GREEN, LCD_BLACK);
  }
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM2_Init();
  MX_ADC1_Init();
  /* USER CODE BEGIN 2 */
  if (HAL_ADCEx_Calibration_Start(&hadc1) != HAL_OK)
  {
    Error_Handler();
  }
  {
    GPIO_InitTypeDef TFT_GPIO = {0};
    TFT_GPIO.Pin = GPIO_PIN_4 | GPIO_PIN_5 | GPIO_PIN_6 |
                   GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9;
    TFT_GPIO.Mode = GPIO_MODE_OUTPUT_PP;
    TFT_GPIO.Pull = GPIO_NOPULL;
    TFT_GPIO.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOB, &TFT_GPIO);
    HAL_GPIO_WritePin(GPIOB, TFT_GPIO.Pin, GPIO_PIN_RESET);
  }
  HAL_TIM_Base_Start(&htim2);
  ST7735_Init();
  ST7735_Clear(LCD_BLACK);
  uint8_t temperature = 0;
  uint8_t humidity = 0;
  uint8_t dht_ok = 0;
  uint32_t last_dht_read = HAL_GetTick() - 2000U;
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    uint16_t water_raw;
    uint8_t vibration_alarm;

    if ((HAL_GetTick() - last_dht_read) >= 2000U)
    {
      dht_ok = DHT11_Read(&temperature, &humidity);
      last_dht_read = HAL_GetTick();
      if (dht_ok)
      {
        HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_8);
      }
    }

    water_raw = Water_ReadRaw();
    vibration_alarm = ((int32_t)(vibration_alarm_until - HAL_GetTick()) > 0) ? 1U : 0U;
    LCD_ShowValues(temperature, humidity, water_raw, dht_ok, vibration_alarm);
    HAL_Delay(200);
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};
  RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK)
  {
    Error_Handler();
  }
  PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_ADC;
  PeriphClkInit.AdcClockSelection = RCC_ADCPCLK2_DIV2;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief ADC1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_ADC1_Init(void)
{

  /* USER CODE BEGIN ADC1_Init 0 */

  /* USER CODE END ADC1_Init 0 */

  ADC_ChannelConfTypeDef sConfig = {0};

  /* USER CODE BEGIN ADC1_Init 1 */

  /* USER CODE END ADC1_Init 1 */

  /** Common config
  */
  hadc1.Instance = ADC1;
  hadc1.Init.ScanConvMode = ADC_SCAN_DISABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.NbrOfConversion = 1;
  if (HAL_ADC_Init(&hadc1) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Regular Channel
  */
  sConfig.Channel = ADC_CHANNEL_10;
  sConfig.Rank = ADC_REGULAR_RANK_1;
  sConfig.SamplingTime = ADC_SAMPLETIME_239CYCLES_5;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN ADC1_Init 2 */

  /* USER CODE END ADC1_Init 2 */

}

/**
  * @brief TIM2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM2_Init(void)
{

  /* USER CODE BEGIN TIM2_Init 0 */

  /* USER CODE END TIM2_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM2_Init 1 */

  /* USER CODE END TIM2_Init 1 */
  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 7;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 65535;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim2) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim2, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM2_Init 2 */

  /* USER CODE END TIM2_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1|LED_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOB, TFT_SCL_Pin|TFT_SDA_Pin|TFT_RES_Pin|TFT_DC_Pin
                          |TFT_CS_Pin|TFT_BLK_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pins : PA1 LED_Pin */
  GPIO_InitStruct.Pin = GPIO_PIN_1|LED_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pin : PA4 */
  GPIO_InitStruct.Pin = GPIO_PIN_4;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING_FALLING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pins : TFT_SCL_Pin TFT_SDA_Pin TFT_RES_Pin TFT_DC_Pin
                           TFT_CS_Pin TFT_BLK_Pin */
  GPIO_InitStruct.Pin = TFT_SCL_Pin|TFT_SDA_Pin|TFT_RES_Pin|TFT_DC_Pin
                          |TFT_CS_Pin|TFT_BLK_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* EXTI interrupt init*/
  HAL_NVIC_SetPriority(EXTI4_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(EXTI4_IRQn);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
  if (GPIO_Pin == GPIO_PIN_4)
  {
    vibration_alarm_until = HAL_GetTick() + VIBRATION_HOLD_MS;
  }
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
