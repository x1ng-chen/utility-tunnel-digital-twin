#include "multi_sensor.h"
#include "node_a_sensor_map.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

int main(void) {
  /* Startup test: unconfigured/floating inputs do not trigger actuators */
  {
    SensorReading unconf[4];
    SensorReading_Init(&unconf[0], "MQ4-01", SENSOR_KIND_MQ4, 0U);
    SensorReading_Init(&unconf[1], "FLAME-01", SENSOR_KIND_FLAME, 0U);
    SensorReading_Init(&unconf[2], "CO-01", SENSOR_KIND_CO, 0U);
    SensorReading_Init(&unconf[3], "LEVEL-01", SENSOR_KIND_LEVEL, 0U);
    /* Even if raw floating levels look like alarms */
    unconf[0].alarm = 1U;
    unconf[1].alarm = 1U;
    unconf[2].alarm = 1U;
    unconf[3].alarm = 1U;

    SensorSafetyResult start_res = SensorSafety_Evaluate(unconf, 4U);
    assert(start_res.alarm_active == 0U);
    assert(start_res.ventilation_required == 0U);
    assert(start_res.audible_required == 0U);
    assert(start_res.source_count == 0U);
  }

  /* Uncalibrated analog channel does not trigger actuators */
  {
    SensorReading uncal[1];
    SensorReading_Init(&uncal[0], "MQ4-02", SENSOR_KIND_MQ4, 1U);
    SensorReading_SetAnalog(&uncal[0], 2500U, 2014000UL, 100U, SENSOR_QUALITY_GOOD);
    uncal[0].alarm = 1U;
    uncal[0].commissioned_for_alarm = 1U;
    uncal[0].calibrated = 0U; /* Not calibrated */

    SensorSafetyResult uncal_res = SensorSafety_Evaluate(uncal, 1U);
    assert(uncal_res.alarm_active == 0U);
    assert(uncal_res.ventilation_required == 0U);
    assert(uncal_res.audible_required == 0U);
    assert(!has_source(&uncal_res, "MQ4-02"));
  }

  /* Core safety gating test:
     MQ4-01 commissioned alarm -> ventilation; CO-02 suspect -> telemetry only;
     disabled FLAME-03 active level -> ignored; FLAME-04 good/alarm -> audible alarm. */
  {
    SensorReading readings[4];

    /* MQ4-01: commissioned, calibrated, good quality, alarm -> ventilation */
    SensorReading_Init(&readings[0], "MQ4-01", SENSOR_KIND_MQ4, 1U);
    SensorReading_SetAnalog(&readings[0], 1200U, 967000UL, 100U, SENSOR_QUALITY_GOOD);
    readings[0].calibrated = 1U;
    readings[0].commissioned_for_alarm = 1U;
    readings[0].alarm = 1U;

    /* CO-02: suspect -> telemetry only */
    SensorReading_Init(&readings[1], "CO-02", SENSOR_KIND_CO, 1U);
    SensorReading_SetAnalog(&readings[1], 2000U, 1611000UL, 100U, SENSOR_QUALITY_SUSPECT);
    readings[1].calibrated = 0U;
    readings[1].commissioned_for_alarm = 0U;
    readings[1].alarm = 1U;

    /* FLAME-03: disabled -> ignored */
    SensorReading_Init(&readings[2], "FLAME-03", SENSOR_KIND_FLAME, 0U);
    readings[2].alarm = 1U;
    readings[2].digital_value = 1U;

    /* FLAME-04: good quality, commissioned, alarm -> audible alarm */
    SensorReading_Init(&readings[3], "FLAME-04", SENSOR_KIND_FLAME, 1U);
    SensorReading_SetDigital(&readings[3], 1U, 1U, 100U, SENSOR_QUALITY_GOOD);
    readings[3].commissioned_for_alarm = 1U;

    SensorSafetyResult result = SensorSafety_Evaluate(readings, 4U);
    assert(result.ventilation_required == 1U);
    assert(result.audible_required == 1U);
    assert(has_source(&result, "MQ4-01"));
    assert(has_source(&result, "FLAME-04"));
    assert(!has_source(&result, "CO-02"));
    assert(!has_source(&result, "FLAME-03"));
  }

  printf("multi_sensor_safety_host_test passed!\n");
  return 0;
}
