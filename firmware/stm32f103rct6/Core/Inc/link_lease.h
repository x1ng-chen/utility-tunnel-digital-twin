#ifndef LINK_LEASE_H
#define LINK_LEASE_H

#include <stdint.h>

/* HAL_GetTick arithmetic is valid across rollover, but a producer sampled
 * later in the same loop can make last_online_ms one tick newer than now_ms.
 * Treat that small apparent backwards interval as fresh instead of allowing
 * unsigned subtraction to turn it into an immediate timeout. */
static inline uint8_t LinkLease_Expired(uint32_t now_ms,
                                        uint32_t last_online_ms,
                                        uint32_t timeout_ms)
{
  const uint32_t elapsed_ms = now_ms - last_online_ms;
  return (elapsed_ms < 0x80000000U && elapsed_ms >= timeout_ms) ? 1U : 0U;
}

#endif
