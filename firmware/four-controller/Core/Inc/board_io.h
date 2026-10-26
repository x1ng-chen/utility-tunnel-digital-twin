#ifndef BOARD_IO_H
#define BOARD_IO_H

#include <stdint.h>

#define SENSOR_STATUS_OK      0U
#define SENSOR_STATUS_MISSING 1U
#define SENSOR_STATUS_SUSPECT 2U

typedef struct
{
  uint16_t value;   /* 数字量 0/1；ADC 原始值；SHT 温度（0.01 °C） */
  uint16_t aux;     /* SHT 湿度（0.01 %RH）；氧气毫伏；其他 0 */
  uint8_t status;   /* SENSOR_STATUS_* */
} SensorSample;

void BoardIo_Init(void);
void BoardIo_SampleAll(void);
const SensorSample *BoardIo_Samples(void);
uint8_t BoardIo_SampleCount(void);
uint16_t BoardIo_SensorId(uint8_t index);
uint8_t BoardIo_AlarmActive(void);

/* 最近一次本地 I²C 扫描找到的地址；0 表示总线上没有任何应答。 */
extern volatile uint8_t BoardIo_I2cScanResult;

/* SHT 读取失败点：0=成功，1=写地址 NACK，2/3=命令 NACK，4=读地址 NACK，5/6=CRC 错。 */
extern volatile uint8_t BoardIo_ShtDebug;
extern volatile uint8_t BoardIo_ShtRaw[6];
extern volatile uint8_t BoardIo_I2cIdleSda;
extern volatile uint8_t BoardIo_I2cIdleScl;
/* 探测到的候选温湿度地址：0x44/0x45/0x40，0 表示都没应答。 */
extern volatile uint8_t BoardIo_ShtFoundAddr;

/* 屏幕初始化会改动 GPIOB 配置，之后用它重新把 I²C 引脚设回开漏。 */
void BoardIo_ReinitI2c(void);

/* 供执行器/屏幕等模块共用的本地总线访问。 */
uint8_t BoardIo_I2cRead16(uint8_t address, uint8_t reg, uint16_t *value);
uint8_t BoardIo_I2cWrite16(uint8_t address, uint8_t reg, uint16_t value);
uint8_t BoardIo_AdcRead(uint32_t channel, uint16_t *raw);
uint16_t BoardIo_AdcToMillivolts(uint16_t raw);

#endif
