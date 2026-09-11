#include <stdio.h>

#include "joystick.h"

#define CHECK(condition) do { \
  if (!(condition)) { \
    (void)fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    return 1; \
  } \
} while (0)

int main(void)
{
  CHECK(Joystick_TestSample(2048U, 2048U, 1U, 0U) == UI_EVT_NONE);
  CHECK(Joystick_TestSample(3600U, 2048U, 1U, 10U) == UI_EVT_RIGHT);
  CHECK(Joystick_TestSample(2048U, 400U, 1U, 20U) == UI_EVT_UP);
  CHECK(Joystick_TestSample(2048U, 2048U, 0U, 30U) == UI_EVT_PRESS);

  Joystick_TestReset(2048U, 2048U);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 1U, 0U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(3600U, 2048U, 1U, 10U) == UI_EVT_RIGHT);
  CHECK(Joystick_TestProcessSample(2450U, 2048U, 1U, 100U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2400U, 2048U, 1U, 110U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 400U, 1U, 120U) == UI_EVT_UP);
  CHECK(Joystick_TestProcessSample(2048U, 400U, 1U, 469U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 400U, 1U, 470U) == UI_EVT_UP);
  CHECK(Joystick_TestProcessSample(2048U, 400U, 1U, 569U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 400U, 1U, 570U) == UI_EVT_UP);

  Joystick_TestReset(2048U, 2048U);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 1U, 0U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 10U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 34U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 35U) == UI_EVT_PRESS);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 1034U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 1035U) == UI_EVT_LONG_PRESS);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 2035U) == UI_EVT_NONE);

  (void)puts("Joystick host test: PASS");
  return 0;
}
