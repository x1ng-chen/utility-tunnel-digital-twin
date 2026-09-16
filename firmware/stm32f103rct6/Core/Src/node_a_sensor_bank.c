#include "node_a_sensor_bank.h"
#include <string.h>

#define SHT30_CMD_MEASURE_HIGH 0x2C06U
#define GAS_ADC_FILTER_SAMPLES 64U
#define DIGITAL_DEBOUNCE_SAMPLES 4U

static void I2c_Delay_Bank(const NodeASensorBank *bank) {
  if (bank && bank->service_cb) {
    bank->service_cb(bank->service_ctx);
  }
  for (volatile int d = 0; d < 20; ++d) {
    __NOP();
  }
}

static void I2c_Scl_Set(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state) {
  HAL_GPIO_WritePin(port, pin, state);
}

static void I2c_Sda_Set(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state) {
  HAL_GPIO_WritePin(port, pin, state);
}

static void I2c_Start_Bank(const NodeASensorBank *bank, GPIO_TypeDef *scl_port, uint16_t scl_pin,
                           GPIO_TypeDef *sda_port, uint16_t sda_pin) {
  I2c_Sda_Set(sda_port, sda_pin, GPIO_PIN_SET);
  I2c_Scl_Set(scl_port, scl_pin, GPIO_PIN_SET);
  I2c_Delay_Bank(bank);
  I2c_Sda_Set(sda_port, sda_pin, GPIO_PIN_RESET);
  I2c_Delay_Bank(bank);
  I2c_Scl_Set(scl_port, scl_pin, GPIO_PIN_RESET);
}

static void I2c_Stop_Bank(const NodeASensorBank *bank, GPIO_TypeDef *scl_port, uint16_t scl_pin,
                          GPIO_TypeDef *sda_port, uint16_t sda_pin) {
  I2c_Sda_Set(sda_port, sda_pin, GPIO_PIN_RESET);
  I2c_Delay_Bank(bank);
  I2c_Scl_Set(scl_port, scl_pin, GPIO_PIN_SET);
  I2c_Delay_Bank(bank);
  I2c_Sda_Set(sda_port, sda_pin, GPIO_PIN_SET);
  I2c_Delay_Bank(bank);
}

static uint8_t I2c_WriteByte_Bank(const NodeASensorBank *bank, GPIO_TypeDef *scl_port, uint16_t scl_pin,
                                  GPIO_TypeDef *sda_port, uint16_t sda_pin, uint8_t value) {
  for (uint8_t bit = 0U; bit < 8U; ++bit) {
    I2c_Sda_Set(sda_port, sda_pin, (value & 0x80U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    I2c_Delay_Bank(bank);
    I2c_Scl_Set(scl_port, scl_pin, GPIO_PIN_SET);
    I2c_Delay_Bank(bank);
    I2c_Scl_Set(scl_port, scl_pin, GPIO_PIN_RESET);
    value <<= 1U;
  }
  I2c_Sda_Set(sda_port, sda_pin, GPIO_PIN_SET);
  I2c_Delay_Bank(bank);
  I2c_Scl_Set(scl_port, scl_pin, GPIO_PIN_SET);
  I2c_Delay_Bank(bank);
  uint8_t ack = (HAL_GPIO_ReadPin(sda_port, sda_pin) == GPIO_PIN_RESET) ? 1U : 0U;
  I2c_Scl_Set(scl_port, scl_pin, GPIO_PIN_RESET);
  return ack;
}

static uint8_t I2c_ReadByte_Bank(const NodeASensorBank *bank, GPIO_TypeDef *scl_port, uint16_t scl_pin,
                                 GPIO_TypeDef *sda_port, uint16_t sda_pin, uint8_t ack) {
  uint8_t value = 0U;
  I2c_Sda_Set(sda_port, sda_pin, GPIO_PIN_SET);
  for (uint8_t bit = 0U; bit < 8U; ++bit) {
    value <<= 1U;
    I2c_Delay_Bank(bank);
    I2c_Scl_Set(scl_port, scl_pin, GPIO_PIN_SET);
    I2c_Delay_Bank(bank);
    if (HAL_GPIO_ReadPin(sda_port, sda_pin) == GPIO_PIN_SET) {
      value |= 1U;
    }
    I2c_Scl_Set(scl_port, scl_pin, GPIO_PIN_RESET);
  }
  I2c_Sda_Set(sda_port, sda_pin, ack ? GPIO_PIN_RESET : GPIO_PIN_SET);
  I2c_Delay_Bank(bank);
  I2c_Scl_Set(scl_port, scl_pin, GPIO_PIN_SET);
  I2c_Delay_Bank(bank);
  I2c_Scl_Set(scl_port, scl_pin, GPIO_PIN_RESET);
  I2c_Sda_Set(sda_port, sda_pin, GPIO_PIN_SET);
  return value;
}

static uint8_t Sht30_Crc8(const uint8_t *data, uint8_t length) {
  uint8_t crc = 0xFFU;
  while (length-- > 0U) {
    crc ^= *data++;
    for (uint8_t i = 0U; i < 8U; ++i) {
      crc = (crc & 0x80U) ? (uint8_t)((crc << 1U) ^ 0x31U) : (uint8_t)(crc << 1U);
    }
  }
  return crc;
}

static uint8_t Sht30_ReadSample(const NodeASensorBank *bank, const NodeI2CSensorPin *cfg,
                                int16_t *temp_c, uint16_t *hum_rh) {
  uint8_t response[6];
  I2c_Start_Bank(bank, cfg->scl_port, cfg->scl_pin, cfg->sda_port, cfg->sda_pin);
  if (!I2c_WriteByte_Bank(bank, cfg->scl_port, cfg->scl_pin, cfg->sda_port, cfg->sda_pin,
                          (uint8_t)(cfg->i2c_address << 1U)) ||
      !I2c_WriteByte_Bank(bank, cfg->scl_port, cfg->scl_pin, cfg->sda_port, cfg->sda_pin,
                          (uint8_t)(SHT30_CMD_MEASURE_HIGH >> 8U)) ||
      !I2c_WriteByte_Bank(bank, cfg->scl_port, cfg->scl_pin, cfg->sda_port, cfg->sda_pin,
                          (uint8_t)SHT30_CMD_MEASURE_HIGH)) {
    I2c_Stop_Bank(bank, cfg->scl_port, cfg->scl_pin, cfg->sda_port, cfg->sda_pin);
    return 0U;
  }
  I2c_Stop_Bank(bank, cfg->scl_port, cfg->scl_pin, cfg->sda_port, cfg->sda_pin);

  for (uint8_t wait = 0U; wait < 20U; ++wait) {
    I2c_Delay_Bank(bank);
  }

  I2c_Start_Bank(bank, cfg->scl_port, cfg->scl_pin, cfg->sda_port, cfg->sda_pin);
  if (!I2c_WriteByte_Bank(bank, cfg->scl_port, cfg->scl_pin, cfg->sda_port, cfg->sda_pin,
                          (uint8_t)((cfg->i2c_address << 1U) | 1U))) {
    I2c_Stop_Bank(bank, cfg->scl_port, cfg->scl_pin, cfg->sda_port, cfg->sda_pin);
    return 0U;
  }
  for (uint8_t i = 0U; i < 6U; ++i) {
    response[i] = I2c_ReadByte_Bank(bank, cfg->scl_port, cfg->scl_pin, cfg->sda_port,
                                    cfg->sda_pin, i < 5U);
  }
  I2c_Stop_Bank(bank, cfg->scl_port, cfg->scl_pin, cfg->sda_port, cfg->sda_pin);

  if (Sht30_Crc8(response, 2U) != response[2] || Sht30_Crc8(&response[3], 2U) != response[5]) {
    return 0U;
  }
  uint16_t raw_temp = (uint16_t)(((uint16_t)response[0] << 8U) | response[1]);
  uint16_t raw_hum = (uint16_t)(((uint16_t)response[3] << 8U) | response[4]);
  *temp_c = (int16_t)(((int32_t)17500 * raw_temp) / 65535 - 4500);
  *hum_rh = (uint16_t)(((uint32_t)10000 * raw_hum) / 65535U);
  return 1U;
}

void NodeASensorBank_Init(NodeASensorBank *bank, ADC_HandleTypeDef *hadc,
                          NodeAServiceCallback service_cb, void *service_ctx) {
  if (bank == NULL) return;
  memset(bank, 0, sizeof(*bank));
  bank->hadc = hadc;
  bank->service_cb = service_cb;
  bank->service_ctx = service_ctx;
  bank->cursor = 0U;

  uint8_t idx = 0U;
  for (uint8_t i = 0U; i < NODE_A_I2C_SENSOR_COUNT; ++i, ++idx) {
    SensorReading_Init(&bank->readings[idx], kNodeAI2CPins[i].asset_code,
                       SENSOR_KIND_SHT30, 0U);
  }
  for (uint8_t i = 0U; i < NODE_A_ANALOG_PIN_COUNT; ++i, ++idx) {
    SensorReading_Init(&bank->readings[idx], kNodeAAnalogPins[i].asset_code,
                       kNodeAAnalogPins[i].kind, 0U);
  }
  for (uint8_t i = 0U; i < NODE_A_DIGITAL_PIN_COUNT; ++i, ++idx) {
    SensorReading_Init(&bank->readings[idx], kNodeADigitalPins[i].asset_code,
                       kNodeADigitalPins[i].kind, 0U);
  }

  /* Default enabled: commission existing MQ4-01, CO-01, O2-01, SHT-01, MQ2-01, FLAME-01, LEVEL-01 */
  int8_t pos;
  if ((pos = NodeASensorBank_FindIndex(bank, "SHT-01")) >= 0) NodeASensorBank_SetEnabled(bank, (uint8_t)pos, 1U);
  if ((pos = NodeASensorBank_FindIndex(bank, "MQ4-01")) >= 0) {
    NodeASensorBank_SetEnabled(bank, (uint8_t)pos, 1U);
    NodeASensorBank_SetCalibrated(bank, (uint8_t)pos, 1U);
  }
  if ((pos = NodeASensorBank_FindIndex(bank, "CO-01")) >= 0) NodeASensorBank_SetEnabled(bank, (uint8_t)pos, 1U);
  if ((pos = NodeASensorBank_FindIndex(bank, "O2-01")) >= 0) NodeASensorBank_SetEnabled(bank, (uint8_t)pos, 1U);
  if ((pos = NodeASensorBank_FindIndex(bank, "MQ2-01")) >= 0) NodeASensorBank_SetEnabled(bank, (uint8_t)pos, 1U);
  if ((pos = NodeASensorBank_FindIndex(bank, "FLAME-01")) >= 0) NodeASensorBank_SetEnabled(bank, (uint8_t)pos, 1U);
  if ((pos = NodeASensorBank_FindIndex(bank, "LEVEL-01")) >= 0) NodeASensorBank_SetEnabled(bank, (uint8_t)pos, 1U);
}

uint8_t NodeASensorBank_Count(const NodeASensorBank *bank) {
  (void)bank;
  return NODE_A_SENSOR_COUNT;
}

const SensorReading *NodeASensorBank_Readings(const NodeASensorBank *bank) {
  return bank ? bank->readings : NULL;
}

int8_t NodeASensorBank_FindIndex(const NodeASensorBank *bank, const char *asset_code) {
  if (!bank || !asset_code) return -1;
  for (uint8_t i = 0U; i < NODE_A_SENSOR_COUNT; ++i) {
    if (strcmp(bank->readings[i].asset_code, asset_code) == 0) {
      return (int8_t)i;
    }
  }
  return -1;
}

const SensorReading *NodeASensorBank_FindReading(const NodeASensorBank *bank,
                                                 const char *asset_code) {
  int8_t idx = NodeASensorBank_FindIndex(bank, asset_code);
  return (idx >= 0) ? &bank->readings[idx] : NULL;
}

void NodeASensorBank_SetEnabled(NodeASensorBank *bank, uint8_t index, uint8_t enabled) {
  if (!bank || index >= NODE_A_SENSOR_COUNT) return;
  bank->readings[index].enabled = enabled ? 1U : 0U;
  if (!enabled) {
    SensorReading_SetMissing(&bank->readings[index], bank->readings[index].sampled_at_ms);
  }
}

void NodeASensorBank_SetCalibrated(NodeASensorBank *bank, uint8_t index, uint8_t calibrated) {
  if (!bank || index >= NODE_A_SENSOR_COUNT) return;
  bank->calibrated[index] = calibrated ? 1U : 0U;
}

void NodeASensorBank_Tick(NodeASensorBank *bank, uint32_t now_ms) {
  if (bank == NULL) return;

  uint8_t item = bank->cursor;
  bank->cursor = (uint8_t)((bank->cursor + 1U) % NODE_A_SENSOR_COUNT);

  SensorReading *reading = &bank->readings[item];

  if (item < NODE_A_I2C_SENSOR_COUNT) {
    /* SHT30 instance */
    if (!reading->enabled) {
      SensorReading_SetMissing(reading, now_ms);
      return;
    }
    const NodeI2CSensorPin *cfg = &kNodeAI2CPins[item];
    int16_t temp_c = 0;
    uint16_t hum_rh = 0;
    if (Sht30_ReadSample(bank, cfg, &temp_c, &hum_rh)) {
      SensorReading_SetSht30(reading, temp_c, hum_rh, now_ms, SENSOR_QUALITY_GOOD);
    } else {
      SensorReading_SetMissing(reading, now_ms);
    }
  } else if (item < (NODE_A_I2C_SENSOR_COUNT + NODE_A_ANALOG_PIN_COUNT)) {
    /* Analog channel */
    uint8_t a_idx = (uint8_t)(item - NODE_A_I2C_SENSOR_COUNT);
    if (!reading->enabled) {
      SensorReading_SetMissing(reading, now_ms);
      return;
    }
    const NodeAnalogPin *cfg = &kNodeAAnalogPins[a_idx];
    uint16_t raw = 0U;
    uint8_t ok = 0U;

    if (bank->hadc && bank->hadc->Instance) {
      ADC_ChannelConfTypeDef channel = {0};
      channel.Channel = cfg->adc_channel;
      channel.Rank = ADC_REGULAR_RANK_1;
      channel.SamplingTime = ADC_SAMPLETIME_239CYCLES_5;
      if (HAL_ADC_ConfigChannel(bank->hadc, &channel) == HAL_OK) {
        if (HAL_ADC_Start(bank->hadc) == HAL_OK) {
          if (HAL_ADC_PollForConversion(bank->hadc, 5U) == HAL_OK) {
            raw = (uint16_t)HAL_ADC_GetValue(bank->hadc);
            ok = 1U;
          }
          (void)HAL_ADC_Stop(bank->hadc);
        }
      }
    }

    if (bank->service_cb) {
      bank->service_cb(bank->service_ctx);
    }

    if (ok) {
      bank->adc_accum[a_idx] += raw;
      bank->adc_count[a_idx]++;
      if (bank->adc_count[a_idx] >= GAS_ADC_FILTER_SAMPLES) {
        bank->adc_filtered[a_idx] = (uint16_t)(bank->adc_accum[a_idx] / bank->adc_count[a_idx]);
        bank->adc_accum[a_idx] = 0U;
        bank->adc_count[a_idx] = 0U;
      } else if (bank->adc_filtered[a_idx] == 0U) {
        bank->adc_filtered[a_idx] = raw;
      }
      uint16_t val = bank->adc_filtered[a_idx];
      uint32_t uv = (uint32_t)((((uint64_t)val * 3300000ULL) + 2047ULL) / 4095ULL);
      SensorQuality q;
      if (val >= 4095U) {
        q = SENSOR_QUALITY_BAD;
      } else if (bank->calibrated[item]) {
        q = SENSOR_QUALITY_GOOD;
      } else {
        q = SENSOR_QUALITY_SUSPECT;
      }
      SensorReading_SetAnalog(reading, val, uv, now_ms, q);
    } else {
      SensorReading_SetMissing(reading, now_ms);
    }
  } else {
    /* Digital channel */
    uint8_t d_idx = (uint8_t)(item - NODE_A_I2C_SENSOR_COUNT - NODE_A_ANALOG_PIN_COUNT);
    if (!reading->enabled) {
      SensorReading_SetMissing(reading, now_ms);
      reading->alarm = 0U;
      return;
    }
    const NodeDigitalPin *cfg = &kNodeADigitalPins[d_idx];
    GPIO_PinState pin_state = HAL_GPIO_ReadPin(cfg->port, cfg->pin);
    /* Active-low for flame, level, and MQ2 comparator outputs */
    uint8_t active_sample = (pin_state == GPIO_PIN_RESET) ? 1U : 0U;
    uint8_t stable = DigitalDebounce_Update(&bank->debounces[d_idx], active_sample,
                                           DIGITAL_DEBOUNCE_SAMPLES);
    SensorReading_SetDigital(reading, stable, stable, now_ms, SENSOR_QUALITY_GOOD);
  }
}
