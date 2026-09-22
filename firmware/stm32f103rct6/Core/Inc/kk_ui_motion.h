#ifndef KK_UI_MOTION_H
#define KK_UI_MOTION_H

#include <stdint.h>

/* RGB565/ST7735 adaptation of KK_UI's fixed-point, non-overshooting motion
 * primitives.  Keeping this independent of the display driver lets host tests
 * exercise the exact timing used on both controller variants. */
#define KK_UI_MOTION_Q12_ONE 4096U

uint16_t KK_UI_MotionEaseQ12(uint32_t elapsed_ms, uint32_t duration_ms);
int32_t KK_UI_MotionLerpQ12(int32_t from, int32_t to, uint16_t progress_q12);

#endif /* KK_UI_MOTION_H */
