#include "screen_protocol.h"

#include <climits>
#include <cstring>

namespace screen_protocol {
namespace {

constexpr char kSnapshotSchema[] = "ut.screen.snapshot.v1";
constexpr char kMenuCommandSchema[] = "ut.menu.command.v1";
constexpr char kCommandAckSchema[] = "ut.command.ack.v1";
constexpr char kTimeSyncSchema[] = "ut.time.sync.v1";
constexpr uint64_t kMinEpochMs = kMinEpochSeconds * 1000ULL;
constexpr uint32_t kAlarmSourceMask = 0xffU;

class Writer {
 public:
  Writer(char* output, size_t capacity)
      : output_(output), capacity_(capacity), position_(0U), storage_ok_(true) {}

  void character(char value) {
    if (position_ < capacity_) {
      output_[position_] = value;
    } else {
      storage_ok_ = false;
    }
    ++position_;
  }

  void literal(const char* value) {
    while (*value != '\0') character(*value++);
  }

  void string(const char* value) {
    character('"');
    for (size_t index = 0U; value[index] != '\0'; ++index) {
      const unsigned char byte = static_cast<unsigned char>(value[index]);
      switch (byte) {
        case '"': literal("\\\""); break;
        case '\\': literal("\\\\"); break;
        case '\b': literal("\\b"); break;
        case '\f': literal("\\f"); break;
        case '\n': literal("\\n"); break;
        case '\r': literal("\\r"); break;
        case '\t': literal("\\t"); break;
        default:
          if (byte < 0x20U) {
            static const char hex[] = "0123456789abcdef";
            literal("\\u00");
            character(hex[(byte >> 4U) & 0x0fU]);
            character(hex[byte & 0x0fU]);
          } else {
            character(static_cast<char>(byte));
          }
          break;
      }
    }
    character('"');
  }

  void unsignedNumber(uint64_t value) {
    char digits[21];
    size_t count = 0U;
    do {
      digits[count++] = static_cast<char>('0' + (value % 10ULL));
      value /= 10ULL;
    } while (value != 0ULL);
    while (count != 0U) character(digits[--count]);
  }

  void signedNumber(int32_t value) {
    if (value < 0) {
      character('-');
      const uint32_t magnitude = static_cast<uint32_t>(-(static_cast<int64_t>(value)));
      unsignedNumber(magnitude);
    } else {
      unsignedNumber(static_cast<uint32_t>(value));
    }
  }

  void boolean(bool value) { literal(value ? "true" : "false"); }

  bool finish(size_t* written) {
    if (!storage_ok_ || position_ >= capacity_) return false;
    output_[position_] = '\0';
    *written = position_;
    return true;
  }

  size_t requiredSize() const { return position_; }

 private:
  char* output_;
  size_t capacity_;
  size_t position_;
  bool storage_ok_;
};

class Reader {
 public:
  Reader(const char* input, size_t length)
      : input_(input), length_(length), position_(0U), result_(Result::Ok) {}

  bool beginObject() { return punctuation('{'); }
  bool endObject() { return punctuation('}'); }
  bool beginArray() { return punctuation('['); }
  bool endArray() { return punctuation(']'); }
  bool comma() {
    skipWhitespace();
    if (position_ < length_ && input_[position_] == ',') {
      ++position_;
      return true;
    }
    fail((position_ < length_ && input_[position_] == '}')
             ? Result::MissingField
             : Result::MalformedJson);
    return false;
  }

  bool key(const char* expected) {
    char actual[32];
    if (!readString(actual, sizeof(actual))) return false;
    if (std::strcmp(actual, expected) != 0) {
      fail(Result::MissingField);
      return false;
    }
    return punctuation(':');
  }

  bool readString(char* output, size_t capacity,
                  Result invalid_result = Result::InvalidString) {
    skipWhitespace();
    if (position_ >= length_ || input_[position_] != '"') {
      fail(Result::WrongType);
      return false;
    }
    ++position_;
    size_t written = 0U;
    while (position_ < length_) {
      unsigned char byte = static_cast<unsigned char>(input_[position_++]);
      if (byte == '"') {
        if (written >= capacity) {
          fail(invalid_result);
          return false;
        }
        output[written] = '\0';
        return true;
      }
      if (byte < 0x20U) {
        fail(invalid_result);
        return false;
      }
      if (byte == '\\') {
        if (position_ >= length_) {
          fail(Result::MalformedJson);
          return false;
        }
        const char escaped = input_[position_++];
        switch (escaped) {
          case '"': byte = '"'; break;
          case '\\': byte = '\\'; break;
          case '/': byte = '/'; break;
          case 'b': byte = '\b'; break;
          case 'f': byte = '\f'; break;
          case 'n': byte = '\n'; break;
          case 'r': byte = '\r'; break;
          case 't': byte = '\t'; break;
          case 'u': {
            uint16_t code = 0U;
            for (uint8_t digit = 0U; digit < 4U; ++digit) {
              if (position_ >= length_) {
                fail(Result::MalformedJson);
                return false;
              }
              const int value = hexValue(input_[position_++]);
              if (value < 0) {
                fail(Result::MalformedJson);
                return false;
              }
              code = static_cast<uint16_t>((code << 4U) | static_cast<uint16_t>(value));
            }
            if (code > 0x7fU || code < 0x20U) {
              fail(invalid_result);
              return false;
            }
            byte = static_cast<unsigned char>(code);
            break;
          }
          default:
            fail(Result::MalformedJson);
            return false;
        }
      } else if (byte >= 0x80U) {
        fail(invalid_result);
        return false;
      }
      if (written + 1U >= capacity) {
        fail(invalid_result);
        return false;
      }
      output[written++] = static_cast<char>(byte);
    }
    fail(Result::MalformedJson);
    return false;
  }

  bool readUnsigned64(uint64_t* output) {
    skipWhitespace();
    if (position_ >= length_ || input_[position_] < '0' || input_[position_] > '9') {
      fail(Result::WrongType);
      return false;
    }
    if (input_[position_] == '0' && position_ + 1U < length_ &&
        input_[position_ + 1U] >= '0' && input_[position_ + 1U] <= '9') {
      fail(Result::MalformedJson);
      return false;
    }
    uint64_t value = 0ULL;
    while (position_ < length_ && input_[position_] >= '0' && input_[position_] <= '9') {
      const uint8_t digit = static_cast<uint8_t>(input_[position_] - '0');
      if (value > (UINT64_MAX - digit) / 10ULL) {
        fail(Result::NumberOverflow);
        return false;
      }
      value = value * 10ULL + digit;
      ++position_;
    }
    if (position_ < length_ &&
        (input_[position_] == '.' || input_[position_] == 'e' || input_[position_] == 'E')) {
      fail(Result::WrongType);
      return false;
    }
    *output = value;
    return true;
  }

  bool readUnsigned32(uint32_t* output) {
    uint64_t value = 0ULL;
    if (!readUnsigned64(&value)) return false;
    if (value > UINT32_MAX) {
      fail(Result::NumberOverflow);
      return false;
    }
    *output = static_cast<uint32_t>(value);
    return true;
  }

  bool readUnsigned16(uint16_t* output) {
    uint64_t value = 0ULL;
    if (!readUnsigned64(&value)) return false;
    if (value > UINT16_MAX) {
      fail(Result::NumberOverflow);
      return false;
    }
    *output = static_cast<uint16_t>(value);
    return true;
  }

  bool readUnsigned8(uint8_t* output) {
    uint64_t value = 0ULL;
    if (!readUnsigned64(&value)) return false;
    if (value > UINT8_MAX) {
      fail(Result::NumberOverflow);
      return false;
    }
    *output = static_cast<uint8_t>(value);
    return true;
  }

  bool readSigned32(int32_t* output) {
    skipWhitespace();
    bool negative = false;
    if (position_ < length_ && input_[position_] == '-') {
      negative = true;
      ++position_;
      if (position_ >= length_ || input_[position_] < '0' || input_[position_] > '9') {
        fail(Result::MalformedJson);
        return false;
      }
    }
    uint64_t magnitude = 0ULL;
    if (!readUnsigned64(&magnitude)) return false;
    const uint64_t limit = negative ? 2147483648ULL : 2147483647ULL;
    if (magnitude > limit) {
      fail(Result::NumberOverflow);
      return false;
    }
    *output = negative
                  ? static_cast<int32_t>(-static_cast<int64_t>(magnitude))
                  : static_cast<int32_t>(magnitude);
    return true;
  }

  bool readBool(bool* output) {
    skipWhitespace();
    if (remainingStartsWith("true")) {
      position_ += 4U;
      *output = true;
      return true;
    }
    if (remainingStartsWith("false")) {
      position_ += 5U;
      *output = false;
      return true;
    }
    fail(Result::WrongType);
    return false;
  }

  Result finish() {
    if (result_ != Result::Ok) return result_;
    skipWhitespace();
    return position_ == length_ ? Result::Ok : Result::TrailingData;
  }

  Result result() const { return result_; }

 private:
  static int hexValue(char value) {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10;
    return -1;
  }

  void skipWhitespace() {
    while (position_ < length_ &&
           (input_[position_] == ' ' || input_[position_] == '\t' ||
            input_[position_] == '\r' || input_[position_] == '\n')) {
      ++position_;
    }
  }

  bool punctuation(char expected) {
    skipWhitespace();
    if (position_ >= length_ || input_[position_] != expected) {
      fail(Result::MalformedJson);
      return false;
    }
    ++position_;
    return true;
  }

  bool remainingStartsWith(const char* value) const {
    const size_t count = std::strlen(value);
    return count <= length_ - position_ &&
           std::memcmp(input_ + position_, value, count) == 0;
  }

  void fail(Result result) {
    if (result_ == Result::Ok) result_ = result;
  }

  const char* input_;
  size_t length_;
  size_t position_;
  Result result_;
};

template <size_t N>
bool hasTerminator(const char (&value)[N]) {
  return std::memchr(value, '\0', N) != nullptr;
}

bool isSafeToken(const char* value, size_t maximum_length, bool allow_empty) {
  const size_t length = std::strlen(value);
  if ((!allow_empty && length == 0U) || length > maximum_length) return false;
  for (size_t index = 0U; index < length; ++index) {
    const char byte = value[index];
    if (!((byte >= 'a' && byte <= 'z') || (byte >= 'A' && byte <= 'Z') ||
          (byte >= '0' && byte <= '9') || byte == '-' || byte == '_' || byte == '.')) {
      return false;
    }
  }
  return true;
}

bool validFanDuty(uint8_t value) {
  return value == 0U || value == 30U || value == 60U || value == 100U;
}

bool validBrightness(uint8_t value) {
  return value == 25U || value == 50U || value == 75U || value == 100U;
}

bool validQuality(Quality value) {
  return static_cast<uint8_t>(value) <= static_cast<uint8_t>(Quality::Invalid);
}

bool validTimestamp(uint64_t value, uint64_t generated_at_ms, Quality quality) {
  if (quality == Quality::Unknown && value == 0ULL) return true;
  return value >= kMinEpochMs && value <= kMaxEpochMilliseconds &&
         value <= generated_at_ms;
}

Result validateReading(const Reading& reading, int32_t minimum, int32_t maximum,
                       uint64_t generated_at_ms) {
  if (!validQuality(reading.quality)) return Result::InvalidEnum;
  if (reading.value < minimum || reading.value > maximum ||
      !validTimestamp(reading.sampled_at_ms, generated_at_ms, reading.quality)) {
    return Result::OutOfRange;
  }
  return Result::Ok;
}

Result validateSnapshot(const ScreenSnapshot& value) {
  if (!hasTerminator(value.source) || std::strcmp(value.source, "CTRL-01") != 0) {
    return Result::InvalidTarget;
  }
  if (value.generated_at_ms < kMinEpochMs ||
      value.generated_at_ms > kMaxEpochMilliseconds) {
    return Result::OutOfRange;
  }
  Result result = validateReading(value.temperature, -5000, 10000,
                                  value.generated_at_ms);
  if (result != Result::Ok) return result;
  result = validateReading(value.humidity, 0, 10000, value.generated_at_ms);
  if (result != Result::Ok) return result;
  result = validateReading(value.oxygen, 0, 100000, value.generated_at_ms);
  if (result != Result::Ok) return result;
  result = validateReading(value.methane, 0, 100000, value.generated_at_ms);
  if (result != Result::Ok) return result;
  result = validateReading(value.carbon_monoxide, 0, 100000,
                           value.generated_at_ms);
  if (result != Result::Ok) return result;
  result = validateReading(value.smoke, 0, 4095, value.generated_at_ms);
  if (result != Result::Ok) return result;
  result = validateReading(value.water, 0, 4095, value.generated_at_ms);
  if (result != Result::Ok) return result;
  result = validateReading(value.flame, 0, 1, value.generated_at_ms);
  if (result != Result::Ok) return result;
  if (static_cast<uint8_t>(value.alarm_severity) >
      static_cast<uint8_t>(AlarmSeverity::Critical)) {
    return Result::InvalidEnum;
  }
  if ((value.warning_sources & ~kAlarmSourceMask) != 0U ||
      (value.critical_sources & ~kAlarmSourceMask) != 0U) {
    return Result::OutOfRange;
  }
  for (size_t index = 0U; index < 2U; ++index) {
    const FanSnapshot& fan = value.fans[index];
    if (!validQuality(fan.quality)) return Result::InvalidEnum;
    if (!validFanDuty(fan.target_duty_percent) || fan.actual_rpm > 100000U ||
        fan.voltage_mv > 36000U || fan.current_ma > 10000U ||
        !validTimestamp(fan.sampled_at_ms, value.generated_at_ms, fan.quality)) {
      return Result::OutOfRange;
    }
  }
  if (value.actuators.led_mode > 7U ||
      !validBrightness(value.actuators.led_brightness_percent)) {
    return Result::OutOfRange;
  }
  if (value.connectivity.updated_at_ms < kMinEpochMs ||
      value.connectivity.updated_at_ms > value.generated_at_ms) {
    return Result::OutOfRange;
  }
  if (!hasTerminator(value.last_command.command_id)) return Result::InvalidIdentifier;
  if (value.last_command.complete) {
    if (!isSafeToken(value.last_command.command_id, kCommandIdCapacity - 1U, false)) {
      return Result::InvalidIdentifier;
    }
    if (value.last_command.completed_at_ms < kMinEpochMs ||
        value.last_command.completed_at_ms > value.generated_at_ms) {
      return Result::OutOfRange;
    }
  } else {
    if (!isSafeToken(value.last_command.command_id, kCommandIdCapacity - 1U, true)) {
      return Result::InvalidIdentifier;
    }
    if (value.last_command.accepted || value.last_command.completed_at_ms != 0ULL) {
      return Result::OutOfRange;
    }
  }
  return Result::Ok;
}

Result validateCommand(const MenuCommand& value) {
  if (!hasTerminator(value.command_id) ||
      !isSafeToken(value.command_id, kCommandIdCapacity - 1U, false)) {
    return Result::InvalidIdentifier;
  }
  if (!hasTerminator(value.target) || std::strcmp(value.target, "CTRL-01") != 0) {
    return Result::InvalidTarget;
  }
  if (static_cast<uint8_t>(value.action) >
      static_cast<uint8_t>(CommandAction::BuzzerRestore)) {
    return Result::InvalidEnum;
  }
  switch (value.action) {
    case CommandAction::Fan1Duty:
    case CommandAction::Fan2Duty:
      if (!validFanDuty(value.value)) return Result::OutOfRange;
      break;
    case CommandAction::LedMode:
      if (value.value > 7U) return Result::OutOfRange;
      break;
    case CommandAction::LedBrightness:
      if (!validBrightness(value.value)) return Result::OutOfRange;
      break;
    case CommandAction::FansBothStart:
    case CommandAction::FansAllStop:
    case CommandAction::BuzzerTest:
    case CommandAction::BuzzerMute:
    case CommandAction::BuzzerRestore:
      if (value.value != 0U) return Result::OutOfRange;
      break;
  }
  if (value.created_at_ms < kMinEpochMs ||
      value.created_at_ms > kMaxEpochMilliseconds || value.ttl_ms == 0U ||
      value.ttl_ms > kCommandMaxTtlMs) {
    return Result::OutOfRange;
  }
  return Result::Ok;
}

Result validateAck(const CommandAck& value) {
  if (!hasTerminator(value.command_id) ||
      !isSafeToken(value.command_id, kCommandIdCapacity - 1U, false)) {
    return Result::InvalidIdentifier;
  }
  if (static_cast<uint8_t>(value.status) > static_cast<uint8_t>(AckStatus::Expired)) {
    return Result::InvalidEnum;
  }
  if (!hasTerminator(value.reason) ||
      !isSafeToken(value.reason, kAckReasonCapacity - 1U, false)) {
    return Result::InvalidString;
  }
  if (value.applied_value < 0 || value.applied_value > 100 ||
      value.completed_at_ms < kMinEpochMs ||
      value.completed_at_ms > kMaxEpochMilliseconds) {
    return Result::OutOfRange;
  }
  return Result::Ok;
}

Result validateTime(const TimeSync& value) {
  if (static_cast<uint8_t>(value.source) > static_cast<uint8_t>(TimeSource::Snapshot) ||
      static_cast<uint8_t>(value.state) > static_cast<uint8_t>(TimeState::Holdover)) {
    return Result::InvalidEnum;
  }
  if (value.epoch_seconds < kMinEpochSeconds ||
      value.epoch_seconds > kMaxEpochSeconds) {
    return Result::OutOfRange;
  }
  return Result::Ok;
}

const char* actionText(CommandAction action) {
  static const char* const values[] = {
      "fan1_duty",       "fans_both_start", "fans_all_stop",
      "fan2_duty",       "led_mode",        "led_brightness",
      "buzzer_test",     "buzzer_mute",     "buzzer_restore",
  };
  return values[static_cast<uint8_t>(action)];
}

bool parseAction(const char* text, CommandAction* action) {
  for (uint8_t index = 0U; index <= static_cast<uint8_t>(CommandAction::BuzzerRestore);
       ++index) {
    const CommandAction candidate = static_cast<CommandAction>(index);
    if (std::strcmp(text, actionText(candidate)) == 0) {
      *action = candidate;
      return true;
    }
  }
  return false;
}

const char* ackStatusText(AckStatus status) {
  static const char* const values[] = {"accepted", "rejected", "duplicate", "expired"};
  return values[static_cast<uint8_t>(status)];
}

bool parseAckStatus(const char* text, AckStatus* status) {
  for (uint8_t index = 0U; index <= static_cast<uint8_t>(AckStatus::Expired); ++index) {
    const AckStatus candidate = static_cast<AckStatus>(index);
    if (std::strcmp(text, ackStatusText(candidate)) == 0) {
      *status = candidate;
      return true;
    }
  }
  return false;
}

const char* timeSourceText(TimeSource source) {
  return source == TimeSource::Ntp ? "ntp" : "snapshot";
}

bool parseTimeSource(const char* text, TimeSource* source) {
  if (std::strcmp(text, "ntp") == 0) {
    *source = TimeSource::Ntp;
    return true;
  }
  if (std::strcmp(text, "snapshot") == 0) {
    *source = TimeSource::Snapshot;
    return true;
  }
  return false;
}

const char* timeStateText(TimeState state) {
  return state == TimeState::Synchronized ? "synchronized" : "holdover";
}

bool parseTimeState(const char* text, TimeState* state) {
  if (std::strcmp(text, "synchronized") == 0) {
    *state = TimeState::Synchronized;
    return true;
  }
  if (std::strcmp(text, "holdover") == 0) {
    *state = TimeState::Holdover;
    return true;
  }
  return false;
}

Result prepareOutput(char* output, size_t output_capacity, size_t* written) {
  if (written != nullptr) *written = 0U;
  if (output != nullptr && output_capacity > 0U) output[0] = '\0';
  if (output == nullptr || written == nullptr) return Result::NullArgument;
  if (output_capacity == 0U) return Result::OutputTooSmall;
  return Result::Ok;
}

Result finishOutput(Writer* writer, char* output, size_t* written) {
  if (writer->requiredSize() > kUartLineLimit) {
    output[0] = '\0';
    *written = 0U;
    return Result::TooLarge;
  }
  if (writer->finish(written)) return Result::Ok;
  output[0] = '\0';
  *written = 0U;
  return Result::OutputTooSmall;
}

Result validateInput(const char* json, size_t length, const void* output) {
  if (json == nullptr || output == nullptr) return Result::NullArgument;
  if (length > kUartLineLimit) return Result::TooLarge;
  if (length == 0U) return Result::MalformedJson;
  return Result::Ok;
}

void writeReading(Writer* writer, const Reading& reading) {
  writer->character('[');
  writer->signedNumber(reading.value);
  writer->character(',');
  writer->unsignedNumber(reading.sampled_at_ms);
  writer->character(',');
  writer->unsignedNumber(static_cast<uint8_t>(reading.quality));
  writer->character(']');
}

bool parseReading(Reader* reader, Reading* reading) {
  uint8_t quality = 0U;
  if (!reader->beginArray() || !reader->readSigned32(&reading->value) ||
      !reader->comma() || !reader->readUnsigned64(&reading->sampled_at_ms) ||
      !reader->comma() || !reader->readUnsigned8(&quality) || !reader->endArray()) {
    return false;
  }
  reading->quality = static_cast<Quality>(quality);
  return true;
}

void writeFan(Writer* writer, const FanSnapshot& fan) {
  writer->character('[');
  writer->unsignedNumber(fan.target_duty_percent);
  writer->character(',');
  writer->boolean(fan.running);
  writer->character(',');
  writer->unsignedNumber(fan.actual_rpm);
  writer->character(',');
  writer->unsignedNumber(fan.voltage_mv);
  writer->character(',');
  writer->unsignedNumber(fan.current_ma);
  writer->character(',');
  writer->unsignedNumber(fan.sampled_at_ms);
  writer->character(',');
  writer->unsignedNumber(static_cast<uint8_t>(fan.quality));
  writer->character(']');
}

bool parseFan(Reader* reader, FanSnapshot* fan) {
  uint8_t quality = 0U;
  if (!reader->beginArray() || !reader->readUnsigned8(&fan->target_duty_percent) ||
      !reader->comma() || !reader->readBool(&fan->running) || !reader->comma() ||
      !reader->readUnsigned32(&fan->actual_rpm) || !reader->comma() ||
      !reader->readUnsigned16(&fan->voltage_mv) || !reader->comma() ||
      !reader->readUnsigned16(&fan->current_ma) || !reader->comma() ||
      !reader->readUnsigned64(&fan->sampled_at_ms) || !reader->comma() ||
      !reader->readUnsigned8(&quality) || !reader->endArray()) {
    return false;
  }
  fan->quality = static_cast<Quality>(quality);
  return true;
}

Result readSchema(Reader* reader, const char* expected) {
  char schema[32];
  if (!reader->beginObject() || !reader->key("schema") ||
      !reader->readString(schema, sizeof(schema))) {
    return reader->result();
  }
  return std::strcmp(schema, expected) == 0 ? Result::Ok : Result::UnknownSchema;
}

Result readerFailure(const Reader& reader) {
  return reader.result() == Result::Ok ? Result::MalformedJson : reader.result();
}

}  // namespace

Result BuildSnapshot(const ScreenSnapshot& snapshot, char* output,
                     size_t output_capacity, size_t* written) {
  Result result = prepareOutput(output, output_capacity, written);
  if (result != Result::Ok) return result;
  result = validateSnapshot(snapshot);
  if (result != Result::Ok) return result;

  Writer writer(output, output_capacity);
  writer.literal("{\"schema\":\"");
  writer.literal(kSnapshotSchema);
  writer.literal("\",\"source\":");
  writer.string(snapshot.source);
  writer.literal(",\"generatedAtMs\":");
  writer.unsignedNumber(snapshot.generated_at_ms);
  writer.literal(",\"seq\":");
  writer.unsignedNumber(snapshot.sequence);
  writer.literal(",\"sensors\":{\"temperature\":");
  writeReading(&writer, snapshot.temperature);
  writer.literal(",\"humidity\":");
  writeReading(&writer, snapshot.humidity);
  writer.literal(",\"oxygen\":");
  writeReading(&writer, snapshot.oxygen);
  writer.literal(",\"methane\":");
  writeReading(&writer, snapshot.methane);
  writer.literal(",\"carbonMonoxide\":");
  writeReading(&writer, snapshot.carbon_monoxide);
  writer.literal(",\"smoke\":");
  writeReading(&writer, snapshot.smoke);
  writer.literal(",\"water\":");
  writeReading(&writer, snapshot.water);
  writer.literal(",\"flame\":");
  writeReading(&writer, snapshot.flame);
  writer.literal("},\"alarm\":[");
  writer.unsignedNumber(static_cast<uint8_t>(snapshot.alarm_severity));
  writer.character(',');
  writer.unsignedNumber(snapshot.warning_sources);
  writer.character(',');
  writer.unsignedNumber(snapshot.critical_sources);
  writer.literal("],\"fans\":[");
  writeFan(&writer, snapshot.fans[0]);
  writer.character(',');
  writeFan(&writer, snapshot.fans[1]);
  writer.literal("],\"actuators\":[");
  writer.boolean(snapshot.actuators.relay_on);
  writer.character(',');
  writer.unsignedNumber(snapshot.actuators.led_mode);
  writer.character(',');
  writer.unsignedNumber(snapshot.actuators.led_brightness_percent);
  writer.character(',');
  writer.boolean(snapshot.actuators.buzzer_on);
  writer.character(',');
  writer.boolean(snapshot.actuators.buzzer_muted);
  writer.literal("],\"connectivity\":[");
  writer.boolean(snapshot.connectivity.node_a_online);
  writer.character(',');
  writer.boolean(snapshot.connectivity.gateway_online);
  writer.character(',');
  writer.boolean(snapshot.connectivity.iotda_online);
  writer.character(',');
  writer.boolean(snapshot.connectivity.mqtt_online);
  writer.character(',');
  writer.unsignedNumber(snapshot.connectivity.updated_at_ms);
  writer.literal("],\"lastCommand\":[");
  writer.string(snapshot.last_command.command_id);
  writer.character(',');
  writer.boolean(snapshot.last_command.accepted);
  writer.character(',');
  writer.boolean(snapshot.last_command.complete);
  writer.character(',');
  writer.unsignedNumber(snapshot.last_command.completed_at_ms);
  writer.literal("]}");
  return finishOutput(&writer, output, written);
}

Result ParseSnapshot(const char* json, size_t length, uint64_t now_epoch_ms,
                     ScreenSnapshot* snapshot) {
  Result result = validateInput(json, length, snapshot);
  if (result != Result::Ok) return result;
  Reader reader(json, length);
  result = readSchema(&reader, kSnapshotSchema);
  if (result != Result::Ok) return result;
  ScreenSnapshot value{};
  uint8_t severity = 0U;

  if (!reader.comma() || !reader.key("source") ||
      !reader.readString(value.source, sizeof(value.source)) || !reader.comma() ||
      !reader.key("generatedAtMs") ||
      !reader.readUnsigned64(&value.generated_at_ms) || !reader.comma() ||
      !reader.key("seq") || !reader.readUnsigned32(&value.sequence) ||
      !reader.comma() || !reader.key("sensors") || !reader.beginObject() ||
      !reader.key("temperature") || !parseReading(&reader, &value.temperature) ||
      !reader.comma() || !reader.key("humidity") ||
      !parseReading(&reader, &value.humidity) || !reader.comma() ||
      !reader.key("oxygen") || !parseReading(&reader, &value.oxygen) ||
      !reader.comma() || !reader.key("methane") ||
      !parseReading(&reader, &value.methane) || !reader.comma() ||
      !reader.key("carbonMonoxide") ||
      !parseReading(&reader, &value.carbon_monoxide) || !reader.comma() ||
      !reader.key("smoke") || !parseReading(&reader, &value.smoke) ||
      !reader.comma() || !reader.key("water") ||
      !parseReading(&reader, &value.water) || !reader.comma() ||
      !reader.key("flame") || !parseReading(&reader, &value.flame) ||
      !reader.endObject() || !reader.comma() || !reader.key("alarm") ||
      !reader.beginArray() || !reader.readUnsigned8(&severity) ||
      !reader.comma() || !reader.readUnsigned32(&value.warning_sources) ||
      !reader.comma() || !reader.readUnsigned32(&value.critical_sources) ||
      !reader.endArray() || !reader.comma() || !reader.key("fans") ||
      !reader.beginArray() || !parseFan(&reader, &value.fans[0]) ||
      !reader.comma() || !parseFan(&reader, &value.fans[1]) ||
      !reader.endArray() || !reader.comma() || !reader.key("actuators") ||
      !reader.beginArray() || !reader.readBool(&value.actuators.relay_on) ||
      !reader.comma() || !reader.readUnsigned8(&value.actuators.led_mode) ||
      !reader.comma() ||
      !reader.readUnsigned8(&value.actuators.led_brightness_percent) ||
      !reader.comma() || !reader.readBool(&value.actuators.buzzer_on) ||
      !reader.comma() || !reader.readBool(&value.actuators.buzzer_muted) ||
      !reader.endArray() || !reader.comma() || !reader.key("connectivity") ||
      !reader.beginArray() ||
      !reader.readBool(&value.connectivity.node_a_online) || !reader.comma() ||
      !reader.readBool(&value.connectivity.gateway_online) || !reader.comma() ||
      !reader.readBool(&value.connectivity.iotda_online) || !reader.comma() ||
      !reader.readBool(&value.connectivity.mqtt_online) || !reader.comma() ||
      !reader.readUnsigned64(&value.connectivity.updated_at_ms) ||
      !reader.endArray() || !reader.comma() || !reader.key("lastCommand") ||
      !reader.beginArray() ||
      !reader.readString(value.last_command.command_id,
                         sizeof(value.last_command.command_id),
                         Result::InvalidIdentifier) ||
      !reader.comma() || !reader.readBool(&value.last_command.accepted) ||
      !reader.comma() || !reader.readBool(&value.last_command.complete) ||
      !reader.comma() ||
      !reader.readUnsigned64(&value.last_command.completed_at_ms) ||
      !reader.endArray() || !reader.endObject()) {
    return readerFailure(reader);
  }
  result = reader.finish();
  if (result != Result::Ok) return result;
  value.alarm_severity = static_cast<AlarmSeverity>(severity);
  result = validateSnapshot(value);
  if (result != Result::Ok) return result;
  if (now_epoch_ms < value.generated_at_ms ||
      now_epoch_ms - value.generated_at_ms > kSnapshotMaxAgeMs) {
    return Result::Stale;
  }
  *snapshot = value;
  return Result::Ok;
}

Result BuildMenuCommand(const MenuCommand& command, char* output,
                        size_t output_capacity, size_t* written) {
  Result result = prepareOutput(output, output_capacity, written);
  if (result != Result::Ok) return result;
  result = validateCommand(command);
  if (result != Result::Ok) return result;
  Writer writer(output, output_capacity);
  writer.literal("{\"schema\":\"");
  writer.literal(kMenuCommandSchema);
  writer.literal("\",\"cmdId\":");
  writer.string(command.command_id);
  writer.literal(",\"target\":");
  writer.string(command.target);
  writer.literal(",\"action\":");
  writer.string(actionText(command.action));
  writer.literal(",\"value\":");
  writer.unsignedNumber(command.value);
  writer.literal(",\"createdAtMs\":");
  writer.unsignedNumber(command.created_at_ms);
  writer.literal(",\"ttlMs\":");
  writer.unsignedNumber(command.ttl_ms);
  writer.character('}');
  return finishOutput(&writer, output, written);
}

Result ParseMenuCommand(const char* json, size_t length, uint64_t now_epoch_ms,
                        MenuCommand* command) {
  Result result = validateInput(json, length, command);
  if (result != Result::Ok) return result;
  Reader reader(json, length);
  result = readSchema(&reader, kMenuCommandSchema);
  if (result != Result::Ok) return result;
  MenuCommand value{};
  char action[24];
  if (!reader.comma() || !reader.key("cmdId") ||
      !reader.readString(value.command_id, sizeof(value.command_id),
                         Result::InvalidIdentifier) ||
      !reader.comma() || !reader.key("target") ||
      !reader.readString(value.target, sizeof(value.target)) || !reader.comma() ||
      !reader.key("action") || !reader.readString(action, sizeof(action)) ||
      !reader.comma() || !reader.key("value") ||
      !reader.readUnsigned8(&value.value) || !reader.comma() ||
      !reader.key("createdAtMs") ||
      !reader.readUnsigned64(&value.created_at_ms) || !reader.comma() ||
      !reader.key("ttlMs") || !reader.readUnsigned32(&value.ttl_ms) ||
      !reader.endObject()) {
    return readerFailure(reader);
  }
  result = reader.finish();
  if (result != Result::Ok) return result;
  if (!parseAction(action, &value.action)) return Result::InvalidEnum;
  result = validateCommand(value);
  if (result != Result::Ok) return result;
  if (now_epoch_ms < value.created_at_ms ||
      now_epoch_ms - value.created_at_ms >= value.ttl_ms) {
    return Result::Expired;
  }
  *command = value;
  return Result::Ok;
}

Result BuildCommandAck(const CommandAck& acknowledgement, char* output,
                       size_t output_capacity, size_t* written) {
  Result result = prepareOutput(output, output_capacity, written);
  if (result != Result::Ok) return result;
  result = validateAck(acknowledgement);
  if (result != Result::Ok) return result;
  Writer writer(output, output_capacity);
  writer.literal("{\"schema\":\"");
  writer.literal(kCommandAckSchema);
  writer.literal("\",\"cmdId\":");
  writer.string(acknowledgement.command_id);
  writer.literal(",\"status\":");
  writer.string(ackStatusText(acknowledgement.status));
  writer.literal(",\"reason\":");
  writer.string(acknowledgement.reason);
  writer.literal(",\"appliedValue\":");
  writer.signedNumber(acknowledgement.applied_value);
  writer.literal(",\"completedAtMs\":");
  writer.unsignedNumber(acknowledgement.completed_at_ms);
  writer.character('}');
  return finishOutput(&writer, output, written);
}

Result ParseCommandAck(const char* json, size_t length,
                       CommandAck* acknowledgement) {
  Result result = validateInput(json, length, acknowledgement);
  if (result != Result::Ok) return result;
  Reader reader(json, length);
  result = readSchema(&reader, kCommandAckSchema);
  if (result != Result::Ok) return result;
  CommandAck value{};
  char status[16];
  if (!reader.comma() || !reader.key("cmdId") ||
      !reader.readString(value.command_id, sizeof(value.command_id),
                         Result::InvalidIdentifier) ||
      !reader.comma() || !reader.key("status") ||
      !reader.readString(status, sizeof(status)) || !reader.comma() ||
      !reader.key("reason") ||
      !reader.readString(value.reason, sizeof(value.reason)) || !reader.comma() ||
      !reader.key("appliedValue") ||
      !reader.readSigned32(&value.applied_value) || !reader.comma() ||
      !reader.key("completedAtMs") ||
      !reader.readUnsigned64(&value.completed_at_ms) || !reader.endObject()) {
    return readerFailure(reader);
  }
  result = reader.finish();
  if (result != Result::Ok) return result;
  if (!parseAckStatus(status, &value.status)) return Result::InvalidEnum;
  result = validateAck(value);
  if (result != Result::Ok) return result;
  *acknowledgement = value;
  return Result::Ok;
}

Result BuildTimeSync(const TimeSync& time_sync, char* output,
                     size_t output_capacity, size_t* written) {
  Result result = prepareOutput(output, output_capacity, written);
  if (result != Result::Ok) return result;
  result = validateTime(time_sync);
  if (result != Result::Ok) return result;
  Writer writer(output, output_capacity);
  writer.literal("{\"schema\":\"");
  writer.literal(kTimeSyncSchema);
  writer.literal("\",\"source\":");
  writer.string(timeSourceText(time_sync.source));
  writer.literal(",\"state\":");
  writer.string(timeStateText(time_sync.state));
  writer.literal(",\"epochSeconds\":");
  writer.unsignedNumber(time_sync.epoch_seconds);
  writer.literal(",\"seq\":");
  writer.unsignedNumber(time_sync.sequence);
  writer.character('}');
  return finishOutput(&writer, output, written);
}

Result ParseTimeSync(const char* json, size_t length, TimeSync* time_sync) {
  Result result = validateInput(json, length, time_sync);
  if (result != Result::Ok) return result;
  Reader reader(json, length);
  result = readSchema(&reader, kTimeSyncSchema);
  if (result != Result::Ok) return result;
  TimeSync value{};
  char source[16];
  char state[16];
  if (!reader.comma() || !reader.key("source") ||
      !reader.readString(source, sizeof(source)) || !reader.comma() ||
      !reader.key("state") || !reader.readString(state, sizeof(state)) ||
      !reader.comma() || !reader.key("epochSeconds") ||
      !reader.readUnsigned64(&value.epoch_seconds) || !reader.comma() ||
      !reader.key("seq") || !reader.readUnsigned32(&value.sequence) ||
      !reader.endObject()) {
    return readerFailure(reader);
  }
  result = reader.finish();
  if (result != Result::Ok) return result;
  if (!parseTimeSource(source, &value.source) || !parseTimeState(state, &value.state)) {
    return Result::InvalidEnum;
  }
  result = validateTime(value);
  if (result != Result::Ok) return result;
  *time_sync = value;
  return Result::Ok;
}

}  // namespace screen_protocol
