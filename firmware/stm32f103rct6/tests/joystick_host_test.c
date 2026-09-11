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
  Joystick_TestReset(2048U, 2048U);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 1U, 0U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(3600U, 2048U, 1U, 10U) == UI_EVT_RIGHT);
  CHECK(Joystick_TestProcessSample(3600U, 2048U, 1U, 360U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(400U, 2048U, 1U, 370U) == UI_EVT_LEFT);
  CHECK(Joystick_TestProcessSample(400U, 2048U, 1U, 720U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 3600U, 1U, 730U) == UI_EVT_DOWN);
  CHECK(Joystick_TestProcessSample(2048U, 3600U, 1U, 1080U) == UI_EVT_DOWN);
  CHECK(Joystick_TestProcessSample(2048U, 3600U, 1U, 1180U) == UI_EVT_DOWN);

  Joystick_TestReset(2048U, 2048U);
  CHECK(Joystick_TestProcessSample(3600U, 2048U, 1U, 0U) == UI_EVT_RIGHT);
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
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 35U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 1034U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 1035U) == UI_EVT_LONG_PRESS);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 2035U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 1U, 2040U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 1U, 2065U) == UI_EVT_NONE);

  Joystick_TestReset(2048U, 2048U);
  CHECK(Joystick_TestProcessSample(2048U, 3600U, 1U, 0U) == UI_EVT_DOWN);
  CHECK(Joystick_TestProcessSample(2048U, 3600U, 1U, 350U) == UI_EVT_DOWN);
  CHECK(Joystick_TestProcessSample(2048U, 3600U, 1U, 450U) == UI_EVT_DOWN);

  Joystick_TestReset(2048U, 2048U);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 0U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 0U, 25U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 1U, 30U) == UI_EVT_NONE);
  CHECK(Joystick_TestProcessSample(2048U, 2048U, 1U, 55U) == UI_EVT_PRESS);

  (void)puts("Joystick host test: PASS");
  return 0;
}
