#ifndef NODE_B_SENSOR_BANK_H
#define NODE_B_SENSOR_BANK_H

#include <stdint.h>
#include "stm32f1xx_hal.h"
#include "multi_sensor.h"
#include "node_sensor_pin_map.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NODE_B_SENSOR_COUNT (NODE_B_ANALOG_PIN_COUNT + NODE_B_DIGITAL_PIN_COUNT)

typedef struct {
  SensorReading readings[NODE_B_SENSOR_COUNT];
  DigitalDebounce debounces[NODE_B_DIGITAL_PIN_COUNT];
  uint32_t adc_accum[NODE_B_ANALOG_PIN_COUNT];
  uint16_t adc_count[NODE_B_ANALOG_PIN_COUNT];
  uint16_t adc_filtered[NODE_B_ANALOG_PIN_COUNT];
  ADC_HandleTypeDef *hadc;
  uint8_t cursor;
  uint8_t calibrated[NODE_B_SENSOR_COUNT];
} NodeBSensorBank;

void NodeBSensorBank_Init(NodeBSensorBank *bank, ADC_HandleTypeDef *hadc);

void NodeBSensorBank_Tick(NodeBSensorBank *bank, uint32_t now_ms);

const SensorReading *NodeBSensorBank_Readings(const NodeBSensorBank *bank);

uint8_t NodeBSensorBank_Count(const NodeBSensorBank *bank);

const SensorReading *NodeBSensorBank_FindReading(const NodeBSensorBank *bank,
                                                 const char *asset_code);

int8_t NodeBSensorBank_FindIndex(const NodeBSensorBank *bank, const char *asset_code);

void NodeBSensorBank_SetEnabled(NodeBSensorBank *bank, uint8_t index, uint8_t enabled);

void NodeBSensorBank_SetCalibrated(NodeBSensorBank *bank, uint8_t index, uint8_t calibrated);

void NodeBSensorBank_SetCommissionedForAlarm(NodeBSensorBank *bank, uint8_t index, uint8_t commissioned);

#ifdef __cplusplus
}
#endif

#endif /* NODE_B_SENSOR_BANK_H */
