#include "network_time.h"

#include <string.h>

#define NETWORK_TIME_BEIJING_OFFSET_SECONDS (8ULL * 3600ULL)

typedef struct {
  const char *at;
  const char *end;
} TimeCursor;

static void skip(TimeCursor *cursor)
{
  while ((cursor->at < cursor->end) && ((*cursor->at == ' ') || (*cursor->at == '\t') ||
         (*cursor->at == '\r') || (*cursor->at == '\n'))) ++cursor->at;
}

static uint8_t ch(TimeCursor *cursor, char expected)
{
  skip(cursor);
  if ((cursor->at >= cursor->end) || *cursor->at != expected) return 0U;
  ++cursor->at;
  return 1U;
}

static uint8_t string_value(TimeCursor *cursor, char *output, size_t capacity)
{
  size_t length = 0U;
  skip(cursor);
  if ((cursor->at >= cursor->end) || *cursor->at != '"') return 0U;
  ++cursor->at;
  while (cursor->at < cursor->end) {
    char value = *cursor->at++;
    if (value == '"') {
      if (output != 0) output[length] = '\0';
      return 1U;
    }
    if ((value == '\\') || ((unsigned char)value < 0x20U) || length + 1U >= capacity) return 0U;
    if (output != 0) output[length] = value;
    ++length;
  }
  return 0U;
}

static uint8_t named(TimeCursor *cursor, const char *name)
{
  char actual[24];
  if (!string_value(cursor, actual, sizeof(actual)) || strcmp(actual, name) != 0) return 0U;
  return ch(cursor, ':');
}

static uint8_t number(TimeCursor *cursor, uint64_t *value)
{
  uint64_t result = 0U;
  uint8_t digits = 0U;
  skip(cursor);
  while (cursor->at < cursor->end && *cursor->at >= '0' && *cursor->at <= '9') {
    const uint8_t digit = (uint8_t)(*cursor->at - '0');
    if (result > (UINT64_MAX - digit) / 10U) return 0U;
    result = result * 10U + digit;
    ++cursor->at;
    digits = 1U;
  }
  if (!digits) return 0U;
  *value = result;
  return 1U;
}

static uint8_t parse(const char *line, size_t length, uint64_t *epoch,
                     uint32_t *sequence)
{
  TimeCursor cursor;
  char schema[24], source[16], state[16];
  uint64_t epoch_value, sequence_value;
  if ((line == 0) || (epoch == 0) || (sequence == 0) ||
      (length == 0U) || (length > NETWORK_TIME_LINE_SIZE)) return 0U;
  cursor.at = line;
  cursor.end = line + length;
  if (
      !ch(&cursor, '{') || !named(&cursor, "schema") ||
      !string_value(&cursor, schema, sizeof(schema)) || strcmp(schema, "ut.time.sync.v1") != 0 ||
      !ch(&cursor, ',') || !named(&cursor, "source") || !string_value(&cursor, source, sizeof(source)) ||
      (strcmp(source, "ntp") != 0 && strcmp(source, "snapshot") != 0) ||
      !ch(&cursor, ',') || !named(&cursor, "state") || !string_value(&cursor, state, sizeof(state)) ||
      (strcmp(state, "synchronized") != 0 && strcmp(state, "holdover") != 0) ||
      !ch(&cursor, ',') || !named(&cursor, "epochSeconds") || !number(&cursor, &epoch_value) ||
      !ch(&cursor, ',') || !named(&cursor, "seq") || !number(&cursor, &sequence_value) ||
      sequence_value > UINT32_MAX || !ch(&cursor, '}')) return 0U;
  skip(&cursor);
  if (cursor.at != cursor.end || epoch_value < NETWORK_TIME_MIN_EPOCH_SECONDS ||
      epoch_value > NETWORK_TIME_MAX_EPOCH_SECONDS) return 0U;
  *epoch = epoch_value;
  *sequence = (uint32_t)sequence_value;
  return 1U;
}

void NetworkTime_Init(UiClock *clock)
{
  if (clock != 0) (void)memset(clock, 0, sizeof(*clock));
}

uint8_t NetworkTime_Update(UiClock *clock, const char *line, size_t length,
                           uint32_t now_ms)
{
  uint64_t epoch;
  uint32_t sequence;
  if ((clock == 0) || (line == 0) || (length == 0U) ||
      (length > NETWORK_TIME_LINE_SIZE) || !parse(line, length, &epoch, &sequence) ||
      (clock->synchronized && ((int32_t)(sequence - clock->sequence) <= 0))) return 0U;
  clock->synchronized = 1U;
  clock->epoch_seconds = epoch;
  clock->synchronized_ms = now_ms;
  clock->sequence = sequence;
  return 1U;
}

uint64_t NetworkTime_EpochMilliseconds(const UiClock *clock, uint32_t now_ms)
{
  uint64_t elapsed;
  if ((clock == 0) || !clock->synchronized) return 0ULL;
  elapsed = (uint64_t)((uint32_t)(now_ms - clock->synchronized_ms));
  return clock->epoch_seconds * 1000ULL + elapsed;
}

void NetworkTime_ToSnapshot(const UiClock *clock, uint32_t now_ms,
                            UiClockSnapshot *snapshot)
{
  uint64_t seconds;
  uint32_t day_seconds;
  if (snapshot == 0) return;
  (void)memset(snapshot, 0, sizeof(*snapshot));
  if ((clock == 0) || !clock->synchronized) return;
  seconds = clock->epoch_seconds + NETWORK_TIME_BEIJING_OFFSET_SECONDS +
            ((uint64_t)((uint32_t)(now_ms - clock->synchronized_ms)) / 1000ULL);
  day_seconds = (uint32_t)(seconds % 86400ULL);
  snapshot->synchronized = 1U;
  snapshot->hour = (uint8_t)(day_seconds / 3600U);
  snapshot->minute = (uint8_t)((day_seconds % 3600U) / 60U);
}
