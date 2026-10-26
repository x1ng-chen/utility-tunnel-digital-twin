#ifndef MODBUS_SLAVE_H
#define MODBUS_SLAVE_H

#include <stdint.h>
#include "board_io.h"

/* 输入寄存器布局（功能码 03/04，起始 0，固定 52 个）：
 *   0       签名 0x5554
 *   1       板号 1..4
 *   2       协议版本 0x0100
 *   3       有效传感器数量
 *   4..5    uptime 秒（高/低 16 位）
 *   6       采样序列
 *   7       保留
 *   8+4*i   传感器 ID（空槽 0xFFFF）
 *   9+4*i   主值（raw / 温度 0.01°C）
 *   10+4*i  辅助值（湿度 0.01%RH / 氧气 mV）
 *   11+4*i  状态 0=ok 1=missing 2=suspect
 */
#define MODBUS_REGISTER_COUNT 52U
#define MODBUS_SLOT_COUNT     11U

/* 保持寄存器（功能码 03 读、06 写）：
 *   0 命令码：1=风机PWM 2=继电器 3=蜂鸣器 4=灯带颜色
 *   1 参数
 *   2 触发：写 1 执行当前命令，完成后清零
 *   3 结果：0=空闲 1=成功 2=不支持
 */
#define MODBUS_HOLDING_COUNT 4U

void Modbus_Init(uint8_t address);
void Modbus_Poll(void);
void Modbus_SetSamples(const SensorSample *samples, uint8_t count,
                       uint32_t uptime_s, uint16_t sequence);

/* 仅用于台架排查：在 485 上主动发一帧非 Modbus 数据。 */
void Modbus_DebugPing(void);

#endif
