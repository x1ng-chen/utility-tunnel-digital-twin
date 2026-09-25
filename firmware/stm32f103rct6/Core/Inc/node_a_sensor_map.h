#ifndef NODE_A_SENSOR_MAP_H
#define NODE_A_SENSOR_MAP_H

#include "stm32f1xx_hal.h"

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

/* Only the methane channel has completed a physical alarm-response bench
 * check. Oxygen and CO remain telemetry-only until their analog front ends
 * are calibrated; their provisional raw thresholds must not drive actuators. */
#define NODE_A_OPERATIONAL_GAS_ALARM(oxygen_state, methane_state, co_state) \
  ((uint8_t)((methane_state) != 0U))

#define NODE_A_GAS_VENTILATION_HOLD_MS    30000U
#define NODE_A_GAS_VENTILATION_SHOULD_RUN(alarm, cooling, elapsed_ms) \
  ((uint8_t)(((alarm) != 0U) || \
             (((cooling) != 0U) && \
              ((elapsed_ms) < NODE_A_GAS_VENTILATION_HOLD_MS))))

#endif
