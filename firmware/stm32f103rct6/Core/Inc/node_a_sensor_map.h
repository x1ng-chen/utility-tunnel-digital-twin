#ifndef NODE_A_SENSOR_MAP_H
#define NODE_A_SENSOR_MAP_H

#if defined(__has_include)
  #if __has_include("stm32f1xx_hal.h")
    #include "stm32f1xx_hal.h"
  #endif
#else
  #include "stm32f1xx_hal.h"
#endif
#include "multi_sensor.h"
#include <string.h>

/* Node A gas-sensor analog inputs. Keep this mapping aligned with the
 * physical harness and the ADC GPIO configuration in stm32f1xx_hal_msp.c. */
#define NODE_A_CO_ADC_CHANNEL       ADC_CHANNEL_11 /* PC1 */
#define NODE_A_METHANE_ADC_CHANNEL  ADC_CHANNEL_12 /* PC2 */
#define NODE_A_OXYGEN_ADC_CHANNEL   ADC_CHANNEL_13 /* PC3 */

/* Use 64-bit arithmetic: 4095 * 3.3 V fits in 32 bits, but common gas-sensor
 * readings do not when raw is multiplied by the reference in microvolts. */
#define NODE_A_ADC_RAW_TO_UV(raw) \
  ((uint32_t)((((uint64_t)(raw) * 3300000ULL) + 2047ULL) / 4095ULL))

#define NODE_A_MEDIAN3(a, b, c) \
  (((a) > (b)) ? (((b) > (c)) ? (b) : (((a) > (c)) ? (c) : (a))) \
               : (((a) > (c)) ? (a) : (((b) > (c)) ? (c) : (b))))

#define NODE_A_EMA_QUARTER(previous, sample) \
  ((uint16_t)((((uint32_t)(previous) * 3UL) + (uint32_t)(sample) + 2UL) / 4UL))

#define NODE_A_HIGH_ALARM_STATE(current, value, on_threshold, off_threshold) \
  ((uint8_t)(((current) != 0U) ? ((value) > (off_threshold)) \
                                     : ((value) >= (on_threshold))))
#define NODE_A_LOW_ALARM_STATE(current, value, on_threshold, off_threshold) \
  ((uint8_t)(((current) != 0U) ? ((value) < (off_threshold)) \
                                     : ((value) <= (on_threshold))))

#define NODE_A_CO_WARNING_ON_RAW          1800U
#define NODE_A_CO_WARNING_OFF_RAW         1700U
#define NODE_A_CO_ALARM_ON_RAW            2200U
#define NODE_A_CO_ALARM_OFF_RAW           2100U
#define NODE_A_METHANE_WARNING_ON_RAW      650U
#define NODE_A_METHANE_WARNING_OFF_RAW     600U
#define NODE_A_METHANE_ALARM_ON_RAW        900U
#define NODE_A_METHANE_ALARM_OFF_RAW       850U
#define NODE_A_OXYGEN_WARNING_ON_RAW        36U
#define NODE_A_OXYGEN_WARNING_OFF_RAW       40U
#define NODE_A_OXYGEN_ALARM_ON_RAW          32U
#define NODE_A_OXYGEN_ALARM_OFF_RAW         35U

/* Gas inputs remain telemetry-only until their analog front ends have warmed
 * up and been calibrated against known references.  Set this flag to 1 only
 * after MQ4 commissioning; provisional raw thresholds must not drive outputs. */
#define NODE_A_OXYGEN_SAFETY_COMMISSIONED  0U
#define NODE_A_METHANE_SAFETY_COMMISSIONED 0U
#define NODE_A_CO_SAFETY_COMMISSIONED      0U
#define NODE_A_OPERATIONAL_GAS_ALARM(oxygen_state, methane_state, co_state) \
  ((uint8_t)((NODE_A_METHANE_SAFETY_COMMISSIONED != 0U) && \
             ((methane_state) != 0U)))

#define NODE_A_GAS_VENTILATION_HOLD_MS    30000U
#define NODE_A_GAS_VENTILATION_SHOULD_RUN(alarm, cooling, elapsed_ms) \
  ((uint8_t)(((alarm) != 0U) || \
             (((cooling) != 0U) && \
              ((elapsed_ms) < NODE_A_GAS_VENTILATION_HOLD_MS))))

#define SENSOR_SAFETY_MAX_SOURCES 16U

typedef struct {
  uint8_t alarm_active;
  uint8_t ventilation_required;
  uint8_t audible_required;
  uint8_t source_count;
  char sources[SENSOR_SAFETY_MAX_SOURCES][12];
} SensorSafetyResult;

static inline uint8_t has_source(const SensorSafetyResult *result, const char *asset_code) {
  if (result == NULL || asset_code == NULL) return 0U;
  for (uint8_t i = 0U; i < result->source_count; ++i) {
    if (strncmp(result->sources[i], asset_code, sizeof(result->sources[i])) == 0) {
      return 1U;
    }
  }
  return 0U;
}

static inline SensorSafetyResult SensorSafety_Evaluate(const SensorReading *readings, uint8_t count) {
  SensorSafetyResult result;
  memset(&result, 0, sizeof(result));
  if (readings == NULL || count == 0U) {
    return result;
  }

  for (uint8_t i = 0U; i < count; ++i) {
    const SensorReading *r = &readings[i];
    if (!r->enabled || !r->online || r->quality != SENSOR_QUALITY_GOOD) {
      continue;
    }
    if (!r->commissioned_for_alarm) {
      continue;
    }

    uint8_t is_analog = (r->kind == SENSOR_KIND_MQ4 || r->kind == SENSOR_KIND_O2 || r->kind == SENSOR_KIND_CO);
    if (is_analog && !r->calibrated) {
      continue;
    }

    if (r->alarm) {
      result.alarm_active = 1U;
      if (result.source_count < SENSOR_SAFETY_MAX_SOURCES) {
        size_t j = 0;
        while (j < sizeof(result.sources[result.source_count]) - 1U && r->asset_code[j] != '\0') {
          result.sources[result.source_count][j] = r->asset_code[j];
          ++j;
        }
        result.sources[result.source_count][j] = '\0';
        result.source_count++;
      }

      if (r->kind == SENSOR_KIND_MQ4 || r->kind == SENSOR_KIND_MQ2 || r->kind == SENSOR_KIND_CO) {
        result.ventilation_required = 1U;
        result.audible_required = 1U;
      } else if (r->kind == SENSOR_KIND_FLAME) {
        result.audible_required = 1U;
      } else if (r->kind == SENSOR_KIND_LEVEL) {
        result.audible_required = 1U;
      }
    }
  }

  return result;
}

#endif
