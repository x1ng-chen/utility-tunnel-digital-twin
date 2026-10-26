#ifndef JOYSTICK_H
#define JOYSTICK_H

#include <stdint.h>

void Joystick_Init(void);
void Joystick_Read(uint16_t *x, uint16_t *y, uint8_t *pressed);

#endif
