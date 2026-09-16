#ifndef SENSOR_TELEMETRY_H
#define SENSOR_TELEMETRY_H

#include "multi_sensor.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SENSOR_TELEMETRY_FRAME_LIMIT 768U

typedef struct {
  uint32_t sequence;
  uint8_t next_index;
} SensorTelemetryCursor;

void SensorTelemetry_Init(SensorTelemetryCursor *cursor, uint32_t initial_sequence);

uint8_t SensorTelemetry_FormatNext(const SensorReading *readings,
                                   uint8_t count,
                                   SensorTelemetryCursor *cursor,
                                   char *buffer,
                                   uint16_t capacity,
                                   uint16_t *length);

#ifdef __cplusplus
}
#endif

#endif /* SENSOR_TELEMETRY_H */
