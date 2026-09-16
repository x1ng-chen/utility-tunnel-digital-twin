#include "screen_snapshot.h"

#include <string.h>

typedef struct {
  const char *at;
  const char *end;
} Cursor;

static void skip_space(Cursor *cursor)
{
  while ((cursor->at < cursor->end) && ((*cursor->at == ' ') ||
         (*cursor->at == '\t') || (*cursor->at == '\r') || (*cursor->at == '\n'))) {
    ++cursor->at;
  }
}

static uint8_t character(Cursor *cursor, char expected)
{
  skip_space(cursor);
  if ((cursor->at >= cursor->end) || (*cursor->at != expected)) return 0U;
  ++cursor->at;
  return 1U;
}

static uint8_t literal(Cursor *cursor, const char *expected)
{
  size_t length = strlen(expected);
  skip_space(cursor);
  if ((size_t)(cursor->end - cursor->at) < length) return 0U;
  if (memcmp(cursor->at, expected, length) != 0) return 0U;
  cursor->at += length;
  return 1U;
}

static uint8_t string_value(Cursor *cursor, char *output, size_t capacity)
{
  size_t length = 0U;
  skip_space(cursor);
  if ((cursor->at >= cursor->end) || (*cursor->at != '"')) return 0U;
  ++cursor->at;
  while (cursor->at < cursor->end) {
    const char value = *cursor->at++;
    if (value == '"') {
      if (output != 0) output[length] = '\0';
      return 1U;
    }
    if ((value == '\\') || ((unsigned char)value < 0x20U) ||
        (length + 1U >= capacity)) return 0U;
    if (output != 0) output[length] = value;
    ++length;
  }
  return 0U;
}

/* Key parsing is intentionally separate so a missing, reordered, or unknown
 * key cannot partially update the displayed model. */
static uint8_t named_key(Cursor *cursor, const char *name)
{
  char actual[32];
  if (!string_value(cursor, actual, sizeof(actual)) || strcmp(actual, name) != 0) return 0U;
  return character(cursor, ':');
}

static uint8_t unsigned_value(Cursor *cursor, uint64_t *value)
{
  uint64_t result = 0U;
  uint8_t digits = 0U;
  skip_space(cursor);
  while (cursor->at < cursor->end) {
    const unsigned char digit = (unsigned char)*cursor->at;
    if ((digit < (unsigned char)'0') || (digit > (unsigned char)'9')) break;
    if (result > (UINT64_MAX - (uint64_t)(digit - (unsigned char)'0')) / 10U) return 0U;
    result = result * 10U + (uint64_t)(digit - (unsigned char)'0');
    ++cursor->at;
    digits = 1U;
  }
  if (digits == 0U) return 0U;
  *value = result;
  return 1U;
}

static uint8_t signed_value(Cursor *cursor, int32_t *value)
{
  uint8_t negative = 0U;
  uint64_t magnitude;
  skip_space(cursor);
  if ((cursor->at < cursor->end) && (*cursor->at == '-')) {
    negative = 1U;
    ++cursor->at;
  }
  if (!unsigned_value(cursor, &magnitude) || magnitude > 2147483648ULL) return 0U;
  if (negative) {
    if (magnitude == 2147483648ULL) *value = INT32_MIN;
    else *value = -(int32_t)magnitude;
  } else {
    if (magnitude > 2147483647ULL) return 0U;
    *value = (int32_t)magnitude;
  }
  return 1U;
}

static uint8_t boolean_value(Cursor *cursor, uint8_t *value)
{
  if (literal(cursor, "true")) { *value = 1U; return 1U; }
  if (literal(cursor, "false")) { *value = 0U; return 1U; }
  return 0U;
}

/* Link status travels as the UiLinkStatus ordinal, not as a boolean: an
 * unobserved gateway or cloud session has to stay distinguishable from one
 * that was observed to be down. */
static uint8_t link_status_value(Cursor *cursor, uint8_t *value)
{
  uint64_t status;
  if (!unsigned_value(cursor, &status) || status > (uint64_t)UI_LINK_OFFLINE) return 0U;
  *value = (uint8_t)status;
  return 1U;
}

static uint8_t valid_timestamp(uint64_t sampled, uint64_t generated, UiDataQuality quality)
{
  if ((quality == UI_QUALITY_UNKNOWN) && (sampled == 0ULL)) return 1U;
  return sampled >= 1704067200000ULL && sampled <= 4102444799999ULL && sampled <= generated;
}

static uint8_t safe_token(const char *value, size_t capacity, uint8_t allow_empty)
{
  size_t index;
  if ((value == 0) || (capacity == 0U)) return 0U;
  for (index = 0U; index < capacity; ++index) {
    if (value[index] == '\0') return allow_empty || (index != 0U);
    if (index + 1U >= capacity) return 0U;
    const unsigned char ch = (unsigned char)value[index];
    if (!((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
                           (ch >= '0' && ch <= '9') || ch == '-' || ch == '_' || ch == '.')) return 0U;
  }
  return 0U;
}

static uint8_t reading(Cursor *cursor, UiReading *reading, int32_t minimum,
                       int32_t maximum, uint64_t generated)
{
  uint64_t sampled;
  uint64_t quality;
  if (!character(cursor, '[') || !signed_value(cursor, &reading->value) ||
      !character(cursor, ',') || !unsigned_value(cursor, &sampled) ||
      !character(cursor, ',') || !unsigned_value(cursor, &quality) ||
      !character(cursor, ']') || (quality > UI_QUALITY_INVALID) ||
      (reading->value < minimum) || (reading->value > maximum) ||
      !valid_timestamp(sampled, generated, (UiDataQuality)quality)) return 0U;
  reading->sampled_ms = sampled;
  reading->quality = (UiDataQuality)quality;
  (void)sampled;
  return 1U;
}

/* `target` is the actual duty percent the producer applied, and `brightness`
 * below is the same domain: the menu offers 0/30/60/100 and 25/50/75/100
 * presets, but the legacy Web/IoTDA controller path may command any whole
 * percent, and the menu ladder is enforced on the command path (Node A's
 * IsFanPreset/IsBrightness), never here.  Rejecting a non-preset here would
 * discard the entire snapshot - every sensor and alarm in it - over a fan that
 * is simply not on a preset. */
static uint8_t fan(Cursor *cursor, UiFanSnapshot *fan_snapshot, uint64_t generated)
{
  uint64_t target, running, rpm, voltage, current, sampled, quality;
  if (!character(cursor, '[') || !unsigned_value(cursor, &target) ||
      !character(cursor, ',') || !unsigned_value(cursor, &running) ||
      !character(cursor, ',') || !unsigned_value(cursor, &rpm) ||
      !character(cursor, ',') || !unsigned_value(cursor, &voltage) ||
      !character(cursor, ',') || !unsigned_value(cursor, &current) ||
      !character(cursor, ',') || !unsigned_value(cursor, &sampled) ||
      !character(cursor, ',') || !unsigned_value(cursor, &quality) ||
      !character(cursor, ']') || target > 100U || running > 1U ||
      rpm > 100000U || voltage > 36000U || current > 10000U ||
      quality > UI_QUALITY_INVALID ||
      !valid_timestamp(sampled, generated, (UiDataQuality)quality)) return 0U;
  fan_snapshot->target_duty_percent = (uint8_t)target;
  fan_snapshot->running = (uint8_t)running;
  fan_snapshot->actual_rpm = (uint32_t)rpm;
  fan_snapshot->voltage_mv = (uint16_t)voltage;
  fan_snapshot->current_ma = (uint16_t)current;
  fan_snapshot->sampled_ms = sampled;
  fan_snapshot->quality = (UiDataQuality)quality;
  (void)sampled;
  return 1U;
}

static uint8_t parse_model(const char *line, size_t length, uint32_t received_ms,
                           UiSnapshot *snapshot, uint32_t *sequence)
{
  Cursor cursor;
  char schema[32], source[16], command_id[40];
  uint64_t generated, sequence_value, alarm, warning, critical;
  uint8_t relay, buzzer, muted;
  uint8_t node_a, gateway, iotda, mqtt;
  uint64_t led_mode, brightness, connectivity_updated;
  uint8_t command_accepted, command_complete;
  uint64_t command_completed;
  if ((line == 0) || (snapshot == 0) || (sequence == 0) ||
      (length == 0U) || (length > SCREEN_SNAPSHOT_LINE_SIZE)) return 0U;
  cursor.at = line;
  cursor.end = line + length;
  if (!character(&cursor, '{') || !named_key(&cursor, "schema") ||
      !string_value(&cursor, schema, sizeof(schema)) || strcmp(schema, "ut.screen.snapshot.v1") != 0 ||
      !character(&cursor, ',') || !named_key(&cursor, "source") ||
      !string_value(&cursor, source, sizeof(source)) || strcmp(source, "CTRL-01") != 0 ||
      !character(&cursor, ',') || !named_key(&cursor, "generatedAtMs") ||
      !unsigned_value(&cursor, &generated) || !character(&cursor, ',') ||
      !named_key(&cursor, "seq") || !unsigned_value(&cursor, &sequence_value) ||
      sequence_value > UINT32_MAX || !character(&cursor, ',') ||
      !named_key(&cursor, "sensors") || !character(&cursor, '{') ||
      !named_key(&cursor, "temperature") || !reading(&cursor, &snapshot->temperature_centi_c, -5000, 10000, generated) ||
      !character(&cursor, ',') || !named_key(&cursor, "humidity") || !reading(&cursor, &snapshot->humidity_centi_rh, 0, 10000, generated) ||
      !character(&cursor, ',') || !named_key(&cursor, "oxygen") || !reading(&cursor, &snapshot->oxygen_milli_percent, 0, 100000, generated) ||
      !character(&cursor, ',') || !named_key(&cursor, "methane") || !reading(&cursor, &snapshot->methane_ppm, 0, 100000, generated) ||
      !character(&cursor, ',') || !named_key(&cursor, "carbonMonoxide") || !reading(&cursor, &snapshot->carbon_monoxide_ppm, 0, 100000, generated) ||
      !character(&cursor, ',') || !named_key(&cursor, "smoke") || !reading(&cursor, &snapshot->smoke, 0, 4095, generated) ||
      !character(&cursor, ',') || !named_key(&cursor, "water") || !reading(&cursor, &snapshot->water_level_raw, 0, 4095, generated) ||
      !character(&cursor, ',') || !named_key(&cursor, "flame") || !reading(&cursor, &snapshot->flame, 0, 1, generated) ||
      !character(&cursor, '}') || !character(&cursor, ',') || !named_key(&cursor, "alarm") ||
      !character(&cursor, '[') || !unsigned_value(&cursor, &alarm) || alarm > UI_ALARM_CRITICAL ||
      !character(&cursor, ',') || !unsigned_value(&cursor, &warning) || warning > UI_ALARM_SOURCE_MASK ||
      !character(&cursor, ',') || !unsigned_value(&cursor, &critical) || critical > UI_ALARM_SOURCE_MASK ||
      !character(&cursor, ']') || !character(&cursor, ',') || !named_key(&cursor, "fans") ||
      !character(&cursor, '[') || !fan(&cursor, &snapshot->fans[0], generated) ||
      !character(&cursor, ',') || !fan(&cursor, &snapshot->fans[1], generated) ||
      !character(&cursor, ']') || !character(&cursor, ',') || !named_key(&cursor, "actuators") ||
      !character(&cursor, '[') || !boolean_value(&cursor, &relay) ||
      !character(&cursor, ',') || !unsigned_value(&cursor, &led_mode) || led_mode > UI_LED_FLASH ||
      !character(&cursor, ',') || !unsigned_value(&cursor, &brightness) || brightness > 100U ||
      !character(&cursor, ',') || !boolean_value(&cursor, &buzzer) ||
      !character(&cursor, ',') || !boolean_value(&cursor, &muted) ||
      !character(&cursor, ']') || !character(&cursor, ',') || !named_key(&cursor, "connectivity") ||
      !character(&cursor, '[') || !link_status_value(&cursor, &node_a) ||
      !character(&cursor, ',') || !link_status_value(&cursor, &mqtt) ||
      !character(&cursor, ',') || !link_status_value(&cursor, &gateway) ||
      !character(&cursor, ',') || !link_status_value(&cursor, &iotda) ||
      !character(&cursor, ',') || !unsigned_value(&cursor, &connectivity_updated) ||
      !character(&cursor, ']') || !character(&cursor, ',') || !named_key(&cursor, "lastCommand") ||
      !character(&cursor, '[') || !string_value(&cursor, command_id, sizeof(command_id)) ||
      !character(&cursor, ',') || !boolean_value(&cursor, &command_accepted) ||
      !character(&cursor, ',') || !boolean_value(&cursor, &command_complete) ||
      !character(&cursor, ',') || !unsigned_value(&cursor, &command_completed) ||
      !character(&cursor, ']')) return 0U;
  while (character(&cursor, ',')) {
    if (named_key(&cursor, "items")) {
      if (!character(&cursor, '[')) return 0U;
      if (!character(&cursor, ']')) {
        while (1) {
          char item_id[16];
          char item_src[16];
          uint64_t item_k, item_q, item_a, item_t;
          int32_t item_v, item_sc;
          size_t i;
          if (!character(&cursor, '{') ||
              !named_key(&cursor, "id") || !string_value(&cursor, item_id, sizeof(item_id)) ||
              !character(&cursor, ',') || !named_key(&cursor, "k") || !unsigned_value(&cursor, &item_k) ||
              !character(&cursor, ',') || !named_key(&cursor, "v") || !signed_value(&cursor, &item_v) ||
              !character(&cursor, ',') || !named_key(&cursor, "sc") || !signed_value(&cursor, &item_sc) ||
              !character(&cursor, ',') || !named_key(&cursor, "q") || !unsigned_value(&cursor, &item_q) ||
              !character(&cursor, ',') || !named_key(&cursor, "a") || !unsigned_value(&cursor, &item_a) ||
              !character(&cursor, ',') || !named_key(&cursor, "s") || !string_value(&cursor, item_src, sizeof(item_src)) ||
              !character(&cursor, ',') || !named_key(&cursor, "t") || !unsigned_value(&cursor, &item_t) ||
              !character(&cursor, '}')) return 0U;
          if (item_q > (uint64_t)UI_QUALITY_MISSING || item_a > 1U) return 0U;
          for (i = 0U; i < snapshot->sensor_count; ++i) {
            if (strcmp(snapshot->sensors[i].asset_code, item_id) == 0) return 0U;
          }
          if (snapshot->sensor_count < SCREEN_SENSOR_CAPACITY) {
            ScreenSensorReading *r = &snapshot->sensors[snapshot->sensor_count++];
            (void)strncpy(r->asset_code, item_id, sizeof(r->asset_code) - 1U);
            r->asset_code[sizeof(r->asset_code) - 1U] = '\0';
            r->kind = (uint8_t)item_k;
            r->value = item_v;
            r->scale = item_sc;
            r->quality = (UiDataQuality)item_q;
            r->alarm = (uint8_t)item_a;
            (void)strncpy(r->source, item_src, sizeof(r->source) - 1U);
            r->source[sizeof(r->source) - 1U] = '\0';
            r->updated_at_ms = item_t;
          }
          if (character(&cursor, ']')) break;
          if (!character(&cursor, ',')) return 0U;
        }
      }
    } else if (named_key(&cursor, "alarmLabel")) {
      if (!string_value(&cursor, snapshot->alarm_label, sizeof(snapshot->alarm_label))) return 0U;
    } else {
      return 0U;
    }
  }
  if (!character(&cursor, '}')) return 0U;
  if (snapshot->alarm_label[0] == '\0') {
    size_t i;
    for (i = 0U; i < snapshot->sensor_count; ++i) {
      if (snapshot->sensors[i].alarm != 0U) {
        (void)strncpy(snapshot->alarm_label, snapshot->sensors[i].asset_code, sizeof(snapshot->alarm_label) - 1U);
        snapshot->alarm_label[sizeof(snapshot->alarm_label) - 1U] = '\0';
        break;
      }
    }
  }
  skip_space(&cursor);
  if (cursor.at != cursor.end || generated < 1704067200000ULL ||
      generated > 4102444799999ULL || connectivity_updated < 1704067200000ULL ||
      connectivity_updated > generated ||
      (command_complete ? (!safe_token(command_id, sizeof(command_id), 0U) ||
                           command_completed < 1704067200000ULL ||
                           command_completed > generated) :
                          (!safe_token(command_id, sizeof(command_id), 1U) || command_accepted || command_completed != 0ULL))) return 0U;
  (void)source;
  (void)received_ms;
  snapshot->alarm_severity = (UiAlarmSeverity)alarm;
  snapshot->warning_sources = (uint32_t)warning;
  snapshot->critical_sources = (uint32_t)critical;
  snapshot->alarm_sources = snapshot->warning_sources | snapshot->critical_sources;
  snapshot->actuators.relay_on = (uint8_t)relay;
  snapshot->actuators.led_mode = (UiLedMode)led_mode;
  snapshot->actuators.led_brightness_percent = (uint8_t)brightness;
  snapshot->actuators.buzzer_on = (uint8_t)buzzer;
  snapshot->actuators.buzzer_muted = (uint8_t)muted;
  snapshot->connectivity.node_a = (uint8_t)node_a;
  snapshot->connectivity.mqtt = (uint8_t)mqtt;
  snapshot->connectivity.gateway = (uint8_t)gateway;
  snapshot->connectivity.iotda = (uint8_t)iotda;
  snapshot->connectivity.updated_ms = connectivity_updated;
  (void)memcpy(snapshot->last_command.command_id, command_id, sizeof(snapshot->last_command.command_id));
  snapshot->last_command.accepted = (uint8_t)command_accepted;
  snapshot->last_command.complete = (uint8_t)command_complete;
  snapshot->last_command.completed_ms = command_completed;
  *sequence = (uint32_t)sequence_value;
  return 1U;
}

void ScreenSnapshot_Init(ScreenSnapshotContext *context)
{
  if (context != 0) (void)memset(context, 0, sizeof(*context));
}

uint8_t ScreenSnapshot_Parse(const char *line, size_t length, UiSnapshot *snapshot)
{
  uint32_t sequence;
  UiSnapshot temporary;
  if ((line == 0) || (snapshot == 0) || (length == 0U) ||
      (length > SCREEN_SNAPSHOT_LINE_SIZE)) return 0U;
  (void)memset(&temporary, 0, sizeof(temporary));
  if (!parse_model(line, length, 0U, &temporary, &sequence)) return 0U;
  *snapshot = temporary;
  return 1U;
}

uint8_t ScreenSnapshot_Apply(ScreenSnapshotContext *context, const char *line,
                             size_t length, uint32_t now_ms, UiSnapshot *snapshot)
{
  UiSnapshot temporary;
  uint32_t sequence;
  size_t i, j;
  uint8_t found;
  (void)memset(&temporary, 0, sizeof(temporary));
  if ((context == 0) || (snapshot == 0) || (length == 0U) ||
      (length > SCREEN_SNAPSHOT_LINE_SIZE) ||
      !parse_model(line, length, now_ms, &temporary, &sequence)) return 0U;
  if (context->initialized && ((int32_t)(sequence - context->sequence) <= 0)) return 0U;
  context->initialized = 1U;
  context->sequence = sequence;
  context->received_ms = now_ms;

  /* Merge rotation: preserve existing sensors and update/replace by asset code */
  for (i = 0U; i < temporary.sensor_count; ++i) {
    found = 0U;
    for (j = 0U; j < snapshot->sensor_count; ++j) {
      if (strcmp(snapshot->sensors[j].asset_code, temporary.sensors[i].asset_code) == 0) {
        snapshot->sensors[j] = temporary.sensors[i];
        found = 1U;
        break;
      }
    }
    if (!found && (snapshot->sensor_count < SCREEN_SENSOR_CAPACITY)) {
      snapshot->sensors[snapshot->sensor_count++] = temporary.sensors[i];
    }
  }
  if (temporary.alarm_label[0] != '\0') {
    (void)strncpy(snapshot->alarm_label, temporary.alarm_label, sizeof(snapshot->alarm_label) - 1U);
    snapshot->alarm_label[sizeof(snapshot->alarm_label) - 1U] = '\0';
  } else {
    for (i = 0U; i < snapshot->sensor_count; ++i) {
      if (snapshot->sensors[i].alarm != 0U) {
        (void)strncpy(snapshot->alarm_label, snapshot->sensors[i].asset_code, sizeof(snapshot->alarm_label) - 1U);
        snapshot->alarm_label[sizeof(snapshot->alarm_label) - 1U] = '\0';
        break;
      }
    }
  }

  /* Copy standard fields */
  snapshot->temperature_centi_c = temporary.temperature_centi_c;
  snapshot->humidity_centi_rh = temporary.humidity_centi_rh;
  snapshot->oxygen_milli_percent = temporary.oxygen_milli_percent;
  snapshot->methane_ppm = temporary.methane_ppm;
  snapshot->carbon_monoxide_ppm = temporary.carbon_monoxide_ppm;
  snapshot->smoke = temporary.smoke;
  snapshot->water_level_raw = temporary.water_level_raw;
  snapshot->flame = temporary.flame;
  snapshot->alarm_severity = temporary.alarm_severity;
  snapshot->warning_sources = temporary.warning_sources;
  snapshot->critical_sources = temporary.critical_sources;
  snapshot->alarm_sources = temporary.alarm_sources;
  snapshot->fans[0] = temporary.fans[0];
  snapshot->fans[1] = temporary.fans[1];
  snapshot->actuators = temporary.actuators;
  snapshot->connectivity = temporary.connectivity;
  snapshot->last_command = temporary.last_command;
  return 1U;
}

uint8_t ScreenSnapshot_IsStale(const ScreenSnapshotContext *context, uint32_t now_ms)
{
  return (context != 0) && context->initialized &&
         ((uint32_t)(now_ms - context->received_ms) >= SCREEN_SNAPSHOT_STALE_MS);
}

void ScreenSnapshot_SetMqttAvailability(UiSnapshot *snapshot, uint8_t online,
                                        uint64_t updated_ms)
{
  if (snapshot == 0) return;
  /* This is a real observation from the ESP link, so it is Online or Offline,
   * never Unknown: it may clear a previous Unknown. */
  snapshot->connectivity.mqtt = online ? (uint8_t)UI_LINK_ONLINE
                                       : (uint8_t)UI_LINK_OFFLINE;
  snapshot->connectivity.updated_ms = updated_ms;
}

void ScreenSnapshot_Tick(const ScreenSnapshotContext *context, uint32_t now_ms,
                         UiSnapshot *snapshot)
{
  UiReading *readings;
  size_t index;
  if (snapshot == 0) return;
  if (ScreenSnapshot_IsStale(context, now_ms)) {
    readings = &snapshot->temperature_centi_c;
    for (index = 0U; index < 8U; ++index) {
      if (readings[index].quality == UI_QUALITY_VALID) readings[index].quality = UI_QUALITY_STALE;
    }
    for (index = 0U; index < 2U; ++index) {
      if (snapshot->fans[index].quality == UI_QUALITY_VALID) snapshot->fans[index].quality = UI_QUALITY_STALE;
    }
    snapshot->connectivity.mqtt = (uint8_t)UI_LINK_UNKNOWN;
    snapshot->connectivity.updated_ms = now_ms;
  }
  /* Expire individual readings to missing after the freshness window */
  for (index = 0U; index < snapshot->sensor_count; ++index) {
    if (snapshot->sensors[index].quality != UI_QUALITY_MISSING) {
      if ((context != 0) && context->initialized &&
          ((uint32_t)(now_ms - (uint32_t)snapshot->sensors[index].updated_at_ms) >= SCREEN_SNAPSHOT_STALE_MS)) {
        snapshot->sensors[index].quality = UI_QUALITY_MISSING;
      }
    }
  }
}

uint8_t ScreenSnapshot_AlarmCount(const UiSnapshot *snapshot)
{
  uint8_t count = 0U;
  size_t i;
  if (snapshot == 0) return 0U;
  for (i = 0U; i < snapshot->sensor_count; ++i) {
    if (snapshot->sensors[i].alarm != 0U) {
      ++count;
    }
  }
  if ((count == 0U) && (snapshot->alarm_severity != UI_ALARM_NONE)) {
    return 1U;
  }
  return count;
}

UiDataQuality ScreenSnapshot_WorstQuality(const UiSnapshot *snapshot)
{
  UiDataQuality worst = UI_QUALITY_VALID;
  size_t i;
  if (snapshot == 0) return UI_QUALITY_UNKNOWN;
  for (i = 0U; i < snapshot->sensor_count; ++i) {
    const UiDataQuality q = snapshot->sensors[i].quality;
    if (q == UI_QUALITY_MISSING) return UI_QUALITY_MISSING;
    if ((q == UI_QUALITY_INVALID) && (worst != UI_QUALITY_MISSING)) worst = UI_QUALITY_INVALID;
    else if ((q == UI_QUALITY_STALE) && (worst != UI_QUALITY_MISSING) && (worst != UI_QUALITY_INVALID)) worst = UI_QUALITY_STALE;
    else if ((q == UI_QUALITY_UNKNOWN) && (worst == UI_QUALITY_VALID)) worst = UI_QUALITY_UNKNOWN;
  }
  return worst;
}

const char *ScreenSnapshot_AlarmLabel(const UiSnapshot *snapshot)
{
  size_t i;
  if (snapshot == 0) return "";
  if (snapshot->alarm_label[0] != '\0') return snapshot->alarm_label;
  for (i = 0U; i < snapshot->sensor_count; ++i) {
    if (snapshot->sensors[i].alarm != 0U) {
      return snapshot->sensors[i].asset_code;
    }
  }
  return "";
}
