#include "board_config.h"

#if BOARD_ID == 1
/* 1 号 / 左下：P3 + 中央 P5，共 11 路。
 * 独立 5V 模块集中在 PA4-PA7、PC4、PC5、PB1；氧气在 PA0；
 * 屏幕占用 PB3/PB5/PB6/PB7/PB8/PB9。 */
static const SensorDef sensors[] =
{
  { 9U, SENSOR_MQ2,   3U, "MQ2-03",   GPIOC, GPIO_PIN_4,  0U,             0U },
  {10U, SENSOR_MQ4,   3U, "MQ4-03",   GPIOA, GPIO_PIN_4,  ADC_CHANNEL_4,  0U },
  {11U, SENSOR_CO,    3U, "CO-03",    GPIOA, GPIO_PIN_5,  ADC_CHANNEL_5,  0U },
  {12U, SENSOR_FLAME, 3U, "FLAME-03", GPIOB, GPIO_PIN_14, 0U,             0U },
  {17U, SENSOR_MQ2,   5U, "MQ2-05",   GPIOC, GPIO_PIN_5,  0U,             0U },
  {18U, SENSOR_MQ4,   5U, "MQ4-05",   GPIOA, GPIO_PIN_6,  ADC_CHANNEL_6,  0U },
  {19U, SENSOR_CO,    5U, "CO-05",    GPIOA, GPIO_PIN_7,  ADC_CHANNEL_7,  0U },
  {20U, SENSOR_FLAME, 5U, "FLAME-05", GPIOC, GPIO_PIN_7,  0U,             0U },
  {23U, SENSOR_SHT,   0U, "SHT-03",   NULL,  0U,          0U,             0x44U },
  {27U, SENSOR_LEVEL, 0U, "LEVEL-03", GPIOB, GPIO_PIN_1,  0U,             0U },
  {30U, SENSOR_O2,    0U, "O2-02",    GPIOA, GPIO_PIN_0,  ADC_CHANNEL_0,  0U }
};
#elif BOARD_ID == 2
/* 2 号 / 右下：P4 共 7 路。屏幕 SPI3、摇杆、风机 2、继电器 2、INA-FAN2。 */
static const SensorDef sensors[] =
{
  {13U, SENSOR_MQ2,   4U, "MQ2-04",   GPIOB, GPIO_PIN_12, 0U,             0U },
  {14U, SENSOR_MQ4,   4U, "MQ4-04",   GPIOA, GPIO_PIN_4,  ADC_CHANNEL_4,  0U },
  {15U, SENSOR_CO,    4U, "CO-04",    GPIOB, GPIO_PIN_0,  ADC_CHANNEL_8,  0U },
  {16U, SENSOR_FLAME, 4U, "FLAME-04", GPIOC, GPIO_PIN_6,  0U,             0U },
  {24U, SENSOR_SHT,   0U, "SHT-04",   NULL,  0U,          0U,             0x45U },
  {28U, SENSOR_LEVEL, 0U, "LEVEL-04", GPIOC, GPIO_PIN_10, 0U,             0U },
  {31U, SENSOR_O2,    0U, "O2-03",    GPIOA, GPIO_PIN_6,  ADC_CHANNEL_6,  0U }
};
#elif BOARD_ID == 3
/* 3 号 / 右上：P2 共 6 路。蜂鸣器 PB0、灯带 PB15。 */
static const SensorDef sensors[] =
{
  { 5U, SENSOR_MQ2,   2U, "MQ2-02",   GPIOB, GPIO_PIN_12, 0U,             0U },
  { 6U, SENSOR_MQ4,   2U, "MQ4-02",   GPIOA, GPIO_PIN_4,  ADC_CHANNEL_4,  0U },
  { 7U, SENSOR_CO,    2U, "CO-02",    GPIOC, GPIO_PIN_3,  ADC_CHANNEL_13, 0U },
  { 8U, SENSOR_FLAME, 2U, "FLAME-02", GPIOC, GPIO_PIN_6,  0U,             0U },
  {22U, SENSOR_SHT,   0U, "SHT-02",   NULL,  0U,          0U,             0x45U },
  {26U, SENSOR_LEVEL, 0U, "LEVEL-02", GPIOC, GPIO_PIN_12, 0U,             0U }
};
#elif BOARD_ID == 4
/* 4 号 / 左上：P1 共 7 路。风机 1、继电器 1、INA-FAN1。 */
static const SensorDef sensors[] =
{
  { 1U, SENSOR_MQ2,   1U, "MQ2-01",   GPIOB, GPIO_PIN_12, 0U,             0U },
  { 2U, SENSOR_MQ4,   1U, "MQ4-01",   GPIOC, GPIO_PIN_2,  ADC_CHANNEL_12, 0U },
  { 3U, SENSOR_CO,    1U, "CO-01",    GPIOC, GPIO_PIN_1,  ADC_CHANNEL_11, 0U },
  { 4U, SENSOR_FLAME, 1U, "FLAME-01", GPIOB, GPIO_PIN_14, 0U,             0U },
  {21U, SENSOR_SHT,   0U, "SHT-01",   NULL,  0U,          0U,             0x44U },
  {25U, SENSOR_LEVEL, 0U, "LEVEL-01", GPIOC, GPIO_PIN_0,  0U,             0U },
  {29U, SENSOR_O2,    0U, "O2-01",    GPIOC, GPIO_PIN_3,  ADC_CHANNEL_13, 0U }
};
#endif

const BoardConfig board_config =
{
  .id = BOARD_ID,
  .sensors = sensors,
  .sensor_count = (uint8_t)(sizeof sensors / sizeof sensors[0]),
#if BOARD_ID == 4
  .i2c_port = GPIOB,
  .i2c_scl = GPIO_PIN_6,
  .i2c_sda = GPIO_PIN_7,
#else
  .i2c_port = GPIOB,
  .i2c_scl = GPIO_PIN_10,
  .i2c_sda = GPIO_PIN_11,
#endif
  .has_fan = (BOARD_ID == 2 || BOARD_ID == 4) ? 1U : 0U,
  .has_buzzer = (BOARD_ID == 3) ? 1U : 0U,
  .has_led = (BOARD_ID == 3) ? 1U : 0U,
  .has_screen = (BOARD_ID == 1 || BOARD_ID == 2) ? 1U : 0U,
  .has_joystick = (BOARD_ID == 2) ? 1U : 0U
};
