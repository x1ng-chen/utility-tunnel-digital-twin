#include <cstdint>
#include <cstdio>
#include <cstring>

#include "screen_protocol.h"
#include "screen_routing.h"

namespace {
using namespace screen_protocol;
using namespace screen_routing;

int failures = 0;

#define CHECK_TRUE(expression)                                                     \
  do {                                                                             \
    if (!(expression)) {                                                           \
      std::fprintf(stderr, "%s:%d: CHECK_TRUE(%s) failed\n", __FILE__, __LINE__, \
                   #expression);                                                   \
      ++failures;                                                                  \
    }                                                                              \
  } while (0)

#define CHECK_EQ(expected, actual)                                                     \
  do {                                                                                 \
    const auto expected_value = (expected);                                             \
    const auto actual_value = (actual);                                                 \
    if (!(expected_value == actual_value)) {                                            \
      std::fprintf(stderr, "%s:%d: CHECK_EQ(%s, %s) failed\n", __FILE__, __LINE__, \
                   #expected, #actual);                                                 \
      ++failures;                                                                       \
    }                                                                                  \
  } while (0)

constexpr uint64_t kNowMs = 1704067220000ULL;

constexpr char kValidMenu[] =
    "{\"schema\":\"ut.menu.command.v1\",\"cmdId\":\"menu-CTRL-02-7-42\"," \
    "\"target\":\"CTRL-01\",\"action\":\"fan1_duty\",\"value\":60," \
    "\"createdAtMs\":1704067219000,\"ttlMs\":10000}";

constexpr char kExpectedNormalized[] =
    "{\"schema\":\"ut.command.v1\",\"cmdId\":\"menu-CTRL-02-7-42\"," \
    "\"target\":\"CTRL-01\",\"action\":\"fan1_duty\",\"value\":60," \
    "\"createdAtMs\":1704067219000,\"ttlMs\":10000}";

constexpr char kTelemetry[] =
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":77,\"readings\":["
    "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":22.34,\"unit\":\"degC\",\"quality\":\"good\"},"
    "{\"assetCode\":\"ENV-01\",\"metric\":\"humidity\",\"value\":52.10,\"unit\":\"%RH\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"oxygen.concentration\",\"value\":20.9,\"unit\":\"%Vol\",\"quality\":\"suspect\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"methane.concentration\",\"value\":12,\"unit\":\"ppm\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"carbon_monoxide.concentration\",\"value\":4,\"unit\":\"ppm\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"smoke.alarm\",\"value\":1,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"flame.alarm\",\"value\":0,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"LEVEL-L01\",\"metric\":\"level.detected\",\"value\":1,\"unit\":\"bool\",\"quality\":\"good\"}]}";

constexpr char kFan1Telemetry[] =
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":78,\"readings\":["
    "{\"assetCode\":\"FAN-01\",\"metric\":\"supply.voltage\",\"value\":11.9,\"unit\":\"V\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-01\",\"metric\":\"motor.current\",\"value\":320,\"unit\":\"mA\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-01\",\"metric\":\"rotational.speed\",\"value\":2400,\"unit\":\"rpm\",\"quality\":\"good\"}],"
    "\"diag\":{\"relayActive\":1,\"pwmPercent\":60}}";

constexpr char kFan2Telemetry[] =
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":79,\"readings\":["
    "{\"assetCode\":\"FAN-02\",\"metric\":\"supply.voltage\",\"value\":11.8,\"unit\":\"V\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-02\",\"metric\":\"motor.current\",\"value\":280,\"unit\":\"mA\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-02\",\"metric\":\"rotational.speed\",\"value\":1600,\"unit\":\"rpm\",\"quality\":\"good\"}],"
    "\"diag\":{\"relayActive\":1,\"pwmPercent\":30}}";

constexpr char kAck[] =
    "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"menu-CTRL-02-7-42\"," \
    "\"status\":\"accepted\",\"reason\":\"fan_pwm_set\"," \
    "\"appliedValue\":60,\"completedAtMs\":1704067219950}";

void test_role_routes_are_exact_and_idempotent() {
  const RouteTopics& ctrl01 = TopicsForRole(Role::Ctrl01);
  CHECK_EQ(1U, ctrl01.subscription_count);
  CHECK_TRUE(std::strcmp(ctrl01.subscriptions[0], "ut/v1/CTRL-01/cmd/#") == 0);
  CHECK_TRUE(ctrl01.serial_publish_topic == nullptr);

  const RouteTopics& ctrl02 = TopicsForRole(Role::Ctrl02);
  CHECK_EQ(2U, ctrl02.subscription_count);
  CHECK_TRUE(std::strcmp(ctrl02.subscriptions[0], "ut/v1/CTRL-01/telemetry") == 0);
  CHECK_TRUE(std::strcmp(ctrl02.subscriptions[1], "ut/v1/CTRL-01/cmd_ack") == 0);
  CHECK_TRUE(std::strcmp(ctrl02.serial_publish_topic,
                         "ut/v1/CTRL-01/cmd/menu") == 0);
  CHECK_TRUE(std::strcmp(ctrl02.subscriptions[0], ctrl02.subscriptions[1]) != 0);
  CHECK_TRUE(&TopicsForRole(Role::Ctrl02) == &ctrl02);
}

void test_ctrl01_one_menu_delivery_produces_one_uart_command() {
  TelemetryAccumulator accumulator{};
  InitTelemetryAccumulator(&accumulator);
  RouteOutput output{};
  size_t uart_command_count = 0U;
  const RouteResult result = RouteMqttMessage(
      Role::Ctrl01, "ut/v1/CTRL-01/cmd/menu", kValidMenu,
      sizeof(kValidMenu) - 1U, kNowMs, &accumulator, &output);
  if (result == RouteResult::Ok && output.kind == OutputKind::UartCommand) {
    ++uart_command_count;
  }
  CHECK_EQ(RouteResult::Ok, result);
  CHECK_EQ(1U, uart_command_count);
  CHECK_TRUE(std::strcmp(output.payload, kExpectedNormalized) == 0);
}

void test_subsecond_clock_accepts_node_b_command_from_same_second() {
  const uint64_t now_ms =
      EpochMillisecondsFromUnixParts(1704067220LL, 654321L);
  CHECK_EQ(1704067220654ULL, now_ms);
  CHECK_EQ(0ULL,
           EpochMillisecondsFromUnixParts(
               static_cast<int64_t>(kMinEpochSeconds) - 1LL, 999999L));
  CHECK_EQ(0ULL,
           EpochMillisecondsFromUnixParts(1704067220LL, 1000000L));

  constexpr char command[] =
      "{\"schema\":\"ut.menu.command.v1\",\"cmdId\":\"menu-ms-1\"," \
      "\"target\":\"CTRL-01\",\"action\":\"fan1_duty\",\"value\":60," \
      "\"createdAtMs\":1704067220321,\"ttlMs\":10000}";
  char output[kUartLineLimit + 1U]{};
  size_t written = 0U;
  CHECK_EQ(RouteResult::Ok,
           NormalizeMenuCommand(command, sizeof(command) - 1U, now_ms,
                                output, sizeof(output), &written));
  CHECK_TRUE(std::strstr(output, "\"createdAtMs\":1704067220321") !=
             nullptr);
}

size_t drainUartQueue(UartTxQueue* queue, size_t available_per_pump,
                      char* output, size_t output_capacity) {
  size_t written = 0U;
  while (UartTxQueuedFrameCount(queue) != 0U) {
    const uint8_t* bytes = nullptr;
    const size_t count =
        UartTxPeek(queue, available_per_pump, &bytes);
    if (count == 0U || bytes == nullptr || written + count > output_capacity) {
      return 0U;
    }
    std::memcpy(output + written, bytes, count);
    written += count;
    UartTxConsume(queue, count);
  }
  return written;
}

void test_uart_tx_queue_handles_long_line_and_backpressure_without_blocking() {
  UartTxQueue queue{};
  InitUartTxQueue(&queue);
  char longest[kUartLineLimit];
  std::memset(longest, 'x', sizeof(longest));
  longest[0] = '{';
  longest[sizeof(longest) - 1U] = '}';
  CHECK_EQ(UartTxEnqueueResult::Queued,
           EnqueueUartTxLine(&queue, UartTxFrameKind::Snapshot, longest,
                             sizeof(longest)));
  CHECK_EQ(1U, UartTxQueuedFrameCount(&queue));

  const uint8_t* bytes = reinterpret_cast<const uint8_t*>(longest);
  CHECK_EQ(0U, UartTxPeek(&queue, 0U, &bytes));
  CHECK_TRUE(bytes == nullptr);
  CHECK_EQ(1U, UartTxQueuedFrameCount(&queue));
  CHECK_EQ(kUartTxChunkLimit,
           UartTxPeek(&queue, kUartLineLimit + 2U, &bytes));
  CHECK_TRUE(bytes != nullptr);
  CHECK_EQ(1U, UartTxQueuedFrameCount(&queue));

  char drained[kUartLineLimit + 2U]{};
  const size_t drained_length =
      drainUartQueue(&queue, 7U, drained, sizeof(drained));
  CHECK_EQ(kUartLineLimit + 2U, drained_length);
  CHECK_TRUE(std::memcmp(drained, longest, sizeof(longest)) == 0);
  CHECK_EQ('\r', drained[kUartLineLimit]);
  CHECK_EQ('\n', drained[kUartLineLimit + 1U]);
  CHECK_EQ(0U, UartTxQueuedFrameCount(&queue));

  char oversized[kUartLineLimit + 1U]{};
  CHECK_EQ(UartTxEnqueueResult::TooLarge,
           EnqueueUartTxLine(&queue, UartTxFrameKind::Snapshot, oversized,
                             sizeof(oversized)));
}

void test_uart_tx_queue_coalesces_snapshots_and_never_mixes_frames() {
  UartTxQueue queue{};
  InitUartTxQueue(&queue);
  constexpr char old_snapshot[] = "{\"snapshot\":1}";
  constexpr char acknowledgement[] =
      "{\"cmdId\":\"menu-CTRL-02-boot-7\",\"status\":\"accepted\"}";
  constexpr char new_snapshot[] = "{\"snapshot\":2}";
  CHECK_EQ(UartTxEnqueueResult::Queued,
           EnqueueUartTxLine(&queue, UartTxFrameKind::Snapshot, old_snapshot,
                             sizeof(old_snapshot) - 1U));
  CHECK_EQ(UartTxEnqueueResult::Queued,
           EnqueueUartTxLine(&queue, UartTxFrameKind::Acknowledgement,
                             acknowledgement,
                             sizeof(acknowledgement) - 1U));
  CHECK_EQ(UartTxEnqueueResult::Coalesced,
           EnqueueUartTxLine(&queue, UartTxFrameKind::Snapshot, new_snapshot,
                             sizeof(new_snapshot) - 1U));
  CHECK_EQ(2U, UartTxQueuedFrameCount(&queue));
  CHECK_EQ(1U, queue.coalesced_frames);

  char drained[256]{};
  const size_t length = drainUartQueue(&queue, 5U, drained, sizeof(drained));
  constexpr char expected[] =
      "{\"snapshot\":2}\r\n"
      "{\"cmdId\":\"menu-CTRL-02-boot-7\",\"status\":\"accepted\"}\r\n";
  CHECK_EQ(sizeof(expected) - 1U, length);
  CHECK_TRUE(std::memcmp(drained, expected, sizeof(expected) - 1U) == 0);
  CHECK_TRUE(std::strstr(drained, "menu-CTRL-02-boot-7") != nullptr);
}

void test_uart_tx_queue_full_policy_preserves_accepted_command_ids() {
  UartTxQueue queue{};
  InitUartTxQueue(&queue);
  constexpr const char* acknowledgements[] = {
      "{\"cmdId\":\"ack-1\"}", "{\"cmdId\":\"ack-2\"}",
      "{\"cmdId\":\"ack-3\"}", "{\"cmdId\":\"ack-4\"}",
      "{\"cmdId\":\"ack-5\"}",
  };
  for (size_t index = 0U; index < kUartTxQueueCapacity; ++index) {
    CHECK_EQ(UartTxEnqueueResult::Queued,
             EnqueueUartTxLine(&queue, UartTxFrameKind::Acknowledgement,
                               acknowledgements[index],
                               std::strlen(acknowledgements[index])));
  }
  CHECK_EQ(UartTxEnqueueResult::Full,
           EnqueueUartTxLine(&queue, UartTxFrameKind::Acknowledgement,
                             acknowledgements[kUartTxQueueCapacity],
                             std::strlen(
                                 acknowledgements[kUartTxQueueCapacity])));
  CHECK_EQ(1U, queue.dropped_frames);
  CHECK_EQ(kUartTxQueueCapacity, UartTxQueuedFrameCount(&queue));

  char drained[256]{};
  const size_t length = drainUartQueue(&queue, 3U, drained, sizeof(drained));
  CHECK_TRUE(length != 0U);
  for (size_t index = 0U; index < kUartTxQueueCapacity; ++index) {
    CHECK_TRUE(std::strstr(drained, acknowledgements[index]) != nullptr);
  }
  CHECK_TRUE(std::strstr(drained,
                         acknowledgements[kUartTxQueueCapacity]) == nullptr);
}

void test_uart_tx_queue_ack_evicts_stale_snapshot_when_full() {
  UartTxQueue queue{};
  InitUartTxQueue(&queue);
  constexpr char snapshot[] = "{\"snapshot\":1}";
  constexpr char time_sync[] = "{\"time\":1}";
  constexpr char ack1[] = "{\"cmdId\":\"ack-1\"}";
  constexpr char ack2[] = "{\"cmdId\":\"ack-2\"}";
  constexpr char ack3[] = "{\"cmdId\":\"ack-3\"}";
  CHECK_EQ(UartTxEnqueueResult::Queued,
           EnqueueUartTxLine(&queue, UartTxFrameKind::Snapshot, snapshot,
                             sizeof(snapshot) - 1U));
  CHECK_EQ(UartTxEnqueueResult::Queued,
           EnqueueUartTxLine(&queue, UartTxFrameKind::TimeSync, time_sync,
                             sizeof(time_sync) - 1U));
  CHECK_EQ(UartTxEnqueueResult::Queued,
           EnqueueUartTxLine(&queue, UartTxFrameKind::Acknowledgement, ack1,
                             sizeof(ack1) - 1U));
  CHECK_EQ(UartTxEnqueueResult::Queued,
           EnqueueUartTxLine(&queue, UartTxFrameKind::Acknowledgement, ack2,
                             sizeof(ack2) - 1U));
  CHECK_EQ(kUartTxQueueCapacity, UartTxQueuedFrameCount(&queue));

  // A full queue drops the lowest-priority frame to admit an acknowledgement:
  // the coalesced snapshot is evicted and every command id survives.
  CHECK_EQ(UartTxEnqueueResult::Queued,
           EnqueueUartTxLine(&queue, UartTxFrameKind::Acknowledgement, ack3,
                             sizeof(ack3) - 1U));
  CHECK_EQ(kUartTxQueueCapacity, UartTxQueuedFrameCount(&queue));
  CHECK_EQ(1U, queue.dropped_frames);

  char drained[256]{};
  const size_t length = drainUartQueue(&queue, 3U, drained, sizeof(drained));
  CHECK_TRUE(length != 0U);
  CHECK_TRUE(std::strstr(drained, "time") != nullptr);
  CHECK_TRUE(std::strstr(drained, "ack-1") != nullptr);
  CHECK_TRUE(std::strstr(drained, "ack-2") != nullptr);
  CHECK_TRUE(std::strstr(drained, "ack-3") != nullptr);
  CHECK_TRUE(std::strstr(drained, "snapshot") == nullptr);
}

void test_normalization_preserves_every_menu_field() {
  char output[kUartLineLimit + 1U]{};
  size_t written = 99U;
  CHECK_EQ(RouteResult::Ok,
           NormalizeMenuCommand(kValidMenu, sizeof(kValidMenu) - 1U, kNowMs,
                                output, sizeof(output), &written));
  CHECK_EQ(sizeof(kExpectedNormalized) - 1U, written);
  CHECK_TRUE(std::strcmp(output, kExpectedNormalized) == 0);
}

void test_normalization_rejects_missing_future_expired_and_oversized_input() {
  const char missing[] = "{\"schema\":\"ut.menu.command.v1\"}";
  const char future[] =
      "{\"schema\":\"ut.menu.command.v1\",\"cmdId\":\"menu-1\"," \
      "\"target\":\"CTRL-01\",\"action\":\"fan1_duty\",\"value\":30," \
      "\"createdAtMs\":1704067220001,\"ttlMs\":10000}";
  char output[kUartLineLimit + 1U] = {'x'};
  size_t written = 99U;
  CHECK_EQ(RouteResult::InvalidPayload,
           NormalizeMenuCommand(missing, sizeof(missing) - 1U, kNowMs,
                                output, sizeof(output), &written));
  CHECK_EQ(0U, written);
  CHECK_EQ('\0', output[0]);
  CHECK_EQ(RouteResult::Expired,
           NormalizeMenuCommand(future, sizeof(future) - 1U, kNowMs,
                                output, sizeof(output), &written));
  CHECK_EQ(RouteResult::Expired,
           NormalizeMenuCommand(kValidMenu, sizeof(kValidMenu) - 1U,
                                1704067229000ULL, output, sizeof(output), &written));
  char oversized[kUartLineLimit + 2U];
  std::memset(oversized, 'x', sizeof(oversized));
  CHECK_EQ(RouteResult::TooLarge,
           NormalizeMenuCommand(oversized, sizeof(oversized), kNowMs,
                                output, sizeof(output), &written));

  char zero_capacity_sentinel = 'x';
  written = 99U;
  CHECK_EQ(RouteResult::OutputTooSmall,
           NormalizeMenuCommand(kValidMenu, sizeof(kValidMenu) - 1U, kNowMs,
                                &zero_capacity_sentinel, 0U, &written));
  CHECK_EQ('x', zero_capacity_sentinel);
  CHECK_EQ(0U, written);
}

void test_ctrl02_serial_menu_has_one_safe_publish_route() {
  RouteOutput output{};
  CHECK_EQ(RouteResult::Ok,
           RouteSerialLine(Role::Ctrl02, kValidMenu, sizeof(kValidMenu) - 1U,
                           kNowMs, &output));
  CHECK_EQ(OutputKind::MqttPublish, output.kind);
  CHECK_TRUE(std::strcmp(output.topic, "ut/v1/CTRL-01/cmd/menu") == 0);
  CHECK_TRUE(std::strcmp(output.payload, kValidMenu) == 0);

  CHECK_EQ(RouteResult::WrongRole,
           RouteSerialLine(Role::Ctrl01, kValidMenu, sizeof(kValidMenu) - 1U,
                           kNowMs, &output));
  CHECK_EQ(OutputKind::None, output.kind);
  CHECK_EQ(RouteResult::InvalidPayload,
           RouteSerialLine(Role::Ctrl02, kAck, sizeof(kAck) - 1U, kNowMs,
                           &output));
}

void test_ctrl02_aggregates_telemetry_into_complete_bounded_snapshot() {
  TelemetryAccumulator accumulator{};
  InitTelemetryAccumulator(&accumulator);
  RouteOutput output{};
  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            kTelemetry, sizeof(kTelemetry) - 1U, kNowMs,
                            &accumulator, &output));
  CHECK_EQ(OutputKind::UartLine, output.kind);
  CHECK_TRUE(output.payload_length <= kUartLineLimit);
  ScreenSnapshot snapshot{};
  CHECK_EQ(Result::Ok,
           ParseSnapshot(output.payload, output.payload_length, kNowMs,
                         &snapshot));
  CHECK_EQ(77U, snapshot.sequence);
  CHECK_EQ(2234, snapshot.temperature.value);
  CHECK_EQ(5210, snapshot.humidity.value);
  CHECK_EQ(20900, snapshot.oxygen.value);
  CHECK_EQ(Quality::Invalid, snapshot.oxygen.quality);
  CHECK_EQ(12, snapshot.methane.value);
  CHECK_EQ(4, snapshot.carbon_monoxide.value);
  CHECK_EQ(1, snapshot.smoke.value);
  CHECK_EQ(1, snapshot.water.value);
  CHECK_TRUE(snapshot.connectivity.node_a_online);
  CHECK_TRUE(snapshot.connectivity.mqtt_online);
  CHECK_EQ(AlarmSeverity::Critical, snapshot.alarm_severity);

  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            kFan1Telemetry, sizeof(kFan1Telemetry) - 1U,
                            kNowMs + 1U, &accumulator, &output));
  CHECK_EQ(Result::Ok,
           ParseSnapshot(output.payload, output.payload_length, kNowMs + 1U,
                         &snapshot));
  CHECK_EQ(11900U, snapshot.fans[0].voltage_mv);
  CHECK_EQ(320U, snapshot.fans[0].current_ma);
  CHECK_EQ(2400U, snapshot.fans[0].actual_rpm);
  CHECK_EQ(60U, snapshot.fans[0].target_duty_percent);
  CHECK_TRUE(snapshot.fans[0].running);
  CHECK_TRUE(snapshot.actuators.relay_on);

  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            kFan2Telemetry, sizeof(kFan2Telemetry) - 1U,
                            kNowMs + 2U, &accumulator, &output));
  CHECK_EQ(Result::Ok,
           ParseSnapshot(output.payload, output.payload_length, kNowMs + 2U,
                         &snapshot));
  CHECK_EQ(30U, snapshot.fans[1].target_duty_percent);
  CHECK_EQ(11800U, snapshot.fans[1].voltage_mv);
  CHECK_EQ(280U, snapshot.fans[1].current_ma);
  CHECK_EQ(1600U, snapshot.fans[1].actual_rpm);
  CHECK_EQ(2234, snapshot.temperature.value);
}

void test_ctrl02_forwards_only_valid_ack_and_preserves_result() {
  TelemetryAccumulator accumulator{};
  InitTelemetryAccumulator(&accumulator);
  RouteOutput output{};
  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/cmd_ack", kAck,
                            sizeof(kAck) - 1U, kNowMs, &accumulator, &output));
  CHECK_EQ(OutputKind::UartLine, output.kind);
  CommandAck ack{};
  CHECK_EQ(Result::Ok,
           ParseCommandAck(output.payload, output.payload_length, &ack));
  CHECK_TRUE(std::strcmp(ack.command_id, "menu-CTRL-02-7-42") == 0);
  CHECK_EQ(AckStatus::Accepted, ack.status);
  CHECK_EQ(60, ack.applied_value);
  CHECK_TRUE(std::strcmp(ack.reason, "fan_pwm_set") == 0);

  const char malformed[] = "{\"schema\":\"ut.command.ack.v1\"}";
  CHECK_EQ(RouteResult::InvalidPayload,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/cmd_ack",
                            malformed, sizeof(malformed) - 1U, kNowMs,
                            &accumulator, &output));
  CHECK_EQ(OutputKind::None, output.kind);
}

void test_roles_reject_wrong_topics_without_crosstalk() {
  TelemetryAccumulator accumulator{};
  InitTelemetryAccumulator(&accumulator);
  RouteOutput output{};
  CHECK_EQ(RouteResult::WrongTopic,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-02/telemetry",
                            kTelemetry, sizeof(kTelemetry) - 1U, kNowMs,
                            &accumulator, &output));
  CHECK_EQ(OutputKind::None, output.kind);
  CHECK_EQ(RouteResult::WrongTopic,
           RouteMqttMessage(Role::Ctrl01, "ut/v1/CTRL-01/telemetry",
                            kTelemetry, sizeof(kTelemetry) - 1U, kNowMs,
                            &accumulator, &output));
  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(Role::Ctrl01, "ut/v1/CTRL-01/cmd/menu",
                            kValidMenu, sizeof(kValidMenu) - 1U, kNowMs,
                            &accumulator, &output));
  CHECK_EQ(OutputKind::UartCommand, output.kind);
  CHECK_TRUE(std::strcmp(output.payload, kExpectedNormalized) == 0);
}

void test_malformed_stale_and_large_telemetry_do_not_mutate_snapshot() {
  TelemetryAccumulator accumulator{};
  InitTelemetryAccumulator(&accumulator);
  RouteOutput output{};
  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            kTelemetry, sizeof(kTelemetry) - 1U, kNowMs,
                            &accumulator, &output));
  const TelemetryAccumulator before = accumulator;
  const char malformed[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":78,\"readings\":[";
  CHECK_EQ(RouteResult::InvalidPayload,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            malformed, sizeof(malformed) - 1U, kNowMs + 1U,
                            &accumulator, &output));
  CHECK_TRUE(std::memcmp(&before, &accumulator, sizeof(before)) == 0);

  const char concatenated_root[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":78,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":25,"
      "\"unit\":\"degC\",\"quality\":\"good\"}]}{}";
  CHECK_EQ(RouteResult::InvalidPayload,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            concatenated_root, sizeof(concatenated_root) - 1U,
                            kNowMs + 1U, &accumulator, &output));
  CHECK_TRUE(std::memcmp(&before, &accumulator, sizeof(before)) == 0);

  const char stray_token[] =
      "{x\"schema\":\"ut.telemetry.v1\",\"seq\":78,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":25,"
      "\"unit\":\"degC\",\"quality\":\"good\"}]}";
  CHECK_EQ(RouteResult::InvalidPayload,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            stray_token, sizeof(stray_token) - 1U,
                            kNowMs + 1U, &accumulator, &output));
  CHECK_TRUE(std::memcmp(&before, &accumulator, sizeof(before)) == 0);

  const char repeated_top_level_comma[] =
      "{\"schema\":\"ut.telemetry.v1\",,\"seq\":78,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":25,"
      "\"unit\":\"degC\",\"quality\":\"good\"}]}";
  CHECK_EQ(RouteResult::InvalidPayload,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            repeated_top_level_comma,
                            sizeof(repeated_top_level_comma) - 1U,
                            kNowMs + 1U, &accumulator, &output));
  CHECK_TRUE(std::memcmp(&before, &accumulator, sizeof(before)) == 0);

  const char wrong_asset[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":78,\"readings\":["
      "{\"assetCode\":\"FAN-01\",\"metric\":\"smoke.alarm\",\"value\":1,"
      "\"unit\":\"bool\",\"quality\":\"good\"}]}";
  CHECK_EQ(RouteResult::InvalidPayload,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            wrong_asset, sizeof(wrong_asset) - 1U, kNowMs + 1U,
                            &accumulator, &output));
  CHECK_TRUE(std::memcmp(&before, &accumulator, sizeof(before)) == 0);

  const char repeated_comma[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":78,\"readings\":[,"
      "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":25,"
      "\"unit\":\"degC\",\"quality\":\"good\"}]}";
  CHECK_EQ(RouteResult::InvalidPayload,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            repeated_comma, sizeof(repeated_comma) - 1U,
                            kNowMs + 1U, &accumulator, &output));
  CHECK_TRUE(std::memcmp(&before, &accumulator, sizeof(before)) == 0);

  const char invalid_known_reading[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":78,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":250,"
      "\"unit\":\"degC\",\"quality\":\"good\"},"
      "{\"assetCode\":\"ENV-01\",\"metric\":\"humidity\",\"value\":50,"
      "\"unit\":\"%RH\",\"quality\":\"good\"}]}";
  CHECK_EQ(RouteResult::InvalidPayload,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            invalid_known_reading,
                            sizeof(invalid_known_reading) - 1U, kNowMs + 1U,
                            &accumulator, &output));
  CHECK_TRUE(std::memcmp(&before, &accumulator, sizeof(before)) == 0);

  const char stale[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":76,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":25,"
      "\"unit\":\"degC\",\"quality\":\"good\"}]}";
  CHECK_EQ(RouteResult::Stale,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry", stale,
                            sizeof(stale) - 1U, kNowMs + 2U, &accumulator,
                            &output));
  CHECK_TRUE(std::memcmp(&before, &accumulator, sizeof(before)) == 0);

  char oversized[kTransportPayloadLimit + 2U];
  std::memset(oversized, 'x', sizeof(oversized));
  CHECK_EQ(RouteResult::TooLarge,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            oversized, sizeof(oversized), kNowMs + 3U,
                            &accumulator, &output));
  CHECK_TRUE(std::memcmp(&before, &accumulator, sizeof(before)) == 0);
}

void test_sequence_gate_rejects_duplicates_and_allows_explicit_new_session() {
  constexpr char sequence_100[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":100,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":25,"
      "\"unit\":\"degC\",\"quality\":\"good\"}]}";
  constexpr char sequence_50[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":50,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":24,"
      "\"unit\":\"degC\",\"quality\":\"good\"}]}";
  TelemetryAccumulator accumulator{};
  InitTelemetryAccumulator(&accumulator);
  RouteOutput output{};
  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            sequence_100, sizeof(sequence_100) - 1U, kNowMs,
                            &accumulator, &output));
  const TelemetryAccumulator accepted = accumulator;
  CHECK_EQ(RouteResult::Stale,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            sequence_100, sizeof(sequence_100) - 1U,
                            kNowMs + 1U, &accumulator, &output));
  CHECK_TRUE(std::memcmp(&accepted, &accumulator, sizeof(accepted)) == 0);

  BeginTelemetrySession(&accumulator);
  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            sequence_50, sizeof(sequence_50) - 1U,
                            kNowMs + 2U, &accumulator, &output));
  CHECK_EQ(50U, accumulator.last_sequence);
  CHECK_EQ(RouteResult::Stale,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            sequence_50, sizeof(sequence_50) - 1U,
                            kNowMs + 3U, &accumulator, &output));
}

void test_sequence_gate_recovers_low_restart_sequence_after_stale_window() {
  constexpr char sequence_100[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":100,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":25,"
      "\"unit\":\"degC\",\"quality\":\"good\"}]}";
  constexpr char restarted_sequence[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":1,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"humidity\",\"value\":45,"
      "\"unit\":\"%RH\",\"quality\":\"good\"}]}";
  TelemetryAccumulator accumulator{};
  InitTelemetryAccumulator(&accumulator);
  RouteOutput output{};
  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            sequence_100, sizeof(sequence_100) - 1U, kNowMs,
                            &accumulator, &output));
  const TelemetryAccumulator accepted = accumulator;
  CHECK_EQ(RouteResult::Stale,
           RouteMqttMessage(
               Role::Ctrl02, "ut/v1/CTRL-01/telemetry", restarted_sequence,
               sizeof(restarted_sequence) - 1U,
               kNowMs + kSequenceRestartSilenceMs - 1U, &accumulator,
               &output));
  CHECK_TRUE(std::memcmp(&accepted, &accumulator, sizeof(accepted)) == 0);
  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(
               Role::Ctrl02, "ut/v1/CTRL-01/telemetry", restarted_sequence,
               sizeof(restarted_sequence) - 1U,
               kNowMs + kSequenceRestartSilenceMs, &accumulator, &output));
  CHECK_EQ(1U, accumulator.last_sequence);
  CHECK_EQ(Quality::Unknown, accumulator.snapshot.temperature.quality);
  CHECK_EQ(Quality::Valid, accumulator.snapshot.humidity.quality);
}

void test_sequence_gate_recovers_any_rollback_after_long_silence() {
  constexpr char sequence_100[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":100,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":25,"
      "\"unit\":\"degC\",\"quality\":\"good\"}]}";
  constexpr char sequence_50[] =
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":50,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"humidity\",\"value\":45,"
      "\"unit\":\"%RH\",\"quality\":\"good\"}]}";
  TelemetryAccumulator accumulator{};
  InitTelemetryAccumulator(&accumulator);
  RouteOutput output{};
  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(Role::Ctrl02, "ut/v1/CTRL-01/telemetry",
                            sequence_100, sizeof(sequence_100) - 1U, kNowMs,
                            &accumulator, &output));
  CHECK_EQ(RouteResult::Ok,
           RouteMqttMessage(
               Role::Ctrl02, "ut/v1/CTRL-01/telemetry", sequence_50,
               sizeof(sequence_50) - 1U,
               kNowMs + kSequenceResyncSilenceMs, &accumulator, &output));
  CHECK_EQ(50U, accumulator.last_sequence);
  CHECK_EQ(Quality::Unknown, accumulator.snapshot.temperature.quality);
  CHECK_EQ(Quality::Valid, accumulator.snapshot.humidity.quality);
}

void test_ntp_configuration_is_once_per_wifi_association() {
  NtpAssociationState association{};
  InitNtpAssociationState(&association);
  CHECK_TRUE(!ShouldConfigureNtp(&association, false));
  CHECK_TRUE(ShouldConfigureNtp(&association, true));
  CHECK_TRUE(!ShouldConfigureNtp(&association, true));
  CHECK_TRUE(!ShouldConfigureNtp(&association, false));
  CHECK_TRUE(ShouldConfigureNtp(&association, true));
  CHECK_TRUE(!ShouldConfigureNtp(&association, true));
}

void test_time_sync_is_immediate_periodic_valid_and_wrap_safe() {
  TimeSyncSchedule schedule{};
  InitTimeSyncSchedule(&schedule);
  char output[kUartLineLimit + 1U] = {'x'};
  size_t written = 99U;
  CHECK_EQ(TimeEmitResult::InvalidEpoch,
           BuildDueTimeSync(&schedule, 100U, kMinEpochSeconds - 1ULL, output,
                            sizeof(output), &written));
  CHECK_EQ(0U, written);
  CHECK_EQ('\0', output[0]);
  CHECK_EQ(TimeEmitResult::Emitted,
           BuildDueTimeSync(&schedule, 100U, kMinEpochSeconds, output,
                            sizeof(output), &written));
  TimeSync sync{};
  CHECK_EQ(Result::Ok, ParseTimeSync(output, written, &sync));
  CHECK_EQ(0U, sync.sequence);
  CHECK_EQ(TimeEmitResult::NotDue,
           BuildDueTimeSync(&schedule, 100U + kTimeSyncPeriodMs - 1U,
                            kMinEpochSeconds + 599ULL, output,
                            sizeof(output), &written));
  CHECK_EQ(TimeEmitResult::Emitted,
           BuildDueTimeSync(&schedule, 100U + kTimeSyncPeriodMs,
                            kMinEpochSeconds + 600ULL, output,
                            sizeof(output), &written));
  CHECK_EQ(Result::Ok, ParseTimeSync(output, written, &sync));
  CHECK_EQ(1U, sync.sequence);

  InitTimeSyncSchedule(&schedule);
  constexpr uint32_t near_wrap = 0xfffffff0U;
  CHECK_EQ(TimeEmitResult::Emitted,
           BuildDueTimeSync(&schedule, near_wrap, kMinEpochSeconds, output,
                            sizeof(output), &written));
  CHECK_EQ(TimeEmitResult::NotDue,
           BuildDueTimeSync(&schedule, near_wrap + kTimeSyncPeriodMs - 1U,
                            kMinEpochSeconds + 599ULL, output,
                            sizeof(output), &written));
  CHECK_EQ(TimeEmitResult::Emitted,
           BuildDueTimeSync(&schedule, near_wrap + kTimeSyncPeriodMs,
                            kMinEpochSeconds + 600ULL, output,
                            sizeof(output), &written));
}

}  // namespace

int main() {
  test_role_routes_are_exact_and_idempotent();
  test_ctrl01_one_menu_delivery_produces_one_uart_command();
  test_subsecond_clock_accepts_node_b_command_from_same_second();
  test_uart_tx_queue_handles_long_line_and_backpressure_without_blocking();
  test_uart_tx_queue_coalesces_snapshots_and_never_mixes_frames();
  test_uart_tx_queue_full_policy_preserves_accepted_command_ids();
  test_uart_tx_queue_ack_evicts_stale_snapshot_when_full();
  test_normalization_preserves_every_menu_field();
  test_normalization_rejects_missing_future_expired_and_oversized_input();
  test_ctrl02_serial_menu_has_one_safe_publish_route();
  test_ctrl02_aggregates_telemetry_into_complete_bounded_snapshot();
  test_ctrl02_forwards_only_valid_ack_and_preserves_result();
  test_roles_reject_wrong_topics_without_crosstalk();
  test_malformed_stale_and_large_telemetry_do_not_mutate_snapshot();
  test_sequence_gate_rejects_duplicates_and_allows_explicit_new_session();
  test_sequence_gate_recovers_low_restart_sequence_after_stale_window();
  test_sequence_gate_recovers_any_rollback_after_long_silence();
  test_ntp_configuration_is_once_per_wifi_association();
  test_time_sync_is_immediate_periodic_valid_and_wrap_safe();
  if (failures == 0) std::puts("screen_routing tests passed");
  return failures == 0 ? 0 : 1;
}
