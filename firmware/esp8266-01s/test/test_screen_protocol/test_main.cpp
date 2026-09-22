#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

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
constexpr uint64_t kExpectedMaxEpochSeconds = 4102444799ULL;
constexpr uint64_t kExpectedMaxEpochMilliseconds = 4102444799999ULL;

std::string replaceOnce(std::string value, const std::string& needle,
                        const std::string& replacement) {
  const size_t position = value.find(needle);
  CHECK_TRUE(position != std::string::npos);
  if (position != std::string::npos) value.replace(position, needle.size(), replacement);
  return value;
}

std::string replaceAll(std::string value, const std::string& needle,
                       const std::string& replacement) {
  size_t position = 0U;
  size_t replacements = 0U;
  while ((position = value.find(needle, position)) != std::string::npos) {
    value.replace(position, needle.size(), replacement);
    position += replacement.size();
    ++replacements;
  }
  CHECK_TRUE(replacements != 0U);
  return value;
}

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
  value.connectivity = ConnectivitySnapshot{
      LinkStatus::Online, LinkStatus::Online, LinkStatus::Unknown,
      LinkStatus::Unknown, kFreshNowMs - 200ULL};
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

template <typename Value>
void checkBuilderInvalidOutputContract(
    Result (*builder)(const Value&, char*, size_t, size_t*),
    const Value& value) {
  char output[8] = {'x', 'x', 'x', 'x', 'x', 'x', 'x', '\0'};
  size_t written = 99U;

  CHECK_EQ(Result::NullArgument, builder(value, nullptr, sizeof(output), &written));
  CHECK_EQ(0U, written);

  output[0] = 'x';
  CHECK_EQ(Result::NullArgument, builder(value, output, sizeof(output), nullptr));
  CHECK_EQ('\0', output[0]);

  CHECK_EQ(Result::NullArgument, builder(value, nullptr, 0U, nullptr));

  written = 99U;
  CHECK_EQ(Result::NullArgument, builder(value, nullptr, 0U, &written));
  CHECK_EQ(0U, written);

  output[0] = 'x';
  written = 99U;
  CHECK_EQ(Result::OutputTooSmall, builder(value, output, 0U, &written));
  CHECK_EQ(0U, written);
  CHECK_EQ('x', output[0]);

  output[0] = 'x';
  CHECK_EQ(Result::NullArgument, builder(value, output, 0U, nullptr));
  CHECK_EQ('x', output[0]);
}

template <typename Value>
void fillSentinel(Value* value) {
  std::memset(value, 0xa5, sizeof(*value));
}

template <typename Value>
void checkUnchanged(const Value& expected, const Value& actual) {
  CHECK_TRUE(std::memcmp(&expected, &actual, sizeof(Value)) == 0);
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
  CHECK_TRUE(output.connectivity.mqtt == LinkStatus::Online);
  /* An unobserved link survives the round trip as unknown, so the display
   * cannot turn "never measured" into "measured offline". */
  CHECK_TRUE(output.connectivity.gateway == LinkStatus::Unknown);
  CHECK_TRUE(output.connectivity.iotda == LinkStatus::Unknown);
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
  /* Duty and brightness are telemetry percent fields, not the menu ladder: the
   * legacy controller path can hold a fan at any whole percent, and a snapshot
   * that rejected it would discard every other reading with it. */
  snapshot = validSnapshot();
  snapshot.fans[0].target_duty_percent = 45U;
  CHECK_EQ(Result::Ok, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  snapshot = validSnapshot();
  snapshot.actuators.led_brightness_percent = 60U;
  CHECK_EQ(Result::Ok, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  snapshot = validSnapshot();
  snapshot.fans[0].target_duty_percent = 101U;
  CHECK_EQ(Result::OutOfRange, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  snapshot = validSnapshot();
  snapshot.actuators.led_brightness_percent = 101U;
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

void test_epoch_bounds_cover_every_timestamp_field() {
  char encoded[2048]{};
  size_t length = 99U;
  ScreenSnapshot snapshot = validSnapshot();
  retimeSnapshot(&snapshot, kExpectedMaxEpochMilliseconds);
  CHECK_EQ(kExpectedMaxEpochSeconds, kMaxEpochSeconds);
  CHECK_EQ(kExpectedMaxEpochMilliseconds, kMaxEpochMilliseconds);
  CHECK_EQ(Result::Ok, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  CHECK_EQ(Result::Ok,
           ParseSnapshot(encoded, length, kExpectedMaxEpochMilliseconds, &snapshot));

  std::string snapshot_above(encoded, length);
  snapshot_above = replaceAll(snapshot_above, "4102444799999", "4102444800000");
  ScreenSnapshot parsed_snapshot{};
  CHECK_EQ(Result::OutOfRange,
           ParseSnapshot(snapshot_above.c_str(), snapshot_above.size(),
                         kExpectedMaxEpochMilliseconds + 1ULL, &parsed_snapshot));

  const auto check_snapshot_field = [&](uint64_t ScreenSnapshot::*field) {
    ScreenSnapshot invalid = validSnapshot();
    invalid.*field = kExpectedMaxEpochMilliseconds + 1ULL;
    length = 99U;
    encoded[0] = 'x';
    CHECK_EQ(Result::OutOfRange,
             BuildSnapshot(invalid, encoded, sizeof(encoded), &length));
    CHECK_EQ(0U, length);
    CHECK_EQ('\0', encoded[0]);
  };
  check_snapshot_field(&ScreenSnapshot::generated_at_ms);

  for (size_t index = 0U; index < 8U; ++index) {
    ScreenSnapshot invalid = validSnapshot();
    retimeSnapshot(&invalid, kExpectedMaxEpochMilliseconds);
    Reading* readings[] = {&invalid.temperature, &invalid.humidity, &invalid.oxygen,
                           &invalid.methane, &invalid.carbon_monoxide,
                           &invalid.smoke, &invalid.water, &invalid.flame};
    readings[index]->sampled_at_ms = kExpectedMaxEpochMilliseconds + 1ULL;
    length = 99U;
    encoded[0] = 'x';
    CHECK_EQ(Result::OutOfRange,
             BuildSnapshot(invalid, encoded, sizeof(encoded), &length));
    CHECK_EQ(0U, length);
    CHECK_EQ('\0', encoded[0]);
  }
  for (size_t index = 0U; index < 2U; ++index) {
    ScreenSnapshot invalid = validSnapshot();
    retimeSnapshot(&invalid, kExpectedMaxEpochMilliseconds);
    invalid.fans[index].sampled_at_ms = kExpectedMaxEpochMilliseconds + 1ULL;
    length = 99U;
    encoded[0] = 'x';
    CHECK_EQ(Result::OutOfRange,
             BuildSnapshot(invalid, encoded, sizeof(encoded), &length));
    CHECK_EQ(0U, length);
    CHECK_EQ('\0', encoded[0]);
  }
  {
    ScreenSnapshot invalid = validSnapshot();
    retimeSnapshot(&invalid, kExpectedMaxEpochMilliseconds);
    invalid.connectivity.updated_at_ms = kExpectedMaxEpochMilliseconds + 1ULL;
    length = 99U;
    encoded[0] = 'x';
    CHECK_EQ(Result::OutOfRange,
             BuildSnapshot(invalid, encoded, sizeof(encoded), &length));
    CHECK_EQ(0U, length);
    CHECK_EQ('\0', encoded[0]);
  }
  {
    ScreenSnapshot invalid = validSnapshot();
    retimeSnapshot(&invalid, kExpectedMaxEpochMilliseconds);
    invalid.last_command.completed_at_ms = kExpectedMaxEpochMilliseconds + 1ULL;
    length = 99U;
    encoded[0] = 'x';
    CHECK_EQ(Result::OutOfRange,
             BuildSnapshot(invalid, encoded, sizeof(encoded), &length));
    CHECK_EQ(0U, length);
    CHECK_EQ('\0', encoded[0]);
  }

  MenuCommand command = validCommand();
  command.created_at_ms = kExpectedMaxEpochMilliseconds;
  CHECK_EQ(Result::Ok, BuildMenuCommand(command, encoded, sizeof(encoded), &length));
  MenuCommand parsed_command{};
  CHECK_EQ(Result::Ok,
           ParseMenuCommand(encoded, length, kExpectedMaxEpochMilliseconds,
                            &parsed_command));
  std::string command_above(encoded, length);
  command_above = replaceOnce(command_above, "4102444799999", "4102444800000");
  CHECK_EQ(Result::OutOfRange,
           ParseMenuCommand(command_above.c_str(), command_above.size(),
                            kExpectedMaxEpochMilliseconds + 1ULL,
                            &parsed_command));
  command.created_at_ms = kExpectedMaxEpochMilliseconds + 1ULL;
  CHECK_EQ(Result::OutOfRange,
           BuildMenuCommand(command, encoded, sizeof(encoded), &length));

  CommandAck ack = validAck();
  ack.completed_at_ms = kExpectedMaxEpochMilliseconds;
  CHECK_EQ(Result::Ok, BuildCommandAck(ack, encoded, sizeof(encoded), &length));
  CommandAck parsed_ack{};
  CHECK_EQ(Result::Ok, ParseCommandAck(encoded, length, &parsed_ack));
  std::string ack_above(encoded, length);
  ack_above = replaceOnce(ack_above, "4102444799999", "4102444800000");
  CHECK_EQ(Result::OutOfRange,
           ParseCommandAck(ack_above.c_str(), ack_above.size(), &parsed_ack));
  ack.completed_at_ms = kExpectedMaxEpochMilliseconds + 1ULL;
  CHECK_EQ(Result::OutOfRange,
           BuildCommandAck(ack, encoded, sizeof(encoded), &length));

  TimeSync time_sync = validTimeSync();
  time_sync.epoch_seconds = kExpectedMaxEpochSeconds;
  CHECK_EQ(Result::Ok, BuildTimeSync(time_sync, encoded, sizeof(encoded), &length));
  TimeSync parsed_time{};
  CHECK_EQ(Result::Ok, ParseTimeSync(encoded, length, &parsed_time));
  std::string time_above(encoded, length);
  time_above = replaceOnce(time_above, "4102444799", "4102444800");
  CHECK_EQ(Result::OutOfRange,
           ParseTimeSync(time_above.c_str(), time_above.size(), &parsed_time));
  time_sync.epoch_seconds = kExpectedMaxEpochSeconds + 1ULL;
  CHECK_EQ(Result::OutOfRange,
           BuildTimeSync(time_sync, encoded, sizeof(encoded), &length));

  time_sync.epoch_seconds = UINT64_MAX;
  CHECK_EQ(Result::OutOfRange,
           BuildTimeSync(time_sync, encoded, sizeof(encoded), &length));
  const char maximum_uint64[] =
      "{\"schema\":\"ut.time.sync.v1\",\"source\":\"ntp\"," \
      "\"state\":\"synchronized\",\"epochSeconds\":18446744073709551615,\"seq\":1}";
  CHECK_EQ(Result::OutOfRange,
           ParseTimeSync(maximum_uint64, sizeof(maximum_uint64) - 1U, &parsed_time));
  const char overflowing_uint64[] =
      "{\"schema\":\"ut.time.sync.v1\",\"source\":\"ntp\"," \
      "\"state\":\"synchronized\",\"epochSeconds\":18446744073709551616,\"seq\":1}";
  CHECK_EQ(Result::NumberOverflow,
           ParseTimeSync(overflowing_uint64, sizeof(overflowing_uint64) - 1U,
                         &parsed_time));
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

  // Deliberately model a full unterminated 40-byte identifier without writing
  // a terminator into the following struct field.
  std::memset(command.command_id, '1', sizeof(command.command_id));
  CHECK_EQ(Result::InvalidIdentifier,
           BuildMenuCommand(command, encoded, sizeof(encoded), &length));
  command = validCommand();
  std::strcpy(command.target, "CTRL-02");
  CHECK_EQ(Result::InvalidTarget,
           BuildMenuCommand(command, encoded, sizeof(encoded), &length));

  const CommandAction actions[] = {
      CommandAction::Fan1Duty, CommandAction::Fan1Duty,
      CommandAction::Fan1Duty, CommandAction::Fan1Duty,
      CommandAction::FansBothStart, CommandAction::FansAllStop,
      CommandAction::Fan2Duty, CommandAction::Fan2Duty,
      CommandAction::Fan2Duty, CommandAction::Fan2Duty,
      CommandAction::LedMode, CommandAction::LedMode,
      CommandAction::LedMode, CommandAction::LedMode,
      CommandAction::LedMode, CommandAction::LedMode,
      CommandAction::LedMode, CommandAction::LedMode,
      CommandAction::LedBrightness, CommandAction::LedBrightness,
      CommandAction::LedBrightness, CommandAction::LedBrightness,
      CommandAction::BuzzerTest, CommandAction::BuzzerMute,
      CommandAction::BuzzerRestore,
  };
  const uint8_t values[] = {
      0U, 30U, 60U, 100U, 0U, 0U, 0U, 30U, 60U, 100U,
      0U, 1U, 2U, 3U, 4U, 5U, 6U, 7U,
      25U, 50U, 75U, 100U, 0U, 0U, 0U,
  };
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

  const CommandAction zero_only_actions[] = {
      CommandAction::FansBothStart, CommandAction::FansAllStop,
      CommandAction::BuzzerTest, CommandAction::BuzzerMute,
      CommandAction::BuzzerRestore,
  };
  for (size_t index = 0U;
       index < sizeof(zero_only_actions) / sizeof(zero_only_actions[0]); ++index) {
    command = validCommand();
    command.action = zero_only_actions[index];
    command.value = 1U;
    CHECK_EQ(Result::OutOfRange,
             BuildMenuCommand(command, encoded, sizeof(encoded), &length));
  }

  command = validCommand();
  command.action = CommandAction::Fan2Duty;
  command.value = 45U;
  CHECK_EQ(Result::OutOfRange,
           BuildMenuCommand(command, encoded, sizeof(encoded), &length));

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

void test_parsers_reject_duplicate_unknown_keys_invalid_target_and_40_char_id() {
  MenuCommand output{};
  const char duplicate[] =
      "{\"schema\":\"ut.menu.command.v1\",\"cmdId\":\"menu-1\"," \
      "\"cmdId\":\"menu-2\",\"target\":\"CTRL-01\",\"action\":\"fan1_duty\"," \
      "\"value\":30,\"createdAtMs\":1704067219000,\"ttlMs\":10000}";
  const char unknown[] =
      "{\"schema\":\"ut.menu.command.v1\",\"cmdId\":\"menu-1\"," \
      "\"extra\":0,\"target\":\"CTRL-01\",\"action\":\"fan1_duty\"," \
      "\"value\":30,\"createdAtMs\":1704067219000,\"ttlMs\":10000}";
  const char invalid_target[] =
      "{\"schema\":\"ut.menu.command.v1\",\"cmdId\":\"menu-1\"," \
      "\"target\":\"CTRL-02\",\"action\":\"fan1_duty\",\"value\":30," \
      "\"createdAtMs\":1704067219000,\"ttlMs\":10000}";
  const char oversized_id[] =
      "{\"schema\":\"ut.menu.command.v1\"," \
      "\"cmdId\":\"1234567890123456789012345678901234567890\"," \
      "\"target\":\"CTRL-01\",\"action\":\"fan1_duty\",\"value\":30," \
      "\"createdAtMs\":1704067219000,\"ttlMs\":10000}";

  CHECK_EQ(Result::MissingField,
           ParseMenuCommand(duplicate, sizeof(duplicate) - 1U, kFreshNowMs, &output));
  CHECK_EQ(Result::MissingField,
           ParseMenuCommand(unknown, sizeof(unknown) - 1U, kFreshNowMs, &output));
  CHECK_EQ(Result::InvalidTarget,
           ParseMenuCommand(invalid_target, sizeof(invalid_target) - 1U,
                            kFreshNowMs, &output));
  CHECK_EQ(Result::InvalidIdentifier,
           ParseMenuCommand(oversized_id, sizeof(oversized_id) - 1U,
                            kFreshNowMs, &output));
}

void test_every_parser_rejects_duplicate_and_unknown_root_keys() {
  ScreenSnapshot snapshot{};
  MenuCommand command{};
  CommandAck ack{};
  TimeSync time_sync{};
  char encoded[kUartLineLimit + 1U]{};
  size_t length = 0U;

  CHECK_EQ(Result::Ok,
           BuildSnapshot(validSnapshot(), encoded, sizeof(encoded), &length));
  const std::string snapshot_json(encoded, length);
  const std::string snapshot_duplicate = replaceOnce(
      snapshot_json, "\"schema\":\"ut.screen.snapshot.v1\"",
      "\"schema\":\"ut.screen.snapshot.v1\","
      "\"schema\":\"ut.screen.snapshot.v1\"");
  const std::string snapshot_unknown = replaceOnce(
      snapshot_json, "\"schema\":\"ut.screen.snapshot.v1\"",
      "\"schema\":\"ut.screen.snapshot.v1\",\"extra\":0");

  CHECK_EQ(Result::Ok,
           BuildMenuCommand(validCommand(), encoded, sizeof(encoded), &length));
  const std::string command_json(encoded, length);
  const std::string command_duplicate = replaceOnce(
      command_json, "\"schema\":\"ut.menu.command.v1\"",
      "\"schema\":\"ut.menu.command.v1\","
      "\"schema\":\"ut.menu.command.v1\"");
  const std::string command_unknown = replaceOnce(
      command_json, "\"schema\":\"ut.menu.command.v1\"",
      "\"schema\":\"ut.menu.command.v1\",\"extra\":0");

  CHECK_EQ(Result::Ok,
           BuildCommandAck(validAck(), encoded, sizeof(encoded), &length));
  const std::string ack_json(encoded, length);
  const std::string ack_duplicate = replaceOnce(
      ack_json, "\"schema\":\"ut.command.ack.v1\"",
      "\"schema\":\"ut.command.ack.v1\","
      "\"schema\":\"ut.command.ack.v1\"");
  const std::string ack_unknown = replaceOnce(
      ack_json, "\"schema\":\"ut.command.ack.v1\"",
      "\"schema\":\"ut.command.ack.v1\",\"extra\":0");

  CHECK_EQ(Result::Ok,
           BuildTimeSync(validTimeSync(), encoded, sizeof(encoded), &length));
  const std::string time_json(encoded, length);
  const std::string time_duplicate = replaceOnce(
      time_json, "\"schema\":\"ut.time.sync.v1\"",
      "\"schema\":\"ut.time.sync.v1\","
      "\"schema\":\"ut.time.sync.v1\"");
  const std::string time_unknown = replaceOnce(
      time_json, "\"schema\":\"ut.time.sync.v1\"",
      "\"schema\":\"ut.time.sync.v1\",\"extra\":0");

  CHECK_EQ(Result::MissingField,
           ParseSnapshot(snapshot_duplicate.c_str(), snapshot_duplicate.size(),
                         kFreshNowMs, &snapshot));
  CHECK_EQ(Result::MissingField,
           ParseSnapshot(snapshot_unknown.c_str(), snapshot_unknown.size(),
                         kFreshNowMs, &snapshot));
  CHECK_EQ(Result::MissingField,
           ParseMenuCommand(command_duplicate.c_str(), command_duplicate.size(),
                            kFreshNowMs, &command));
  CHECK_EQ(Result::MissingField,
           ParseMenuCommand(command_unknown.c_str(), command_unknown.size(),
                            kFreshNowMs, &command));
  CHECK_EQ(Result::MissingField,
           ParseCommandAck(ack_duplicate.c_str(), ack_duplicate.size(), &ack));
  CHECK_EQ(Result::MissingField,
           ParseCommandAck(ack_unknown.c_str(), ack_unknown.size(), &ack));
  CHECK_EQ(Result::MissingField,
           ParseTimeSync(time_duplicate.c_str(), time_duplicate.size(), &time_sync));
  CHECK_EQ(Result::MissingField,
           ParseTimeSync(time_unknown.c_str(), time_unknown.size(), &time_sync));
}

void test_field_specific_errors_distinguish_strings_enums_and_ranges() {
  char encoded[kUartLineLimit + 1U]{};
  size_t length = 0U;
  ScreenSnapshot snapshot = validSnapshot();
  CHECK_EQ(Result::Ok, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));

  std::string invalid_source(encoded, length);
  invalid_source = replaceOnce(invalid_source, "\"source\":\"CTRL-01\"",
                               "\"source\":\"CTRL-012\"");
  ScreenSnapshot parsed{};
  CHECK_EQ(Result::InvalidString,
           ParseSnapshot(invalid_source.c_str(), invalid_source.size(), kFreshNowMs,
                         &parsed));

  std::string invalid_quality(encoded, length);
  const size_t temperature = invalid_quality.find("\"temperature\":[");
  const size_t quality = invalid_quality.find("]", temperature);
  CHECK_TRUE(temperature != std::string::npos && quality != std::string::npos);
  if (quality != std::string::npos) invalid_quality[quality - 1U] = '4';
  CHECK_EQ(Result::InvalidEnum,
           ParseSnapshot(invalid_quality.c_str(), invalid_quality.size(), kFreshNowMs,
                         &parsed));

  std::string invalid_alarm(encoded, length);
  invalid_alarm = replaceOnce(invalid_alarm, "\"alarm\":[1,", "\"alarm\":[3,");
  CHECK_EQ(Result::InvalidEnum,
           ParseSnapshot(invalid_alarm.c_str(), invalid_alarm.size(), kFreshNowMs,
                         &parsed));

  snapshot = validSnapshot();
  snapshot.humidity.value = 10001;
  CHECK_EQ(Result::OutOfRange,
           BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  snapshot = validSnapshot();
  snapshot.temperature.quality = static_cast<Quality>(4U);
  CHECK_EQ(Result::InvalidEnum,
           BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  snapshot = validSnapshot();
  snapshot.alarm_severity = static_cast<AlarmSeverity>(3U);
  CHECK_EQ(Result::InvalidEnum,
           BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));

  const char invalid_action[] =
      "{\"schema\":\"ut.menu.command.v1\",\"cmdId\":\"menu-1\"," \
      "\"target\":\"CTRL-01\",\"action\":\"turbo\",\"value\":30," \
      "\"createdAtMs\":1704067219000,\"ttlMs\":10000}";
  MenuCommand parsed_command{};
  CHECK_EQ(Result::InvalidEnum,
           ParseMenuCommand(invalid_action, sizeof(invalid_action) - 1U,
                            kFreshNowMs, &parsed_command));

  const char invalid_reason[] =
      "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"menu-1\"," \
      "\"status\":\"rejected\"," \
      "\"reason\":\"123456789012345678901234567890123456789012345678\"," \
      "\"appliedValue\":0,\"completedAtMs\":1704067219950}";
  CommandAck parsed_ack{};
  CHECK_EQ(Result::InvalidString,
           ParseCommandAck(invalid_reason, sizeof(invalid_reason) - 1U, &parsed_ack));
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
  tiny[0] = 'x'; written = 99U;
  CHECK_EQ(Result::OutputTooSmall,
           BuildSnapshot(validSnapshot(), tiny, sizeof(tiny), &written));
  CHECK_EQ(0U, written); CHECK_EQ('\0', tiny[0]);
  tiny[0] = 'x'; written = 99U;
  CHECK_EQ(Result::OutputTooSmall,
           BuildCommandAck(validAck(), tiny, sizeof(tiny), &written));
  CHECK_EQ(0U, written); CHECK_EQ('\0', tiny[0]);
  tiny[0] = 'x'; written = 99U;
  CHECK_EQ(Result::OutputTooSmall,
           BuildTimeSync(validTimeSync(), tiny, sizeof(tiny), &written));
  CHECK_EQ(0U, written); CHECK_EQ('\0', tiny[0]);

  ScreenSnapshot largest = validSnapshot();
  retimeSnapshot(&largest, kExpectedMaxEpochMilliseconds);
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
    largest.fans[index].running = false;
    largest.fans[index].actual_rpm = 100000U;
    largest.fans[index].voltage_mv = 36000U;
    largest.fans[index].current_ma = 10000U;
  }
  largest.warning_sources = 0xffU;
  largest.critical_sources = 0xffU;
  largest.alarm_severity = AlarmSeverity::Critical;
  largest.temperature.quality = Quality::Invalid;
  largest.humidity.quality = Quality::Invalid;
  largest.oxygen.quality = Quality::Invalid;
  largest.methane.quality = Quality::Invalid;
  largest.carbon_monoxide.quality = Quality::Invalid;
  largest.smoke.quality = Quality::Invalid;
  largest.water.quality = Quality::Invalid;
  largest.flame.quality = Quality::Invalid;
  largest.fans[0].quality = Quality::Invalid;
  largest.fans[1].quality = Quality::Invalid;
  largest.actuators.relay_on = false;
  largest.actuators.led_mode = 15U;
  largest.actuators.led_brightness_percent = 100U;
  largest.actuators.buzzer_on = false;
  largest.actuators.buzzer_muted = false;
  largest.connectivity.node_a = LinkStatus::Offline;
  largest.connectivity.gateway = LinkStatus::Unknown;
  largest.connectivity.iotda = LinkStatus::Unknown;
  largest.connectivity.mqtt = LinkStatus::Offline;
  std::strcpy(largest.last_command.command_id,
              "123456789012345678901234567890123456789");
  largest.last_command.accepted = false;
  largest.last_command.complete = true;
  char largest_json[2048]{};
  size_t largest_length = 0U;
  CHECK_EQ(Result::Ok,
           BuildSnapshot(largest, largest_json, sizeof(largest_json),
                         &largest_length));
  CHECK_TRUE(largest_length <= kUartLineLimit);
  ScreenSnapshot reparsed{};
  CHECK_EQ(Result::Ok,
           ParseSnapshot(largest_json, largest_length,
                         kExpectedMaxEpochMilliseconds, &reparsed));
}

void test_every_builder_failure_clears_output_and_written() {
  char output[2048]{};
  size_t written = 99U;

  ScreenSnapshot snapshot = validSnapshot();
  snapshot.humidity.value = 10001;
  output[0] = 'x';
  CHECK_EQ(Result::OutOfRange,
           BuildSnapshot(snapshot, output, sizeof(output), &written));
  CHECK_EQ(0U, written); CHECK_EQ('\0', output[0]);

  MenuCommand command = validCommand();
  std::strcpy(command.target, "CTRL-02");
  written = 99U; output[0] = 'x';
  CHECK_EQ(Result::InvalidTarget,
           BuildMenuCommand(command, output, sizeof(output), &written));
  CHECK_EQ(0U, written); CHECK_EQ('\0', output[0]);

  CommandAck ack = validAck();
  std::strcpy(ack.reason, "bad reason");
  written = 99U; output[0] = 'x';
  CHECK_EQ(Result::InvalidString,
           BuildCommandAck(ack, output, sizeof(output), &written));
  CHECK_EQ(0U, written); CHECK_EQ('\0', output[0]);

  TimeSync time_sync = validTimeSync();
  time_sync.epoch_seconds = kMinEpochSeconds - 1ULL;
  written = 99U; output[0] = 'x';
  CHECK_EQ(Result::OutOfRange,
           BuildTimeSync(time_sync, output, sizeof(output), &written));
  CHECK_EQ(0U, written); CHECK_EQ('\0', output[0]);
}

void test_every_builder_handles_partial_null_and_zero_capacity_outputs() {
  checkBuilderInvalidOutputContract(&BuildSnapshot, validSnapshot());
  checkBuilderInvalidOutputContract(&BuildMenuCommand, validCommand());
  checkBuilderInvalidOutputContract(&BuildCommandAck, validAck());
  checkBuilderInvalidOutputContract(&BuildTimeSync, validTimeSync());
}

void test_parser_failures_leave_caller_objects_unchanged() {
  char encoded[kUartLineLimit + 1U]{};
  size_t length = 0U;

  CHECK_EQ(Result::Ok,
           BuildSnapshot(validSnapshot(), encoded, sizeof(encoded), &length));
  const std::string snapshot_json(encoded, length);
  const std::string snapshot_schema = replaceOnce(
      snapshot_json, "ut.screen.snapshot.v1", "ut.screen.snapshot.v2");
  const std::string snapshot_type = replaceOnce(
      snapshot_json, "\"seq\":77", "\"seq\":\"77\"");
  const std::string snapshot_range = replaceOnce(
      snapshot_json, "\"humidity\":[5210", "\"humidity\":[10001");
  const std::string snapshot_malformed =
      snapshot_json.substr(0U, snapshot_json.size() - 1U);
  const auto check_snapshot = [&](const std::string& json, uint64_t now,
                                  Result expected_result) {
    ScreenSnapshot output{};
    fillSentinel(&output);
    ScreenSnapshot before{};
    std::memcpy(&before, &output, sizeof(before));
    CHECK_EQ(expected_result,
             ParseSnapshot(json.c_str(), json.size(), now, &output));
    checkUnchanged(before, output);
  };
  check_snapshot(snapshot_malformed, kFreshNowMs, Result::MalformedJson);
  check_snapshot(snapshot_schema, kFreshNowMs, Result::UnknownSchema);
  check_snapshot(snapshot_type, kFreshNowMs, Result::WrongType);
  check_snapshot(snapshot_range, kFreshNowMs, Result::OutOfRange);
  check_snapshot(snapshot_json, kFreshNowMs + kSnapshotMaxAgeMs, Result::Stale);

  CHECK_EQ(Result::Ok,
           BuildMenuCommand(validCommand(), encoded, sizeof(encoded), &length));
  const std::string command_json(encoded, length);
  const std::string command_schema = replaceOnce(
      command_json, "ut.menu.command.v1", "ut.menu.command.v2");
  const std::string command_type = replaceOnce(
      command_json, "\"value\":60", "\"value\":\"60\"");
  const std::string command_range = replaceOnce(
      command_json, "\"value\":60", "\"value\":45");
  const std::string command_malformed =
      command_json.substr(0U, command_json.size() - 1U);
  const auto check_command = [&](const std::string& json, uint64_t now,
                                 Result expected_result) {
    MenuCommand output{};
    fillSentinel(&output);
    MenuCommand before{};
    std::memcpy(&before, &output, sizeof(before));
    CHECK_EQ(expected_result,
             ParseMenuCommand(json.c_str(), json.size(), now, &output));
    checkUnchanged(before, output);
  };
  check_command(command_malformed, kFreshNowMs, Result::MalformedJson);
  check_command(command_schema, kFreshNowMs, Result::UnknownSchema);
  check_command(command_type, kFreshNowMs, Result::WrongType);
  check_command(command_range, kFreshNowMs, Result::OutOfRange);
  check_command(command_json, kFreshNowMs + 9000ULL, Result::Expired);

  CHECK_EQ(Result::Ok,
           BuildCommandAck(validAck(), encoded, sizeof(encoded), &length));
  const std::string ack_json(encoded, length);
  const std::string ack_schema = replaceOnce(
      ack_json, "ut.command.ack.v1", "ut.command.ack.v2");
  const std::string ack_type = replaceOnce(
      ack_json, "\"appliedValue\":60", "\"appliedValue\":\"60\"");
  const std::string ack_range = replaceOnce(
      ack_json, "\"appliedValue\":60", "\"appliedValue\":101");
  const std::string ack_malformed = ack_json.substr(0U, ack_json.size() - 1U);
  const auto check_ack = [&](const std::string& json, Result expected_result) {
    CommandAck output{};
    fillSentinel(&output);
    CommandAck before{};
    std::memcpy(&before, &output, sizeof(before));
    CHECK_EQ(expected_result,
             ParseCommandAck(json.c_str(), json.size(), &output));
    checkUnchanged(before, output);
  };
  check_ack(ack_malformed, Result::MalformedJson);
  check_ack(ack_schema, Result::UnknownSchema);
  check_ack(ack_type, Result::WrongType);
  check_ack(ack_range, Result::OutOfRange);

  CHECK_EQ(Result::Ok,
           BuildTimeSync(validTimeSync(), encoded, sizeof(encoded), &length));
  const std::string time_json(encoded, length);
  const std::string time_schema = replaceOnce(
      time_json, "ut.time.sync.v1", "ut.time.sync.v2");
  const std::string time_type = replaceOnce(
      time_json, "\"epochSeconds\":1704067200",
      "\"epochSeconds\":\"1704067200\"");
  const std::string time_range = replaceOnce(
      time_json, "\"epochSeconds\":1704067200",
      "\"epochSeconds\":1704067199");
  const std::string time_malformed = time_json.substr(0U, time_json.size() - 1U);
  const auto check_time = [&](const std::string& json, Result expected_result) {
    TimeSync output{};
    fillSentinel(&output);
    TimeSync before{};
    std::memcpy(&before, &output, sizeof(before));
    CHECK_EQ(expected_result,
             ParseTimeSync(json.c_str(), json.size(), &output));
    checkUnchanged(before, output);
  };
  check_time(time_malformed, Result::MalformedJson);
  check_time(time_schema, Result::UnknownSchema);
  check_time(time_type, Result::WrongType);
  check_time(time_range, Result::OutOfRange);
}

uint32_t nextFuzzValue(uint32_t* state) {
  uint32_t value = *state;
  value ^= value << 13U;
  value ^= value >> 17U;
  value ^= value << 5U;
  *state = value;
  return value;
}

void fuzzParsersDeterministically() {
  char seeds[4][kUartLineLimit + 1U]{};
  size_t seed_lengths[4]{};
  CHECK_EQ(Result::Ok,
           BuildSnapshot(validSnapshot(), seeds[0], sizeof(seeds[0]),
                         &seed_lengths[0]));
  CHECK_EQ(Result::Ok,
           BuildMenuCommand(validCommand(), seeds[1], sizeof(seeds[1]),
                            &seed_lengths[1]));
  CHECK_EQ(Result::Ok,
           BuildCommandAck(validAck(), seeds[2], sizeof(seeds[2]),
                           &seed_lengths[2]));
  CHECK_EQ(Result::Ok,
           BuildTimeSync(validTimeSync(), seeds[3], sizeof(seeds[3]),
                         &seed_lengths[3]));

  uint32_t state = 0x51a7f00dU;
  char mutated[kUartLineLimit + 2U]{};
  char rebuilt[kUartLineLimit + 1U]{};
  for (size_t iteration = 0U; iteration < 100000U; ++iteration) {
    const size_t seed_index = iteration % 4U;
    size_t length = seed_lengths[seed_index];
    std::memcpy(mutated, seeds[seed_index], length);
    const size_t changes = 1U + nextFuzzValue(&state) % 4U;
    for (size_t change = 0U; change < changes && length != 0U; ++change) {
      const size_t position = nextFuzzValue(&state) % length;
      mutated[position] = static_cast<char>(nextFuzzValue(&state) & 0xffU);
    }
    if ((iteration % 17U) == 0U) {
      length = nextFuzzValue(&state) % (kUartLineLimit + 2U);
      for (size_t index = 0U; index < length; ++index) {
        mutated[index] = static_cast<char>(nextFuzzValue(&state) & 0xffU);
      }
    } else if ((iteration % 11U) == 0U && length < kUartLineLimit + 1U) {
      mutated[length++] = static_cast<char>(nextFuzzValue(&state) & 0xffU);
    } else if ((iteration % 7U) == 0U && length != 0U) {
      length = nextFuzzValue(&state) % length;
    }

    ScreenSnapshot snapshot{};
    MenuCommand command{};
    CommandAck ack{};
    TimeSync time_sync{};
    size_t rebuilt_length = 0U;
    if (ParseSnapshot(mutated, length, kFreshNowMs, &snapshot) == Result::Ok) {
      CHECK_EQ(Result::Ok,
               BuildSnapshot(snapshot, rebuilt, sizeof(rebuilt), &rebuilt_length));
      CHECK_TRUE(rebuilt_length <= kUartLineLimit);
    }
    if (ParseMenuCommand(mutated, length, kFreshNowMs, &command) == Result::Ok) {
      CHECK_EQ(Result::Ok,
               BuildMenuCommand(command, rebuilt, sizeof(rebuilt), &rebuilt_length));
      CHECK_TRUE(rebuilt_length <= kUartLineLimit);
    }
    if (ParseCommandAck(mutated, length, &ack) == Result::Ok) {
      CHECK_EQ(Result::Ok,
               BuildCommandAck(ack, rebuilt, sizeof(rebuilt), &rebuilt_length));
      CHECK_TRUE(rebuilt_length <= kUartLineLimit);
    }
    if (ParseTimeSync(mutated, length, &time_sync) == Result::Ok) {
      CHECK_EQ(Result::Ok,
               BuildTimeSync(time_sync, rebuilt, sizeof(rebuilt), &rebuilt_length));
      CHECK_TRUE(rebuilt_length <= kUartLineLimit);
    }
  }
}

}  // namespace

void test_multi_sensor_snapshot_round_trip() {
  ScreenSnapshot snapshot = validSnapshot();
  snapshot.sensor_count = 3U;

  // 1. FLAME-04 alarm from CTRL-02
  std::strcpy(snapshot.sensors[0].asset_code, "FLAME-04");
  snapshot.sensors[0].kind = static_cast<uint8_t>(SensorKind::Flame);
  snapshot.sensors[0].value = 1;
  snapshot.sensors[0].scale = 1;
  snapshot.sensors[0].quality = Quality::Valid;
  snapshot.sensors[0].alarm = 1U;
  std::strcpy(snapshot.sensors[0].source, "CTRL-02");
  snapshot.sensors[0].updated_at_ms = kFreshNowMs - 500ULL;

  // 2. MQ4-01 good from CTRL-01
  std::strcpy(snapshot.sensors[1].asset_code, "MQ4-01");
  snapshot.sensors[1].kind = static_cast<uint8_t>(SensorKind::Mq4);
  snapshot.sensors[1].value = 120;
  snapshot.sensors[1].scale = 1;
  snapshot.sensors[1].quality = Quality::Valid;
  snapshot.sensors[1].alarm = 0U;
  std::strcpy(snapshot.sensors[1].source, "CTRL-01");
  snapshot.sensors[1].updated_at_ms = kFreshNowMs - 400ULL;

  // 3. SHT-03 missing
  std::strcpy(snapshot.sensors[2].asset_code, "SHT-03");
  snapshot.sensors[2].kind = static_cast<uint8_t>(SensorKind::Sht30);
  snapshot.sensors[2].value = 0;
  snapshot.sensors[2].scale = 100;
  snapshot.sensors[2].quality = Quality::Missing;
  snapshot.sensors[2].alarm = 0U;
  std::strcpy(snapshot.sensors[2].source, "CTRL-01");
  snapshot.sensors[2].updated_at_ms = kFreshNowMs - 300ULL;

  std::strcpy(snapshot.alarm_label, "FLAME-04");

  char encoded[kUartLineLimit + 1U]{};
  size_t length = 0U;
  CHECK_EQ(Result::Ok, BuildSnapshot(snapshot, encoded, sizeof(encoded), &length));
  CHECK_TRUE(length <= kUartLineLimit);

  ScreenSnapshot parsed{};
  CHECK_EQ(Result::Ok, ParseSnapshot(encoded, length, kFreshNowMs, &parsed));

  CHECK_EQ(3U, parsed.sensor_count);
  CHECK_TRUE(std::strcmp(parsed.sensors[0].asset_code, "FLAME-04") == 0);
  CHECK_TRUE(std::strcmp(parsed.sensors[0].source, "CTRL-02") == 0);
  CHECK_EQ(1U, parsed.sensors[0].alarm);

  CHECK_TRUE(std::strcmp(parsed.sensors[1].asset_code, "MQ4-01") == 0);
  CHECK_TRUE(std::strcmp(parsed.sensors[1].source, "CTRL-01") == 0);
  CHECK_EQ(Quality::Valid, parsed.sensors[1].quality);

  CHECK_TRUE(std::strcmp(parsed.sensors[2].asset_code, "SHT-03") == 0);
  CHECK_EQ(Quality::Missing, parsed.sensors[2].quality);

  CHECK_EQ(1U, SummaryAlarmCount(parsed));
  CHECK_EQ(Quality::Missing, WorstQuality(parsed));
  CHECK_TRUE(std::strcmp(AlarmLabel(parsed), "FLAME-04") == 0);
}

int main() {
  test_multi_sensor_snapshot_round_trip();
  test_snapshot_round_trip_is_complete_and_canonical();
  test_snapshot_rejects_missing_unknown_malformed_wrong_type_and_nonfinite();
  test_snapshot_enforces_bounds_and_freshness();
  test_epoch_bounds_cover_every_timestamp_field();
  test_menu_command_preserves_39_character_id_and_decodes_escapes();
  test_menu_command_rejects_identifier_target_action_value_and_ttl_boundaries();
  test_parsers_reject_duplicate_unknown_keys_invalid_target_and_40_char_id();
  test_every_parser_rejects_duplicate_and_unknown_root_keys();
  test_field_specific_errors_distinguish_strings_enums_and_ranges();
  test_ack_round_trip_preserves_result_and_escaped_reason();
  test_ack_rejects_missing_or_oversized_id_and_unknown_status();
  test_json_number_rejects_whitespace_after_minus();
  test_time_sync_round_trip_and_epoch_boundary();
  test_uart_line_limit_and_output_buffer_are_exact();
  test_every_builder_failure_clears_output_and_written();
  test_every_builder_handles_partial_null_and_zero_capacity_outputs();
  test_parser_failures_leave_caller_objects_unchanged();
  fuzzParsersDeterministically();
  if (failures == 0) std::puts("screen_protocol tests passed");
  return failures == 0 ? 0 : 1;
}
