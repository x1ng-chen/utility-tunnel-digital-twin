#ifndef BOARD_IO_H
#define BOARD_IO_H

#include <stdint.h>

#define SENSOR_STATUS_OK      0U
#define SENSOR_STATUS_MISSING 1U
#define SENSOR_STATUS_SUSPECT 2U
#define SENSOR_STATUS_LATCHED 3U

typedef struct
{
  uint16_t value;   /* 数字量 0/1；ADC 原始值；SHT 温度（0.01 °C） */
  uint16_t aux;     /* SHT 湿度（0.01 %RH）；氧气毫伏；其他 0 */
  uint8_t status;   /* SENSOR_STATUS_* */
  uint32_t sampled_at; /* Monotonic observation time, not UTC. */
} SensorSample;

void BoardIo_Init(void);
void BoardIo_SampleAll(void);
void BoardIo_Poll(uint32_t now);
void BoardIo_FastTick(uint32_t now);
uint16_t BoardIo_Sequence(void);
const SensorSample *BoardIo_Samples(void);
uint8_t BoardIo_SampleCount(void);
uint16_t BoardIo_SensorId(uint8_t index);
uint8_t BoardIo_AlarmActive(void);

/* Main-loop-only diagnostics; never called from an interrupt. Probe bits map
 * to 0x40 / 0x44 / 0x45. ACKs are not device identity or valid measurements. */
typedef struct {
  uint32_t good, failed, last_good_ms, raw_read_ms, clock_timeouts;
  uint8_t address, stage, idle_sda, idle_scl, ack_mask, probes_run;
  uint8_t raw[6];
} BoardIoI2cDiagnostics;
/* Returns 0 during an outstanding SHT conversion; performs no probes then. */
uint8_t BoardIo_GetI2cDiagnostics(BoardIoI2cDiagnostics *out);

/* 最近一次本地 I²C 扫描找到的地址；0 表示总线上没有任何应答。 */
extern volatile uint8_t BoardIo_I2cScanResult;

/* SHT: 0=成功, 1=写地址NACK, 2/3=命令NACK, 4=读地址NACK,
 * 5/6=CRC错, 7=SCL释放后未能在有界等待内变高。 */
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
