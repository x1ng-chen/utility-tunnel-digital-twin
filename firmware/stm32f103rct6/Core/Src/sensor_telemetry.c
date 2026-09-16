#include "sensor_telemetry.h"
#include <stdio.h>
#include <string.h>

static const char *quality_to_str(SensorQuality q) {
  switch (q) {
    case SENSOR_QUALITY_GOOD: return "good";
    case SENSOR_QUALITY_SUSPECT: return "suspect";
    case SENSOR_QUALITY_BAD: return "bad";
    case SENSOR_QUALITY_MISSING:
    default: return "missing";
  }
}

void SensorTelemetry_Init(SensorTelemetryCursor *cursor, uint32_t initial_sequence) {
  if (cursor == NULL) return;
  cursor->sequence = initial_sequence;
  cursor->next_index = 0U;
}

static int format_reading_json(const SensorReading *r, char *dest, size_t dest_cap) {
  const char *q_str = quality_to_str(r->quality);

  switch (r->kind) {
    case SENSOR_KIND_SHT30: {
      int32_t temp_val = (r->quality == SENSOR_QUALITY_MISSING) ? 0 : r->temperature_centi_c;
      uint32_t hum_val = (r->quality == SENSOR_QUALITY_MISSING) ? 0U : r->humidity_centi_rh;
      const char *temp_sign = "";
      if (temp_val < 0) {
        temp_sign = "-";
        temp_val = -temp_val;
      }
      return snprintf(dest, dest_cap,
        "{\"assetCode\":\"%s\",\"metric\":\"temperature\",\"value\":%s%ld.%02ld,\"unit\":\"degC\",\"quality\":\"%s\"},"
        "{\"assetCode\":\"%s\",\"metric\":\"humidity\",\"value\":%lu.%02lu,\"unit\":\"%%RH\",\"quality\":\"%s\"}",
        r->asset_code, temp_sign, (long)(temp_val / 100), (long)(temp_val % 100), q_str,
        r->asset_code, (unsigned long)(hum_val / 100U), (unsigned long)(hum_val % 100U), q_str);
    }
    case SENSOR_KIND_MQ4:
    case SENSOR_KIND_O2:
    case SENSOR_KIND_CO: {
      uint32_t raw_val = (r->quality == SENSOR_QUALITY_MISSING) ? 0U : (uint32_t)r->raw;
      uint32_t uv_val = (r->quality == SENSOR_QUALITY_MISSING) ? 0UL : r->microvolts;
      return snprintf(dest, dest_cap,
        "{\"assetCode\":\"%s\",\"metric\":\"raw\",\"value\":%lu,\"unit\":\"adc\",\"quality\":\"%s\"},"
        "{\"assetCode\":\"%s\",\"metric\":\"voltage\",\"value\":%lu.%03lu,\"unit\":\"mV\",\"quality\":\"%s\"}",
        r->asset_code, (unsigned long)raw_val, q_str,
        r->asset_code, (unsigned long)(uv_val / 1000UL), (unsigned long)(uv_val % 1000UL), q_str);
    }
    case SENSOR_KIND_FLAME: {
      uint8_t alarm_val = (r->quality == SENSOR_QUALITY_MISSING) ? 0U : r->alarm;
      return snprintf(dest, dest_cap,
        "{\"assetCode\":\"%s\",\"metric\":\"flame.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"}",
        r->asset_code, (unsigned int)alarm_val, q_str);
    }
    case SENSOR_KIND_LEVEL: {
      uint8_t alarm_val = (r->quality == SENSOR_QUALITY_MISSING) ? 0U : r->alarm;
      return snprintf(dest, dest_cap,
        "{\"assetCode\":\"%s\",\"metric\":\"level.detected\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"}",
        r->asset_code, (unsigned int)alarm_val, q_str);
    }
    case SENSOR_KIND_MQ2: {
      uint8_t alarm_val = (r->quality == SENSOR_QUALITY_MISSING) ? 0U : r->alarm;
      return snprintf(dest, dest_cap,
        "{\"assetCode\":\"%s\",\"metric\":\"smoke.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"}",
        r->asset_code, (unsigned int)alarm_val, q_str);
    }
    default:
      return -1;
  }
}

uint8_t SensorTelemetry_FormatNext(const SensorReading *readings,
                                   uint8_t count,
                                   SensorTelemetryCursor *cursor,
                                   char *buffer,
                                   uint16_t capacity,
                                   uint16_t *length) {
  if (readings == NULL || count == 0U || cursor == NULL ||
      buffer == NULL || capacity < 64U || length == NULL) {
    return 0U;
  }

  uint16_t max_payload = (capacity > SENSOR_TELEMETRY_FRAME_LIMIT)
                             ? (SENSOR_TELEMETRY_FRAME_LIMIT - 1U)
                             : (capacity - 1U);

  char temp_buf[256];
  int prefix_len = snprintf(buffer, capacity,
                            "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":[",
                            (unsigned long)cursor->sequence);
  if (prefix_len <= 0 || (uint16_t)prefix_len >= max_payload) {
    return 0U;
  }

  uint16_t curr_len = (uint16_t)prefix_len;
  uint8_t start_idx = cursor->next_index;
  if (start_idx >= count) start_idx = 0U;
  uint8_t curr_idx = start_idx;
  uint8_t packed_count = 0U;

  while (packed_count < count) {
    int item_len = format_reading_json(&readings[curr_idx], temp_buf, sizeof(temp_buf));
    if (item_len <= 0) {
      curr_idx = (uint8_t)((curr_idx + 1U) % count);
      packed_count++;
      continue;
    }

    uint16_t extra = (packed_count > 0U) ? 1U : 0U; /* leading comma */
    /* 4 bytes for "]}\r\n" */
    if ((curr_len + extra + (uint16_t)item_len + 4U) > max_payload) {
      break;
    }

    if (extra > 0U) {
      buffer[curr_len++] = ',';
    }
    memcpy(&buffer[curr_len], temp_buf, (size_t)item_len);
    curr_len = (uint16_t)(curr_len + (uint16_t)item_len);
    buffer[curr_len] = '\0';

    packed_count++;
    curr_idx = (uint8_t)((curr_idx + 1U) % count);
  }

  if (packed_count == 0U) {
    return 0U;
  }

  buffer[curr_len++] = ']';
  buffer[curr_len++] = '}';
  buffer[curr_len++] = '\r';
  buffer[curr_len++] = '\n';
  buffer[curr_len] = '\0';

  *length = curr_len;
  cursor->next_index = curr_idx;
  cursor->sequence++;
  return 1U;
}
