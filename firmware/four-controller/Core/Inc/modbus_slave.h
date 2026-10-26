#ifndef MODBUS_SLAVE_H
#define MODBUS_SLAVE_H
#include <stdint.h>
#include "board_io.h"
#include "../../common/protocol.h"
#define MODBUS_REGISTER_COUNT UT_INPUT_COUNT
#define MODBUS_SLOT_COUNT 11U
#define MODBUS_HOLDING_COUNT UT_COMMAND_REGS
void Modbus_Init(uint8_t address);
void Modbus_Poll(void);
void Modbus_SetSamples(const SensorSample *samples,uint8_t count,uint32_t uptime_s,uint16_t sequence);
void Modbus_DebugPing(void);
#endif
