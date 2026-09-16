#ifndef MULTI_SENSOR_H
#define MULTI_SENSOR_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  SENSOR_QUALITY_GOOD = 0,
  SENSOR_QUALITY_SUSPECT = 1,
  SENSOR_QUALITY_BAD = 2,
  SENSOR_QUALITY_MISSING = 3
} SensorQuality;

typedef enum {
  SENSOR_KIND_SHT30 = 0,
  SENSOR_KIND_FLAME = 1,
  SENSOR_KIND_MQ4 = 2,
  SENSOR_KIND_MQ2 = 3,
  SENSOR_KIND_O2 = 4,
  SENSOR_KIND_CO = 5,
  SENSOR_KIND_LEVEL = 6
} SensorKind;

typedef struct {
  char asset_code[10];
  SensorKind kind;
  SensorQuality quality;
  uint8_t enabled;
  uint8_t online;
  uint8_t alarm;
  uint8_t calibrated;
  uint8_t commissioned_for_alarm;
  uint8_t digital_value;
  uint16_t raw;
  uint32_t microvolts;
  uint32_t sampled_at_ms;
  int16_t temperature_centi_c;
  uint16_t humidity_centi_rh;
} SensorReading;

typedef struct {
  uint8_t stable;
  uint8_t candidate;
  uint8_t count;
} DigitalDebounce;

void SensorReading_Init(SensorReading *reading, const char *asset_code,
                        SensorKind kind, uint8_t enabled);

void SensorReading_SetAnalog(SensorReading *reading, uint16_t raw,
                             uint32_t microvolts, uint32_t sampled_at_ms,
                             SensorQuality quality);

void SensorReading_SetDigital(SensorReading *reading, uint8_t digital_value,
                              uint8_t alarm, uint32_t sampled_at_ms,
                              SensorQuality quality);

void SensorReading_SetSht30(SensorReading *reading, int16_t temperature_centi_c,
                            uint16_t humidity_centi_rh, uint32_t sampled_at_ms,
                            SensorQuality quality);

void SensorReading_SetMissing(SensorReading *reading, uint32_t sampled_at_ms);

uint8_t DigitalDebounce_Update(DigitalDebounce *debounce, uint8_t sample,
                               uint8_t required_count);

#ifdef __cplusplus
}
#endif

#endif /* MULTI_SENSOR_H */
