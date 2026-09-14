#pragma once

#include <cstddef>
#include <cstdint>

namespace screen_protocol {

constexpr size_t kUartLineLimit = 768U;
constexpr size_t kCommandIdCapacity = 40U;  // 39 characters plus NUL.
constexpr size_t kDeviceIdCapacity = 8U;
constexpr size_t kAckReasonCapacity = 48U;
constexpr uint64_t kMinEpochSeconds = 1704067200ULL;  // 2024-01-01T00:00:00Z.
// End of 2099 UTC. Keeping both representations bounded makes subtraction and
// seconds-to-milliseconds conversion safe in the STM32/ESP uint64_t consumers.
constexpr uint64_t kMaxEpochSeconds = 4102444799ULL;
constexpr uint64_t kMaxEpochMilliseconds = 4102444799999ULL;
constexpr uint32_t kSnapshotMaxAgeMs = 5000U;
constexpr uint32_t kCommandMaxTtlMs = 30000U;

enum class Result : uint8_t {
  Ok = 0,
  NullArgument,
  TooLarge,
  OutputTooSmall,
  MalformedJson,
  TrailingData,
  MissingField,
  WrongType,
  NumberOverflow,
  InvalidString,
  UnknownSchema,
  InvalidIdentifier,
  InvalidTarget,
  InvalidEnum,
  OutOfRange,
  Stale,
  Expired,
};

enum class Quality : uint8_t {
  Unknown = 0,
  Valid = 1,
  Stale = 2,
  Invalid = 3,
};

enum class AlarmSeverity : uint8_t {
  None = 0,
  Warning = 1,
  Critical = 2,
};

/* A link the screen reports on.  Unknown is a first-class state, not "false":
 * this firmware has no observed status for the IoTDA gateway or the cloud
 * session, so it must say so rather than claim they are offline.  Offline is
 * reserved for a status that was actually observed to be down. */
enum class LinkStatus : uint8_t {
  Unknown = 0,
  Online = 1,
  Offline = 2,
};

enum class CommandAction : uint8_t {
  Fan1Duty = 0,
  FansBothStart,
  FansAllStop,
  Fan2Duty,
  LedMode,
  LedBrightness,
  BuzzerTest,
  BuzzerMute,
  BuzzerRestore,
};

enum class AckStatus : uint8_t {
  Accepted = 0,
  Rejected,
  Duplicate,
  Expired,
};

enum class TimeSource : uint8_t {
  Ntp = 0,
  Snapshot,
};

enum class TimeState : uint8_t {
  Synchronized = 0,
  Holdover,
};

struct Reading {
  int32_t value;
  uint64_t sampled_at_ms;
  Quality quality;
};

struct FanSnapshot {
  uint8_t target_duty_percent;
  bool running;
  uint32_t actual_rpm;
  uint16_t voltage_mv;
  uint16_t current_ma;
  uint64_t sampled_at_ms;
  Quality quality;
};

struct ActuatorSnapshot {
  bool relay_on;
  uint8_t led_mode;
  uint8_t led_brightness_percent;
  bool buzzer_on;
  bool buzzer_muted;
};

struct ConnectivitySnapshot {
  /* Observed on the telemetry wire: a frame that reached CTRL-02 was produced
   * by Node A and carried by the broker, so both are structurally online. */
  LinkStatus node_a;
  LinkStatus mqtt;
  /* Not observable from any topic CTRL-02 subscribes to today.  They stay
   * Unknown until a status source feeds them, and the screen renders them as
   * unknown rather than inventing an OFFLINE. */
  LinkStatus gateway;
  LinkStatus iotda;
  uint64_t updated_at_ms;
};

struct LastCommandResult {
  char command_id[kCommandIdCapacity];
  bool accepted;
  bool complete;
  uint64_t completed_at_ms;
};

struct ScreenSnapshot {
  char source[kDeviceIdCapacity];
  uint64_t generated_at_ms;
  uint32_t sequence;
  Reading temperature;
  Reading humidity;
  Reading oxygen;
  Reading methane;
  Reading carbon_monoxide;
  Reading smoke;
  Reading water;
  Reading flame;
  AlarmSeverity alarm_severity;
  uint32_t warning_sources;
  uint32_t critical_sources;
  FanSnapshot fans[2];
  ActuatorSnapshot actuators;
  ConnectivitySnapshot connectivity;
  LastCommandResult last_command;
};

struct MenuCommand {
  char command_id[kCommandIdCapacity];
  char target[kDeviceIdCapacity];
  CommandAction action;
  uint8_t value;
  uint64_t created_at_ms;
  uint32_t ttl_ms;
};

struct CommandAck {
  char command_id[kCommandIdCapacity];
  AckStatus status;
  char reason[kAckReasonCapacity];
  int32_t applied_value;
  uint64_t completed_at_ms;
};

struct TimeSync {
  TimeSource source;
  TimeState state;
  uint64_t epoch_seconds;
  uint32_t sequence;
};

Result BuildSnapshot(const ScreenSnapshot& snapshot, char* output,
                     size_t output_capacity, size_t* written);
Result ParseSnapshot(const char* json, size_t length, uint64_t now_epoch_ms,
                     ScreenSnapshot* snapshot);

Result BuildMenuCommand(const MenuCommand& command, char* output,
                        size_t output_capacity, size_t* written);
Result ParseMenuCommand(const char* json, size_t length, uint64_t now_epoch_ms,
                        MenuCommand* command);

Result BuildCommandAck(const CommandAck& acknowledgement, char* output,
                       size_t output_capacity, size_t* written);
Result ParseCommandAck(const char* json, size_t length,
                       CommandAck* acknowledgement);

Result BuildTimeSync(const TimeSync& time_sync, char* output,
                     size_t output_capacity, size_t* written);
Result ParseTimeSync(const char* json, size_t length, TimeSync* time_sync);

}  // namespace screen_protocol
