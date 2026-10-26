#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

#include "stm32f1xx_hal.h"

/* 四主控固件通过 BOARD_ID 选择板型：1 左下、2 右下、3 右上、4 左上。
 * 引脚依据 docs/hardware/four-controller-wiring-20261026/README.md（V0.3）。 */
#ifndef BOARD_ID
#error "BOARD_ID must be defined as 1, 2, 3 or 4"
#endif
#if (BOARD_ID < 1) || (BOARD_ID > 4)
#error "BOARD_ID must be 1, 2, 3 or 4"
#endif

/* 传感器物理编号 1..31 的分配：
 *   P1 01-04、P2 05-08、P3 09-12、P4 13-16、P5 17-20、
 *   SHT-01..04 = 21..24、LEVEL-01..04 = 25..28、O2-01..03 = 29..31。 */
typedef enum
{
  SENSOR_MQ2 = 0,   /* 数字 DO，低有效 */
  SENSOR_MQ4,       /* 模拟 AO */
  SENSOR_CO,        /* 模拟 AO，MQ-7 */
  SENSOR_FLAME,     /* 数字 DO，低有效 */
  SENSOR_SHT,       /* 软件 I2C，温湿度 */
  SENSOR_LEVEL,     /* 数字 DO，低有效 */
  SENSOR_O2         /* 模拟 AO，裸探头毫伏 */
} SensorType;

typedef struct
{
  uint8_t id;                    /* 物理编号 1..31 */
  SensorType type;
  uint8_t station;               /* P1..P5 = 1..5，附加传感器为 0 */
  const char *tag;               /* 实物标签 */
  GPIO_TypeDef *port;            /* 数字量输入口，模拟量填 ADC 所在口 */
  uint16_t pin;                  /* 数字量引脚，模拟量填对应引脚 */
  uint32_t adc_channel;          /* 模拟量通道，其他填 0 */
  uint8_t i2c_address;           /* SHT 地址，其他填 0 */
} SensorDef;

typedef struct
{
  uint8_t id;
  const SensorDef *sensors;
  uint8_t sensor_count;
  GPIO_TypeDef *i2c_port;        /* 本板唯一软件 I2C 总线 */
  uint16_t i2c_scl;
  uint16_t i2c_sda;
  uint8_t has_fan;               /* 2/4 号带风机和继电器 */
  uint8_t has_buzzer;            /* 3 号带蜂鸣器 */
  uint8_t has_led;               /* 3 号带 WS2812 */
  uint8_t has_screen;            /* 1/2 号带屏幕 */
  uint8_t has_joystick;          /* 2 号带摇杆 */
} BoardConfig;

extern const BoardConfig board_config;

#endif
