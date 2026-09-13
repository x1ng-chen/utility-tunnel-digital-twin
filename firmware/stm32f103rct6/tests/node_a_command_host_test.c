#include <stdio.h>
#include <string.h>

#include "node_a_command.h"

#define CHECK(condition) do { \
  if (!(condition)) { \
    (void)fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    return 1; \
  } \
} while (0)

static const NodeASafetyState SAFE = {0, 0, 0, 0, 0};
static const NodeASafetyState VENTILATING = {0, 0, 0, 0, 1};

static NodeAActuatorState default_actuators(void)
{
  NodeAActuatorState actual;
  actual.fan1_pwm_percent = 100U;
  actual.fan2_pwm_percent = 100U;
  actual.relay_on = 0U;
  actual.buzzer_on = 0U;
  actual.buzzer_muted = 0U;
  actual.led_mode = NODE_A_LED_OFF;
  actual.led_brightness_percent = 100U;
  return actual;
}

/* Parse a well-formed command and apply it at now_ms (received_at_ms = 0). */
static NodeACommandResult apply(const char *json, uint32_t now_ms,
                                const NodeASafetyState *safety,
                                NodeAActuatorState *actual)
{
  NodeACommand command;
  NodeACommandResult result;
  if (NodeACommand_ParseHeader(json, &command) != 1U ||
      NodeACommand_ParseBody(json, &command) != 1U)
  {
    (void)fprintf(stderr, "FAIL: test command did not parse: %s\n", json);
    result.status = NODE_A_STATUS_REJECTED;
    result.reason = "parse_failure";
    result.applied_value = 0U;
    return result;
  }
  command.received_at_ms = 0U;
  return NodeACommand_Apply(&command, now_ms, safety, actual);
}

static int test_header_bounds(void)
{
  NodeACommand command;
  static const char maximum_id[] = "012345678901234567890123456789012345678"; /* 39 */
  char json[256];

  _Static_assert(sizeof(maximum_id) == 40U, "maximum command id must be 39 chars");

  CHECK(NodeACommand_ParseHeader(
      "{\"schema\":\"ut.command.v1\",\"cmdId\":\"web-1\"}", &command) == 1U);
  CHECK(strcmp(command.command_id, "web-1") == 0);

  (void)snprintf(json, sizeof(json),
      "{\"schema\":\"ut.command.v1\",\"cmdId\":\"%s\"}", maximum_id);
  CHECK(NodeACommand_ParseHeader(json, &command) == 1U);
  CHECK(strcmp(command.command_id, maximum_id) == 0);

  (void)snprintf(json, sizeof(json),
      "{\"schema\":\"ut.command.v1\",\"cmdId\":\"%s0\"}", maximum_id);
  CHECK(NodeACommand_ParseHeader(json, &command) == 0U);

  /* Wrong schema, empty cmdId, unsafe characters and missing cmdId all fail. */
  CHECK(NodeACommand_ParseHeader(
      "{\"schema\":\"ut.other\",\"cmdId\":\"web-1\"}", &command) == 0U);
  CHECK(NodeACommand_ParseHeader(
      "{\"schema\":\"ut.command.v1\",\"cmdId\":\"\"}", &command) == 0U);
  CHECK(NodeACommand_ParseHeader(
      "{\"schema\":\"ut.command.v1\",\"cmdId\":\"bad id\"}", &command) == 0U);
  CHECK(NodeACommand_ParseHeader(
      "{\"schema\":\"ut.command.v1\"}", &command) == 0U);
  CHECK(NodeACommand_ParseHeader(NULL, &command) == 0U);
  return 0;
}

static int test_body_bounds(void)
{
  NodeACommand command;

  CHECK(NodeACommand_ParseBody(
      "{\"action\":\"status\",\"ttlMs\":1}", &command) == 1U);
  CHECK(command.action == NODE_A_ACTION_STATUS);
  CHECK(command.ttl_ms == 1U);

  CHECK(NodeACommand_ParseBody(
      "{\"action\":\"status\",\"ttlMs\":30000}", &command) == 1U);
  CHECK(NodeACommand_ParseBody(
      "{\"action\":\"status\",\"ttlMs\":0}", &command) == 0U);
  CHECK(NodeACommand_ParseBody(
      "{\"action\":\"status\",\"ttlMs\":30001}", &command) == 0U);
  CHECK(NodeACommand_ParseBody(
      "{\"action\":\"status\"}", &command) == 0U);
  CHECK(NodeACommand_ParseBody(
      "{\"ttlMs\":10000}", &command) == 0U);

  /* Unknown action strings parse but resolve to UNKNOWN for the dispatcher. */
  CHECK(NodeACommand_ParseBody(
      "{\"action\":\"no_such_action\",\"ttlMs\":10000}", &command) == 1U);
  CHECK(command.action == NODE_A_ACTION_UNKNOWN);

  /* Menu value and legacy dutyPercent both fill the same value slot. */
  CHECK(NodeACommand_ParseBody(
      "{\"action\":\"fan1_duty\",\"ttlMs\":10000,\"value\":60}", &command) == 1U);
  CHECK(command.has_value == 1U && command.value == 60U);
  CHECK(NodeACommand_ParseBody(
      "{\"action\":\"fan_pwm\",\"ttlMs\":10000,\"dutyPercent\":45}", &command) == 1U);
  CHECK(command.has_value == 1U && command.value == 45U);
  CHECK(NodeACommand_ParseBody(
      "{\"action\":\"fan_pwm\",\"ttlMs\":10000}", &command) == 1U);
  CHECK(command.has_value == 0U);
  CHECK(NodeACommand_ParseBody(NULL, &command) == 0U);
  return 0;
}

static int test_fan_duties(void)
{
  NodeAActuatorState actual;
  NodeACommandResult result;

  actual = default_actuators();
  result = apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"m-1\","
      "\"action\":\"fan1_duty\",\"ttlMs\":10000,\"value\":30}",
      1U, &SAFE, &actual);
  CHECK(result.status == NODE_A_STATUS_ACCEPTED);
  CHECK(actual.fan1_pwm_percent == 30U && actual.fan2_pwm_percent == 100U);

  actual = default_actuators();
  result = apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"m-2\","
      "\"action\":\"fan1_duty\",\"ttlMs\":10000,\"value\":60}",
      1U, &SAFE, &actual);
  CHECK(result.applied_value == 60U);
  CHECK(actual.fan1_pwm_percent == 60U);

  actual = default_actuators();
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"m-3\","
      "\"action\":\"fan2_duty\",\"ttlMs\":10000,\"value\":100}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_ACCEPTED);
  CHECK(actual.fan2_pwm_percent == 100U);

  /* Legacy fan_pwm accepts any 0..100 duty and targets fan 1. */
  actual = default_actuators();
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"w-1\","
      "\"action\":\"fan_pwm\",\"ttlMs\":10000,\"dutyPercent\":45}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_ACCEPTED);
  CHECK(actual.fan1_pwm_percent == 45U);

  /* Menu duty must be a preset; a non-preset value rejects without moving. */
  actual = default_actuators();
  result = apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"m-4\","
      "\"action\":\"fan1_duty\",\"ttlMs\":10000,\"value\":45}",
      1U, &SAFE, &actual);
  CHECK(result.status == NODE_A_STATUS_REJECTED);
  CHECK(strcmp(result.reason, "invalid_duty_percent") == 0);
  CHECK(actual.fan1_pwm_percent == 100U);

  actual = default_actuators();
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"w-2\","
      "\"action\":\"fan_pwm\",\"ttlMs\":10000,\"dutyPercent\":101}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_REJECTED);
  CHECK(actual.fan1_pwm_percent == 100U);

  actual = default_actuators();
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"w-3\","
      "\"action\":\"fan_pwm\",\"ttlMs\":10000}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_REJECTED);
  return 0;
}

static int test_both_start_and_stop(void)
{
  NodeAActuatorState actual;

  actual = default_actuators();
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"m-5\","
      "\"action\":\"fans_both_start\",\"ttlMs\":10000,\"value\":0}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_ACCEPTED);
  CHECK(actual.fan1_pwm_percent == 100U && actual.fan2_pwm_percent == 100U);
  CHECK(actual.relay_on == 1U);

  actual = default_actuators();
  actual.relay_on = 1U;
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"m-6\","
      "\"action\":\"fans_all_stop\",\"ttlMs\":10000,\"value\":0}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_ACCEPTED);
  CHECK(actual.fan1_pwm_percent == 0U && actual.fan2_pwm_percent == 0U);
  CHECK(actual.relay_on == 0U);
  return 0;
}

static int test_led_modes_and_brightness(void)
{
  NodeAActuatorState actual;
  unsigned int mode;

  for (mode = 0U; mode <= (unsigned int)NODE_A_LED_FLASH; ++mode)
  {
    char json[256];
    actual = default_actuators();
    (void)snprintf(json, sizeof(json),
        "{\"schema\":\"ut.command.v1\",\"cmdId\":\"led-%u\","
        "\"action\":\"led_mode\",\"ttlMs\":10000,\"value\":%u}", mode, mode);
    CHECK(apply(json, 1U, &SAFE, &actual).status == NODE_A_STATUS_ACCEPTED);
    CHECK(actual.led_mode == mode);
  }

  actual = default_actuators();
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"led-bad\","
      "\"action\":\"led_mode\",\"ttlMs\":10000,\"value\":8}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_REJECTED);
  CHECK(actual.led_mode == NODE_A_LED_OFF);

  {
    static const unsigned int brightness[] = {25U, 50U, 75U, 100U};
    unsigned int index;
    for (index = 0U; index < sizeof(brightness) / sizeof(brightness[0]); ++index)
    {
      char json[256];
      actual = default_actuators();
      (void)snprintf(json, sizeof(json),
          "{\"schema\":\"ut.command.v1\",\"cmdId\":\"br-%u\","
          "\"action\":\"led_brightness\",\"ttlMs\":10000,\"value\":%u}",
          index, brightness[index]);
      CHECK(apply(json, 1U, &SAFE, &actual).status == NODE_A_STATUS_ACCEPTED);
      CHECK(actual.led_brightness_percent == brightness[index]);
    }
  }

  actual = default_actuators();
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"br-bad\","
      "\"action\":\"led_brightness\",\"ttlMs\":10000,\"value\":40}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_REJECTED);
  CHECK(actual.led_brightness_percent == 100U);

  /* Legacy single-color actions map onto the mode field. */
  actual = default_actuators();
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"w-led\","
      "\"action\":\"led_green\",\"ttlMs\":10000}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_ACCEPTED);
  CHECK(actual.led_mode == NODE_A_LED_GREEN);
  return 0;
}

static int test_buzzer_actions_and_safety_transition(void)
{
  NodeAActuatorState actual;

  actual = default_actuators();
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"b-test\","
      "\"action\":\"buzzer_test\",\"ttlMs\":10000,\"value\":0}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_ACCEPTED);
  CHECK(actual.buzzer_on == 1U && actual.buzzer_muted == 0U);

  actual = default_actuators();
  actual.buzzer_on = 1U;
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"b-mute\","
      "\"action\":\"buzzer_mute\",\"ttlMs\":10000,\"value\":0}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_ACCEPTED);
  CHECK(actual.buzzer_on == 0U && actual.buzzer_muted == 1U);

  /* A new alarm invalidates the mute (safety transition). */
  NodeACommand_AlarmActivated(&actual);
  CHECK(actual.buzzer_muted == 0U);

  actual = default_actuators();
  actual.buzzer_muted = 1U;
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"b-restore\","
      "\"action\":\"buzzer_restore\",\"ttlMs\":10000,\"value\":0}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_ACCEPTED);
  CHECK(actual.buzzer_muted == 0U);

  /* Legacy buzzer_off only silences; it does not mute. */
  actual = default_actuators();
  actual.buzzer_on = 1U;
  CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"w-bz\","
      "\"action\":\"buzzer_off\",\"ttlMs\":10000}",
      1U, &SAFE, &actual).status == NODE_A_STATUS_ACCEPTED);
  CHECK(actual.buzzer_on == 0U && actual.buzzer_muted == 0U);
  return 0;
}

static int test_invalid_action_and_ttl(void)
{
  NodeAActuatorState actual = default_actuators();
  NodeACommandResult result;

  result = apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"bad-act\","
      "\"action\":\"no_such_action\",\"ttlMs\":10000}", 1U, &SAFE, &actual);
  CHECK(result.status == NODE_A_STATUS_REJECTED);
  CHECK(strcmp(result.reason, "actuator_unmapped") == 0);

  /* Expired TTL is reported before any value/safety judgement. */
  result = apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"expired\","
      "\"action\":\"fan1_duty\",\"ttlMs\":10000,\"value\":60}",
      10000U, &SAFE, &actual);
  CHECK(result.status == NODE_A_STATUS_EXPIRED);
  CHECK(strcmp(result.reason, "ttl_elapsed") == 0);
  CHECK(actual.fan1_pwm_percent == 100U);

  /* At the boundary just before expiry the command still executes. */
  result = apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"edge\","
      "\"action\":\"fan1_duty\",\"ttlMs\":10000,\"value\":60}",
      9999U, &SAFE, &actual);
  CHECK(result.status == NODE_A_STATUS_ACCEPTED);
  CHECK(actual.fan1_pwm_percent == 60U);

  /* Menu commands with zero-only actions must not accept a stray value. */
  result = apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"bad-start\","
      "\"action\":\"fans_both_start\",\"ttlMs\":10000,\"value\":1}",
      1U, &SAFE, &actual);
  CHECK(result.status == NODE_A_STATUS_REJECTED);
  CHECK(strcmp(result.reason, "invalid_value") == 0);
  result = apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"bad-test\","
      "\"action\":\"buzzer_test\",\"ttlMs\":10000,\"value\":1}",
      1U, &SAFE, &actual);
  CHECK(result.status == NODE_A_STATUS_REJECTED);
  CHECK(strcmp(result.reason, "invalid_value") == 0);
  return 0;
}

static int test_safety_rejection_leaves_state_unchanged(void)
{
  static const char *const rejected_actions[] = {
    "{\"schema\":\"ut.command.v1\",\"cmdId\":\"s-1\",\"action\":\"safe_state\",\"ttlMs\":10000}",
    "{\"schema\":\"ut.command.v1\",\"cmdId\":\"s-2\",\"action\":\"relay_off\",\"ttlMs\":10000}",
    "{\"schema\":\"ut.command.v1\",\"cmdId\":\"s-3\",\"action\":\"fan_pwm\",\"ttlMs\":10000,\"dutyPercent\":30}",
    "{\"schema\":\"ut.command.v1\",\"cmdId\":\"s-4\",\"action\":\"fan2_pwm\",\"ttlMs\":10000,\"dutyPercent\":30}",
    "{\"schema\":\"ut.command.v1\",\"cmdId\":\"s-5\",\"action\":\"fan1_duty\",\"ttlMs\":10000,\"value\":30}",
    "{\"schema\":\"ut.command.v1\",\"cmdId\":\"s-6\",\"action\":\"fan2_duty\",\"ttlMs\":10000,\"value\":30}",
    "{\"schema\":\"ut.command.v1\",\"cmdId\":\"s-7\",\"action\":\"fans_both_start\",\"ttlMs\":10000,\"value\":0}",
    "{\"schema\":\"ut.command.v1\",\"cmdId\":\"s-8\",\"action\":\"fans_all_stop\",\"ttlMs\":10000,\"value\":0}",
  };
  unsigned int index;

  for (index = 0U; index < sizeof(rejected_actions) / sizeof(rejected_actions[0]); ++index)
  {
    NodeAActuatorState actual = default_actuators();
    actual.relay_on = 1U;
    NodeACommandResult result = apply(rejected_actions[index], 1U, &VENTILATING, &actual);
    CHECK(result.status == NODE_A_STATUS_REJECTED);
    CHECK(strcmp(result.reason, "automatic_ventilation_active") == 0);
    CHECK(actual.fan1_pwm_percent == 100U);
    CHECK(actual.fan2_pwm_percent == 100U);
    CHECK(actual.relay_on == 1U);
  }

  /* Non-fan actuators remain available during ventilation. */
  {
    NodeAActuatorState actual = default_actuators();
    CHECK(apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"s-led\","
        "\"action\":\"led_red\",\"ttlMs\":10000}",
        1U, &VENTILATING, &actual).status == NODE_A_STATUS_ACCEPTED);
    CHECK(actual.led_mode == NODE_A_LED_RED);
  }
  return 0;
}

static int test_duplicate_atomicity(void)
{
  NodeACommandDedup dedup;
  NodeACommand_DedupInit(&dedup);

  CHECK(NodeACommand_IsDuplicate(NULL, "dup-1") == 0U);
  CHECK(NodeACommand_IsDuplicate(&dedup, NULL) == 0U);
  NodeACommand_Remember(&dedup, NULL);
  CHECK(NodeACommand_IsDuplicate(&dedup, "dup-1") == 0U);
  NodeACommand_Remember(&dedup, "dup-1");
  CHECK(NodeACommand_IsDuplicate(&dedup, "dup-1") == 1U);
  CHECK(NodeACommand_IsDuplicate(&dedup, "dup-2") == 0U);

  /* A rejected command is still remembered so a retry is a duplicate. */
  NodeACommand_Remember(&dedup, "dup-3");
  CHECK(NodeACommand_IsDuplicate(&dedup, "dup-3") == 1U);

  /* The ring wraps and evicts the oldest entry after capacity fills. */
  {
    NodeACommandDedup ring;
    char id[8];
    unsigned int index;
    NodeACommand_DedupInit(&ring);
    for (index = 0U; index < NODE_A_COMMAND_DEDUP_CAPACITY; ++index)
    {
      (void)snprintf(id, sizeof(id), "ring-%u", index);
      NodeACommand_Remember(&ring, id);
    }
    CHECK(NodeACommand_IsDuplicate(&ring, "ring-0") == 1U);
    NodeACommand_Remember(&ring, "ring-8");
    CHECK(NodeACommand_IsDuplicate(&ring, "ring-0") == 0U);
    CHECK(NodeACommand_IsDuplicate(&ring, "ring-8") == 1U);
  }
  return 0;
}

static int test_ack_format_truthfulness(void)
{
  char out[256];
  char long_reason[NODE_A_COMMAND_REASON_MAX + 2U];
  size_t length;

  length = NodeACommand_FormatAck(out, sizeof(out), "menu-1", "accepted",
                                  "fan_duty_set", 60U);
  CHECK(length > 0U && length < sizeof(out));
  CHECK(strcmp(out,
      "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"menu-1\",\"status\":\"accepted\","
      "\"reason\":\"fan_duty_set\",\"appliedValue\":60}") == 0);

  length = NodeACommand_FormatAck(out, sizeof(out), "unknown", "rejected",
                                  "invalid_command", 0U);
  CHECK(strcmp(out,
      "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"unknown\",\"status\":\"rejected\","
      "\"reason\":\"invalid_command\",\"appliedValue\":0}") == 0);

  /* A too-small buffer must not silently truncate the acknowledgement. */
  CHECK(NodeACommand_FormatAck(out, 16U, "menu-1", "accepted",
                               "fan_duty_set", 60U) == 0U);
  /* FormatAck must never emit malformed JSON if a transport-facing field is
   * accidentally passed without the parser's safe-token guarantee. */
  CHECK(NodeACommand_FormatAck(out, sizeof(out), "bad\"id", "accepted",
                               "fan_duty_set", 60U) == 0U);
  (void)memset(long_reason, 'r', sizeof(long_reason) - 1U);
  long_reason[sizeof(long_reason) - 1U] = '\0';
  CHECK(NodeACommand_FormatAck(out, sizeof(out), "menu-1", "accepted",
                               long_reason, 60U) == 0U);
  return 0;
}

static int test_active_alarm_rejects_manual_silence_and_visual_override(void)
{
  static const NodeASafetyState ALARM = {1, 0, 0, 0, 1};
  NodeAActuatorState actual;
  NodeACommandResult result;

  actual = default_actuators();
  actual.buzzer_on = 1U;
  result = apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"alarm-mute\","
      "\"action\":\"buzzer_mute\",\"ttlMs\":10000}",
      1U, &ALARM, &actual);
  CHECK(result.status == NODE_A_STATUS_REJECTED);
  CHECK(strcmp(result.reason, "active_safety_alarm") == 0);
  CHECK(actual.buzzer_on == 1U && actual.buzzer_muted == 0U);

  result = apply("{\"schema\":\"ut.command.v1\",\"cmdId\":\"alarm-led\","
      "\"action\":\"led_mode\",\"ttlMs\":10000,\"value\":3}",
      1U, &ALARM, &actual);
  CHECK(result.status == NODE_A_STATUS_REJECTED);
  CHECK(strcmp(result.reason, "active_safety_alarm") == 0);
  CHECK(actual.led_mode == NODE_A_LED_OFF);
  return 0;
}

int main(void)
{
  if (test_header_bounds() != 0) return 1;
  if (test_body_bounds() != 0) return 1;
  if (test_fan_duties() != 0) return 1;
  if (test_both_start_and_stop() != 0) return 1;
  if (test_led_modes_and_brightness() != 0) return 1;
  if (test_buzzer_actions_and_safety_transition() != 0) return 1;
  if (test_invalid_action_and_ttl() != 0) return 1;
  if (test_safety_rejection_leaves_state_unchanged() != 0) return 1;
  if (test_duplicate_atomicity() != 0) return 1;
  if (test_ack_format_truthfulness() != 0) return 1;
  if (test_active_alarm_rejects_manual_silence_and_visual_override() != 0) return 1;
  (void)puts("NodeACommand host test: PASS");
  return 0;
}
