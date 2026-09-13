#include "node_a_command.h"

#include <stdio.h>
#include <string.h>

/* Action strings are matched in enum order.  Index 0 (UNKNOWN) is empty. */
static const char *const action_names[] = {
    "",                  /* NODE_A_ACTION_UNKNOWN */
    "status",
    "safe_state",
    "buzzer_off",
    "buzzer_on",
    "relay_off",
    "relay_on",
    "fan_pwm",
    "fan2_pwm",
    "led_off",
    "led_red",
    "led_green",
    "led_blue",
    "fan1_duty",
    "fans_both_start",
    "fans_all_stop",
    "fan2_duty",
    "led_mode",
    "led_brightness",
    "buzzer_test",
    "buzzer_mute",
    "buzzer_restore",
};

static const char *const kReasonInvalidCommand = "invalid_command";
static const char *const kReasonTtlElapsed = "ttl_elapsed";
static const char *const kReasonControllerOnline = "controller_online";
static const char *const kReasonSafeStateApplied = "safe_state_applied";
static const char *const kReasonAutoVentActive = "automatic_ventilation_active";
static const char *const kReasonBuzzerSilent = "buzzer_silent";
static const char *const kReasonBuzzerActive = "buzzer_active";
static const char *const kReasonRelayOff = "relay_off";
static const char *const kReasonRelayActive = "relay_active";
static const char *const kReasonFanPwmSet = "fan_pwm_set";
static const char *const kReasonFan2PwmSet = "fan2_pwm_set";
static const char *const kReasonFanDutySet = "fan_duty_set";
static const char *const kReasonInvalidDuty = "invalid_duty_percent";
static const char *const kReasonFansBothStarted = "fans_both_started";
static const char *const kReasonFansAllStopped = "fans_all_stopped";
static const char *const kReasonLedOff = "led_off";
static const char *const kReasonLedRed = "led_red";
static const char *const kReasonLedGreen = "led_green";
static const char *const kReasonLedBlue = "led_blue";
static const char *const kReasonLedModeSet = "led_mode_set";
static const char *const kReasonLedBrightnessSet = "led_brightness_set";
static const char *const kReasonBuzzerTestStarted = "buzzer_test_started";
static const char *const kReasonBuzzerMuted = "buzzer_muted";
static const char *const kReasonBuzzerRestored = "buzzer_restored";
static const char *const kReasonInvalidValue = "invalid_value";
static const char *const kReasonActuatorUnmapped = "actuator_unmapped";

static uint8_t Json_ReadString(const char *json, const char *key,
                               char *destination, size_t destination_size)
{
  char needle[32];
  const char *cursor;
  size_t length = 0U;

  if ((json == NULL) || (key == NULL) ||
      (snprintf(needle, sizeof(needle), "\"%s\"", key) <= 0) ||
      (destination == NULL) || (destination_size == 0U)) return 0U;
  cursor = strstr(json, needle);
  if (cursor == NULL) return 0U;
  cursor += strlen(needle);
  while ((*cursor == ' ') || (*cursor == '\t')) ++cursor;
  if (*cursor++ != ':') return 0U;
  while ((*cursor == ' ') || (*cursor == '\t')) ++cursor;
  if (*cursor++ != '"') return 0U;
  while ((*cursor != '\0') && (*cursor != '"'))
  {
    if ((*cursor == '\\') || ((unsigned char)*cursor < 0x20U) ||
        (length >= (destination_size - 1U))) return 0U;
    destination[length++] = *cursor++;
  }
  if ((*cursor != '"') || (length == 0U)) return 0U;
  destination[length] = '\0';
  return 1U;
}

static uint8_t Json_ReadUnsigned(const char *json, const char *key, uint32_t *value)
{
  char needle[32];
  const char *cursor;
  uint32_t parsed = 0U;
  uint8_t digits = 0U;

  if ((json == NULL) || (key == NULL) || (value == NULL) ||
      (snprintf(needle, sizeof(needle), "\"%s\"", key) <= 0)) return 0U;
  cursor = strstr(json, needle);
  if (cursor == NULL) return 0U;
  cursor += strlen(needle);
  while ((*cursor == ' ') || (*cursor == '\t')) ++cursor;
  if (*cursor++ != ':') return 0U;
  while ((*cursor == ' ') || (*cursor == '\t')) ++cursor;
  while ((*cursor >= '0') && (*cursor <= '9'))
  {
    if ((parsed > 429496729U) || ((parsed == 429496729U) && (*cursor > '5'))) return 0U;
    parsed = (parsed * 10U) + (uint32_t)(*cursor++ - '0');
    ++digits;
  }
  if (digits == 0U) return 0U;
  *value = parsed;
  return 1U;
}

static uint8_t CommandId_IsSafe(const char *command_id)
{
  size_t index;
  const size_t length = strlen(command_id);
  if ((length == 0U) || (length > NODE_A_COMMAND_ID_MAX)) return 0U;
  for (index = 0U; index < length; ++index)
  {
    const char value = command_id[index];
    if (!(((value >= 'a') && (value <= 'z')) || ((value >= 'A') && (value <= 'Z')) ||
          ((value >= '0') && (value <= '9')) || (value == '-') || (value == '_'))) return 0U;
  }
  return 1U;
}

static NodeACommandAction ActionFromString(const char *text)
{
  uint8_t index;
  for (index = 1U; index < (uint8_t)(sizeof(action_names) / sizeof(action_names[0])); ++index)
    if (strcmp(text, action_names[index]) == 0) return (NodeACommandAction)index;
  return NODE_A_ACTION_UNKNOWN;
}

uint8_t NodeACommand_ParseHeader(const char *json, NodeACommand *command)
{
  char schema[NODE_A_COMMAND_ACTION_MAX];

  if ((json == NULL) || (command == NULL)) return 0U;
  (void)memset(command, 0, sizeof(*command));
  if (!Json_ReadString(json, "schema", schema, sizeof(schema)) ||
      (strcmp(schema, "ut.command.v1") != 0) ||
      !Json_ReadString(json, "cmdId", command->command_id,
                       sizeof(command->command_id)) ||
      !CommandId_IsSafe(command->command_id)) return 0U;
  return 1U;
}

uint8_t NodeACommand_ParseBody(const char *json, NodeACommand *command)
{
  char action[NODE_A_COMMAND_ACTION_MAX];
  uint32_t ttl_ms;
  uint32_t value;

  if ((json == NULL) || (command == NULL)) return 0U;
  if (!Json_ReadString(json, "action", action, sizeof(action))) return 0U;
  command->action = ActionFromString(action);
  if (!Json_ReadUnsigned(json, "ttlMs", &ttl_ms) || (ttl_ms == 0U) ||
      (ttl_ms > NODE_A_COMMAND_TTL_MAX_MS)) return 0U;
  command->ttl_ms = ttl_ms;
  if (Json_ReadUnsigned(json, "value", &value))
  {
    command->value = value;
    command->has_value = 1U;
  }
  else if (Json_ReadUnsigned(json, "dutyPercent", &value))
  {
    command->value = value;
    command->has_value = 1U;
  }
  else
  {
    command->value = 0U;
    command->has_value = 0U;
  }
  return 1U;
}

static NodeACommandResult Result(NodeACommandStatus status,
                                 const char *reason, uint32_t applied_value)
{
  NodeACommandResult result;
  result.status = status;
  result.reason = reason;
  result.applied_value = applied_value;
  return result;
}

/* A menu fan preset is one of the reviewed duty steps; the legacy Web path may
 * still request any 0..100 duty. */
static uint8_t IsFanPreset(uint32_t value)
{
  return (value == 0U) || (value == 30U) || (value == 60U) || (value == 100U);
}

static uint8_t IsBrightness(uint32_t value)
{
  return (value == 25U) || (value == 50U) || (value == 75U) || (value == 100U);
}

static uint8_t SafetyAlarmActive(const NodeASafetyState *safety)
{
  return (uint8_t)((safety->smoke_alarm != 0U) ||
                   (safety->flame_alarm != 0U) ||
                   (safety->gas_alarm != 0U));
}

NodeACommandResult NodeACommand_Apply(const NodeACommand *command,
                                      uint32_t now_ms,
                                      const NodeASafetyState *safety,
                                      NodeAActuatorState *actual)
{
  uint32_t elapsed_ms;

  if ((command == NULL) || (safety == NULL) || (actual == NULL))
    return Result(NODE_A_STATUS_REJECTED, kReasonInvalidCommand, 0U);

  /* TTL expiry is judged before value or safety so a stale command is always
   * reported as expired, matching the previous dispatcher's ordering. */
  elapsed_ms = now_ms - command->received_at_ms;
  if (elapsed_ms >= command->ttl_ms)
    return Result(NODE_A_STATUS_EXPIRED, kReasonTtlElapsed, 0U);

  switch (command->action)
  {
    case NODE_A_ACTION_STATUS:
      return Result(NODE_A_STATUS_ACCEPTED, kReasonControllerOnline, 0U);

    case NODE_A_ACTION_SAFE_STATE:
      if (SafetyAlarmActive(safety))
        return Result(NODE_A_STATUS_REJECTED, "active_safety_alarm", 0U);
      if (safety->gas_ventilation_active != 0U)
        return Result(NODE_A_STATUS_REJECTED, kReasonAutoVentActive, 0U);
      actual->buzzer_on = 0U;
      actual->buzzer_muted = 0U;
      actual->relay_on = 0U;
      actual->led_mode = NODE_A_LED_OFF;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonSafeStateApplied, 0U);

    case NODE_A_ACTION_BUZZER_OFF:
      if (SafetyAlarmActive(safety))
        return Result(NODE_A_STATUS_REJECTED, "active_safety_alarm", 0U);
      actual->buzzer_on = 0U;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonBuzzerSilent, 0U);

    case NODE_A_ACTION_BUZZER_ON:
      actual->buzzer_on = 1U;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonBuzzerActive, 1U);

    case NODE_A_ACTION_RELAY_OFF:
      if (safety->gas_ventilation_active != 0U)
        return Result(NODE_A_STATUS_REJECTED, kReasonAutoVentActive, 0U);
      actual->relay_on = 0U;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonRelayOff, 0U);

    case NODE_A_ACTION_RELAY_ON:
      actual->relay_on = 1U;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonRelayActive, 1U);

    case NODE_A_ACTION_FAN_PWM:
      if ((command->has_value == 0U) || (command->value > 100U))
        return Result(NODE_A_STATUS_REJECTED, kReasonInvalidDuty, 0U);
      if (safety->gas_ventilation_active != 0U)
        return Result(NODE_A_STATUS_REJECTED, kReasonAutoVentActive, 0U);
      actual->fan1_pwm_percent = (uint8_t)command->value;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonFanPwmSet, command->value);

    case NODE_A_ACTION_FAN2_PWM:
      if ((command->has_value == 0U) || (command->value > 100U))
        return Result(NODE_A_STATUS_REJECTED, kReasonInvalidDuty, 0U);
      if (safety->gas_ventilation_active != 0U)
        return Result(NODE_A_STATUS_REJECTED, kReasonAutoVentActive, 0U);
      actual->fan2_pwm_percent = (uint8_t)command->value;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonFan2PwmSet, command->value);

    case NODE_A_ACTION_LED_OFF:
      if (SafetyAlarmActive(safety))
        return Result(NODE_A_STATUS_REJECTED, "active_safety_alarm", 0U);
      actual->led_mode = NODE_A_LED_OFF;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonLedOff, 0U);

    case NODE_A_ACTION_LED_RED:
      if (SafetyAlarmActive(safety))
        return Result(NODE_A_STATUS_REJECTED, "active_safety_alarm", 0U);
      actual->led_mode = NODE_A_LED_RED;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonLedRed, NODE_A_LED_RED);

    case NODE_A_ACTION_LED_GREEN:
      if (SafetyAlarmActive(safety))
        return Result(NODE_A_STATUS_REJECTED, "active_safety_alarm", 0U);
      actual->led_mode = NODE_A_LED_GREEN;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonLedGreen, NODE_A_LED_GREEN);

    case NODE_A_ACTION_LED_BLUE:
      if (SafetyAlarmActive(safety))
        return Result(NODE_A_STATUS_REJECTED, "active_safety_alarm", 0U);
      actual->led_mode = NODE_A_LED_BLUE;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonLedBlue, NODE_A_LED_BLUE);

    case NODE_A_ACTION_FAN1_DUTY:
      if ((command->has_value == 0U) || !IsFanPreset(command->value))
        return Result(NODE_A_STATUS_REJECTED, kReasonInvalidDuty, 0U);
      if (safety->gas_ventilation_active != 0U)
        return Result(NODE_A_STATUS_REJECTED, kReasonAutoVentActive, 0U);
      actual->fan1_pwm_percent = (uint8_t)command->value;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonFanDutySet, command->value);

    case NODE_A_ACTION_FAN2_DUTY:
      if ((command->has_value == 0U) || !IsFanPreset(command->value))
        return Result(NODE_A_STATUS_REJECTED, kReasonInvalidDuty, 0U);
      if (safety->gas_ventilation_active != 0U)
        return Result(NODE_A_STATUS_REJECTED, kReasonAutoVentActive, 0U);
      actual->fan2_pwm_percent = (uint8_t)command->value;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonFanDutySet, command->value);

    case NODE_A_ACTION_FANS_BOTH_START:
      if ((command->has_value != 0U) && (command->value != 0U))
        return Result(NODE_A_STATUS_REJECTED, kReasonInvalidValue, 0U);
      if (safety->gas_ventilation_active != 0U)
        return Result(NODE_A_STATUS_REJECTED, kReasonAutoVentActive, 0U);
      actual->fan1_pwm_percent = 100U;
      actual->fan2_pwm_percent = 100U;
      actual->relay_on = 1U;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonFansBothStarted, 100U);

    case NODE_A_ACTION_FANS_ALL_STOP:
      if ((command->has_value != 0U) && (command->value != 0U))
        return Result(NODE_A_STATUS_REJECTED, kReasonInvalidValue, 0U);
      if (safety->gas_ventilation_active != 0U)
        return Result(NODE_A_STATUS_REJECTED, kReasonAutoVentActive, 0U);
      actual->fan1_pwm_percent = 0U;
      actual->fan2_pwm_percent = 0U;
      actual->relay_on = 0U;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonFansAllStopped, 0U);

    case NODE_A_ACTION_LED_MODE:
      if (SafetyAlarmActive(safety))
        return Result(NODE_A_STATUS_REJECTED, "active_safety_alarm", 0U);
      if ((command->has_value == 0U) || (command->value > (uint32_t)NODE_A_LED_FLASH))
        return Result(NODE_A_STATUS_REJECTED, kReasonInvalidValue, 0U);
      actual->led_mode = (uint8_t)command->value;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonLedModeSet, command->value);

    case NODE_A_ACTION_LED_BRIGHTNESS:
      if (SafetyAlarmActive(safety))
        return Result(NODE_A_STATUS_REJECTED, "active_safety_alarm", 0U);
      if ((command->has_value == 0U) || !IsBrightness(command->value))
        return Result(NODE_A_STATUS_REJECTED, kReasonInvalidValue, 0U);
      actual->led_brightness_percent = (uint8_t)command->value;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonLedBrightnessSet, command->value);

    case NODE_A_ACTION_BUZZER_TEST:
      if ((command->has_value != 0U) && (command->value != 0U))
        return Result(NODE_A_STATUS_REJECTED, kReasonInvalidValue, 0U);
      actual->buzzer_on = 1U;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonBuzzerTestStarted, 1U);

    case NODE_A_ACTION_BUZZER_MUTE:
      if ((command->has_value != 0U) && (command->value != 0U))
        return Result(NODE_A_STATUS_REJECTED, kReasonInvalidValue, 0U);
      if (SafetyAlarmActive(safety))
        return Result(NODE_A_STATUS_REJECTED, "active_safety_alarm", 0U);
      actual->buzzer_on = 0U;
      actual->buzzer_muted = 1U;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonBuzzerMuted, 1U);

    case NODE_A_ACTION_BUZZER_RESTORE:
      if ((command->has_value != 0U) && (command->value != 0U))
        return Result(NODE_A_STATUS_REJECTED, kReasonInvalidValue, 0U);
      actual->buzzer_muted = 0U;
      return Result(NODE_A_STATUS_ACCEPTED, kReasonBuzzerRestored, 0U);

    default:
      return Result(NODE_A_STATUS_REJECTED, kReasonActuatorUnmapped, 0U);
  }
}

void NodeACommand_AlarmActivated(NodeAActuatorState *actual)
{
  if (actual == NULL) return;
  /* A new alarm must invalidate a user mute so the audible alarm can sound. */
  actual->buzzer_muted = 0U;
}

void NodeACommand_DedupInit(NodeACommandDedup *dedup)
{
  if (dedup == NULL) return;
  (void)memset(dedup, 0, sizeof(*dedup));
}

uint8_t NodeACommand_IsDuplicate(const NodeACommandDedup *dedup,
                                 const char *command_id)
{
  uint8_t index;
  if ((dedup == NULL) || (command_id == NULL)) return 0U;
  for (index = 0U; index < NODE_A_COMMAND_DEDUP_CAPACITY; ++index)
    if (strcmp(dedup->ids[index], command_id) == 0) return 1U;
  return 0U;
}

void NodeACommand_Remember(NodeACommandDedup *dedup, const char *command_id)
{
  if ((dedup == NULL) || (command_id == NULL)) return;
  (void)snprintf(dedup->ids[dedup->next], NODE_A_COMMAND_ID_MAX + 1U, "%s", command_id);
  dedup->next = (uint8_t)((dedup->next + 1U) % NODE_A_COMMAND_DEDUP_CAPACITY);
}

size_t NodeACommand_FormatAck(char *out, size_t capacity,
                              const char *command_id, const char *status,
                              const char *reason, uint32_t applied_value)
{
  const char *field;
  size_t field_length;
  int length;

  if ((out == NULL) || (capacity == 0U) || (command_id == NULL) ||
      (status == NULL) || (reason == NULL)) return 0U;
  field_length = strlen(command_id);
  if ((field_length == 0U) || (field_length > NODE_A_COMMAND_ID_MAX)) return 0U;
  for (field = command_id; *field != '\0'; ++field)
    if (((unsigned char)*field < 0x20U) || (*field == '"') || (*field == '\\')) return 0U;
  field_length = strlen(status);
  if ((field_length == 0U) || (field_length > 16U)) return 0U;
  for (field = status; *field != '\0'; ++field)
    if (((unsigned char)*field < 0x20U) || (*field == '"') || (*field == '\\')) return 0U;
  field_length = strlen(reason);
  if ((field_length == 0U) || (field_length > NODE_A_COMMAND_REASON_MAX)) return 0U;
  for (field = reason; *field != '\0'; ++field)
    if (((unsigned char)*field < 0x20U) || (*field == '"') || (*field == '\\')) return 0U;

  length = snprintf(out, capacity,
    "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"%s\",\"status\":\"%s\","
    "\"reason\":\"%s\",\"appliedValue\":%lu}",
    command_id, status, reason, (unsigned long)applied_value);
  if ((length <= 0) || ((size_t)length >= capacity)) return 0U;
  return (size_t)length;
}
