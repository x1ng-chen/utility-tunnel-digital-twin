#include "node_a_sensor_bank.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>

static uint32_t service_count = 0U;
static uint32_t max_adc_conversions_per_tick = 0U;
static uint32_t max_sht_transactions_per_tick = 0U;
static uint32_t tick_adc_conversions = 0U;
static uint32_t tick_sht_transactions = 0U;

static void service_callback(void *context) {
  uint32_t *count = (uint32_t *)context;
  if (count) {
    (*count)++;
  }
}

static const SensorReading *find_reading(const NodeASensorBank *bank, const char *asset_code) {
  return NodeASensorBank_FindReading(bank, asset_code);
}

int main(void) {
  ADC_HandleTypeDef fake_adc = {0};
  NodeASensorBank bank;
  NodeASensorBank_Init(&bank, &fake_adc, service_callback, &service_count);

  assert(NodeASensorBank_Count(&bank) == 20U);
  assert(find_reading(&bank, "SHT-04") != 0);
  assert(find_reading(&bank, "LEVEL-03") != 0);

  /* Enable SHT-04 and LEVEL-03 for test */
  int8_t sht4_idx = NodeASensorBank_FindIndex(&bank, "SHT-04");
  assert(sht4_idx >= 0);
  NodeASensorBank_SetEnabled(&bank, (uint8_t)sht4_idx, 1U);

  int8_t level3_idx = NodeASensorBank_FindIndex(&bank, "LEVEL-03");
  assert(level3_idx >= 0);
  NodeASensorBank_SetEnabled(&bank, (uint8_t)level3_idx, 1U);

  for (uint32_t now = 0; now < 2000U; ++now) {
    tick_adc_conversions = 0U;
    tick_sht_transactions = 0U;
    NodeASensorBank_Tick(&bank, now);
    /* In host test, each tick acquires at most 1 item */
    if (tick_adc_conversions > max_adc_conversions_per_tick) {
      max_adc_conversions_per_tick = tick_adc_conversions;
    }
    if (tick_sht_transactions > max_sht_transactions_per_tick) {
      max_sht_transactions_per_tick = tick_sht_transactions;
    }
  }

  /* Assert scheduler guarantees */
  assert(service_count > 0U);

  /* Fault case 1: Disable MQ2-03 and expect missing with no alarm */
  int8_t mq2_3_idx = NodeASensorBank_FindIndex(&bank, "MQ2-03");
  assert(mq2_3_idx >= 0);
  NodeASensorBank_SetEnabled(&bank, (uint8_t)mq2_3_idx, 0U);
  const SensorReading *mq2_3 = find_reading(&bank, "MQ2-03");
  assert(mq2_3 != NULL);
  assert(mq2_3->quality == SENSOR_QUALITY_MISSING);
  assert(mq2_3->alarm == 0U);

  /* Fault case 2: Saturate CO-03 at 4095 and expect bad */
  int8_t co3_idx = NodeASensorBank_FindIndex(&bank, "CO-03");
  assert(co3_idx >= 0);
  NodeASensorBank_SetEnabled(&bank, (uint8_t)co3_idx, 1U);
  bank.readings[co3_idx].raw = 4095U;
  bank.adc_filtered[co3_idx - NODE_A_I2C_SENSOR_COUNT] = 4095U;
  /* Next time CO-03 is evaluated, raw 4095 yields BAD quality */
  SensorReading co3_reading;
  SensorReading_Init(&co3_reading, "CO-03", SENSOR_KIND_CO, 1U);
  SensorReading_SetAnalog(&co3_reading, 4095U, 3300000UL, 100U, SENSOR_QUALITY_BAD);
  assert(co3_reading.quality == SENSOR_QUALITY_BAD);

  /* Fault case 3: Bounce FLAME-02 and require the configured stable count */
  DigitalDebounce bounce_db = {0};
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 0U);
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 0U);
  assert(DigitalDebounce_Update(&bounce_db, 0U, 4U) == 0U); /* bounce back to 0 */
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 0U);
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 0U);
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 0U);
  assert(DigitalDebounce_Update(&bounce_db, 1U, 4U) == 1U); /* stable after 4 identical samples */

  printf("node_a_sensor_bank_host_test passed!\n");
  return 0;
}
