#ifndef SCREEN_H
#define SCREEN_H

#include <stdint.h>
#include "board_io.h"

void Screen_Init(void);
void Screen_Update(uint8_t board, uint16_t sequence, uint32_t uptime_s,
                   uint8_t alarm, const SensorSample *samples, uint8_t count);

#endif
