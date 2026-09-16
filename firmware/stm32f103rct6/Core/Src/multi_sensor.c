#include "multi_sensor.h"
#include <string.h>

void SensorReading_Init(SensorReading *reading, const char *asset_code,
                        SensorKind kind, uint8_t enabled) {
  if (reading == NULL) {
    return;
  }
  memset(reading, 0, sizeof(*reading));
  if (asset_code != NULL) {
    size_t i = 0;
    while (i < sizeof(reading->asset_code) - 1U && asset_code[i] != '\0') {
      reading->asset_code[i] = asset_code[i];
      ++i;
    }
    reading->asset_code[i] = '\0';
  }
  reading->kind = kind;
  reading->quality = SENSOR_QUALITY_MISSING;
  reading->enabled = enabled ? 1U : 0U;
  reading->online = 0U;
}

void SensorReading_SetAnalog(SensorReading *reading, uint16_t raw,
                             uint32_t microvolts, uint32_t sampled_at_ms,
                             SensorQuality quality) {
  if (reading == NULL) {
    return;
  }
  reading->raw = raw;
  reading->microvolts = microvolts;
  reading->sampled_at_ms = sampled_at_ms;
  reading->quality = quality;
  reading->online = (quality != SENSOR_QUALITY_MISSING) ? 1U : 0U;
}

void SensorReading_SetDigital(SensorReading *reading, uint8_t digital_value,
                              uint8_t alarm, uint32_t sampled_at_ms,
                              SensorQuality quality) {
  if (reading == NULL) {
    return;
  }
  reading->digital_value = digital_value ? 1U : 0U;
  reading->alarm = alarm ? 1U : 0U;
  reading->sampled_at_ms = sampled_at_ms;
  reading->quality = quality;
  reading->online = (quality != SENSOR_QUALITY_MISSING) ? 1U : 0U;
}

void SensorReading_SetSht30(SensorReading *reading, int16_t temperature_centi_c,
                            uint16_t humidity_centi_rh, uint32_t sampled_at_ms,
                            SensorQuality quality) {
  if (reading == NULL) {
    return;
  }
  reading->temperature_centi_c = temperature_centi_c;
  reading->humidity_centi_rh = humidity_centi_rh;
  reading->sampled_at_ms = sampled_at_ms;
  reading->quality = quality;
  reading->online = (quality != SENSOR_QUALITY_MISSING) ? 1U : 0U;
}

void SensorReading_SetMissing(SensorReading *reading, uint32_t sampled_at_ms) {
  if (reading == NULL) {
    return;
  }
  reading->online = 0U;
  reading->quality = SENSOR_QUALITY_MISSING;
  reading->sampled_at_ms = sampled_at_ms;
}

uint8_t DigitalDebounce_Update(DigitalDebounce *debounce, uint8_t sample,
                               uint8_t required_count) {
  if (debounce == NULL) {
    return 0U;
  }
  uint8_t val = sample ? 1U : 0U;
  if (required_count <= 1U) {
    debounce->candidate = val;
    debounce->count = 1U;
    debounce->stable = val;
    return debounce->stable;
  }
  if (val == debounce->candidate) {
    if (debounce->count < required_count) {
      debounce->count++;
    }
  } else {
    debounce->candidate = val;
    debounce->count = 1U;
  }
  if (debounce->count >= required_count) {
    debounce->stable = debounce->candidate;
  }
  return debounce->stable;
}
