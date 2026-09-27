#pragma once

#include <cstddef>
#include <cstdint>

#include "screen_protocol.h"

namespace screen_routing {

constexpr size_t kTopicCapacity = 48U;
constexpr size_t kTransportPayloadLimit = 1024U;
constexpr uint32_t kTimeSyncPeriodMs = 600000U;
constexpr uint64_t kSequenceRestartSilenceMs = 5000ULL;
constexpr uint64_t kSequenceResyncSilenceMs = 30000ULL;
constexpr uint32_t kSequenceRestartMaximum = 4U;
constexpr uint32_t kSequenceRestartMinimumPrevious = 16U;
constexpr size_t kUartTxQueueCapacity = 4U;
constexpr size_t kUartTxChunkLimit = 64U;
constexpr size_t kUartTxTerminatorLength = 2U;

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
  uint64_t last_received_at_ms;
  bool initialized;
  bool accept_session_reset;
};

enum class UartTxFrameKind : uint8_t {
  Snapshot = 0,
  Acknowledgement,
  TimeSync,
  Diagnostic,
};

enum class UartTxEnqueueResult : uint8_t {
  Queued = 0,
  Coalesced,
  Full,
  TooLarge,
  Invalid,
};

struct UartTxFrame {
  uint8_t bytes[screen_protocol::kUartLineLimit + kUartTxTerminatorLength];
  uint16_t length;
  uint16_t offset;
  UartTxFrameKind kind;
};

struct UartTxQueue {
  UartTxFrame frames[kUartTxQueueCapacity];
  uint8_t head;
  uint8_t count;
  uint32_t dropped_frames;
  uint32_t coalesced_frames;
};

struct TimeSyncSchedule {
  uint32_t last_emit_ms;
  uint32_t next_sequence;
  bool emitted;
};

struct NtpAssociationState {
  bool configured_for_current_association;
};

struct MqttLinkStatusState {
  bool initialized;
  bool connected;
};

struct NodeBHeartbeatState {
  uint32_t last_sequence;
  bool initialized;
};

enum class MqttLinkStatusResult : uint8_t {
  Emitted = 0,
  Unchanged,
  OutputTooSmall,
};

enum class TimeEmitResult : uint8_t {
  Emitted = 0,
  NotDue,
  InvalidEpoch,
  OutputTooSmall,
};

const RouteTopics& TopicsForRole(Role role);

/* Compact the peer's sensor telemetry for CTRL-01's 9600-baud status screen.
 * Each record is index,value,quality; voltage duplicates are omitted. */
RouteResult BuildPeerTelemetryLine(const char* payload, size_t length,
                                   char* output, size_t capacity,
                                   size_t* written);

void InitTelemetryAccumulator(TelemetryAccumulator* accumulator);

void BeginTelemetrySession(TelemetryAccumulator* accumulator);

uint64_t EpochMillisecondsFromUnixParts(int64_t epoch_seconds,
                                        int32_t microseconds);

void InitUartTxQueue(UartTxQueue* queue);

UartTxEnqueueResult EnqueueUartTxLine(UartTxQueue* queue,
                                     UartTxFrameKind kind,
                                     const char* payload, size_t length);

size_t UartTxQueuedFrameCount(const UartTxQueue* queue);

size_t UartTxPeek(const UartTxQueue* queue, size_t available_bytes,
                  const uint8_t** bytes);

void UartTxConsume(UartTxQueue* queue, size_t consumed_bytes);

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

void InitMqttLinkStatusState(MqttLinkStatusState* state);

bool IsCtrl01BootLine(const char* line, size_t length);

bool IsCtrl02StatusHeartbeat(const char* line, size_t length);

bool ShouldResyncForCtrl02Heartbeat(NodeBHeartbeatState* state,
                                   const char* line, size_t length);

void RequestMqttLinkStatus(MqttLinkStatusState* state);

void RequestTimeSync(TimeSyncSchedule* schedule);

MqttLinkStatusResult BuildMqttLinkStatus(MqttLinkStatusState* state,
                                         bool connected, char* output,
                                         size_t output_capacity,
                                         size_t* written);

TimeEmitResult BuildDueTimeSync(TimeSyncSchedule* schedule, uint32_t now_ms,
                                uint64_t epoch_seconds, char* output,
                                size_t output_capacity, size_t* written);

}  // namespace screen_routing
