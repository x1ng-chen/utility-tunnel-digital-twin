#include "main.h"

#include <stdio.h>

#define NODE_ID                         "node-a"
#define TELEMETRY_INTERVAL_MS           2000U
#define LED_INTERVAL_MS                  500U
#define SHT30_COMMAND_HIGH_REPEATABLE    0x2400U
#define SHT30_ADDRESS_44                 0x44U
#define SHT30_ADDRESS_45                 0x45U

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

void SystemClock_Config(void);
void Error_Handler(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_USART1_UART_Init(void);
static uint8_t Sht30_Read(const SoftI2cBus *bus, uint8_t address, Sht30Reading *reading);
static void SendTelemetry(const Sht30Reading readings[3]);

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
  int length;
  sequence++;
  length = snprintf(message, sizeof(message),
    "{\"schema\":\"ut.node-a.sht30.v1\",\"nodeId\":\"%s\",\"seq\":%lu,\"sht30\":["
    "{\"slot\":1,\"online\":%u,\"temperatureCentiC\":%d,\"humidityCentiRH\":%u},"
    "{\"slot\":2,\"online\":%u,\"temperatureCentiC\":%d,\"humidityCentiRH\":%u},"
    "{\"slot\":3,\"online\":%u,\"temperatureCentiC\":%d,\"humidityCentiRH\":%u}]}\r\n",
    NODE_ID, (unsigned long)sequence,
    readings[0].online, readings[0].temperature_centi_c, readings[0].humidity_centi_rh,
    readings[1].online, readings[1].temperature_centi_c, readings[1].humidity_centi_rh,
    readings[2].online, readings[2].temperature_centi_c, readings[2].humidity_centi_rh);
  if (length > 0 && length < (int)sizeof(message))
  {
    (void)HAL_UART_Transmit(&huart2, (uint8_t *)message, (uint16_t)length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message, (uint16_t)length, 1000U);
  }
}
int main(void)
{
  Sht30Reading readings[3] = {0};
  uint32_t last_telemetry = HAL_MAX_DELAY;
  uint32_t last_led = HAL_MAX_DELAY;
  HAL_Init(); SystemClock_Config(); MX_GPIO_Init(); MX_USART1_UART_Init(); MX_USART2_UART_Init();
  (void)HAL_UART_Transmit(&huart1, (uint8_t *)"#NODE node-a boot\r\n", 19U, 1000U);
  for (;;)
  {
    uint32_t now = HAL_GetTick();
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
  gpio.Pin = LED_Pin; gpio.Mode = GPIO_MODE_OUTPUT_PP; gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LED_GPIO_Port, &gpio);
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
