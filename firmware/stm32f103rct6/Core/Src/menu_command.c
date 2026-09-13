#include "menu_command.h"

#include <stdio.h>
#include <string.h>

typedef struct {
  const char *at;
  const char *end;
} CommandCursor;

static void skip(CommandCursor *cursor)
{
  while ((cursor->at < cursor->end) && ((*cursor->at == ' ') || (*cursor->at == '\t') ||
         (*cursor->at == '\r') || (*cursor->at == '\n'))) ++cursor->at;
}

static uint8_t ch(CommandCursor *cursor, char expected)
{
  skip(cursor);
  if ((cursor->at >= cursor->end) || *cursor->at != expected) return 0U;
  ++cursor->at;
  return 1U;
}

static uint8_t string_value(CommandCursor *cursor, char *output, size_t capacity)
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

static uint8_t named(CommandCursor *cursor, const char *name)
{
  char actual[24];
  if (!string_value(cursor, actual, sizeof(actual)) || strcmp(actual, name) != 0) return 0U;
  return ch(cursor, ':');
}

static uint8_t number(CommandCursor *cursor, int32_t *value)
{
  uint8_t negative = 0U;
  uint32_t result = 0U;
  uint8_t digits = 0U;
  skip(cursor);
  if ((cursor->at < cursor->end) && *cursor->at == '-') { negative = 1U; ++cursor->at; }
  while ((cursor->at < cursor->end) && *cursor->at >= '0' && *cursor->at <= '9') {
    uint8_t digit = (uint8_t)(*cursor->at - '0');
    if (result > (UINT32_MAX - digit) / 10U) return 0U;
    result = result * 10U + digit;
    ++cursor->at;
    digits = 1U;
  }
  if (!digits || result > (negative ? 2147483648UL : 2147483647UL)) return 0U;
  *value = negative ? (result == 2147483648UL ? INT32_MIN : -(int32_t)result) : (int32_t)result;
  return 1U;
}

static uint8_t unsigned_number(CommandCursor *cursor, uint64_t *value)
{
  uint64_t result = 0U;
  uint8_t digits = 0U;
  skip(cursor);
  while ((cursor->at < cursor->end) && *cursor->at >= '0' && *cursor->at <= '9') {
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

static const char *action_name(UiAction action)
{
  static const char *const names[] = {
    "none", "fan1_duty", "fans_both_start", "fans_all_stop", "fan2_duty",
    "led_mode", "led_brightness", "buzzer_test", "buzzer_mute", "buzzer_restore",
  };
  return ((uint8_t)action < (uint8_t)(sizeof(names) / sizeof(names[0]))) ? names[action] : "none";
}

static uint8_t action_value_valid(UiAction action, uint8_t value)
{
  if ((action == UI_ACTION_FAN_1_SET_DUTY) || (action == UI_ACTION_FAN_2_SET_DUTY)) {
    return (value == 0U) || (value == 30U) || (value == 60U) || (value == 100U);
  }
  if (action == UI_ACTION_LED_MODE) return value <= (uint8_t)UI_LED_FLASH;
  if (action == UI_ACTION_LED_BRIGHTNESS) {
    return (value == 25U) || (value == 50U) || (value == 75U) || (value == 100U);
  }
  return value == 0U;
}

void MenuCommand_Init(MenuCommandContext *context, uint32_t boot_id)
{
  if (context == 0) return;
  (void)memset(context, 0, sizeof(*context));
  context->boot_id = boot_id;
}

uint8_t MenuCommand_Begin(MenuCommandContext *context, UiAction action, uint8_t value,
                          uint64_t created_at_ms, char *line, size_t line_capacity,
                          size_t *written)
{
  int length;
  uint32_t next;
  if ((context == 0) || (line == 0) || (written == 0) ||
      ((uint8_t)action == (uint8_t)UI_ACTION_NONE) || created_at_ms == 0ULL) return 0U;
  if (!action_value_valid(action, value)) return 0U;
  next = context->sequence + 1U;
  if (next == 0U) next = 1U;
  context->sequence = next;
  length = snprintf(line, line_capacity,
                    "{\"schema\":\"ut.menu.command.v1\",\"cmdId\":\"menu-CTRL-02-%lu-%lu\","
                    "\"target\":\"CTRL-01\",\"action\":\"%s\",\"value\":%u,"
                    "\"createdAtMs\":%llu,\"ttlMs\":%u}\r\n",
                    (unsigned long)context->boot_id, (unsigned long)next,
                    action_name(action), (unsigned int)value,
                    (unsigned long long)created_at_ms, MENU_COMMAND_TTL_MS);
  if ((length <= 0) || ((size_t)length >= line_capacity) || ((size_t)length > MENU_COMMAND_LINE_SIZE)) {
    context->sequence = next - 1U;
    *written = 0U;
    return 0U;
  }
  (void)snprintf(context->active_command_id, sizeof(context->active_command_id),
                 "menu-CTRL-02-%lu-%lu", (unsigned long)context->boot_id, (unsigned long)next);
  context->pending = 1U;
  *written = (size_t)length;
  return 1U;
}

uint8_t MenuCommand_ParseAck(const char *line, size_t length, MenuCommandAck *ack)
{
  CommandCursor cursor;
  char schema[32], status[16], reason[48];
  int32_t applied;
  if ((line == 0) || (ack == 0) || (length == 0U)) return 0U;
  if (length > 768U) return 0U;
  cursor.at = line;
  cursor.end = line + length;
  if (!ch(&cursor, '{') || !named(&cursor, "schema") || !string_value(&cursor, schema, sizeof(schema)) ||
      strcmp(schema, "ut.command.ack.v1") != 0 || !ch(&cursor, ',') || !named(&cursor, "cmdId") ||
      !string_value(&cursor, ack->command_id, sizeof(ack->command_id)) || ack->command_id[0] == '\0' ||
      !ch(&cursor, ',') || !named(&cursor, "status") || !string_value(&cursor, status, sizeof(status)) ||
      !ch(&cursor, ',') || !named(&cursor, "reason") || !string_value(&cursor, reason, sizeof(reason)) ||
      !ch(&cursor, ',') || !named(&cursor, "appliedValue") || !number(&cursor, &applied)) return 0U;
  /* Node A's bounded ACK predates completedAtMs; ESP-02 may include it. */
  skip(&cursor);
  if (cursor.at < cursor.end && *cursor.at == ',') {
    uint64_t ignored;
    if (!ch(&cursor, ',') || !named(&cursor, "completedAtMs") || !unsigned_number(&cursor, &ignored)) return 0U;
  }
  if (!ch(&cursor, '}')) return 0U;
  skip(&cursor);
  if (cursor.at != cursor.end ||
      (strcmp(status, "accepted") != 0 && strcmp(status, "rejected") != 0 &&
       strcmp(status, "duplicate") != 0 && strcmp(status, "expired") != 0)) return 0U;
  (void)reason;
  ack->accepted = (strcmp(status, "accepted") == 0) ? 1U : 0U;
  ack->applied_value = applied;
  return 1U;
}

uint8_t MenuCommand_AcceptAck(MenuCommandContext *context, const MenuCommandAck *ack)
{
  if ((context == 0) || (ack == 0) || !context->pending ||
      strcmp(context->active_command_id, ack->command_id) != 0) return 0U;
  context->pending = 0U;
  return 1U;
}
