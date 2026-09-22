#include <stdint.h>
#include <stdio.h>

#include "link_lease.h"

#define CHECK(condition) do { \
  if (!(condition)) { \
    (void)fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    return 1; \
  } \
} while (0)

int main(void)
{
  /* A heartbeat sampled one millisecond after the loop timestamp is fresh,
   * not 2^32-1 milliseconds old. */
  CHECK(LinkLease_Expired(1000U, 1001U, 15000U) == 0U);

  CHECK(LinkLease_Expired(15999U, 1000U, 15000U) == 0U);
  CHECK(LinkLease_Expired(16000U, 1000U, 15000U) == 1U);

  /* HAL_GetTick rollover still produces a small forward elapsed interval. */
  CHECK(LinkLease_Expired(5U, 0xFFFFFFF0U, 15000U) == 0U);
  CHECK(LinkLease_Expired(14984U, 0xFFFFFFF0U, 15000U) == 1U);

  (void)puts("LinkLease host test: PASS");
  return 0;
}
