#include "node_sensor_pin_map.h"
#include <assert.h>
#include <string.h>

_Static_assert(NODE_A_ANALOG_PIN_COUNT == 7U, "Node A analog count");
_Static_assert(NODE_A_DIGITAL_PIN_COUNT == 9U, "Node A digital count");
_Static_assert(NODE_B_ANALOG_PIN_COUNT == 6U, "Node B analog count");
_Static_assert(NODE_B_DIGITAL_PIN_COUNT == 6U, "Node B digital count");
_Static_assert(NODE_A_CO1_ADC_CHANNEL == ADC_CHANNEL_11, "CO-01 PC1");
_Static_assert(NODE_A_MQ4_1_ADC_CHANNEL == ADC_CHANNEL_12, "MQ4-01 PC2");
_Static_assert(NODE_A_O2_1_ADC_CHANNEL == ADC_CHANNEL_13, "O2-01 PC3");
_Static_assert(NODE_B_O2_3_ADC_CHANNEL == ADC_CHANNEL_6, "O2-03 PA6");
_Static_assert(NODE_A_LEVEL3_PIN == GPIO_PIN_13, "LEVEL-03 PC13 input only");

typedef struct {
  void *port;
  uint16_t pin;
} PortPin;

static void assert_no_duplicates(const PortPin *pins, size_t count) {
  for (size_t i = 0; i < count; ++i) {
    for (size_t j = i + 1; j < count; ++j) {
      assert(!(pins[i].port == pins[j].port && pins[i].pin == pins[j].pin));
    }
  }
}

static void assert_no_overlap(const PortPin *a, size_t a_count,
                              const PortPin *b, size_t b_count) {
  for (size_t i = 0; i < a_count; ++i) {
    for (size_t j = 0; j < b_count; ++j) {
      assert(!(a[i].port == b[j].port && a[i].pin == b[j].pin));
    }
  }
}

int main(void) {
  /* Check Node A sensor pins against duplicates and reserved pins */
  PortPin node_a_sensor_pins[] = {
    /* 4 I2C lines across 2 buses (PB6, PB7, PB10, PB11) */
    { (void*)GPIOB, GPIO_PIN_6 },
    { (void*)GPIOB, GPIO_PIN_7 },
    { (void*)GPIOB, GPIO_PIN_10 },
    { (void*)GPIOB, GPIO_PIN_11 },
    /* 7 Analog */
    { (void*)GPIOC, GPIO_PIN_1 }, /* CO-01 */
    { (void*)GPIOC, GPIO_PIN_2 }, /* MQ4-01 */
    { (void*)GPIOC, GPIO_PIN_3 }, /* O2-01 */
    { (void*)GPIOA, GPIO_PIN_0 }, /* CO-02 */
    { (void*)GPIOA, GPIO_PIN_4 }, /* MQ4-02 */
    { (void*)GPIOA, GPIO_PIN_5 }, /* O2-02 */
    { (void*)GPIOB, GPIO_PIN_1 }, /* CO-03 */
    /* 9 Digital */
    { (void*)GPIOB, GPIO_PIN_12 }, /* MQ2-01 */
    { (void*)GPIOB, GPIO_PIN_14 }, /* FLAME-01 */
    { (void*)GPIOC, GPIO_PIN_0 },  /* LEVEL-01 */
    { (void*)GPIOC, GPIO_PIN_8 },  /* FLAME-02 */
    { (void*)GPIOC, GPIO_PIN_9 },  /* FLAME-03 */
    { (void*)GPIOC, GPIO_PIN_10 }, /* MQ2-02 */
    { (void*)GPIOC, GPIO_PIN_11 }, /* MQ2-03 */
    { (void*)GPIOC, GPIO_PIN_12 }, /* LEVEL-02 */
    { (void*)GPIOC, GPIO_PIN_13 }  /* LEVEL-03 */
  };
  assert_no_duplicates(node_a_sensor_pins, sizeof(node_a_sensor_pins)/sizeof(node_a_sensor_pins[0]));

  PortPin node_a_reserved_pins[] = {
    { (void*)GPIOA, GPIO_PIN_2 },  /* USART2 TX */
    { (void*)GPIOA, GPIO_PIN_3 },  /* USART2 RX */
    { (void*)GPIOA, GPIO_PIN_9 },  /* USART1 TX */
    { (void*)GPIOA, GPIO_PIN_10 }, /* USART1 RX */
    { (void*)GPIOA, GPIO_PIN_13 }, /* SWD SWDIO */
    { (void*)GPIOA, GPIO_PIN_14 }, /* SWD SWCLK */
    { (void*)GPIOA, GPIO_PIN_8 },  /* Status LED */
    { (void*)GPIOA, GPIO_PIN_1 },  /* Fan Relay */
    { (void*)GPIOA, GPIO_PIN_6 },  /* Fan Tach 1 */
    { (void*)GPIOA, GPIO_PIN_7 },  /* Fan Tach 2 */
    { (void*)GPIOB, GPIO_PIN_8 },  /* Fan PWM 1 */
    { (void*)GPIOB, GPIO_PIN_9 },  /* Fan PWM 2 */
    { (void*)GPIOB, GPIO_PIN_0 },  /* Buzzer */
    { (void*)GPIOB, GPIO_PIN_3 },  /* Screen 1 SPI3 SCK */
    { (void*)GPIOB, GPIO_PIN_5 },  /* Screen 1 SPI3 MOSI */
    { (void*)GPIOC, GPIO_PIN_4 },  /* Screen 1 CS */
    { (void*)GPIOC, GPIO_PIN_5 },  /* Screen 1 DC */
    { (void*)GPIOC, GPIO_PIN_6 },  /* Screen 1 RES */
    { (void*)GPIOC, GPIO_PIN_7 },  /* Screen 1 BLK */
    { (void*)GPIOB, GPIO_PIN_15 }  /* WS2812 */
  };
  assert_no_overlap(node_a_sensor_pins, sizeof(node_a_sensor_pins)/sizeof(node_a_sensor_pins[0]),
                    node_a_reserved_pins, sizeof(node_a_reserved_pins)/sizeof(node_a_reserved_pins[0]));

  /* Check Node B sensor pins against duplicates and reserved pins */
  PortPin node_b_sensor_pins[] = {
    /* 6 Analog */
    { (void*)GPIOA, GPIO_PIN_0 }, /* MQ4-03 */
    { (void*)GPIOA, GPIO_PIN_1 }, /* MQ4-04 */
    { (void*)GPIOA, GPIO_PIN_4 }, /* MQ4-05 */
    { (void*)GPIOA, GPIO_PIN_6 }, /* O2-03 */
    { (void*)GPIOB, GPIO_PIN_0 }, /* CO-04 */
    { (void*)GPIOB, GPIO_PIN_1 }, /* CO-05 */
    /* 6 Digital */
    { (void*)GPIOC, GPIO_PIN_6 },  /* FLAME-04 */
    { (void*)GPIOC, GPIO_PIN_7 },  /* FLAME-05 */
    { (void*)GPIOC, GPIO_PIN_8 },  /* MQ2-04 */
    { (void*)GPIOC, GPIO_PIN_9 },  /* MQ2-05 */
    { (void*)GPIOC, GPIO_PIN_10 }, /* LEVEL-04 */
    { (void*)GPIOC, GPIO_PIN_11 }  /* LEVEL-05 */
  };
  assert_no_duplicates(node_b_sensor_pins, sizeof(node_b_sensor_pins)/sizeof(node_b_sensor_pins[0]));

  PortPin node_b_reserved_pins[] = {
    { (void*)GPIOA, GPIO_PIN_2 },  /* USART2 TX */
    { (void*)GPIOA, GPIO_PIN_3 },  /* USART2 RX */
    { (void*)GPIOA, GPIO_PIN_9 },  /* USART1 TX */
    { (void*)GPIOA, GPIO_PIN_10 }, /* USART1 RX */
    { (void*)GPIOA, GPIO_PIN_13 }, /* SWD SWDIO */
    { (void*)GPIOA, GPIO_PIN_14 }, /* SWD SWCLK */
    { (void*)GPIOA, GPIO_PIN_8 },  /* Status LED */
    { (void*)GPIOA, GPIO_PIN_5 },  /* Screen 2 SPI1 SCK */
    { (void*)GPIOA, GPIO_PIN_7 },  /* Screen 2 SPI1 MOSI */
    { (void*)GPIOB, GPIO_PIN_6 },  /* Screen 2 CS */
    { (void*)GPIOB, GPIO_PIN_7 },  /* Screen 2 DC */
    { (void*)GPIOB, GPIO_PIN_8 },  /* Screen 2 RES */
    { (void*)GPIOB, GPIO_PIN_9 },  /* Screen 2 BLK */
    { (void*)GPIOC, GPIO_PIN_0 },  /* Joystick ADC X */
    { (void*)GPIOC, GPIO_PIN_1 },  /* Joystick ADC Y */
    { (void*)GPIOC, GPIO_PIN_4 }   /* Joystick Key */
  };
  assert_no_overlap(node_b_sensor_pins, sizeof(node_b_sensor_pins)/sizeof(node_b_sensor_pins[0]),
                    node_b_reserved_pins, sizeof(node_b_reserved_pins)/sizeof(node_b_reserved_pins[0]));

  return 0;
}
