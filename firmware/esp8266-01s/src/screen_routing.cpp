#include "screen_routing.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace screen_routing {
namespace {
#if defined(BUILD_ROLE_CTRL01)
#define SCREEN_ROUTING_CTRL01 1
#define SCREEN_ROUTING_CTRL02 0
#elif defined(BUILD_ROLE_CTRL02)
#define SCREEN_ROUTING_CTRL01 0
#define SCREEN_ROUTING_CTRL02 1
#else
#define SCREEN_ROUTING_CTRL01 1
#define SCREEN_ROUTING_CTRL02 1
#endif

using screen_protocol::AckStatus;
using screen_protocol::AlarmSeverity;
using screen_protocol::BuildCommandAck;
using screen_protocol::BuildMenuCommand;
using screen_protocol::BuildSnapshot;
using screen_protocol::BuildTimeSync;
using screen_protocol::CommandAck;
using screen_protocol::CommandAction;
using screen_protocol::LinkStatus;
using screen_protocol::MenuCommand;
using screen_protocol::ParseCommandAck;
using screen_protocol::ParseMenuCommand;
using screen_protocol::Quality;
using screen_protocol::Result;
using screen_protocol::ScreenSnapshot;
using screen_protocol::TimeSource;
using screen_protocol::TimeState;
using screen_protocol::TimeSync;
using screen_protocol::kMaxEpochSeconds;
using screen_protocol::kMinEpochSeconds;
using screen_protocol::kUartLineLimit;

constexpr char kCtrl01MenuCommand[] = "ut/v1/CTRL-01/cmd/menu";

/* The local alarm-source bits the screen renders.  They mirror
 * UiAlarmSource in firmware/stm32f103rct6/Core/Inc/ui_model.h: the gas status
 * frame is the only place the methane bit can come from, and it has to reach
 * the display or a gas alarm would never raise the critical overlay. */
constexpr uint32_t kSourceOxygen = 1U << 2U;
constexpr uint32_t kSourceMethane = 1U << 3U;
constexpr uint32_t kSourceCarbonMonoxide = 1U << 4U;
constexpr uint32_t kSourceSmoke = 1U << 5U;
constexpr uint32_t kSourceWater = 1U << 6U;
constexpr uint32_t kSourceFlame = 1U << 7U;
constexpr uint32_t kAlarmSourceAll =
    kSourceOxygen | kSourceMethane | kSourceCarbonMonoxide | kSourceSmoke |
    kSourceWater | kSourceFlame;
#if SCREEN_ROUTING_CTRL01
constexpr char kCtrl01CommandWildcard[] = "ut/v1/CTRL-01/cmd/#";
#endif
#if SCREEN_ROUTING_CTRL02
constexpr char kCtrl01Telemetry[] = "ut/v1/CTRL-01/telemetry";
constexpr char kCtrl01CommandAck[] = "ut/v1/CTRL-01/cmd_ack";
#endif

#if SCREEN_ROUTING_CTRL01
// `cmd/#` already matches `cmd/menu`, so a separate menu subscription would
// deliver a single menu command twice and emit two UART commands.
const RouteTopics kCtrl01Topics = {
    {kCtrl01CommandWildcard, nullptr}, 1U, nullptr};
#endif
#if SCREEN_ROUTING_CTRL02
const RouteTopics kCtrl02Topics = {
    {kCtrl01Telemetry, kCtrl01CommandAck}, 2U, kCtrl01MenuCommand};
#endif

void clearOutput(RouteOutput* output) {
  if (output == nullptr) return;
  std::memset(output, 0, sizeof(*output));
  output->kind = OutputKind::None;
}

void prepareRawOutput(char* output, size_t output_capacity, size_t* written) {
  if (written != nullptr) *written = 0U;
  if (output != nullptr && output_capacity != 0U) output[0] = '\0';
}

RouteResult mapProtocolResult(Result result) {
  if (result == Result::Ok) return RouteResult::Ok;
  if (result == Result::TooLarge) return RouteResult::TooLarge;
  if (result == Result::OutputTooSmall) return RouteResult::OutputTooSmall;
  if (result == Result::Expired) return RouteResult::Expired;
  if (result == Result::Stale) return RouteResult::Stale;
  return RouteResult::InvalidPayload;
}

#if SCREEN_ROUTING_CTRL01
const char* actionText(CommandAction action) {
  static const char* const names[] = {
      "fan1_duty",       "fans_both_start", "fans_all_stop",
      "fan2_duty",       "led_mode",        "led_brightness",
      "buzzer_test",     "buzzer_mute",     "buzzer_restore",
  };
  const size_t index = static_cast<size_t>(action);
  return index < sizeof(names) / sizeof(names[0]) ? names[index] : "";
}
#endif

bool copyTopic(const char* topic, char* output) {
  const size_t length = std::strlen(topic);
  if (length >= kTopicCapacity) return false;
  std::memcpy(output, topic, length + 1U);
  return true;
}

#if SCREEN_ROUTING_CTRL02
class JsonSyntaxParser {
 public:
  JsonSyntaxParser(const char* begin, const char* end)
      : cursor_(begin), end_(end) {}

  bool parseObjectDocument() {
    skipWhitespace();
    if (cursor_ == end_ || *cursor_ != '{' || !parseValue(0U)) return false;
    skipWhitespace();
    return cursor_ == end_;
  }

 private:
  static bool isDigit(char value) { return value >= '0' && value <= '9'; }

  static bool isHex(char value) {
    return isDigit(value) || (value >= 'a' && value <= 'f') ||
           (value >= 'A' && value <= 'F');
  }

  void skipWhitespace() {
    while (cursor_ != end_ &&
           (*cursor_ == ' ' || *cursor_ == '\t' || *cursor_ == '\r' ||
            *cursor_ == '\n')) {
      ++cursor_;
    }
  }

  bool consume(char expected) {
    if (cursor_ == end_ || *cursor_ != expected) return false;
    ++cursor_;
    return true;
  }

  bool consumeLiteral(const char* literal) {
    while (*literal != '\0') {
      if (cursor_ == end_ || *cursor_ != *literal) return false;
      ++cursor_;
      ++literal;
    }
    return true;
  }

  bool parseString() {
    if (!consume('"')) return false;
    while (cursor_ != end_) {
      const unsigned char byte = static_cast<unsigned char>(*cursor_++);
      if (byte == '"') return true;
      if (byte < 0x20U) return false;
      if (byte != '\\') continue;
      if (cursor_ == end_) return false;
      const char escape = *cursor_++;
      if (escape == '"' || escape == '\\' || escape == '/' ||
          escape == 'b' || escape == 'f' || escape == 'n' ||
          escape == 'r' || escape == 't') {
        continue;
      }
      if (escape != 'u' || end_ - cursor_ < 4) return false;
      for (uint8_t index = 0U; index < 4U; ++index) {
        if (!isHex(*cursor_++)) return false;
      }
    }
    return false;
  }

  bool parseNumber() {
    if (cursor_ != end_ && *cursor_ == '-') ++cursor_;
    if (cursor_ == end_) return false;
    if (*cursor_ == '0') {
      ++cursor_;
      if (cursor_ != end_ && isDigit(*cursor_)) return false;
    } else {
      if (*cursor_ < '1' || *cursor_ > '9') return false;
      do {
        ++cursor_;
      } while (cursor_ != end_ && isDigit(*cursor_));
    }
    if (cursor_ != end_ && *cursor_ == '.') {
      ++cursor_;
      if (cursor_ == end_ || !isDigit(*cursor_)) return false;
      do {
        ++cursor_;
      } while (cursor_ != end_ && isDigit(*cursor_));
    }
    if (cursor_ != end_ && (*cursor_ == 'e' || *cursor_ == 'E')) {
      ++cursor_;
      if (cursor_ != end_ && (*cursor_ == '+' || *cursor_ == '-')) ++cursor_;
      if (cursor_ == end_ || !isDigit(*cursor_)) return false;
      do {
        ++cursor_;
      } while (cursor_ != end_ && isDigit(*cursor_));
    }
    return true;
  }

  bool parseArray(uint8_t depth) {
    if (!consume('[')) return false;
    skipWhitespace();
    if (consume(']')) return true;
    for (;;) {
      if (!parseValue(depth)) return false;
      skipWhitespace();
      if (consume(']')) return true;
      if (!consume(',')) return false;
      skipWhitespace();
    }
  }

  bool parseObject(uint8_t depth) {
    if (!consume('{')) return false;
    skipWhitespace();
    if (consume('}')) return true;
    for (;;) {
      if (!parseString()) return false;
      skipWhitespace();
      if (!consume(':')) return false;
      skipWhitespace();
      if (!parseValue(depth)) return false;
      skipWhitespace();
      if (consume('}')) return true;
      if (!consume(',')) return false;
      skipWhitespace();
    }
  }

  bool parseValue(uint8_t depth) {
    constexpr uint8_t kMaxJsonDepth = 16U;
    if (depth >= kMaxJsonDepth || cursor_ == end_) return false;
    if (*cursor_ == '{') return parseObject(static_cast<uint8_t>(depth + 1U));
    if (*cursor_ == '[') return parseArray(static_cast<uint8_t>(depth + 1U));
    if (*cursor_ == '"') return parseString();
    if (*cursor_ == 't') return consumeLiteral("true");
    if (*cursor_ == 'f') return consumeLiteral("false");
    if (*cursor_ == 'n') return consumeLiteral("null");
    return *cursor_ == '-' || isDigit(*cursor_) ? parseNumber() : false;
  }

  const char* cursor_;
  const char* const end_;
};

bool validJsonEnvelope(const char* json, size_t length) {
  if (json == nullptr || length == 0U || length > kTransportPayloadLimit) {
    return false;
  }
  JsonSyntaxParser parser(json, json + length);
  return parser.parseObjectDocument();
}

const char* findKey(const char* begin, const char* end, const char* key) {
  char needle[40];
  const int count = std::snprintf(needle, sizeof(needle), "\"%s\"", key);
  if (count <= 0 || static_cast<size_t>(count) >= sizeof(needle)) return nullptr;
  const size_t needle_length = static_cast<size_t>(count);
  for (const char* cursor = begin;
       cursor + needle_length <= end; ++cursor) {
    if (std::memcmp(cursor, needle, needle_length) == 0) return cursor;
  }
  return nullptr;
}

size_t countKey(const char* begin, const char* end, const char* key) {
  size_t count = 0U;
  const char* cursor = begin;
  while ((cursor = findKey(cursor, end, key)) != nullptr) {
    ++count;
    ++cursor;
  }
  return count;
}

const char* valueAfterKey(const char* begin, const char* end, const char* key) {
  const char* cursor = findKey(begin, end, key);
  if (cursor == nullptr) return nullptr;
  cursor += std::strlen(key) + 2U;
  while (cursor < end && (*cursor == ' ' || *cursor == '\t' ||
                          *cursor == '\r' || *cursor == '\n')) {
    ++cursor;
  }
  if (cursor == end || *cursor++ != ':') return nullptr;
  while (cursor < end && (*cursor == ' ' || *cursor == '\t' ||
                          *cursor == '\r' || *cursor == '\n')) {
    ++cursor;
  }
  return cursor < end ? cursor : nullptr;
}

bool readStringField(const char* begin, const char* end, const char* key,
                     char* output, size_t capacity) {
  if (countKey(begin, end, key) != 1U || output == nullptr || capacity == 0U) {
    return false;
  }
  const char* cursor = valueAfterKey(begin, end, key);
  if (cursor == nullptr || *cursor++ != '"') return false;
  size_t written = 0U;
  while (cursor < end && *cursor != '"') {
    const unsigned char byte = static_cast<unsigned char>(*cursor++);
    if (byte == '\\' || byte < 0x20U || byte >= 0x80U ||
        written + 1U >= capacity) {
      return false;
    }
    output[written++] = static_cast<char>(byte);
  }
  if (cursor == end || *cursor != '"') return false;
  output[written] = '\0';
  return true;
}

bool readNumberField(const char* begin, const char* end, const char* key,
                     double* output) {
  if (countKey(begin, end, key) != 1U || output == nullptr) return false;
  const char* cursor = valueAfterKey(begin, end, key);
  if (cursor == nullptr) return false;
  char token[32];
  size_t length = 0U;
  while (cursor < end && length + 1U < sizeof(token) &&
         ((*cursor >= '0' && *cursor <= '9') || *cursor == '-' ||
          *cursor == '+' || *cursor == '.' || *cursor == 'e' ||
          *cursor == 'E')) {
    token[length++] = *cursor++;
  }
  if (length == 0U || cursor == end ||
      !(*cursor == ',' || *cursor == '}' || *cursor == ']' ||
        *cursor == ' ' || *cursor == '\t' || *cursor == '\r' ||
        *cursor == '\n')) {
    return false;
  }
  token[length] = '\0';
  char* parse_end = nullptr;
  const double value = std::strtod(token, &parse_end);
  if (parse_end != token + length || !std::isfinite(value)) return false;
  *output = value;
  return true;
}

bool readUint32Field(const char* begin, const char* end, const char* key,
                     uint32_t* output) {
  double value = 0.0;
  if (!readNumberField(begin, end, key, &value) || value < 0.0 ||
      value > 4294967295.0 || std::floor(value) != value) {
    return false;
  }
  *output = static_cast<uint32_t>(value);
  return true;
}

const char* matchingDelimiter(const char* open, const char* end) {
  if (open == nullptr || open == end || (*open != '{' && *open != '[')) return nullptr;
  const char opening = *open;
  const char closing = opening == '{' ? '}' : ']';
  size_t depth = 0U;
  bool in_string = false;
  bool escaped = false;
  for (const char* cursor = open; cursor < end; ++cursor) {
    if (in_string) {
      if (escaped) escaped = false;
      else if (*cursor == '\\') escaped = true;
      else if (*cursor == '"') in_string = false;
      continue;
    }
    if (*cursor == '"') in_string = true;
    else if (*cursor == opening) ++depth;
    else if (*cursor == closing && --depth == 0U) return cursor;
  }
  return nullptr;
}

Quality parseQuality(const char* value) {
  if (std::strcmp(value, "good") == 0) return Quality::Valid;
  if (std::strcmp(value, "stale") == 0) return Quality::Stale;
  if (std::strcmp(value, "suspect") == 0 ||
      std::strcmp(value, "bad") == 0 ||
      std::strcmp(value, "missing") == 0) {
    return Quality::Invalid;
  }
  return Quality::Unknown;
}

bool roundedInRange(double value, double scale, int64_t minimum,
                    int64_t maximum, int64_t* output) {
  const double scaled = value * scale;
  if (!std::isfinite(scaled) || scaled < static_cast<double>(minimum) - 0.5 ||
      scaled > static_cast<double>(maximum) + 0.5) {
    return false;
  }
  const int64_t rounded = static_cast<int64_t>(std::llround(scaled));
  if (rounded < minimum || rounded > maximum) return false;
  *output = rounded;
  return true;
}

/* Recognising a metric means the frame carrying it may never be rejected for
 * an unknown reading.  The list therefore covers every metric Node A emits on
 * ut/v1/CTRL-01/telemetry, not only the ones the screen stores: raw ADC codes
 * and their millivolt conversions are reported for the cloud contract and are
 * validated here without being carried into the snapshot. */
bool isKnownReading(const char* asset, const char* metric) {
  if (std::strcmp(asset, "ENV-01") == 0 &&
      (std::strcmp(metric, "temperature") == 0 ||
       std::strcmp(metric, "humidity") == 0)) {
    return true;
  }
  if ((std::strcmp(asset, "FAN-01") == 0 ||
       std::strcmp(asset, "FAN-02") == 0) &&
      (std::strcmp(metric, "supply.voltage") == 0 ||
       std::strcmp(metric, "motor.current") == 0 ||
       std::strcmp(metric, "rotational.speed") == 0 ||
       std::strcmp(metric, "power") == 0)) {
    return true;
  }
  if ((std::strcmp(asset, "GAS-01") == 0) &&
      (std::strcmp(metric, "oxygen.raw") == 0 ||
       std::strcmp(metric, "oxygen.voltage") == 0 ||
       std::strcmp(metric, "methane.raw") == 0 ||
       std::strcmp(metric, "methane.voltage") == 0 ||
       std::strcmp(metric, "co.raw") == 0 ||
       std::strcmp(metric, "co.voltage") == 0)) {
    return true;
  }
  if (std::strcmp(metric, "oxygen.concentration") == 0 ||
      std::strcmp(metric, "methane.concentration") == 0 ||
      std::strcmp(metric, "methane.ppm") == 0 ||
      std::strcmp(metric, "carbon_monoxide.concentration") == 0 ||
      std::strcmp(metric, "carbonMonoxide.concentration") == 0 ||
      std::strcmp(metric, "co.concentration") == 0 ||
      std::strcmp(metric, "oxygen.warning") == 0 ||
      std::strcmp(metric, "oxygen.alarm") == 0 ||
      std::strcmp(metric, "methane.warning") == 0 ||
      std::strcmp(metric, "methane.alarm") == 0 ||
      std::strcmp(metric, "co.warning") == 0 ||
      std::strcmp(metric, "co.alarm") == 0 ||
      std::strcmp(metric, "smoke.alarm") == 0 ||
      std::strcmp(metric, "level.detected") == 0 ||
      std::strcmp(metric, "water.raw") == 0 ||
      std::strcmp(metric, "flame.alarm") == 0 ||
      std::strcmp(metric, "flame.rawLevel") == 0) {
    return true;
  }
  return std::strcmp(asset, "CTRL-01") == 0 &&
         (std::strcmp(metric, "led.mode") == 0 ||
          std::strcmp(metric, "led.brightnessPercent") == 0 ||
          std::strcmp(metric, "buzzer.active") == 0 ||
          std::strcmp(metric, "buzzer.muted") == 0);
}

/* Maps an alarm flag onto the source bit the screen renders.  A flag whose
 * channel reported a missing or invalid quality is not an observation and is
 * skipped entirely (see the early return in updateReading), which leaves the
 * bit exactly as it was: it is never asserted, but a bit a real measurement
 * raised is also never cleared by an unmeasurable one.  That is deliberate -
 * turning an alarm off because the sensor went offline would report an
 * all-clear nobody measured - so the bit stays latched until the channel comes
 * back and reports a real clear. */
uint32_t alarmSourceFor(const char* metric) {
  if (std::strcmp(metric, "oxygen.warning") == 0 ||
      std::strcmp(metric, "oxygen.alarm") == 0) {
    return kSourceOxygen;
  }
  if (std::strcmp(metric, "methane.warning") == 0 ||
      std::strcmp(metric, "methane.alarm") == 0) {
    return kSourceMethane;
  }
  if (std::strcmp(metric, "co.warning") == 0 ||
      std::strcmp(metric, "co.alarm") == 0) {
    return kSourceCarbonMonoxide;
  }
  return 0U;
}

/* Validation bounds for the readings Node A reports for traceability.  They
 * follow the producer's own derivations: a 12-bit ADC code and the same code
 * scaled to the 3.3 V reference. */
constexpr int64_t kAdcCodeMaximum = 4095;
constexpr int64_t kMillivoltMaximum = 3300;

bool inRange(double value, int64_t minimum, int64_t maximum) {
  return std::isfinite(value) && value >= static_cast<double>(minimum) &&
         value <= static_cast<double>(maximum);
}

uint8_t flagValue(double value) {
  return value != 0.0 ? 1U : 0U;
}

bool updateReading(ScreenSnapshot* snapshot, const char* asset,
                   const char* metric, const char* unit, double value,
                   Quality quality, uint64_t sampled_at_ms,
                   int* fan_index) {
  int64_t converted = 0;
  screen_protocol::Reading* reading = nullptr;
  double scale = 1.0;
  int64_t minimum = 0;
  int64_t maximum = 0;

  /* The residual analog channels.  Node A reports these for traceability and
   * the cloud contract; the screen shows the alarm flags and their quality, so
   * they are validated and accepted here without being stored. */
  if (std::strcmp(asset, "GAS-01") == 0 &&
      (std::strcmp(metric, "oxygen.raw") == 0 ||
       std::strcmp(metric, "methane.raw") == 0 ||
       std::strcmp(metric, "co.raw") == 0) &&
      std::strcmp(unit, "adc") == 0) {
    return inRange(value, 0, kAdcCodeMaximum);
  }
  if (std::strcmp(asset, "GAS-01") == 0 &&
      (std::strcmp(metric, "oxygen.voltage") == 0 ||
       std::strcmp(metric, "methane.voltage") == 0 ||
       std::strcmp(metric, "co.voltage") == 0) &&
      std::strcmp(unit, "mV") == 0) {
    return inRange(value, 0, kMillivoltMaximum);
  }
  /* Delivered power is the product of the two readings the fan snapshot
   * already carries, so it is accepted without a second copy. */
  if ((std::strcmp(asset, "FAN-01") == 0 || std::strcmp(asset, "FAN-02") == 0) &&
      std::strcmp(metric, "power") == 0 && std::strcmp(unit, "W") == 0) {
    return inRange(value, -10000, 10000);
  }
  if (std::strcmp(asset, "GAS-01") == 0 &&
      (std::strcmp(metric, "oxygen.warning") == 0 ||
       std::strcmp(metric, "oxygen.alarm") == 0 ||
       std::strcmp(metric, "methane.warning") == 0 ||
       std::strcmp(metric, "methane.alarm") == 0 ||
       std::strcmp(metric, "co.warning") == 0 ||
       std::strcmp(metric, "co.alarm") == 0) &&
      std::strcmp(unit, "bool") == 0) {
    if (!inRange(value, 0, 1)) return false;
    if (quality == Quality::Invalid || quality == Quality::Unknown) return true;
    const uint32_t source = alarmSourceFor(metric);
    if (source == 0U) return false;
    const bool assertive = flagValue(value) != 0U;
    const bool alarm = std::strstr(metric, ".alarm") != nullptr;
    if (alarm) {
      /* An alarm outranks a warning: the critical set keeps the bit and the
       * warning set must not claim it as well. */
      if (assertive) {
        snapshot->critical_sources |= source;
        snapshot->warning_sources &= ~source;
      } else {
        snapshot->critical_sources &= ~source;
      }
    } else if (assertive) {
      snapshot->warning_sources |= source;
    } else {
      snapshot->warning_sources &= ~source;
    }
    return true;
  }
  if (std::strcmp(asset, "CTRL-01") == 0 &&
      std::strcmp(metric, "led.mode") == 0 &&
      std::strcmp(unit, "enum") == 0) {
    if (!inRange(value, 0, 7)) return false;
    snapshot->actuators.led_mode = static_cast<uint8_t>(value);
    return true;
  }
  if (std::strcmp(asset, "CTRL-01") == 0 &&
      std::strcmp(metric, "led.brightnessPercent") == 0 &&
      std::strcmp(unit, "percent") == 0) {
    if (!inRange(value, 0, 100)) return false;
    snapshot->actuators.led_brightness_percent = static_cast<uint8_t>(value);
    return true;
  }
  if (std::strcmp(asset, "CTRL-01") == 0 &&
      (std::strcmp(metric, "buzzer.active") == 0 ||
       std::strcmp(metric, "buzzer.muted") == 0) &&
      std::strcmp(unit, "bool") == 0) {
    if (!inRange(value, 0, 1)) return false;
    const bool muted = std::strcmp(metric, "buzzer.muted") == 0;
    if (muted) {
      snapshot->actuators.buzzer_muted = flagValue(value) != 0U;
    } else {
      snapshot->actuators.buzzer_on = flagValue(value) != 0U;
    }
    return true;
  }
  if (std::strcmp(asset, "ENV-01") == 0 &&
      std::strcmp(metric, "temperature") == 0 &&
      std::strcmp(unit, "degC") == 0) {
    reading = &snapshot->temperature;
    scale = 100.0; minimum = -5000; maximum = 10000;
  } else if (std::strcmp(asset, "ENV-01") == 0 &&
             std::strcmp(metric, "humidity") == 0 &&
             std::strcmp(unit, "%RH") == 0) {
    reading = &snapshot->humidity;
    scale = 100.0; maximum = 10000;
  } else if (std::strcmp(asset, "GAS-01") == 0 &&
             std::strcmp(metric, "oxygen.concentration") == 0 &&
             std::strcmp(unit, "%Vol") == 0) {
    reading = &snapshot->oxygen;
    scale = 1000.0; maximum = 100000;
  } else if (std::strcmp(asset, "GAS-01") == 0 &&
             (std::strcmp(metric, "methane.concentration") == 0 ||
              std::strcmp(metric, "methane.ppm") == 0) &&
             std::strcmp(unit, "ppm") == 0) {
    reading = &snapshot->methane;
    maximum = 100000;
  } else if (std::strcmp(asset, "GAS-01") == 0 &&
             (std::strcmp(metric, "carbon_monoxide.concentration") == 0 ||
              std::strcmp(metric, "carbonMonoxide.concentration") == 0 ||
              std::strcmp(metric, "co.concentration") == 0) &&
             std::strcmp(unit, "ppm") == 0) {
    reading = &snapshot->carbon_monoxide;
    maximum = 100000;
  } else if (std::strcmp(asset, "GAS-01") == 0 &&
             std::strcmp(metric, "smoke.alarm") == 0 &&
             std::strcmp(unit, "bool") == 0) {
    reading = &snapshot->smoke;
    maximum = 1;
  } else if (((std::strcmp(asset, "LEVEL-L01") == 0 &&
               std::strcmp(metric, "level.detected") == 0) ||
              (std::strcmp(asset, "SEEP-W01") == 0 &&
               std::strcmp(metric, "water.raw") == 0)) &&
             (std::strcmp(unit, "bool") == 0 ||
              std::strcmp(unit, "adc") == 0)) {
    reading = &snapshot->water;
    maximum = 4095;
  } else if (std::strcmp(asset, "GAS-01") == 0 &&
             (std::strcmp(metric, "flame.alarm") == 0 ||
              std::strcmp(metric, "flame.rawLevel") == 0) &&
             std::strcmp(unit, "bool") == 0) {
    reading = &snapshot->flame;
    maximum = 1;
  }
  if (reading != nullptr) {
    if (!roundedInRange(value, scale, minimum, maximum, &converted)) return false;
    reading->value = static_cast<int32_t>(converted);
    reading->sampled_at_ms = sampled_at_ms;
    reading->quality = quality;
    return true;
  }

  int index = -1;
  if (std::strcmp(asset, "FAN-01") == 0) index = 0;
  else if (std::strcmp(asset, "FAN-02") == 0) index = 1;
  if (index < 0) return false;
  *fan_index = index;
  screen_protocol::FanSnapshot& fan = snapshot->fans[index];
  if (std::strcmp(metric, "supply.voltage") == 0 &&
      std::strcmp(unit, "V") == 0) {
    if (!roundedInRange(value, 1000.0, 0, 36000, &converted)) return false;
    fan.voltage_mv = static_cast<uint16_t>(converted);
  } else if (std::strcmp(metric, "motor.current") == 0 &&
             std::strcmp(unit, "mA") == 0) {
    if (value < 0.0) value = -value;
    if (!roundedInRange(value, 1.0, 0, 10000, &converted)) return false;
    fan.current_ma = static_cast<uint16_t>(converted);
  } else if (std::strcmp(metric, "rotational.speed") == 0 &&
             std::strcmp(unit, "rpm") == 0) {
    if (!roundedInRange(value, 1.0, 0, 100000, &converted)) return false;
    fan.actual_rpm = static_cast<uint32_t>(converted);
  } else {
    return false;
  }
  fan.sampled_at_ms = sampled_at_ms;
  fan.quality = quality;
  fan.running = fan.actual_rpm != 0U || fan.target_duty_percent != 0U;
  return true;
}

RouteResult updateTelemetry(TelemetryAccumulator* accumulator,
                            const char* payload, size_t length,
                            uint64_t now_epoch_ms, char* output,
                            size_t output_capacity, size_t* written) {
  if (length > kTransportPayloadLimit) return RouteResult::TooLarge;
  if (accumulator == nullptr || payload == nullptr || output == nullptr ||
      written == nullptr || now_epoch_ms < kMinEpochSeconds * 1000ULL ||
      !validJsonEnvelope(payload, length)) {
    return RouteResult::InvalidPayload;
  }
  const char* end = payload + length;
  char schema[32];
  uint32_t sequence = 0U;
  if (!readStringField(payload, end, "schema", schema, sizeof(schema)) ||
      std::strcmp(schema, "ut.telemetry.v1") != 0 ||
      !readUint32Field(payload, end, "seq", &sequence) ||
      countKey(payload, end, "readings") != 1U) {
    return RouteResult::InvalidPayload;
  }
  if (accumulator->initialized) {
    if (sequence == accumulator->last_sequence) {
      return RouteResult::Stale;  // duplicate delivery (e.g. MQTT redelivery).
    }
    if (sequence < accumulator->last_sequence) {
      const uint64_t silence_ms =
          now_epoch_ms - accumulator->last_received_at_ms;
      const bool explicit_reset = accumulator->accept_session_reset;
      const bool long_silence = silence_ms >= kSequenceResyncSilenceMs;
      const bool low_restart =
          sequence <= kSequenceRestartMaximum &&
          accumulator->last_sequence >= kSequenceRestartMinimumPrevious &&
          silence_ms >= kSequenceRestartSilenceMs;
      if (!explicit_reset && !long_silence && !low_restart) {
        return RouteResult::Stale;  // truly out-of-order packet.
      }
      // Legitimate Node A session restart: discard the stale snapshot so the
      // restart packet seeds a fresh accumulator.
      InitTelemetryAccumulator(accumulator);
    }
  }
  const char* readings = valueAfterKey(payload, end, "readings");
  if (readings == nullptr || *readings != '[') return RouteResult::InvalidPayload;
  const char* readings_end = matchingDelimiter(readings, end);
  if (readings_end == nullptr) return RouteResult::InvalidPayload;

  TelemetryAccumulator candidate = *accumulator;
  if (!candidate.initialized) InitTelemetryAccumulator(&candidate);
  bool recognized = false;
  int frame_fan_index = -1;
  const char* cursor = readings + 1U;
  while (cursor < readings_end) {
    while (cursor < readings_end &&
           (*cursor == ' ' || *cursor == '\t' || *cursor == '\r' ||
            *cursor == '\n')) {
      ++cursor;
    }
    if (cursor == readings_end) break;
    if (*cursor != '{') return RouteResult::InvalidPayload;
    const char* object_end = matchingDelimiter(cursor, readings_end + 1U);
    if (object_end == nullptr) return RouteResult::InvalidPayload;
    char asset[16];
    char metric[40];
    char unit[12];
    char quality_text[12];
    double value = 0.0;
    if (!readStringField(cursor, object_end + 1U, "assetCode", asset,
                         sizeof(asset)) ||
        !readStringField(cursor, object_end + 1U, "metric", metric,
                         sizeof(metric)) ||
        !readNumberField(cursor, object_end + 1U, "value", &value) ||
        !readStringField(cursor, object_end + 1U, "unit", unit,
                         sizeof(unit)) ||
        !readStringField(cursor, object_end + 1U, "quality", quality_text,
                         sizeof(quality_text))) {
      return RouteResult::InvalidPayload;
    }
    const Quality quality = parseQuality(quality_text);
    if (quality == Quality::Unknown) return RouteResult::InvalidPayload;
    const bool known = updateReading(&candidate.snapshot, asset, metric, unit,
                                     value, quality, now_epoch_ms,
                                     &frame_fan_index);
    if (!known && isKnownReading(asset, metric)) {
      return RouteResult::InvalidPayload;
    }
    recognized = recognized || known;
    cursor = object_end + 1U;
    while (cursor < readings_end &&
           (*cursor == ' ' || *cursor == '\t' || *cursor == '\r' ||
            *cursor == '\n')) {
      ++cursor;
    }
    if (cursor < readings_end) {
      if (*cursor != ',') return RouteResult::InvalidPayload;
      ++cursor;
      const char* next = cursor;
      while (next < readings_end &&
             (*next == ' ' || *next == '\t' || *next == '\r' ||
              *next == '\n')) {
        ++next;
      }
      if (next == readings_end || *next == ',') return RouteResult::InvalidPayload;
      cursor = next;
    }
  }
  if (!recognized) return RouteResult::InvalidPayload;

  const char* diag = valueAfterKey(payload, end, "diag");
  if (diag != nullptr) {
    if (*diag != '{') return RouteResult::InvalidPayload;
    const char* diag_end = matchingDelimiter(diag, end);
    if (diag_end == nullptr) return RouteResult::InvalidPayload;
    uint32_t value = 0U;
    if (countKey(diag, diag_end + 1U, "relayActive") == 1U) {
      if (!readUint32Field(diag, diag_end + 1U, "relayActive", &value) ||
          value > 1U) {
        return RouteResult::InvalidPayload;
      }
      candidate.snapshot.actuators.relay_on = value != 0U;
    }
    if (countKey(diag, diag_end + 1U, "pwmPercent") == 1U) {
      /* The legacy Web/IoTDA controller path commands any duty from 0 to 100,
       * so the reported actual duty is bounded the same way.  The 0/30/60/100
       * ladder is a menu-command contract, not a telemetry one. */
      if (frame_fan_index < 0 ||
          !readUint32Field(diag, diag_end + 1U, "pwmPercent", &value) ||
          value > 100U) {
        return RouteResult::InvalidPayload;
      }
      screen_protocol::FanSnapshot& fan =
          candidate.snapshot.fans[frame_fan_index];
      fan.target_duty_percent = static_cast<uint8_t>(value);
      fan.running = fan.actual_rpm != 0U || value != 0U;
    }
  }

  candidate.snapshot.sequence = sequence;
  candidate.snapshot.generated_at_ms = now_epoch_ms;
  /* This frame is the observation: Node A produced it and the broker carried
   * it, so both links are online by construction.  The gateway and IoTDA
   * session are not observable from any topic CTRL-02 subscribes to, so they
   * keep whatever the accumulator was initialised with - unknown - instead of
   * being reported as a false OFFLINE. */
  candidate.snapshot.connectivity.node_a = LinkStatus::Online;
  candidate.snapshot.connectivity.mqtt = LinkStatus::Online;
  candidate.snapshot.connectivity.updated_at_ms = now_epoch_ms;
  /* Recompute the derived sources from the snapshot.  The gas bits are written
   * per reading by the gas status frame, which is the only place the producer
   * reports the operational methane alarm, so they must survive this rebuild. */
  candidate.snapshot.warning_sources &= kAlarmSourceAll;
  candidate.snapshot.critical_sources &= kAlarmSourceAll;
  if (candidate.snapshot.water.quality != Quality::Unknown &&
      candidate.snapshot.water.value != 0) {
    candidate.snapshot.warning_sources |= kSourceWater;
  }
  if (candidate.snapshot.smoke.quality != Quality::Unknown &&
      candidate.snapshot.smoke.value != 0) {
    candidate.snapshot.critical_sources |= kSourceSmoke;
  }
  if (candidate.snapshot.flame.quality != Quality::Unknown &&
      candidate.snapshot.flame.value != 0) {
    candidate.snapshot.critical_sources |= kSourceFlame;
  }
  candidate.snapshot.alarm_severity =
      candidate.snapshot.critical_sources != 0U
          ? AlarmSeverity::Critical
          : (candidate.snapshot.warning_sources != 0U
                 ? AlarmSeverity::Warning
                 : AlarmSeverity::None);
  candidate.last_sequence = sequence;
  candidate.last_received_at_ms = now_epoch_ms;
  candidate.initialized = true;

  const Result build = BuildSnapshot(candidate.snapshot, output,
                                     output_capacity, written);
  if (build != Result::Ok) return mapProtocolResult(build);
  *accumulator = candidate;
  return RouteResult::Ok;
}
#endif

}  // namespace

const RouteTopics& TopicsForRole(Role role) {
#if SCREEN_ROUTING_CTRL01 && SCREEN_ROUTING_CTRL02
  return role == Role::Ctrl02 ? kCtrl02Topics : kCtrl01Topics;
#elif SCREEN_ROUTING_CTRL02
  (void)role;
  return kCtrl02Topics;
#else
  (void)role;
  return kCtrl01Topics;
#endif
}

uint64_t EpochMillisecondsFromUnixParts(int64_t epoch_seconds,
                                        int32_t microseconds) {
  if (epoch_seconds < static_cast<int64_t>(kMinEpochSeconds) ||
      epoch_seconds > static_cast<int64_t>(kMaxEpochSeconds) ||
      microseconds < 0 || microseconds >= 1000000) {
    return 0ULL;
  }
  const uint64_t seconds_ms = static_cast<uint64_t>(epoch_seconds) * 1000ULL;
  const uint64_t fraction_ms = static_cast<uint64_t>(microseconds) / 1000U;
  return seconds_ms + fraction_ms;
}

void InitUartTxQueue(UartTxQueue* queue) {
  if (queue == nullptr) return;
  std::memset(queue, 0, sizeof(*queue));
}

namespace {

size_t uartQueueIndex(const UartTxQueue& queue, size_t logical_index) {
  return (static_cast<size_t>(queue.head) + logical_index) %
         kUartTxQueueCapacity;
}

void assignUartFrame(UartTxFrame* frame, UartTxFrameKind kind,
                     const char* payload, size_t length) {
  std::memcpy(frame->bytes, payload, length);
  frame->bytes[length] = '\r';
  frame->bytes[length + 1U] = '\n';
  frame->length = static_cast<uint16_t>(length + kUartTxTerminatorLength);
  frame->offset = 0U;
  frame->kind = kind;
}

int findReplaceableFrame(const UartTxQueue& queue, UartTxFrameKind kind) {
  for (size_t remaining = static_cast<size_t>(queue.count); remaining != 0U;
       --remaining) {
    const size_t logical_index = remaining - 1U;
    const UartTxFrame& frame =
        queue.frames[uartQueueIndex(queue, logical_index)];
    if (frame.kind == kind && frame.offset == 0U) {
      return static_cast<int>(logical_index);
    }
  }
  return -1;
}

int findEvictableFrame(const UartTxQueue& queue) {
  constexpr UartTxFrameKind priorities[] = {
      UartTxFrameKind::Snapshot,
      UartTxFrameKind::Diagnostic,
      UartTxFrameKind::TimeSync,
  };
  for (UartTxFrameKind kind : priorities) {
    const int index = findReplaceableFrame(queue, kind);
    if (index >= 0) return index;
  }
  return -1;
}

void removeUartFrame(UartTxQueue* queue, size_t logical_index) {
  for (size_t index = logical_index;
       index + 1U < static_cast<size_t>(queue->count); ++index) {
    queue->frames[uartQueueIndex(*queue, index)] =
        queue->frames[uartQueueIndex(*queue, index + 1U)];
  }
  const size_t tail =
      uartQueueIndex(*queue, static_cast<size_t>(queue->count) - 1U);
  std::memset(&queue->frames[tail], 0, sizeof(queue->frames[tail]));
  --queue->count;
}

}  // namespace

UartTxEnqueueResult EnqueueUartTxLine(UartTxQueue* queue,
                                     UartTxFrameKind kind,
                                     const char* payload, size_t length) {
  if (queue == nullptr || payload == nullptr) return UartTxEnqueueResult::Invalid;
  if (length > kUartLineLimit) return UartTxEnqueueResult::TooLarge;
  if (std::memchr(payload, '\r', length) != nullptr ||
      std::memchr(payload, '\n', length) != nullptr) {
    return UartTxEnqueueResult::Invalid;
  }

  if (kind == UartTxFrameKind::Snapshot ||
      kind == UartTxFrameKind::TimeSync) {
    const int replaceable = findReplaceableFrame(*queue, kind);
    if (replaceable >= 0) {
      UartTxFrame& frame = queue->frames[uartQueueIndex(
          *queue, static_cast<size_t>(replaceable))];
      assignUartFrame(&frame, kind, payload, length);
      ++queue->coalesced_frames;
      return UartTxEnqueueResult::Coalesced;
    }
  }

  if (static_cast<size_t>(queue->count) == kUartTxQueueCapacity) {
    if (kind == UartTxFrameKind::Acknowledgement) {
      const int evictable = findEvictableFrame(*queue);
      if (evictable >= 0) {
        removeUartFrame(queue, static_cast<size_t>(evictable));
        ++queue->dropped_frames;
      }
    }
    if (static_cast<size_t>(queue->count) == kUartTxQueueCapacity) {
      ++queue->dropped_frames;
      return UartTxEnqueueResult::Full;
    }
  }

  const size_t tail = uartQueueIndex(*queue, queue->count);
  assignUartFrame(&queue->frames[tail], kind, payload, length);
  ++queue->count;
  return UartTxEnqueueResult::Queued;
}

size_t UartTxQueuedFrameCount(const UartTxQueue* queue) {
  return queue == nullptr ? 0U : static_cast<size_t>(queue->count);
}

size_t UartTxPeek(const UartTxQueue* queue, size_t available_bytes,
                  const uint8_t** bytes) {
  if (bytes != nullptr) *bytes = nullptr;
  if (queue == nullptr || bytes == nullptr || queue->count == 0U ||
      available_bytes == 0U) {
    return 0U;
  }
  const UartTxFrame& frame = queue->frames[queue->head];
  const size_t remaining =
      static_cast<size_t>(frame.length) - static_cast<size_t>(frame.offset);
  size_t count = remaining < available_bytes ? remaining : available_bytes;
  if (count > kUartTxChunkLimit) count = kUartTxChunkLimit;
  *bytes = frame.bytes + frame.offset;
  return count;
}

void UartTxConsume(UartTxQueue* queue, size_t consumed_bytes) {
  if (queue == nullptr || queue->count == 0U || consumed_bytes == 0U) return;
  UartTxFrame& frame = queue->frames[queue->head];
  const size_t remaining =
      static_cast<size_t>(frame.length) - static_cast<size_t>(frame.offset);
  const size_t consumed =
      consumed_bytes < remaining ? consumed_bytes : remaining;
  frame.offset = static_cast<uint16_t>(static_cast<size_t>(frame.offset) +
                                       consumed);
  if (frame.offset != frame.length) return;
  std::memset(&frame, 0, sizeof(frame));
  queue->head = static_cast<uint8_t>(
      (static_cast<size_t>(queue->head) + 1U) % kUartTxQueueCapacity);
  --queue->count;
}

void InitTelemetryAccumulator(TelemetryAccumulator* accumulator) {
  if (accumulator == nullptr) return;
  std::memset(accumulator, 0, sizeof(*accumulator));
  std::strcpy(accumulator->snapshot.source, "CTRL-01");
  accumulator->snapshot.temperature.quality = Quality::Unknown;
  accumulator->snapshot.humidity.quality = Quality::Unknown;
  accumulator->snapshot.oxygen.quality = Quality::Unknown;
  accumulator->snapshot.methane.quality = Quality::Unknown;
  accumulator->snapshot.carbon_monoxide.quality = Quality::Unknown;
  accumulator->snapshot.smoke.quality = Quality::Unknown;
  accumulator->snapshot.water.quality = Quality::Unknown;
  accumulator->snapshot.flame.quality = Quality::Unknown;
  accumulator->snapshot.fans[0].quality = Quality::Unknown;
  accumulator->snapshot.fans[1].quality = Quality::Unknown;
  accumulator->snapshot.actuators.led_brightness_percent = 100U;
}

void BeginTelemetrySession(TelemetryAccumulator* accumulator) {
  if (accumulator == nullptr) return;
  accumulator->accept_session_reset = true;
}

RouteResult NormalizeMenuCommand(const char* payload, size_t length,
                                 uint64_t now_epoch_ms, char* output,
                                 size_t output_capacity, size_t* written) {
  prepareRawOutput(output, output_capacity, written);
#if !SCREEN_ROUTING_CTRL01
  (void)payload;
  (void)length;
  (void)now_epoch_ms;
  return RouteResult::WrongRole;
#else
  if (payload == nullptr || output == nullptr || written == nullptr) {
    return RouteResult::InvalidPayload;
  }
  if (length > kUartLineLimit) return RouteResult::TooLarge;
  MenuCommand command{};
  const Result parsed = ParseMenuCommand(payload, length, now_epoch_ms, &command);
  if (parsed != Result::Ok) return mapProtocolResult(parsed);
  if (output_capacity == 0U) return RouteResult::OutputTooSmall;
  const int count = std::snprintf(
      output, output_capacity,
      "{\"schema\":\"ut.command.v1\",\"cmdId\":\"%s\",\"target\":\"%s\","
      "\"action\":\"%s\",\"value\":%u,\"createdAtMs\":%llu,\"ttlMs\":%lu}",
      command.command_id, command.target, actionText(command.action),
      static_cast<unsigned int>(command.value),
      static_cast<unsigned long long>(command.created_at_ms),
      static_cast<unsigned long>(command.ttl_ms));
  if (count < 0 || static_cast<size_t>(count) >= output_capacity) {
    output[0] = '\0';
    return RouteResult::OutputTooSmall;
  }
  if (static_cast<size_t>(count) > kUartLineLimit) {
    output[0] = '\0';
    return RouteResult::TooLarge;
  }
  *written = static_cast<size_t>(count);
  return RouteResult::Ok;
#endif
}

RouteResult RouteSerialLine(Role role, const char* line, size_t length,
                            uint64_t now_epoch_ms, RouteOutput* output) {
  clearOutput(output);
  if (output == nullptr || line == nullptr) return RouteResult::InvalidPayload;
#if !SCREEN_ROUTING_CTRL02
  (void)role;
  (void)length;
  (void)now_epoch_ms;
  return RouteResult::WrongRole;
#else
  if (role != Role::Ctrl02) return RouteResult::WrongRole;
  MenuCommand command{};
  const Result parsed = ParseMenuCommand(line, length, now_epoch_ms, &command);
  if (parsed != Result::Ok) return mapProtocolResult(parsed);
  const Result built = BuildMenuCommand(command, output->payload,
                                       sizeof(output->payload),
                                       &output->payload_length);
  if (built != Result::Ok) return mapProtocolResult(built);
  if (!copyTopic(kCtrl01MenuCommand, output->topic)) {
    clearOutput(output);
    return RouteResult::OutputTooSmall;
  }
  output->kind = OutputKind::MqttPublish;
  return RouteResult::Ok;
#endif
}

RouteResult RouteMqttMessage(Role role, const char* topic,
                             const char* payload, size_t length,
                             uint64_t now_epoch_ms,
                             TelemetryAccumulator* accumulator,
                             RouteOutput* output) {
  clearOutput(output);
  if (topic == nullptr || payload == nullptr || output == nullptr) {
    return RouteResult::InvalidPayload;
  }
  if (length > kTransportPayloadLimit) return RouteResult::TooLarge;
#if SCREEN_ROUTING_CTRL01 && SCREEN_ROUTING_CTRL02
  if (role == Role::Ctrl01) {
#elif SCREEN_ROUTING_CTRL01
  (void)role;
  (void)accumulator;
  {
#else
  (void)role;
#endif
#if SCREEN_ROUTING_CTRL01
    if (std::strcmp(topic, kCtrl01MenuCommand) != 0) return RouteResult::WrongTopic;
    const RouteResult result = NormalizeMenuCommand(
        payload, length, now_epoch_ms, output->payload,
        sizeof(output->payload), &output->payload_length);
    if (result != RouteResult::Ok) return result;
    copyTopic(topic, output->topic);
    output->kind = OutputKind::UartCommand;
    return RouteResult::Ok;
  }
#endif
#if SCREEN_ROUTING_CTRL02
  if (std::strcmp(topic, kCtrl01Telemetry) == 0) {
    const RouteResult result = updateTelemetry(
        accumulator, payload, length, now_epoch_ms, output->payload,
        sizeof(output->payload), &output->payload_length);
    if (result != RouteResult::Ok) {
      clearOutput(output);
      return result;
    }
    output->kind = OutputKind::UartLine;
    return RouteResult::Ok;
  }
  if (std::strcmp(topic, kCtrl01CommandAck) == 0) {
    CommandAck ack{};
    const Result parsed = ParseCommandAck(payload, length, &ack);
    if (parsed != Result::Ok) return mapProtocolResult(parsed);
    const Result built = BuildCommandAck(ack, output->payload,
                                        sizeof(output->payload),
                                        &output->payload_length);
    if (built != Result::Ok) return mapProtocolResult(built);
    if (accumulator != nullptr) {
      TelemetryAccumulator candidate = *accumulator;
      if (!candidate.initialized) InitTelemetryAccumulator(&candidate);
      std::strcpy(candidate.snapshot.last_command.command_id, ack.command_id);
      candidate.snapshot.last_command.accepted = ack.status == AckStatus::Accepted;
      candidate.snapshot.last_command.complete = true;
      candidate.snapshot.last_command.completed_at_ms = ack.completed_at_ms;
      *accumulator = candidate;
    }
    output->kind = OutputKind::UartLine;
    return RouteResult::Ok;
  }
  return RouteResult::WrongTopic;
#else
  return RouteResult::WrongTopic;
#endif
}

void InitTimeSyncSchedule(TimeSyncSchedule* schedule) {
  if (schedule == nullptr) return;
  std::memset(schedule, 0, sizeof(*schedule));
}

void InitNtpAssociationState(NtpAssociationState* state) {
  if (state == nullptr) return;
  state->configured_for_current_association = false;
}

bool ShouldConfigureNtp(NtpAssociationState* state, bool wifi_connected) {
  if (state == nullptr) return false;
  if (!wifi_connected) {
    state->configured_for_current_association = false;
    return false;
  }
  if (state->configured_for_current_association) return false;
  state->configured_for_current_association = true;
  return true;
}

void InitMqttLinkStatusState(MqttLinkStatusState* state) {
  if (state == nullptr) return;
  state->initialized = false;
  state->connected = false;
}

MqttLinkStatusResult BuildMqttLinkStatus(MqttLinkStatusState* state,
                                         bool connected, char* output,
                                         size_t output_capacity,
                                         size_t* written) {
  if (written != nullptr) *written = 0U;
  if (output != nullptr && output_capacity != 0U) output[0] = '\0';
  if (state == nullptr || output == nullptr || written == nullptr) {
    return MqttLinkStatusResult::OutputTooSmall;
  }
  if (state->initialized && state->connected == connected) {
    return MqttLinkStatusResult::Unchanged;
  }
  const char* status = connected ? "MQTT|UP" : "MQTT|DOWN";
  const size_t length = std::strlen(status);
  if (output_capacity <= length) return MqttLinkStatusResult::OutputTooSmall;
  std::memcpy(output, status, length + 1U);
  *written = length;
  state->initialized = true;
  state->connected = connected;
  return MqttLinkStatusResult::Emitted;
}

TimeEmitResult BuildDueTimeSync(TimeSyncSchedule* schedule, uint32_t now_ms,
                                uint64_t epoch_seconds, char* output,
                                size_t output_capacity, size_t* written) {
  prepareRawOutput(output, output_capacity, written);
  if (schedule == nullptr || output == nullptr || written == nullptr ||
      epoch_seconds < kMinEpochSeconds || epoch_seconds > kMaxEpochSeconds) {
    return TimeEmitResult::InvalidEpoch;
  }
  if (schedule->emitted &&
      static_cast<uint32_t>(now_ms - schedule->last_emit_ms) <
          kTimeSyncPeriodMs) {
    return TimeEmitResult::NotDue;
  }
  const TimeSync time_sync = {TimeSource::Ntp, TimeState::Synchronized,
                              epoch_seconds, schedule->next_sequence};
  const Result result = BuildTimeSync(time_sync, output, output_capacity, written);
  if (result != Result::Ok) return TimeEmitResult::OutputTooSmall;
  schedule->last_emit_ms = now_ms;
  ++schedule->next_sequence;
  schedule->emitted = true;
  return TimeEmitResult::Emitted;
}

}  // namespace screen_routing
