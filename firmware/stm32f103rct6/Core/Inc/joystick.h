#ifndef JOYSTICK_H
#define JOYSTICK_H

#include <stdint.h>

#include "ui_state.h"

/* Configure Node B's PC0/PC1 ADC inputs and PC4 active-low switch. */
void Joystick_Init(void);

/* Capture 16 released-stick samples as the ADC center. */
void Joystick_Calibrate(void);

/* Sample hardware at the five-millisecond acquisition cadence. */
UiInputEvent Joystick_Poll(uint32_t now_ms);

/* Route DMA1 Channel1 interrupts to ADC1's circular scan transfer. */
void Joystick_DmaIrqHandler(void);

/* Feed a raw sample to the production decoder. Kept separate from ADC/GPIO
 * acquisition so deterministic tests and diagnostic adapters use the same
 * filtering logic as the board. switch_released is non-zero when SW is high. */
UiInputEvent Joystick_ProcessSample(uint16_t x, uint16_t y, uint8_t switch_released,
                                    uint32_t now_ms);

/* Test-only decoder controls. They never acquire ADC/GPIO data and let host
 * tests cover timing behavior without a connected board. */
void Joystick_TestReset(uint16_t center_x, uint16_t center_y);
UiInputEvent Joystick_TestProcessSample(uint16_t x, uint16_t y, uint8_t switch_released,
                                        uint32_t now_ms);

#endif /* JOYSTICK_H */
