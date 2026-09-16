#include "sensor_telemetry.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void) {
  SensorReading readings[3];
  SensorReading_Init(&readings[0], "SHT-01", SENSOR_KIND_SHT30, 1U);
  SensorReading_SetSht30(&readings[0], 2345, 5210, 100U, SENSOR_QUALITY_GOOD);

  SensorReading_Init(&readings[1], "MQ4-02", SENSOR_KIND_MQ4, 1U);
  SensorReading_SetAnalog(&readings[1], 1234U, 994212UL, 100U, SENSOR_QUALITY_SUSPECT);

  SensorReading_Init(&readings[2], "FLAME-03", SENSOR_KIND_FLAME, 1U);
  SensorReading_SetMissing(&readings[2], 100U);

  SensorTelemetryCursor cursor = { .sequence = 40U, .next_index = 0U };
  char frame[768];
  uint16_t length = 0U;

  assert(SensorTelemetry_FormatNext(readings, 3U, &cursor, frame,
                                    sizeof frame, &length) == 1U);
  assert(strstr(frame, "\"assetCode\":\"SHT-01\"") != NULL);
  assert(strstr(frame, "\"quality\":\"good\"") != NULL);
  assert(strstr(frame, "\"metric\":\"temperature\"") != NULL);
  assert(strstr(frame, "\"unit\":\"degC\"") != NULL);
  assert(strstr(frame, "\"metric\":\"humidity\"") != NULL);
  assert(strstr(frame, "\"unit\":\"%RH\"") != NULL);

  assert(strstr(frame, "\"assetCode\":\"MQ4-02\"") != NULL);
  assert(strstr(frame, "\"quality\":\"suspect\"") != NULL);
  assert(strstr(frame, "\"metric\":\"raw\"") != NULL);
  assert(strstr(frame, "\"unit\":\"adc\"") != NULL);
  assert(strstr(frame, "\"metric\":\"voltage\"") != NULL);
  assert(strstr(frame, "\"unit\":\"mV\"") != NULL);

  assert(strstr(frame, "\"assetCode\":\"FLAME-03\"") != NULL);
  assert(strstr(frame, "\"quality\":\"missing\"") != NULL);
  assert(strstr(frame, "\"metric\":\"flame.alarm\"") != NULL);
  assert(strstr(frame, "\"unit\":\"bool\"") != NULL);
  assert(strstr(frame, "\"value\":0") != NULL);

  assert(length < sizeof frame);
  assert(length > 0U);
  assert(frame[length - 2] == '\r');
  assert(frame[length - 1] == '\n');
  assert(cursor.sequence == 41U);

  /* Missing values must not reuse prior values */
  SensorReading gas_reading;
  SensorReading_Init(&gas_reading, "CO-01", SENSOR_KIND_CO, 1U);
  SensorReading_SetAnalog(&gas_reading, 2000U, 1611000UL, 100U, SENSOR_QUALITY_GOOD);
  SensorReading_SetMissing(&gas_reading, 200U);
  cursor.sequence = 50U;
  cursor.next_index = 0U;
  assert(SensorTelemetry_FormatNext(&gas_reading, 1U, &cursor, frame, sizeof frame, &length) == 1U);
  assert(strstr(frame, "\"raw\":2000") == NULL);
  assert(strstr(frame, "\"value\":0") != NULL);
  assert(strstr(frame, "\"value\":0.000") != NULL);
  assert(strstr(frame, "\"quality\":\"missing\"") != NULL);

  /* Small buffer returns 0 without advancing sequence or cursor */
  char tiny[40];
  uint16_t tiny_len = 0U;
  uint32_t seq_before = cursor.sequence;
  uint8_t next_before = cursor.next_index;
  assert(SensorTelemetry_FormatNext(readings, 3U, &cursor, tiny, sizeof tiny, &tiny_len) == 0U);
  assert(cursor.sequence == seq_before);
  assert(cursor.next_index == next_before);

  /* Packing rotation: multiple items across smaller capacity buffer */
  SensorReading many[6];
  for (uint8_t i = 0U; i < 6U; ++i) {
    char code[10];
    snprintf(code, sizeof(code), "SHT-%02u", i + 1U);
    SensorReading_Init(&many[i], code, SENSOR_KIND_SHT30, 1U);
    SensorReading_SetSht30(&many[i], 2000 + i * 100, 5000 + i * 100, 100U, SENSOR_QUALITY_GOOD);
  }
  SensorTelemetry_Init(&cursor, 100U);
  uint16_t frames_count = 0U;
  while (frames_count < 10U) {
    uint8_t prev_next = cursor.next_index;
    assert(SensorTelemetry_FormatNext(many, 6U, &cursor, frame, 350U, &length) == 1U);
    assert(length < 350U);
    assert(frame[length - 2] == '\r');
    assert(frame[length - 1] == '\n');
    assert(cursor.sequence == (101U + frames_count));
    frames_count++;
    if (prev_next > cursor.next_index) {
      /* Full rotation completed */
      break;
    }
  }
  assert(frames_count > 1U);

  printf("sensor_telemetry_host_test passed!\n");
  return 0;
}
