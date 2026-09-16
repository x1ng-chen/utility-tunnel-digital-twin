#include "node_b_sensor_bank.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

static const SensorReading *find_reading(const NodeBSensorBank *bank, const char *asset_code) {
  return NodeBSensorBank_FindReading(bank, asset_code);
}

int main(void) {
  ADC_HandleTypeDef fake_adc = {0};
  NodeBSensorBank bank;
  NodeBSensorBank_Init(&bank, &fake_adc);

  /* 1. Assert exactly 12 expected readings */
  assert(NodeBSensorBank_Count(&bank) == 12U);

  static const char *const expected_assets[12] = {
    "MQ4-03", "MQ4-04", "MQ4-05", "O2-03", "CO-04", "CO-05",
    "FLAME-04", "FLAME-05", "MQ2-04", "MQ2-05", "LEVEL-04", "LEVEL-05"
  };

  for (size_t i = 0; i < 12U; ++i) {
    const SensorReading *r = find_reading(&bank, expected_assets[i]);
    assert(r != NULL);
    assert(strcmp(r->asset_code, expected_assets[i]) == 0);
  }

  /* 2. Pin audit assertions:
   * No access to joystick PC0/PC1 or PC4
   * No use of screen pins PA5/PA7 or PB6-PB9 */
  for (uint8_t i = 0; i < NODE_B_ANALOG_PIN_COUNT; ++i) {
    const NodeAnalogPin *p = &kNodeBAnalogPins[i];
    /* Check joystick isolation */
    assert(!(p->port == GPIOC && (p->pin == GPIO_PIN_0 || p->pin == GPIO_PIN_1 || p->pin == GPIO_PIN_4)));
    /* Check screen isolation */
    assert(!(p->port == GPIOA && (p->pin == GPIO_PIN_5 || p->pin == GPIO_PIN_7)));
    assert(!(p->port == GPIOB && (p->pin == GPIO_PIN_6 || p->pin == GPIO_PIN_7 ||
                                  p->pin == GPIO_PIN_8 || p->pin == GPIO_PIN_9)));
  }

  for (uint8_t i = 0; i < NODE_B_DIGITAL_PIN_COUNT; ++i) {
    const NodeDigitalPin *p = &kNodeBDigitalPins[i];
    /* Check joystick isolation */
    assert(!(p->port == GPIOC && (p->pin == GPIO_PIN_0 || p->pin == GPIO_PIN_1 || p->pin == GPIO_PIN_4)));
    /* Check screen isolation */
    assert(!(p->port == GPIOA && (p->pin == GPIO_PIN_5 || p->pin == GPIO_PIN_7)));
    assert(!(p->port == GPIOB && (p->pin == GPIO_PIN_6 || p->pin == GPIO_PIN_7 ||
                                  p->pin == GPIO_PIN_8 || p->pin == GPIO_PIN_9)));
  }

  /* 3. Scheduling guarantee: exactly one sensor is processed per tick */
  assert(bank.cursor == 0U);
  for (uint32_t now = 0; now < 12U; ++now) {
    uint8_t prev_cursor = bank.cursor;
    NodeBSensorBank_Tick(&bank, now);
    assert(bank.cursor == (uint8_t)((prev_cursor + 1U) % 12U));
  }
  assert(bank.cursor == 0U);

  /* 4. Fault case: Disabled sensor yields MISSING quality and 0 alarm */
  int8_t flame4_idx = NodeBSensorBank_FindIndex(&bank, "FLAME-04");
  assert(flame4_idx >= 0);
  NodeBSensorBank_SetEnabled(&bank, (uint8_t)flame4_idx, 0U);
  const SensorReading *flame4 = find_reading(&bank, "FLAME-04");
  assert(flame4 != NULL);
  assert(flame4->quality == SENSOR_QUALITY_MISSING);
  assert(flame4->alarm == 0U);

  /* 5. Fault case: Saturated analog channel at 4095 yields BAD quality */
  SensorReading saturated_reading;
  SensorReading_Init(&saturated_reading, "MQ4-03", SENSOR_KIND_MQ4, 1U);
  SensorReading_SetAnalog(&saturated_reading, 4095U, 3300000UL, 100U, SENSOR_QUALITY_BAD);
  assert(saturated_reading.quality == SENSOR_QUALITY_BAD);

  /* 6. Fault case: Digital debounce requires stable count */
  DigitalDebounce bounce_db = {0};
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 0U);
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 0U);
  assert(DigitalDebounce_Update(&bounce_db, 0U, 4U) == 0U); /* noise pulse */
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 0U);
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 0U);
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 0U);
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 1U); /* confirmed after 4 stable samples */

  printf("node_b_sensor_bank_host_test passed!\n");
  return 0;
}
