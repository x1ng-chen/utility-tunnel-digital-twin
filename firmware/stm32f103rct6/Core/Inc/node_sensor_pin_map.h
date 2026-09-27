#ifndef NODE_SENSOR_PIN_MAP_H
#define NODE_SENSOR_PIN_MAP_H

#include "stm32f1xx_hal.h"
#include "multi_sensor.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NODE_A_ANALOG_PIN_COUNT   7U
#define NODE_A_DIGITAL_PIN_COUNT  9U
#define NODE_A_I2C_SENSOR_COUNT   4U

#define NODE_B_ANALOG_PIN_COUNT   6U
#define NODE_B_DIGITAL_PIN_COUNT  6U

/* Node A Analog Channel Assignments */
#define NODE_A_CO1_ADC_CHANNEL    ADC_CHANNEL_11 /* PC1 */
#define NODE_A_MQ4_1_ADC_CHANNEL  ADC_CHANNEL_12 /* PC2 */
#define NODE_A_O2_1_ADC_CHANNEL   ADC_CHANNEL_13 /* PC3 */
#define NODE_A_CO2_ADC_CHANNEL    ADC_CHANNEL_0  /* PA0 */
#define NODE_A_MQ4_2_ADC_CHANNEL  ADC_CHANNEL_4  /* PA4 */
#define NODE_A_O2_2_ADC_CHANNEL   ADC_CHANNEL_5  /* PA5 */
#define NODE_A_CO3_ADC_CHANNEL    ADC_CHANNEL_9  /* PB1 */

/* Node A Digital Pin Assignments */
#define NODE_A_MQ2_1_PORT         GPIOB
#define NODE_A_MQ2_1_PIN          GPIO_PIN_12
#define NODE_A_FLAME1_PORT        GPIOB
#define NODE_A_FLAME1_PIN         GPIO_PIN_14
#define NODE_A_LEVEL1_PORT        GPIOC
#define NODE_A_LEVEL1_PIN         GPIO_PIN_0
#define NODE_A_FLAME2_PORT        GPIOC
#define NODE_A_FLAME2_PIN         GPIO_PIN_8
#define NODE_A_FLAME3_PORT        GPIOC
#define NODE_A_FLAME3_PIN         GPIO_PIN_9
/* Bench wiring: PC10 is already tied to the FAN-01 transistor base. */
#define NODE_A_MQ2_2_PORT         GPIOB
#define NODE_A_MQ2_2_PIN          GPIO_PIN_13
#define NODE_A_MQ2_3_PORT         GPIOC
#define NODE_A_MQ2_3_PIN          GPIO_PIN_11
#define NODE_A_LEVEL2_PORT        GPIOC
#define NODE_A_LEVEL2_PIN         GPIO_PIN_12
#define NODE_A_LEVEL3_PORT        GPIOC
#define NODE_A_LEVEL3_PIN         GPIO_PIN_13

/* Node B Analog Channel Assignments */
#define NODE_B_MQ4_3_ADC_CHANNEL  ADC_CHANNEL_0  /* PA0 */
#define NODE_B_MQ4_4_ADC_CHANNEL  ADC_CHANNEL_1  /* PA1 */
#define NODE_B_MQ4_5_ADC_CHANNEL  ADC_CHANNEL_4  /* PA4 */
#define NODE_B_O2_3_ADC_CHANNEL   ADC_CHANNEL_6  /* PA6 */
#define NODE_B_CO4_ADC_CHANNEL    ADC_CHANNEL_8  /* PB0 */
#define NODE_B_CO5_ADC_CHANNEL    ADC_CHANNEL_9  /* PB1 */

/* Node B Digital Pin Assignments */
#define NODE_B_FLAME4_PORT        GPIOC
#define NODE_B_FLAME4_PIN         GPIO_PIN_6
#define NODE_B_FLAME5_PORT        GPIOC
#define NODE_B_FLAME5_PIN         GPIO_PIN_7
#define NODE_B_MQ2_4_PORT         GPIOC
#define NODE_B_MQ2_4_PIN          GPIO_PIN_8
#define NODE_B_MQ2_5_PORT         GPIOC
#define NODE_B_MQ2_5_PIN          GPIO_PIN_9
#define NODE_B_LEVEL4_PORT        GPIOC
#define NODE_B_LEVEL4_PIN         GPIO_PIN_10
#define NODE_B_LEVEL5_PORT        GPIOC
#define NODE_B_LEVEL5_PIN         GPIO_PIN_11

typedef struct {
  const char *asset_code;
  SensorKind kind;
  GPIO_TypeDef *port;
  uint16_t pin;
  uint32_t adc_channel;
} NodeAnalogPin;

typedef struct {
  const char *asset_code;
  SensorKind kind;
  GPIO_TypeDef *port;
  uint16_t pin;
} NodeDigitalPin;

typedef struct {
  const char *asset_code;
  GPIO_TypeDef *scl_port;
  uint16_t scl_pin;
  GPIO_TypeDef *sda_port;
  uint16_t sda_pin;
  uint8_t i2c_address;
} NodeI2CSensorPin;

static const NodeI2CSensorPin kNodeAI2CPins[NODE_A_I2C_SENSOR_COUNT] = {
  { "SHT-01", GPIOB, GPIO_PIN_6,  GPIOB, GPIO_PIN_7,  0x44U },
  { "SHT-02", GPIOB, GPIO_PIN_6,  GPIOB, GPIO_PIN_7,  0x45U },
  { "SHT-03", GPIOB, GPIO_PIN_10, GPIOB, GPIO_PIN_11, 0x44U },
  { "SHT-04", GPIOB, GPIO_PIN_10, GPIOB, GPIO_PIN_11, 0x45U }
};

static const NodeAnalogPin kNodeAAnalogPins[NODE_A_ANALOG_PIN_COUNT] = {
  { "CO-01",  SENSOR_KIND_CO,  GPIOC, GPIO_PIN_1, NODE_A_CO1_ADC_CHANNEL },
  { "MQ4-01", SENSOR_KIND_MQ4, GPIOC, GPIO_PIN_2, NODE_A_MQ4_1_ADC_CHANNEL },
  { "O2-01",  SENSOR_KIND_O2,  GPIOC, GPIO_PIN_3, NODE_A_O2_1_ADC_CHANNEL },
  { "CO-02",  SENSOR_KIND_CO,  GPIOA, GPIO_PIN_0, NODE_A_CO2_ADC_CHANNEL },
  { "MQ4-02", SENSOR_KIND_MQ4, GPIOA, GPIO_PIN_4, NODE_A_MQ4_2_ADC_CHANNEL },
  { "O2-02",  SENSOR_KIND_O2,  GPIOA, GPIO_PIN_5, NODE_A_O2_2_ADC_CHANNEL },
  { "CO-03",  SENSOR_KIND_CO,  GPIOB, GPIO_PIN_1, NODE_A_CO3_ADC_CHANNEL }
};

static const NodeDigitalPin kNodeADigitalPins[NODE_A_DIGITAL_PIN_COUNT] = {
  { "MQ2-01",   SENSOR_KIND_MQ2,   NODE_A_MQ2_1_PORT,  NODE_A_MQ2_1_PIN },
  { "FLAME-01", SENSOR_KIND_FLAME, NODE_A_FLAME1_PORT, NODE_A_FLAME1_PIN },
  { "LEVEL-01", SENSOR_KIND_LEVEL, NODE_A_LEVEL1_PORT, NODE_A_LEVEL1_PIN },
  { "FLAME-02", SENSOR_KIND_FLAME, NODE_A_FLAME2_PORT, NODE_A_FLAME2_PIN },
  { "FLAME-03", SENSOR_KIND_FLAME, NODE_A_FLAME3_PORT, NODE_A_FLAME3_PIN },
  { "MQ2-02",   SENSOR_KIND_MQ2,   NODE_A_MQ2_2_PORT,  NODE_A_MQ2_2_PIN },
  { "MQ2-03",   SENSOR_KIND_MQ2,   NODE_A_MQ2_3_PORT,  NODE_A_MQ2_3_PIN },
  { "LEVEL-02", SENSOR_KIND_LEVEL, NODE_A_LEVEL2_PORT, NODE_A_LEVEL2_PIN },
  { "LEVEL-03", SENSOR_KIND_LEVEL, NODE_A_LEVEL3_PORT, NODE_A_LEVEL3_PIN }
};

static const NodeAnalogPin kNodeBAnalogPins[NODE_B_ANALOG_PIN_COUNT] = {
  { "MQ4-03", SENSOR_KIND_MQ4, GPIOA, GPIO_PIN_0, NODE_B_MQ4_3_ADC_CHANNEL },
  { "MQ4-04", SENSOR_KIND_MQ4, GPIOA, GPIO_PIN_1, NODE_B_MQ4_4_ADC_CHANNEL },
  { "MQ4-05", SENSOR_KIND_MQ4, GPIOA, GPIO_PIN_4, NODE_B_MQ4_5_ADC_CHANNEL },
  { "O2-03",  SENSOR_KIND_O2,  GPIOA, GPIO_PIN_6, NODE_B_O2_3_ADC_CHANNEL },
  { "CO-04",  SENSOR_KIND_CO,  GPIOB, GPIO_PIN_0, NODE_B_CO4_ADC_CHANNEL },
  { "CO-05",  SENSOR_KIND_CO,  GPIOB, GPIO_PIN_1, NODE_B_CO5_ADC_CHANNEL }
};

static const NodeDigitalPin kNodeBDigitalPins[NODE_B_DIGITAL_PIN_COUNT] = {
  { "FLAME-04", SENSOR_KIND_FLAME, NODE_B_FLAME4_PORT,  NODE_B_FLAME4_PIN },
  { "FLAME-05", SENSOR_KIND_FLAME, NODE_B_FLAME5_PORT,  NODE_B_FLAME5_PIN },
  { "MQ2-04",   SENSOR_KIND_MQ2,   NODE_B_MQ2_4_PORT,   NODE_B_MQ2_4_PIN },
  { "MQ2-05",   SENSOR_KIND_MQ2,   NODE_B_MQ2_5_PORT,   NODE_B_MQ2_5_PIN },
  { "LEVEL-04", SENSOR_KIND_LEVEL, NODE_B_LEVEL4_PORT,  NODE_B_LEVEL4_PIN },
  { "LEVEL-05", SENSOR_KIND_LEVEL, NODE_B_LEVEL5_PORT,  NODE_B_LEVEL5_PIN }
};

#ifdef __cplusplus
}
#endif

#endif /* NODE_SENSOR_PIN_MAP_H */
