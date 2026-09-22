#include "kk_ui_motion.h"

/* Adapted from KK_UI 0.1.0, MIT licensed.
 * Copyright (c) 2026 Qingdao BaudDance Technology Co., Ltd.
 * cubic-bezier(0.25, 0, 0.20, 1), sampled uniformly in time. */
static const uint16_t ease_curve[65] = {
    0, 6, 23, 53, 98, 159, 236, 329,
    439, 565, 704, 853, 1010, 1170, 1331, 1490,
    1645, 1795, 1938, 2075, 2205, 2328, 2444, 2554,
    2658, 2756, 2848, 2936, 3018, 3095, 3168, 3237,
    3302, 3363, 3420, 3475, 3526, 3574, 3619, 3661,
    3701, 3738, 3773, 3806, 3836, 3864, 3891, 3915,
    3938, 3959, 3978, 3995, 4011, 4025, 4038, 4050,
    4060, 4069, 4076, 4082, 4087, 4091, 4094, 4095,
    4096
};

uint16_t KK_UI_MotionEaseQ12(uint32_t elapsed_ms, uint32_t duration_ms)
{
  uint32_t scaled;
  uint32_t index;
  uint32_t fraction;
  uint32_t value;

  if ((duration_ms == 0U) || (elapsed_ms >= duration_ms)) {
    return KK_UI_MOTION_Q12_ONE;
  }

  /* Compute the table position directly so long animation durations do not
   * lose precision through an intermediate 300 ms reference timeline. */
  scaled = (uint32_t)(((uint64_t)elapsed_ms * 64U * 300U) / duration_ms);
  index = scaled / 300U;
  fraction = scaled % 300U;
  value = ease_curve[index];
  value += ((uint32_t)(ease_curve[index + 1U] - value) * fraction) / 300U;
  return (uint16_t)value;
}

int32_t KK_UI_MotionLerpQ12(int32_t from, int32_t to, uint16_t progress_q12)
{
  return from + (int32_t)(((int64_t)to - from) * progress_q12 /
                          (int64_t)KK_UI_MOTION_Q12_ONE);
}
