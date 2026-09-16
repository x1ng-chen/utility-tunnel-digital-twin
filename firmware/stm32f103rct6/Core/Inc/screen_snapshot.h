#ifndef SCREEN_SNAPSHOT_H
#define SCREEN_SNAPSHOT_H

#include <stddef.h>
#include <stdint.h>

#include "ui_model.h"

#define SCREEN_SNAPSHOT_LINE_SIZE 768U
#define SCREEN_SNAPSHOT_STALE_MS 5000U

typedef struct {
  uint8_t initialized;
  uint32_t sequence;
  uint32_t received_ms;
} ScreenSnapshotContext;

void ScreenSnapshot_Init(ScreenSnapshotContext *context);
uint8_t ScreenSnapshot_Apply(ScreenSnapshotContext *context, const char *line,
                             size_t length, uint32_t now_ms, UiSnapshot *snapshot);
void ScreenSnapshot_SetMqttAvailability(UiSnapshot *snapshot, uint8_t online,
                                        uint64_t updated_ms);
uint8_t ScreenSnapshot_IsStale(const ScreenSnapshotContext *context, uint32_t now_ms);
void ScreenSnapshot_Tick(const ScreenSnapshotContext *context, uint32_t now_ms,
                         UiSnapshot *snapshot);

/* Alias kept small and HAL-free for host probes and board adapters. */
uint8_t ScreenSnapshot_Parse(const char *line, size_t length, UiSnapshot *snapshot);

uint8_t ScreenSnapshot_AlarmCount(const UiSnapshot *snapshot);
UiDataQuality ScreenSnapshot_WorstQuality(const UiSnapshot *snapshot);
const char *ScreenSnapshot_AlarmLabel(const UiSnapshot *snapshot);

#endif /* SCREEN_SNAPSHOT_H */
