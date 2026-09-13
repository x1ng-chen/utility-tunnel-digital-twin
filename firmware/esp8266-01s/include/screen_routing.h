#pragma once

#include <cstddef>
#include <cstdint>

#include "screen_protocol.h"

namespace screen_routing {

constexpr size_t kTopicCapacity = 48U;
constexpr size_t kTransportPayloadLimit = 1024U;
constexpr uint32_t kTimeSyncPeriodMs = 600000U;

enum class Role : uint8_t {
  Ctrl01 = 0,
  Ctrl02,
};

struct RouteTopics {
  const char* subscriptions[2];
  size_t subscription_count;
  const char* serial_publish_topic;
};

enum class OutputKind : uint8_t {
  None = 0,
  MqttPublish,
  UartLine,
  UartCommand,
};

enum class RouteResult : uint8_t {
  Ok = 0,
  WrongRole,
  WrongTopic,
  InvalidPayload,
  TooLarge,
  OutputTooSmall,
  Expired,
  Stale,
};

struct RouteOutput {
  OutputKind kind;
  char topic[kTopicCapacity];
  char payload[screen_protocol::kUartLineLimit + 1U];
  size_t payload_length;
};

struct TelemetryAccumulator {
  screen_protocol::ScreenSnapshot snapshot;
  uint32_t last_sequence;
  bool initialized;
};

struct TimeSyncSchedule {
  uint32_t last_emit_ms;
  uint32_t next_sequence;
  bool emitted;
};

struct NtpAssociationState {
  bool configured_for_current_association;
};

enum class TimeEmitResult : uint8_t {
  Emitted = 0,
  NotDue,
  InvalidEpoch,
  OutputTooSmall,
};

const RouteTopics& TopicsForRole(Role role);

void InitTelemetryAccumulator(TelemetryAccumulator* accumulator);

RouteResult NormalizeMenuCommand(const char* payload, size_t length,
                                 uint64_t now_epoch_ms, char* output,
                                 size_t output_capacity, size_t* written);

RouteResult RouteSerialLine(Role role, const char* line, size_t length,
                            uint64_t now_epoch_ms, RouteOutput* output);

RouteResult RouteMqttMessage(Role role, const char* topic,
                             const char* payload, size_t length,
                             uint64_t now_epoch_ms,
                             TelemetryAccumulator* accumulator,
                             RouteOutput* output);

void InitTimeSyncSchedule(TimeSyncSchedule* schedule);

void InitNtpAssociationState(NtpAssociationState* state);

bool ShouldConfigureNtp(NtpAssociationState* state, bool wifi_connected);

TimeEmitResult BuildDueTimeSync(TimeSyncSchedule* schedule, uint32_t now_ms,
                                uint64_t epoch_seconds, char* output,
                                size_t output_capacity, size_t* written);

}  // namespace screen_routing
