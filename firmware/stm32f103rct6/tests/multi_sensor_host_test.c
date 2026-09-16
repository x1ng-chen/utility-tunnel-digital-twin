#include "multi_sensor.h"
#include <assert.h>
#include <string.h>

int main(void) {
  SensorReading r;
  SensorReading_Init(&r, "MQ4-03", SENSOR_KIND_MQ4, 1U);
  assert(strcmp(r.asset_code, "MQ4-03") == 0);
  assert(r.quality == SENSOR_QUALITY_MISSING);
  SensorReading_SetAnalog(&r, 2048U, 1650403UL, 100U, SENSOR_QUALITY_SUSPECT);
  assert(r.raw == 2048U && r.microvolts == 1650403UL);
  assert(r.sampled_at_ms == 100U && r.quality == SENSOR_QUALITY_SUSPECT);

  DigitalDebounce d = {0};
  assert(DigitalDebounce_Update(&d, 1U, 3U) == 0U);
  assert(DigitalDebounce_Update(&d, 1U, 3U) == 0U);
  assert(DigitalDebounce_Update(&d, 1U, 3U) == 1U);
  assert(d.stable == 1U);
  return 0;
}
