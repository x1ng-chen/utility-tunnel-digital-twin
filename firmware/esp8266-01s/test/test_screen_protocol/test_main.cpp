#include <cstdint>
#include <cstdio>
#include <cstring>

#include "screen_protocol.h"

namespace {
using namespace screen_protocol;

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

constexpr uint64_t kFreshNowMs = kMinEpochSeconds * 1000ULL + 20000ULL;

Reading reading(int32_t value, Quality quality = Quality::Valid) {
  Reading result{};
  result.value = value;
  result.sampled_at_ms = kFreshNowMs - 1000ULL;
  result.quality = quality;
  return result;
}

ScreenSnapshot validSnapshot() {
  ScreenSnapshot value{};
  std::strcpy(value.source, "CTRL-01");
  value.generated_at_ms = kFreshNowMs - 100ULL;
  value.sequence = 77U;
  value.temperature = reading(2234);
  value.humidity = reading(5210);
  value.oxygen = reading(20900);
  value.methane = reading(12);
  value.carbon_monoxide = reading(4);
  value.smoke = reading(0);
  value.water = reading(17);
  value.flame = reading(0);
  value.alarm_severity = AlarmSeverity::Warning;
  value.warning_sources = 0x08U;
  value.critical_sources = 0U;
  value.fans[0] = FanSnapshot{60U, true, 2400U, 11900U, 320U,
                              kFreshNowMs - 500ULL, Quality::Valid};
  value.fans[1] = FanSnapshot{30U, true, 1600U, 11850U, 280U,
                              kFreshNowMs - 500ULL, Quality::Valid};
  value.actuators = ActuatorSnapshot{true, 4U, 75U, true, false};
  value.connectivity = ConnectivitySnapshot{true, true, true, true,
                                             kFreshNowMs - 200ULL};
  std::strcpy(value.last_command.command_id, "menu-CTRL-02-7-42");
  value.last_command.accepted = true;
  value.last_command.complete = true;
  value.last_command.completed_at_ms = kFreshNowMs - 300ULL;
  return value;
}

void retimeSnapshot(ScreenSnapshot* value, uint64_t generated_at_ms) {
  value->generated_at_ms = generated_at_ms;
  value->temperature.sampled_at_ms = generated_at_ms;
  value->humidity.sampled_at_ms = generated_at_ms;
  value->oxygen.sampled_at_ms = generated_at_ms;
  value->methane.sampled_at_ms = generated_at_ms;
  value->carbon_monoxide.sampled_at_ms = generated_at_ms;
  value->smoke.sampled_at_ms = generated_at_ms;
  value->water.sampled_at_ms = generated_at_ms;
  value->flame.sampled_at_ms = generated_at_ms;
  value->fans[0].sampled_at_ms = generated_at_ms;
  value->fans[1].sampled_at_ms = generated_at_ms;
  value->connectivity.updated_at_ms = generated_at_ms;
  value->last_command.completed_at_ms = generated_at_ms;
}

MenuCommand validCommand() {
  MenuCommand value{};
  std::strcpy(value.command_id, "menu-CTRL-02-7-42");
  std::strcpy(value.target, "CTRL-01");
  value.action = CommandAction::Fan1Duty;
  value.value = 60U;
  value.created_at_ms = kFreshNowMs - 1000ULL;
  value.ttl_ms = 10000U;
  return value;
}

CommandAck validAck() {
  CommandAck value{};
  std::strcpy(value.command_id, "menu-CTRL-02-7-42");
  value.status = AckStatus::Accepted;
  std::strcpy(value.reason, "fan_pwm_set");
  value.applied_value = 60;
  value.completed_at_ms = kFreshNowMs - 50ULL;
  return value;
}

TimeSync validTimeSync() {
  TimeSync value{};
  value.source = TimeSource::Ntp;
  value.state = TimeState::Synchronized;
  value.epoch_seconds = kMinEpochSeconds;
  value.sequence = 8U;
  return value;
}

void test_snapshot_round_trip_is_complete_and_canonical() {
  const ScreenSnapshot input = validSnapshot();
  ScreenSnapshot output{};
  char encoded[kUartLineLimit + 1U]{};
  char rebuilt[kUartLineLimit + 1U]{};
  size_t length = 0U;
  size_t rebuilt_length = 0U;

  CHECK_EQ(Result::Ok, BuildSnapshot(input, encoded, sizeof(encoded), &length));
  CHECK_TRUE(length > 0U && length <= kUartLineLimit);
  CHECK_TRUE(std::strstr(encoded, "\"schema\":\"ut.screen.snapshot.v1\"") != nullptr);
  CHECK_TRUE(std::strstr(encoded, "\"carbonMonoxide\"") != nullptr);
  CHECK_EQ(Result::Ok,
           ParseSnapshot(encoded, length, kFreshNowMs, &output));
  CHECK_EQ(77U, output.sequence);
  CHECK_EQ(2234, output.temperature.value);
  CHECK_EQ(20900, output.oxygen.value);
  CHECK_EQ(12, output.methane.value);
  CHECK_EQ(60U, output.fans[0].target_duty_percent);
  CHECK_EQ(280U, output.fans[1].current_ma);
  CHECK_EQ(4U, output.actuators.led_mode);
  CHECK_TRUE(output.connectivity.mqtt_online);
  CHECK_TRUE(output.last_command.accepted);
  CHECK_TRUE(std::strcmp(output.last_command.command_id, input.last_command.command_id) == 0);
  CHECK_EQ(Result::Ok, BuildSnapshot(output, rebuilt, sizeof(rebuilt), &rebuilt_length));
  CHECK_EQ(length, rebuilt_length);
  CHECK_TRUE(std::memcmp(encoded, rebuilt, length + 1U) == 0);
}

void test_snapshot_rejects_missing_unknown_malformed_wrong_type_and_nonfinite() {
  ScreenSnapshot output{};
  const char missing[] = "{\"schema\":\"ut.screen.snapshot.v1\"}";
  const char unknown[] = "{\"schema\":\"ut.screen.snapshot.v2\"}";
  const char malformed[] = "{\"schema\":\"ut.screen.snapshot.v1\"";
  const char wrong_type[] =
      "{\"schema\":1,\"source\":\"CTRL-01\"}";
  const char nonfinite[] =
      "{\"schema\":\"ut.screen.snapshot.v1\",\"source\":\"CTRL-01\"," \
      "\"generatedAtMs\":1704067220000,\"seq\":1,\"sensors\":{" \
      "\"temperature\":[NaN,1704067219000,1]}}";

  CHECK_TRUE(ParseSnapshot(missing, sizeof(missing) - 1U, kFreshNowMs, &output) != Result::Ok);
  CHECK_EQ(Result::UnknownSchema,
           ParseSnapshot(unknown, sizeof(unknown) - 1U, kFreshNowMs, &output));
  CHECK_EQ(Result::MalformedJson,
           ParseSnapshot(malformed, sizeof(malformed) - 1U, kFreshNowMs, &output));
  CHECK_EQ(Result::WrongType,
           ParseSnapshot(wrong_type, sizeof(wrong_type) - 1U, kFreshNowMs, &output));
  CHECK_TRUE(ParseSnapshot(nonfinite, sizeof(nonfinite) - 1U, kFreshNowMs, &output) != Result::Ok);

  char encoded[kUartLineLimit + 1U]{};
  size_t length = 0U;
  CHECK_EQ(Result::Ok, BuildSnapshot(validSnapshot(), encoded, sizeof(encoded), &length));
  char trailing[kUartLineLimit + 8U]{};
  std::memcpy(trailing, encoded, length);
  std::memcpy(trailing + length, "false", 6U);
  CHECK_EQ(Result::TrailingData,
           ParseSnapshot(trailing, length + 5U, kFreshNowMs, &output));
}

void test_snapshot_enforces_bounds_and_freshness() {
  char encoded[kUartLineLimit + 1U]{};
  size_t length = 0U;
  ScreenSnapshot output{};
  ScreenSnapshot snapshot = validSnapshot();

  snapshot.humidity.value = 10001;
  CHECK_EQ(Result::OutOfRange, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  snapshot = validSnapshot();
  snapshot.fans[0].target_duty_percent = 45U;
  CHECK_EQ(Result::OutOfRange, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  snapshot = validSnapshot();
  snapshot.actuators.led_brightness_percent = 60U;
  CHECK_EQ(Result::OutOfRange, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  snapshot = validSnapshot();
  retimeSnapshot(&snapshot, kFreshNowMs - kSnapshotMaxAgeMs);
  CHECK_EQ(Result::Ok, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  CHECK_EQ(Result::Ok, ParseSnapshot(encoded, length, kFreshNowMs, &output));
  retimeSnapshot(&snapshot, snapshot.generated_at_ms - 1U);
  CHECK_EQ(Result::Ok, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  CHECK_EQ(Result::Stale, ParseSnapshot(encoded, length, kFreshNowMs, &output));
  snapshot = validSnapshot();
  retimeSnapshot(&snapshot, kFreshNowMs + 1U);
  CHECK_EQ(Result::Ok, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  CHECK_EQ(Result::Stale, ParseSnapshot(encoded, length, kFreshNowMs, &output));
}

void test_menu_command_preserves_39_character_id_and_decodes_escapes() {
  MenuCommand input = validCommand();
  MenuCommand output{};
  char encoded[kUartLineLimit + 1U]{};
  char rebuilt[kUartLineLimit + 1U]{};
  size_t length = 0U;
  size_t rebuilt_length = 0U;
  std::strcpy(input.command_id, "123456789012345678901234567890123456789");

  CHECK_EQ(Result::Ok, BuildMenuCommand(input, encoded, sizeof(encoded), &length));
  CHECK_EQ(Result::Ok, ParseMenuCommand(encoded, length, kFreshNowMs, &output));
  CHECK_EQ(39U, std::strlen(output.command_id));
  CHECK_TRUE(std::strcmp(output.command_id, input.command_id) == 0);
  CHECK_EQ(Result::Ok, BuildMenuCommand(output, rebuilt, sizeof(rebuilt), &rebuilt_length));
  CHECK_TRUE(std::strcmp(encoded, rebuilt) == 0);

  const char escaped[] =
      "{\"schema\":\"ut.menu.command.v1\",\"cmdId\":\"menu-\\u0043TRL-02-7-42\"," \
      "\"target\":\"CTRL-01\",\"action\":\"fan1_duty\",\"value\":60," \
      "\"createdAtMs\":1704067219000,\"ttlMs\":10000}";
  CHECK_EQ(Result::Ok,
           ParseMenuCommand(escaped, sizeof(escaped) - 1U, kFreshNowMs, &output));
  CHECK_TRUE(std::strcmp(output.command_id, "menu-CTRL-02-7-42") == 0);
}

void test_menu_command_rejects_identifier_target_action_value_and_ttl_boundaries() {
  char encoded[kUartLineLimit + 1U]{};
  size_t length = 0U;
  MenuCommand output{};
  MenuCommand command = validCommand();

  std::strcpy(command.command_id, "1234567890123456789012345678901234567890");
  CHECK_EQ(Result::InvalidIdentifier,
           BuildMenuCommand(command, encoded, sizeof(encoded), &length));
  command = validCommand();
  std::strcpy(command.target, "CTRL-02");
  CHECK_EQ(Result::InvalidTarget,
           BuildMenuCommand(command, encoded, sizeof(encoded), &length));

  const CommandAction actions[] = {
      CommandAction::Fan1Duty, CommandAction::FansBothStart,
      CommandAction::FansAllStop, CommandAction::Fan2Duty,
      CommandAction::LedMode, CommandAction::LedBrightness,
      CommandAction::BuzzerTest, CommandAction::BuzzerMute,
      CommandAction::BuzzerRestore,
  };
  const uint8_t values[] = {100U, 0U, 0U, 30U, 7U, 100U, 0U, 0U, 0U};
  for (size_t index = 0U; index < sizeof(actions) / sizeof(actions[0]); ++index) {
    command = validCommand();
    command.action = actions[index];
    command.value = values[index];
    CHECK_EQ(Result::Ok, BuildMenuCommand(command, encoded, sizeof(encoded), &length));
    CHECK_EQ(Result::Ok, ParseMenuCommand(encoded, length, kFreshNowMs, &output));
  }

  command = validCommand();
  command.value = 45U;
  CHECK_EQ(Result::OutOfRange, BuildMenuCommand(command, encoded, sizeof(encoded), &length));
  command = validCommand();
  command.action = CommandAction::LedMode;
  command.value = 8U;
  CHECK_EQ(Result::OutOfRange, BuildMenuCommand(command, encoded, sizeof(encoded), &length));
  command.action = CommandAction::LedBrightness;
  command.value = 60U;
  CHECK_EQ(Result::OutOfRange, BuildMenuCommand(command, encoded, sizeof(encoded), &length));
  command.action = CommandAction::BuzzerTest;
  command.value = 1U;
  CHECK_EQ(Result::OutOfRange, BuildMenuCommand(command, encoded, sizeof(encoded), &length));

  command = validCommand();
  command.ttl_ms = 0U;
  CHECK_EQ(Result::OutOfRange, BuildMenuCommand(command, encoded, sizeof(encoded), &length));
  command.ttl_ms = kCommandMaxTtlMs + 1U;
  CHECK_EQ(Result::OutOfRange, BuildMenuCommand(command, encoded, sizeof(encoded), &length));
  command = validCommand();
  command.created_at_ms = kFreshNowMs - command.ttl_ms;
  CHECK_EQ(Result::Ok, BuildMenuCommand(command, encoded, sizeof(encoded), &length));
  CHECK_EQ(Result::Expired, ParseMenuCommand(encoded, length, kFreshNowMs, &output));
  command.created_at_ms = kFreshNowMs + 1U;
  CHECK_EQ(Result::Ok, BuildMenuCommand(command, encoded, sizeof(encoded), &length));
  CHECK_EQ(Result::Expired, ParseMenuCommand(encoded, length, kFreshNowMs, &output));

  const char ttl_overflow[] =
      "{\"schema\":\"ut.menu.command.v1\",\"cmdId\":\"menu-1\"," \
      "\"target\":\"CTRL-01\",\"action\":\"fan1_duty\",\"value\":30," \
      "\"createdAtMs\":1704067219000,\"ttlMs\":4294967296}";
  CHECK_EQ(Result::NumberOverflow,
           ParseMenuCommand(ttl_overflow, sizeof(ttl_overflow) - 1U,
                            kFreshNowMs, &output));
}

void test_ack_round_trip_preserves_result_and_escaped_reason() {
  const CommandAck input = validAck();
  CommandAck output{};
  char encoded[kUartLineLimit + 1U]{};
  char rebuilt[kUartLineLimit + 1U]{};
  size_t length = 0U;
  size_t rebuilt_length = 0U;

  CHECK_EQ(Result::Ok, BuildCommandAck(input, encoded, sizeof(encoded), &length));
  CHECK_EQ(Result::Ok, ParseCommandAck(encoded, length, &output));
  CHECK_EQ(AckStatus::Accepted, output.status);
  CHECK_EQ(60, output.applied_value);
  CHECK_TRUE(std::strcmp(input.command_id, output.command_id) == 0);
  CHECK_EQ(Result::Ok, BuildCommandAck(output, rebuilt, sizeof(rebuilt), &rebuilt_length));
  CHECK_TRUE(std::strcmp(encoded, rebuilt) == 0);

  const char escaped[] =
      "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"menu-1\"," \
      "\"status\":\"rejected\",\"reason\":\"safety\\u005flock\"," \
      "\"appliedValue\":0,\"completedAtMs\":1704067219950}";
  CHECK_EQ(Result::Ok, ParseCommandAck(escaped, sizeof(escaped) - 1U, &output));
  CHECK_EQ(AckStatus::Rejected, output.status);
  CHECK_TRUE(std::strcmp(output.reason, "safety_lock") == 0);
}

void test_ack_rejects_missing_or_oversized_id_and_unknown_status() {
  CommandAck output{};
  const char missing[] =
      "{\"schema\":\"ut.command.ack.v1\",\"status\":\"accepted\"," \
      "\"reason\":\"ok\",\"appliedValue\":0,\"completedAtMs\":1704067219950}";
  const char oversized[] =
      "{\"schema\":\"ut.command.ack.v1\"," \
      "\"cmdId\":\"1234567890123456789012345678901234567890\"," \
      "\"status\":\"accepted\",\"reason\":\"ok\",\"appliedValue\":0," \
      "\"completedAtMs\":1704067219950}";
  const char unknown[] =
      "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"menu-1\"," \
      "\"status\":\"maybe\",\"reason\":\"ok\",\"appliedValue\":0," \
      "\"completedAtMs\":1704067219950}";

  CHECK_TRUE(ParseCommandAck(missing, sizeof(missing) - 1U, &output) != Result::Ok);
  CHECK_EQ(Result::InvalidIdentifier,
           ParseCommandAck(oversized, sizeof(oversized) - 1U, &output));
  CHECK_EQ(Result::InvalidEnum,
           ParseCommandAck(unknown, sizeof(unknown) - 1U, &output));
}

void test_json_number_rejects_whitespace_after_minus() {
  CommandAck output{};
  const char invalid[] =
      "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"menu-1\"," \
      "\"status\":\"rejected\",\"reason\":\"invalid_value\"," \
      "\"appliedValue\":- 1,\"completedAtMs\":1704067219950}";
  CHECK_EQ(Result::MalformedJson,
           ParseCommandAck(invalid, sizeof(invalid) - 1U, &output));
}

void test_time_sync_round_trip_and_epoch_boundary() {
  TimeSync input = validTimeSync();
  TimeSync output{};
  char encoded[kUartLineLimit + 1U]{};
  char rebuilt[kUartLineLimit + 1U]{};
  size_t length = 0U;
  size_t rebuilt_length = 0U;

  CHECK_EQ(Result::Ok, BuildTimeSync(input, encoded, sizeof(encoded), &length));
  CHECK_EQ(Result::Ok, ParseTimeSync(encoded, length, &output));
  CHECK_EQ(kMinEpochSeconds, output.epoch_seconds);
  CHECK_EQ(TimeSource::Ntp, output.source);
  CHECK_EQ(TimeState::Synchronized, output.state);
  CHECK_EQ(Result::Ok, BuildTimeSync(output, rebuilt, sizeof(rebuilt), &rebuilt_length));
  CHECK_TRUE(std::strcmp(encoded, rebuilt) == 0);

  input.epoch_seconds = kMinEpochSeconds - 1ULL;
  CHECK_EQ(Result::OutOfRange, BuildTimeSync(input, encoded, sizeof(encoded), &length));
  const char bad_source[] =
      "{\"schema\":\"ut.time.sync.v1\",\"source\":\"gps\"," \
      "\"state\":\"synchronized\",\"epochSeconds\":1704067200,\"seq\":1}";
  CHECK_EQ(Result::InvalidEnum,
           ParseTimeSync(bad_source, sizeof(bad_source) - 1U, &output));
}

void test_uart_line_limit_and_output_buffer_are_exact() {
  MenuCommand command = validCommand();
  MenuCommand parsed{};
  char command_json[kUartLineLimit + 1U]{};
  size_t command_length = 0U;
  CHECK_EQ(Result::Ok,
           BuildMenuCommand(command, command_json, sizeof(command_json), &command_length));

  char exact[kUartLineLimit + 1U]{};
  std::memcpy(exact, command_json, command_length - 1U);
  std::memset(exact + command_length - 1U, ' ', kUartLineLimit - command_length);
  exact[kUartLineLimit - 1U] = '}';
  exact[kUartLineLimit] = '\0';
  CHECK_EQ(Result::Ok,
           ParseMenuCommand(exact, kUartLineLimit, kFreshNowMs, &parsed));

  char too_large[kUartLineLimit + 2U]{};
  std::memcpy(too_large, exact, kUartLineLimit - 1U);
  too_large[kUartLineLimit - 1U] = ' ';
  too_large[kUartLineLimit] = '}';
  CHECK_EQ(Result::TooLarge,
           ParseMenuCommand(too_large, kUartLineLimit + 1U,
                            kFreshNowMs, &parsed));

  char tiny[8] = {'x', 'x', 'x', 'x', 'x', 'x', 'x', '\0'};
  size_t written = 99U;
  CHECK_EQ(Result::OutputTooSmall,
           BuildMenuCommand(command, tiny, sizeof(tiny), &written));
  CHECK_EQ(0U, written);
  CHECK_EQ('\0', tiny[0]);
  CHECK_EQ(Result::OutputTooSmall,
           BuildSnapshot(validSnapshot(), tiny, sizeof(tiny), &written));
  CHECK_EQ(Result::OutputTooSmall,
           BuildCommandAck(validAck(), tiny, sizeof(tiny), &written));
  CHECK_EQ(Result::OutputTooSmall,
           BuildTimeSync(validTimeSync(), tiny, sizeof(tiny), &written));

  ScreenSnapshot largest = validSnapshot();
  retimeSnapshot(&largest, kFreshNowMs);
  largest.sequence = UINT32_MAX;
  largest.temperature.value = -5000;
  largest.humidity.value = 10000;
  largest.oxygen.value = 100000;
  largest.methane.value = 100000;
  largest.carbon_monoxide.value = 100000;
  largest.smoke.value = 4095;
  largest.water.value = 4095;
  largest.flame.value = 1;
  for (size_t index = 0U; index < 2U; ++index) {
    largest.fans[index].target_duty_percent = 100U;
    largest.fans[index].actual_rpm = 100000U;
    largest.fans[index].voltage_mv = 36000U;
    largest.fans[index].current_ma = 10000U;
  }
  largest.warning_sources = 0xffU;
  largest.critical_sources = 0xffU;
  std::strcpy(largest.last_command.command_id,
              "123456789012345678901234567890123456789");
  char largest_json[kUartLineLimit + 1U]{};
  size_t largest_length = 0U;
  CHECK_EQ(Result::Ok,
           BuildSnapshot(largest, largest_json, sizeof(largest_json),
                         &largest_length));
  CHECK_TRUE(largest_length <= kUartLineLimit);
}

}  // namespace

int main() {
  test_snapshot_round_trip_is_complete_and_canonical();
  test_snapshot_rejects_missing_unknown_malformed_wrong_type_and_nonfinite();
  test_snapshot_enforces_bounds_and_freshness();
  test_menu_command_preserves_39_character_id_and_decodes_escapes();
  test_menu_command_rejects_identifier_target_action_value_and_ttl_boundaries();
  test_ack_round_trip_preserves_result_and_escaped_reason();
  test_ack_rejects_missing_or_oversized_id_and_unknown_status();
  test_json_number_rejects_whitespace_after_minus();
  test_time_sync_round_trip_and_epoch_boundary();
  test_uart_line_limit_and_output_buffer_are_exact();
  if (failures == 0) std::puts("screen_protocol tests passed");
  return failures == 0 ? 0 : 1;
}
