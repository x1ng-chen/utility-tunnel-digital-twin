#ifndef NODE_A_COMMAND_H
#define NODE_A_COMMAND_H

#include <stddef.h>
#include <stdint.h>

/* The single, HAL-free command dispatcher for CTRL-01.  Web, IoTDA and
 * menu-originated `ut.command.v1` messages are all parsed and decided here so
 * that the acknowledgement and actuator result never depend on the transport
 * that delivered the command.  The dispatcher mutates only the in-memory
 * actuator view; the caller commits that view to hardware only after a result
 * is ACCEPTED, so a rejected command can never move an actuator. */

#define NODE_A_COMMAND_ID_MAX        39U  /* maximum command-id length in characters */
#define NODE_A_COMMAND_ACTION_MAX    24U
#define NODE_A_COMMAND_REASON_MAX    48U
#define NODE_A_COMMAND_DEDUP_CAPACITY 8U
#define NODE_A_COMMAND_TTL_MAX_MS    30000U
#define NODE_A_COMMAND_JSON_MAX      383U

typedef enum {
  NODE_A_ACTION_UNKNOWN = 0,
  /* Legacy Web/IoTDA actions (preserve bench-tested behavior). */
  NODE_A_ACTION_STATUS,
  NODE_A_ACTION_SAFE_STATE,
  NODE_A_ACTION_BUZZER_OFF,
  NODE_A_ACTION_BUZZER_ON,
  NODE_A_ACTION_RELAY_OFF,
  NODE_A_ACTION_RELAY_ON,
  NODE_A_ACTION_FAN_PWM,        /* legacy fan 1 duty via dutyPercent */
  NODE_A_ACTION_FAN2_PWM,       /* legacy fan 2 duty via dutyPercent */
  NODE_A_ACTION_LED_OFF,
  NODE_A_ACTION_LED_RED,
  NODE_A_ACTION_LED_GREEN,
  NODE_A_ACTION_LED_BLUE,
  /* Menu-originated actions (normalized by ESP-01). */
  NODE_A_ACTION_FAN1_DUTY,
  NODE_A_ACTION_FANS_BOTH_START,
  NODE_A_ACTION_FANS_ALL_STOP,
  NODE_A_ACTION_FAN2_DUTY,
  NODE_A_ACTION_LED_MODE,
  NODE_A_ACTION_LED_BRIGHTNESS,
  NODE_A_ACTION_BUZZER_TEST,
  NODE_A_ACTION_BUZZER_MUTE,
  NODE_A_ACTION_BUZZER_RESTORE,
} NodeACommandAction;

typedef enum {
  NODE_A_STATUS_ACCEPTED = 0,
  NODE_A_STATUS_REJECTED,
  NODE_A_STATUS_DUPLICATE,
  NODE_A_STATUS_EXPIRED,
} NodeACommandStatus;

typedef enum {
  NODE_A_LED_OFF = 0,
  NODE_A_LED_WHITE,
  NODE_A_LED_GREEN,
  NODE_A_LED_YELLOW,
  NODE_A_LED_RED,
  NODE_A_LED_BLUE,
  NODE_A_LED_BREATHE,
  NODE_A_LED_FLASH,
} NodeALedMode;

/* The active local safety model.  Only the methane channel drives automatic
 * ventilation, but smoke/flame/gas alarms all gate the audible alarm. */
typedef struct {
  uint8_t smoke_alarm;
  uint8_t flame_alarm;
  uint8_t gas_alarm;
  uint8_t gas_warning;
  uint8_t gas_ventilation_active;
} NodeASafetyState;

/* The in-memory actuator view.  Durations are not stored here; the caller
 * derives timed-actuator durations from the command TTL when committing. */
typedef struct {
  uint8_t fan1_pwm_percent;
  uint8_t fan2_pwm_percent;
  uint8_t relay_on;
  uint8_t buzzer_on;
  uint8_t buzzer_muted;
  uint8_t led_mode;                 /* NodeALedMode */
  uint8_t led_brightness_percent;
} NodeAActuatorState;

typedef struct {
  char command_id[NODE_A_COMMAND_ID_MAX + 1U];
  NodeACommandAction action;
  uint32_t value;                   /* dutyPercent (legacy fan) or value (menu) */
  uint8_t has_value;
  uint32_t ttl_ms;
  uint32_t received_at_ms;          /* local tick, set by the caller */
} NodeACommand;

typedef struct {
  NodeACommandStatus status;
  const char *reason;               /* static string literal */
  uint32_t applied_value;           /* 0..100 applied duty/brightness/mode */
} NodeACommandResult;

typedef struct {
  char ids[NODE_A_COMMAND_DEDUP_CAPACITY][NODE_A_COMMAND_ID_MAX + 1U];
  uint8_t next;
} NodeACommandDedup;

/* Parse the schema and cmdId of a `ut.command.v1` payload.  Returns 1 when the
 * schema matches and cmdId is a safe 1..39 character token.  On failure the
 * caller acknowledges `unknown` / `rejected` / `invalid_command`. */
uint8_t NodeACommand_ParseHeader(const char *json, NodeACommand *command);

/* Parse one complete bounded `ut.command.v1` object.  Unknown or duplicate
 * fields, malformed delimiters/numbers, and trailing bytes are rejected. */
uint8_t NodeACommand_Parse(const char *json, NodeACommand *command);

/* Parse the action, value/dutyPercent and ttlMs.  Returns 1 when the action
 * string is readable and ttlMs is in 1..30000.  On failure the caller
 * acknowledges `rejected` / `invalid_or_missing_ttl`. */
uint8_t NodeACommand_ParseBody(const char *json, NodeACommand *command);

/* Decide a parsed command against TTL, safety and value bounds.  Only an
 * ACCEPTED result mutates *actual, so a rejected/expired command always leaves
 * the actuator view unchanged.  The caller commits *actual to hardware only
 * after observing ACCEPTED. */
NodeACommandResult NodeACommand_Apply(const NodeACommand *command,
                                      uint32_t now_ms,
                                      const NodeASafetyState *safety,
                                      NodeAActuatorState *actual);

/* A newly-raised alarm must invalidate any user mute so the audible alarm can
 * sound again.  Call on every 0->1 smoke/flame/gas alarm transition. */
void NodeACommand_AlarmActivated(NodeAActuatorState *actual);

void NodeACommand_DedupInit(NodeACommandDedup *dedup);
uint8_t NodeACommand_IsDuplicate(const NodeACommandDedup *dedup,
                                 const char *command_id);
void NodeACommand_Remember(NodeACommandDedup *dedup, const char *command_id);

/* Format the bounded `ut.command.ack.v1` line.  Returns the length written
 * (excluding the trailing NUL, before CRLF is appended), or 0 when the output
 * is too small or any string field is outside the safe bounded token set.  The
 * applied value is the 0..100 duty/brightness/mode/state value that was
 * applied.  A monotonic completion timestamp is intentionally omitted here:
 * Node A has no epoch clock until the Task 10 time sync, and newlib-nano
 * printf omits 64-bit formatting. */
size_t NodeACommand_FormatAck(char *out, size_t capacity,
                              const char *command_id, const char *status,
                              const char *reason, uint32_t applied_value);

#endif /* NODE_A_COMMAND_H */
