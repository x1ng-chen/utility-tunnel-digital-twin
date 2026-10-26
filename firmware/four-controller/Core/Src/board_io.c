#include "board_io.h"
#include "board_config.h"
#include <string.h>

void Error_Handler(void);

#define ADC_SAMPLE_COUNT      64U
#define ADC_REFERENCE_MV      3300UL
#define DIGITAL_DEBOUNCE_N    4U
#define DIGITAL_DEBOUNCE_HOLD 2U

typedef struct
{
  GPIO_TypeDef *port;
  uint16_t scl_pin;
  uint16_t sda_pin;
} SoftI2cBus;

static ADC_HandleTypeDef hadc1;
static SoftI2cBus i2c_bus;
static SensorSample samples[11];
static uint8_t sample_count;

volatile uint8_t BoardIo_I2cScanResult;
volatile uint8_t BoardIo_ShtDebug;
volatile uint8_t BoardIo_ShtRaw[6];

/* ---------- 软件 I2C（沿用旧台架时序，速率不高但足够 SHT30） ---------- */

/* 与旧台架代码一致，每半周期 1 ms，彻底排除时序问题。 */
static void I2c_Delay(void) { HAL_Delay(1U); }

static void I2c_Sda(GPIO_PinState state)
{
  HAL_GPIO_WritePin(i2c_bus.port, i2c_bus.sda_pin, state);
}

static void I2c_Scl(GPIO_PinState state)
{
  HAL_GPIO_WritePin(i2c_bus.port, i2c_bus.scl_pin, state);
}

static void I2c_Start(void)
{
  I2c_Sda(GPIO_PIN_SET); I2c_Scl(GPIO_PIN_SET); I2c_Delay();
  I2c_Sda(GPIO_PIN_RESET); I2c_Delay(); I2c_Scl(GPIO_PIN_RESET);
}

static void I2c_Stop(void)
{
  I2c_Sda(GPIO_PIN_RESET); I2c_Delay(); I2c_Scl(GPIO_PIN_SET);
  I2c_Delay(); I2c_Sda(GPIO_PIN_SET); I2c_Delay();
}

static uint8_t I2c_WriteByte(uint8_t value)
{
  uint8_t bit;
  uint8_t nack;
  for (bit = 0U; bit < 8U; ++bit)
  {
    I2c_Sda((value & 0x80U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    I2c_Delay(); I2c_Scl(GPIO_PIN_SET); I2c_Delay(); I2c_Scl(GPIO_PIN_RESET);
    value <<= 1U;
  }
  I2c_Sda(GPIO_PIN_SET); I2c_Delay(); I2c_Scl(GPIO_PIN_SET); I2c_Delay();
  /* 与旧台架代码一致：SDA 被从机拉低表示 ACK，返回 1；调用处用 ! 判失败。 */
  nack = (HAL_GPIO_ReadPin(i2c_bus.port, i2c_bus.sda_pin) == GPIO_PIN_RESET) ? 1U : 0U;
  I2c_Scl(GPIO_PIN_RESET);
  return nack;   /* 1 = ACK */
}

static uint8_t I2c_ReadByte(uint8_t acknowledge)
{
  uint8_t bit;
  uint8_t value = 0U;
  I2c_Sda(GPIO_PIN_SET);
  for (bit = 0U; bit < 8U; ++bit)
  {
    value <<= 1U;
    I2c_Delay(); I2c_Scl(GPIO_PIN_SET); I2c_Delay();
    if (HAL_GPIO_ReadPin(i2c_bus.port, i2c_bus.sda_pin) == GPIO_PIN_SET) value |= 1U;
    I2c_Scl(GPIO_PIN_RESET);
  }
  I2c_Sda(acknowledge ? GPIO_PIN_RESET : GPIO_PIN_SET);
  I2c_Delay(); I2c_Scl(GPIO_PIN_SET); I2c_Delay(); I2c_Scl(GPIO_PIN_RESET);
  I2c_Sda(GPIO_PIN_SET);
  return value;
}

uint8_t BoardIo_I2cRead16(uint8_t address, uint8_t reg, uint16_t *value)
{
  uint8_t high;
  uint8_t low;
  if (value == NULL) return 0U;
  I2c_Start();
  if (!I2c_WriteByte((uint8_t)(address << 1U)) || !I2c_WriteByte(reg))
  {
    I2c_Stop();
    return 0U;
  }
  I2c_Start();
  if (!I2c_WriteByte((uint8_t)((address << 1U) | 1U)))
  {
    I2c_Stop();
    return 0U;
  }
  high = I2c_ReadByte(1U);
  low = I2c_ReadByte(0U);
  I2c_Stop();
  *value = (uint16_t)(((uint16_t)high << 8U) | low);
  return 1U;
}

uint8_t BoardIo_I2cWrite16(uint8_t address, uint8_t reg, uint16_t value)
{
  I2c_Start();
  if (!I2c_WriteByte((uint8_t)(address << 1U)) || !I2c_WriteByte(reg) ||
      !I2c_WriteByte((uint8_t)(value >> 8U)) || !I2c_WriteByte((uint8_t)value))
  {
    I2c_Stop();
    return 0U;
  }
  I2c_Stop();
  return 1U;
}

static uint8_t __attribute__((unused)) Sht30_Crc(const uint8_t *data, uint8_t length)
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

static uint8_t Sht30_Read(uint8_t address, SensorSample *out)
{
  uint8_t response[6];
  uint8_t i;
  uint16_t raw_temperature;
  uint16_t raw_humidity;

  out->status = SENSOR_STATUS_MISSING;
  I2c_Start();
  if (!I2c_WriteByte((uint8_t)(address << 1U)))
  {
    I2c_Stop();
    BoardIo_ShtDebug = 1U;
    return 0U;
  }
  if (!I2c_WriteByte(0x24U)) { I2c_Stop(); BoardIo_ShtDebug = 2U; return 0U; }
  if (!I2c_WriteByte(0x00U)) { I2c_Stop(); BoardIo_ShtDebug = 3U; return 0U; }
  I2c_Stop();
  HAL_Delay(20U);
  I2c_Start();
  if (!I2c_WriteByte((uint8_t)((address << 1U) | 1U)))
  {
    I2c_Stop();
    BoardIo_ShtDebug = 4U;
    return 0U;
  }
  for (i = 0U; i < sizeof(response); ++i)
  {
    response[i] = I2c_ReadByte((i < (sizeof(response) - 1U)) ? 1U : 0U);
    BoardIo_ShtRaw[i] = response[i];
  }
  I2c_Stop();
  if (Sht30_Crc(response, 2U) != response[2]) { BoardIo_ShtDebug = 5U; return 0U; }
  if (Sht30_Crc(&response[3], 2U) != response[5]) { BoardIo_ShtDebug = 6U; return 0U; }
  BoardIo_ShtDebug = 0U;

  raw_temperature = (uint16_t)(((uint16_t)response[0] << 8U) | response[1]);
  raw_humidity = (uint16_t)(((uint16_t)response[3] << 8U) | response[4]);
  out->value = (uint16_t)(int16_t)(((int32_t)17500 * raw_temperature) / 65535 - 4500);
  out->aux = (uint16_t)(((uint32_t)10000 * raw_humidity) / 65535U);
  out->status = SENSOR_STATUS_OK;
  return 1U;
}

/* ---------- ADC ---------- */

static uint8_t Adc_ReadRaw(uint32_t channel, uint16_t *raw)
{
  ADC_ChannelConfTypeDef config = {0};
  uint32_t sum = 0UL;
  uint16_t valid = 0U;
  uint16_t i;

  if (raw == NULL) return 0U;
  config.Channel = channel;
  config.Rank = ADC_REGULAR_RANK_1;
  config.SamplingTime = ADC_SAMPLETIME_239CYCLES_5;
  if (HAL_ADC_ConfigChannel(&hadc1, &config) != HAL_OK) return 0U;

  for (i = 0U; i < ADC_SAMPLE_COUNT; ++i)
  {
    if (HAL_ADC_Start(&hadc1) != HAL_OK) continue;
    if (HAL_ADC_PollForConversion(&hadc1, 10U) == HAL_OK)
    {
      sum += HAL_ADC_GetValue(&hadc1);
      ++valid;
    }
    (void)HAL_ADC_Stop(&hadc1);
  }
  if (valid == 0U)
  {
    *raw = 0U;
    return 0U;
  }
  *raw = (uint16_t)((sum + (valid / 2U)) / valid);
  return 1U;
}

static uint16_t Adc_ToMillivolts(uint16_t raw)
{
  return (uint16_t)(((uint32_t)raw * ADC_REFERENCE_MV + 2047UL) / 4095UL);
}

uint8_t BoardIo_AdcRead(uint32_t channel, uint16_t *raw)
{
  return Adc_ReadRaw(channel, raw);
}

static uint8_t BoardIo_I2cScan(void)
{
  uint8_t address;

  /* 空闲时 SCL/SDA 都应被上拉到高；任一为低说明总线被拉死。 */
  HAL_GPIO_WritePin(i2c_bus.port, i2c_bus.scl_pin | i2c_bus.sda_pin, GPIO_PIN_SET);
  for (volatile uint32_t wait = 0U; wait < 2000U; ++wait) { __NOP(); }
  if ((HAL_GPIO_ReadPin(i2c_bus.port, i2c_bus.sda_pin) == GPIO_PIN_RESET) ||
      (HAL_GPIO_ReadPin(i2c_bus.port, i2c_bus.scl_pin) == GPIO_PIN_RESET))
    return 0xFEU;

  for (address = 0x08U; address < 0x78U; ++address)
  {
    I2c_Start();
    if (I2c_WriteByte((uint8_t)(address << 1U)) == 1U)
    {
      I2c_Stop();
      return address;
    }
    I2c_Stop();
  }
  return 0U;
}

uint16_t BoardIo_AdcToMillivolts(uint16_t raw)
{
  return Adc_ToMillivolts(raw);
}

/* ---------- 数字量 ---------- */

static uint8_t ReadDigitalActiveLow(const SensorDef *sensor)
{
  uint8_t active = 0U;
  uint8_t i;
  for (i = 0U; i < DIGITAL_DEBOUNCE_N; ++i)
  {
    if (HAL_GPIO_ReadPin(sensor->port, sensor->pin) == GPIO_PIN_RESET) ++active;
    HAL_Delay(DIGITAL_DEBOUNCE_HOLD);
  }
  return (active >= 3U) ? 1U : 0U;
}

/* ---------- 初始化 ---------- */

void BoardIo_Init(void)
{
  GPIO_InitTypeDef gpio = {0};
  uint8_t i;

  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_ADC1_CLK_ENABLE();

  sample_count = board_config.sensor_count;
  memset(samples, 0, sizeof samples);

  for (i = 0U; i < sample_count; ++i)
  {
    const SensorDef *s = &board_config.sensors[i];
    if (s->port == NULL) continue;

    if (s->type == SENSOR_MQ4 || s->type == SENSOR_CO || s->type == SENSOR_O2)
    {
      gpio.Pin = s->pin;
      gpio.Mode = GPIO_MODE_ANALOG;
      gpio.Speed = GPIO_SPEED_FREQ_LOW;
      HAL_GPIO_Init(s->port, &gpio);
    }
    else if (s->type == SENSOR_MQ2 || s->type == SENSOR_FLAME || s->type == SENSOR_LEVEL)
    {
      gpio.Pin = s->pin;
      gpio.Mode = GPIO_MODE_INPUT;
      gpio.Pull = GPIO_PULLUP;
      HAL_GPIO_Init(s->port, &gpio);
    }
  }

  /* 本地软件 I2C：开漏，空闲为高。 */
  i2c_bus.port = board_config.i2c_port;
  i2c_bus.scl_pin = board_config.i2c_scl;
  i2c_bus.sda_pin = board_config.i2c_sda;
  gpio.Pin = i2c_bus.scl_pin | i2c_bus.sda_pin;
  gpio.Mode = GPIO_MODE_OUTPUT_OD;
  gpio.Pull = GPIO_PULLUP;   /* 模块没有上拉时靠内部弱上拉兜底 */
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(i2c_bus.port, &gpio);
  HAL_GPIO_WritePin(i2c_bus.port, i2c_bus.scl_pin | i2c_bus.sda_pin, GPIO_PIN_SET);

  hadc1.Instance = ADC1;
  hadc1.Init.ScanConvMode = ADC_SCAN_DISABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.NbrOfConversion = 1;
  if (HAL_ADC_Init(&hadc1) != HAL_OK) Error_Handler();
  if (HAL_ADCEx_Calibration_Start(&hadc1) != HAL_OK) Error_Handler();

  HAL_Delay(50U);
  /* 给 SHT3x 发软复位 0x30A2，避免芯片停在上电异常状态。 */
  I2c_Start();
  if (I2c_WriteByte(0x88U) == 1U)
  {
    (void)I2c_WriteByte(0x30U);
    (void)I2c_WriteByte(0xA2U);
  }
  I2c_Stop();
  HAL_Delay(10U);
  BoardIo_I2cScanResult = BoardIo_I2cScan();
}

/* ---------- 采集 ---------- */

void BoardIo_SampleAll(void)
{
  uint8_t i;
  for (i = 0U; i < sample_count; ++i)
  {
    const SensorDef *s = &board_config.sensors[i];
    SensorSample *out = &samples[i];
    uint16_t raw = 0U;

    switch (s->type)
    {
      case SENSOR_MQ2:
      case SENSOR_FLAME:
      case SENSOR_LEVEL:
        out->value = ReadDigitalActiveLow(s);
        out->aux = 0U;
        out->status = SENSOR_STATUS_OK;
        break;

      case SENSOR_MQ4:
      case SENSOR_CO:
        if (Adc_ReadRaw(s->adc_channel, &raw))
        {
          out->value = raw;
          out->aux = 0U;
          out->status = SENSOR_STATUS_OK;
        }
        else
        {
          out->value = 0U;
          out->aux = 0U;
          out->status = SENSOR_STATUS_MISSING;
        }
        break;

      case SENSOR_O2:
        if (Adc_ReadRaw(s->adc_channel, &raw))
        {
          out->value = raw;
          out->aux = Adc_ToMillivolts(raw);
          /* 裸探头直连只能作为原始值试验，不声明已标定浓度。 */
          out->status = SENSOR_STATUS_SUSPECT;
        }
        else
        {
          out->value = 0U;
          out->aux = 0U;
          out->status = SENSOR_STATUS_MISSING;
        }
        break;

      case SENSOR_SHT:
      {
        /* 优先用扫描到的地址，失败再试配置地址。 */
        uint8_t target = ((BoardIo_I2cScanResult >= 0x08U) &&
                          (BoardIo_I2cScanResult < 0x78U))
                         ? BoardIo_I2cScanResult : s->i2c_address;
        (void)Sht30_Read(target, out);
        break;
      }

      default:
        out->value = 0U;
        out->aux = 0U;
        out->status = SENSOR_STATUS_MISSING;
        break;
    }
  }
}

const SensorSample *BoardIo_Samples(void) { return samples; }
uint8_t BoardIo_SampleCount(void) { return sample_count; }

uint16_t BoardIo_SensorId(uint8_t index)
{
  if (index >= sample_count) return 0xFFFFU;
  return board_config.sensors[index].id;
}

uint8_t BoardIo_AlarmActive(void)
{
  uint8_t i;
  for (i = 0U; i < sample_count; ++i)
  {
    const SensorDef *s = &board_config.sensors[i];
    if (((s->type == SENSOR_MQ2) || (s->type == SENSOR_FLAME)) &&
        (samples[i].value != 0U))
      return 1U;
  }
  return 0U;
}
