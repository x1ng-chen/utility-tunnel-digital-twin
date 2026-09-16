#ifndef NODE_A_SENSOR_BANK_H
#define NODE_A_SENSOR_BANK_H

#include <stdint.h>
#include "stm32f1xx_hal.h"
#include "multi_sensor.h"
#include "node_sensor_pin_map.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NODE_A_SENSOR_COUNT (NODE_A_I2C_SENSOR_COUNT + NODE_A_ANALOG_PIN_COUNT + NODE_A_DIGITAL_PIN_COUNT)

typedef void (*NodeAServiceCallback)(void *context);

typedef struct {
  SensorReading readings[NODE_A_SENSOR_COUNT];
  DigitalDebounce debounces[NODE_A_DIGITAL_PIN_COUNT];
  uint32_t adc_accum[NODE_A_ANALOG_PIN_COUNT];
  uint16_t adc_count[NODE_A_ANALOG_PIN_COUNT];
  uint16_t adc_filtered[NODE_A_ANALOG_PIN_COUNT];
  ADC_HandleTypeDef *hadc;
  NodeAServiceCallback service_cb;
  void *service_ctx;
  uint8_t cursor;
  uint8_t calibrated[NODE_A_SENSOR_COUNT];
} NodeASensorBank;

void NodeASensorBank_Init(NodeASensorBank *bank, ADC_HandleTypeDef *hadc,
                          NodeAServiceCallback service_cb, void *service_ctx);

void NodeASensorBank_Tick(NodeASensorBank *bank, uint32_t now_ms);

const SensorReading *NodeASensorBank_Readings(const NodeASensorBank *bank);

uint8_t NodeASensorBank_Count(const NodeASensorBank *bank);

const SensorReading *NodeASensorBank_FindReading(const NodeASensorBank *bank,
                                                 const char *asset_code);

int8_t NodeASensorBank_FindIndex(const NodeASensorBank *bank, const char *asset_code);

void NodeASensorBank_SetEnabled(NodeASensorBank *bank, uint8_t index, uint8_t enabled);

void NodeASensorBank_SetCalibrated(NodeASensorBank *bank, uint8_t index, uint8_t calibrated);

#ifdef __cplusplus
}
#endif

#endif /* NODE_A_SENSOR_BANK_H */
