#ifndef NETWORK_TIME_H
#define NETWORK_TIME_H

#include <stddef.h>
#include <stdint.h>

#include "ui_model.h"

#define NETWORK_TIME_MIN_EPOCH_SECONDS 1704067200ULL
#define NETWORK_TIME_MAX_EPOCH_SECONDS 4102444799ULL

typedef struct {
  uint8_t synchronized;
  uint64_t epoch_seconds;
  uint32_t synchronized_ms;
  uint32_t sequence;
} UiClock;

void NetworkTime_Init(UiClock *clock);
uint8_t NetworkTime_Update(UiClock *clock, const char *line, size_t length,
                           uint32_t now_ms);
void NetworkTime_ToSnapshot(const UiClock *clock, uint32_t now_ms,
                            UiClockSnapshot *snapshot);
uint64_t NetworkTime_EpochMilliseconds(const UiClock *clock, uint32_t now_ms);

#endif /* NETWORK_TIME_H */
