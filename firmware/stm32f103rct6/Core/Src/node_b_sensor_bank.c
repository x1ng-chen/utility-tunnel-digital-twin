#include "node_b_sensor_bank.h"
#include <string.h>

#define GAS_ADC_FILTER_SAMPLES 4U
#define DIGITAL_DEBOUNCE_SAMPLES 4U

void NodeBSensorBank_Init(NodeBSensorBank *bank, ADC_HandleTypeDef *hadc) {
  if (bank == NULL) return;
  memset(bank, 0, sizeof(*bank));
  bank->hadc = hadc;
  bank->cursor = 0U;

  uint8_t idx = 0U;
  for (uint8_t i = 0U; i < NODE_B_ANALOG_PIN_COUNT; ++i, ++idx) {
    SensorReading_Init(&bank->readings[idx], kNodeBAnalogPins[i].asset_code,
                       kNodeBAnalogPins[i].kind, 0U);
  }
  for (uint8_t i = 0U; i < NODE_B_DIGITAL_PIN_COUNT; ++i, ++idx) {
    SensorReading_Init(&bank->readings[idx], kNodeBDigitalPins[i].asset_code,
                       kNodeBDigitalPins[i].kind, 0U);
  }

  /* LEVEL-05 was physically removed. The other eleven channels are fitted. */
  for (uint8_t i = 0U; i < NODE_B_SENSOR_COUNT; ++i)
    if (strcmp(bank->readings[i].asset_code, "LEVEL-05") != 0)
      NodeBSensorBank_SetEnabled(bank, i, 1U);
}

uint8_t NodeBSensorBank_Count(const NodeBSensorBank *bank) {
  (void)bank;
  return NODE_B_SENSOR_COUNT;
}

const SensorReading *NodeBSensorBank_Readings(const NodeBSensorBank *bank) {
  return bank ? bank->readings : NULL;
}

int8_t NodeBSensorBank_FindIndex(const NodeBSensorBank *bank, const char *asset_code) {
  if (!bank || !asset_code) return -1;
  for (uint8_t i = 0U; i < NODE_B_SENSOR_COUNT; ++i) {
    if (strcmp(bank->readings[i].asset_code, asset_code) == 0) {
      return (int8_t)i;
    }
  }
  return -1;
}

const SensorReading *NodeBSensorBank_FindReading(const NodeBSensorBank *bank,
                                                 const char *asset_code) {
  int8_t idx = NodeBSensorBank_FindIndex(bank, asset_code);
  return (idx >= 0) ? &bank->readings[idx] : NULL;
}

void NodeBSensorBank_SetEnabled(NodeBSensorBank *bank, uint8_t index, uint8_t enabled) {
  if (!bank || index >= NODE_B_SENSOR_COUNT) return;
  bank->readings[index].enabled = enabled ? 1U : 0U;
  if (!enabled) {
    SensorReading_SetMissing(&bank->readings[index], bank->readings[index].sampled_at_ms);
  }
}

void NodeBSensorBank_SetCalibrated(NodeBSensorBank *bank, uint8_t index, uint8_t calibrated) {
  if (!bank || index >= NODE_B_SENSOR_COUNT) return;
  bank->calibrated[index] = calibrated ? 1U : 0U;
  bank->readings[index].calibrated = calibrated ? 1U : 0U;
}

void NodeBSensorBank_SetCommissionedForAlarm(NodeBSensorBank *bank, uint8_t index, uint8_t commissioned) {
  if (!bank || index >= NODE_B_SENSOR_COUNT) return;
  bank->readings[index].commissioned_for_alarm = commissioned ? 1U : 0U;
}

void NodeBSensorBank_Tick(NodeBSensorBank *bank, uint32_t now_ms) {
  if (bank == NULL) return;

  uint8_t item = bank->cursor;
  bank->cursor = (uint8_t)((bank->cursor + 1U) % NODE_B_SENSOR_COUNT);

  SensorReading *reading = &bank->readings[item];

  if (item < NODE_B_ANALOG_PIN_COUNT) {
    /* Analog channel */
    uint8_t a_idx = item;
    if (!reading->enabled) {
      SensorReading_SetMissing(reading, now_ms);
      return;
    }
    const NodeAnalogPin *cfg = &kNodeBAnalogPins[a_idx];
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
      reading->calibrated = bank->calibrated[item];
      SensorReading_SetAnalog(reading, val, uv, now_ms, q);
    } else {
      SensorReading_SetMissing(reading, now_ms);
    }
  } else {
    /* Digital channel */
    uint8_t d_idx = (uint8_t)(item - NODE_B_ANALOG_PIN_COUNT);
    if (!reading->enabled) {
      SensorReading_SetMissing(reading, now_ms);
      reading->alarm = 0U;
      return;
    }
    const NodeDigitalPin *cfg = &kNodeBDigitalPins[d_idx];
    GPIO_PinState pin_state = HAL_GPIO_ReadPin(cfg->port, cfg->pin);
    /* Active-low for flame, level, and MQ2 comparator outputs */
    uint8_t active_sample = (pin_state == GPIO_PIN_RESET) ? 1U : 0U;
    uint8_t stable = DigitalDebounce_Update(&bank->debounces[d_idx], active_sample,
                                           DIGITAL_DEBOUNCE_SAMPLES);
    SensorReading_SetDigital(reading, stable, stable, now_ms, SENSOR_QUALITY_GOOD);
  }
}
