#include "node_a_telemetry.h"

#include <stdio.h>
#include <string.h>

/* Each frame is written with snprintf into its own fixed-size slot.  The
 * lengths reported back exclude the NUL terminator, and the terminating CRLF
 * is part of the frame so the bridge can split lines without guessing. */
#define TELEMETRY_LINE_LIMIT NODE_A_TELEMETRY_FRAME_SIZE

static uint32_t next_sequence(uint32_t *sequence)
{
  uint32_t value = 0U;
  if (sequence != 0) {
    *sequence = *sequence + 1U;
    value = *sequence;
  }
  return value;
}

static void write_frame(char *frame, uint16_t *length, int written)
{
  if ((frame != 0) && (length != 0)) {
    *length = ((written > 0) && (written < (int)TELEMETRY_LINE_LIMIT))
                  ? (uint16_t)written
                  : 0U;
    if (*length == 0U) frame[0] = '\0';
  }
}

static const char *sht30_quality(const Sht30Reading *reading)
{
  return reading->online ? "good" : "missing";
}

static const char *fan_quality(const Ina226Reading *reading)
{
  if (reading->online == 0U) return "missing";
  return reading->plausible ? "good" : "suspect";
}

static const SensorReading *find_reading_by_code(const SensorReading *sensors, uint8_t count,
                                                 const char *code)
{
  if ((sensors == NULL) || (count == 0U) || (code == NULL)) return NULL;
  for (uint8_t i = 0U; i < count; ++i) {
    if (strcmp(sensors[i].asset_code, code) == 0) {
      return &sensors[i];
    }
  }
  return NULL;
}

/* The AG-02 channels feed the cloud contract as raw ADC codes plus the
 * derived millivolts; the alarm states are reported separately by the gas
 * status frame. */
static void format_environment_frame(char *frame, uint16_t *length, uint32_t sequence,
                                     const NodeATelemetrySnapshot *snapshot)
{
  int written;
  if (snapshot->sensors != NULL && snapshot->sensor_count > 0U) {
    const SensorReading *sht = find_reading_by_code(snapshot->sensors, snapshot->sensor_count, "SHT-01");
    const SensorReading *smoke = find_reading_by_code(snapshot->sensors, snapshot->sensor_count, "MQ2-01");
    const SensorReading *flame = find_reading_by_code(snapshot->sensors, snapshot->sensor_count, "FLAME-01");
    const SensorReading *level = find_reading_by_code(snapshot->sensors, snapshot->sensor_count, "LEVEL-01");
    const SensorReading *o2 = find_reading_by_code(snapshot->sensors, snapshot->sensor_count, "O2-01");

    int32_t temperature_abs = (sht != NULL) ? sht->temperature_centi_c : 0;
    const char *temperature_sign = "";
    if (temperature_abs < 0) {
      temperature_sign = "-";
      temperature_abs = -temperature_abs;
    }
    const char *sht_code = (sht != NULL) ? sht->asset_code : "SHT-01";
    const char *quality = (sht != NULL && sht->online && sht->quality != SENSOR_QUALITY_MISSING) ? "good" : "missing";
    uint32_t hum_rh = (sht != NULL) ? (uint32_t)sht->humidity_centi_rh : 0U;

    const char *smoke_code = (smoke != NULL) ? smoke->asset_code : "MQ2-01";
    const char *smoke_quality = (smoke != NULL && smoke->quality == SENSOR_QUALITY_GOOD) ? "good" : "missing";
    unsigned int smoke_alarm = (smoke != NULL) ? (unsigned int)smoke->alarm : 0U;

    const char *flame_code = (flame != NULL) ? flame->asset_code : "FLAME-01";
    const char *flame_quality = (flame != NULL && flame->quality == SENSOR_QUALITY_GOOD) ? "good" : "missing";
    unsigned int flame_alarm = (flame != NULL && flame->alarm != 0U) ||
                               snapshot->flame_alarm != 0U;

    const char *level_code = (level != NULL) ? level->asset_code : "LEVEL-01";
    const char *level_quality = (level != NULL && level->quality == SENSOR_QUALITY_GOOD) ? "good" : ((level != NULL) ? "suspect" : "missing");
    unsigned int level_detected = (level != NULL) ? (unsigned int)level->alarm : 0U;

    const char *o2_code = (o2 != NULL) ? o2->asset_code : "O2-01";
    const char *oxygen_quality = (o2 != NULL && o2->online && o2->quality != SENSOR_QUALITY_MISSING) ? "suspect" : "missing";
    unsigned int oxygen_raw = (o2 != NULL) ? (unsigned int)o2->raw : 0U;
    unsigned long oxygen_uv = (o2 != NULL) ? (unsigned long)o2->microvolts : 0UL;

    written = snprintf(frame, TELEMETRY_LINE_LIMIT,
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
      "{\"assetCode\":\"%s\",\"metric\":\"temperature\",\"value\":%s%ld.%02ld,\"unit\":\"degC\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"humidity\",\"value\":%lu.%02lu,\"unit\":\"%%RH\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"smoke.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"flame.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"level.detected\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"oxygen.raw\",\"value\":%u,\"unit\":\"adc\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"oxygen.voltage\",\"value\":%lu.%03lu,\"unit\":\"mV\",\"quality\":\"%s\"}]}\r\n",
      (unsigned long)sequence,
      sht_code, temperature_sign, (long)(temperature_abs / 100), (long)(temperature_abs % 100), quality,
      sht_code, (unsigned long)(hum_rh / 100U), (unsigned long)(hum_rh % 100U), quality,
      smoke_code, smoke_alarm, smoke_quality,
      flame_code, flame_alarm, flame_quality,
      level_code, level_detected, level_quality,
      o2_code, oxygen_raw, oxygen_quality,
      o2_code, (unsigned long)(oxygen_uv / 1000UL), (unsigned long)(oxygen_uv % 1000UL), oxygen_quality);
  } else {
    const Sht30Reading *environment = &snapshot->environment;
    int32_t temperature_abs = environment->temperature_centi_c;
    const char *temperature_sign = "";
    const char *quality = sht30_quality(environment);
    const char *oxygen_quality = snapshot->oxygen_online ? "suspect" : "missing";
    const char *smoke_quality = snapshot->smoke_sampled ? "good" : "missing";
    const char *flame_quality = snapshot->flame_sampled ? "good" : "missing";
    const char *level_quality = snapshot->level_stable ? "good" : "suspect";

    if (temperature_abs < 0) {
      temperature_sign = "-";
      temperature_abs = -temperature_abs;
    }
    written = snprintf(frame, TELEMETRY_LINE_LIMIT,
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
      "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":%s%ld.%02ld,\"unit\":\"degC\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"ENV-01\",\"metric\":\"humidity\",\"value\":%lu.%02lu,\"unit\":\"%%RH\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"GAS-01\",\"metric\":\"smoke.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"GAS-01\",\"metric\":\"flame.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"LEVEL-L01\",\"metric\":\"level.detected\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"GAS-01\",\"metric\":\"oxygen.raw\",\"value\":%u,\"unit\":\"adc\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"GAS-01\",\"metric\":\"oxygen.voltage\",\"value\":%lu.%03lu,\"unit\":\"mV\",\"quality\":\"%s\"}]}\r\n",
      (unsigned long)sequence,
      temperature_sign, (long)(temperature_abs / 100), (long)(temperature_abs % 100), quality,
      (unsigned long)(environment->humidity_centi_rh / 100U),
      (unsigned long)(environment->humidity_centi_rh % 100U), quality,
      (unsigned int)snapshot->smoke_alarm, smoke_quality,
      (unsigned int)snapshot->flame_alarm, flame_quality,
      (unsigned int)snapshot->level_detected, level_quality,
      (unsigned int)snapshot->oxygen_raw, oxygen_quality,
      (unsigned long)(snapshot->oxygen_microvolts / 1000UL),
      (unsigned long)(snapshot->oxygen_microvolts % 1000UL), oxygen_quality);
  }
  write_frame(frame, length, written);
}

static void format_fan_frame(char *frame, uint16_t *length, uint32_t sequence,
                             const NodeATelemetrySnapshot *snapshot, uint8_t fan_index)
{
  const Ina226Reading *power = (fan_index == 0U) ? &snapshot->fan1_power
                                                 : &snapshot->fan2_power;
  const char *asset = (fan_index == 0U) ? "FAN-01" : "FAN-02";
  const char *quality = fan_quality(power);
  const uint32_t rpm = (fan_index == 0U) ? snapshot->fan1_rpm : snapshot->fan2_rpm;
  const uint8_t duty = (fan_index == 0U) ? snapshot->actuators.fan1_pwm_percent
                                         : snapshot->actuators.fan2_pwm_percent;
  const uint8_t relay_active = (uint8_t)((snapshot->actuators.relay_on != 0U) &&
                                          (duty != 0U));
  /* Tach capture is independent of INA226. A missing power monitor must not
   * erase a valid RPM measurement; conversely, nonzero duty with no pulses is
   * explicitly suspect rather than reported as healthy zero speed. */
  const char *rpm_quality = (relay_active == 0U || rpm != 0U) ? "good" : "suspect";
  int32_t current_abs = power->current_microamps;
  const char *current_sign = "";
  int written;

  if (current_abs < 0) {
    current_sign = "-";
    current_abs = -current_abs;
  }
  written = snprintf(frame, TELEMETRY_LINE_LIMIT,
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
    "{\"assetCode\":\"%s\",\"metric\":\"supply.voltage\",\"value\":%lu.%03lu,\"unit\":\"V\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"%s\",\"metric\":\"motor.current\",\"value\":%s%ld.%03ld,\"unit\":\"mA\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"%s\",\"metric\":\"rotational.speed\",\"value\":%lu,\"unit\":\"rpm\",\"quality\":\"%s\"}],"
    "\"diag\":{\"relayActive\":%u,\"pwmPercent\":%u,"
    "\"autoVentilation\":%u,\"cooldown\":%u,\"power\":%s%ld.%03ld,"
    "\"inaFault\":%u}}\r\n",
    (unsigned long)sequence,
    asset, (unsigned long)(power->bus_microvolts / 1000000UL),
    (unsigned long)((power->bus_microvolts % 1000000UL) / 1000UL), quality,
    asset, current_sign, (long)(current_abs / 1000L), (long)(current_abs % 1000L), quality,
    asset, (unsigned long)rpm, rpm_quality,
    (unsigned int)relay_active, (unsigned int)duty,
    (unsigned int)(snapshot->auto_ventilation_active ? 1U : 0U),
    (unsigned int)(snapshot->cooldown_active ? 1U : 0U),
    (power->power_microwatts < 0) ? "-" : "",
    (long)(((power->power_microwatts < 0) ? -power->power_microwatts
                                          : power->power_microwatts) / 1000000L),
    (long)(((power->power_microwatts < 0) ? -power->power_microwatts
                                          : power->power_microwatts) % 1000000L / 1000L),
    (unsigned int)power->fault);
  write_frame(frame, length, written);
}

/* The operational alarm state.  `methane.alarm` is the channel that drives
 * automatic ventilation; oxygen and CO carry their own provisional states
 * so the local screen can show them without acting on them. */
static void format_gas_status_frame(char *frame, uint16_t *length, uint32_t sequence,
                                     const NodeATelemetrySnapshot *snapshot)
{
  int written;
  if (snapshot->sensors != NULL && snapshot->sensor_count > 0U) {
    const SensorReading *mq4 = find_reading_by_code(snapshot->sensors, snapshot->sensor_count, "MQ4-01");
    const SensorReading *o2 = find_reading_by_code(snapshot->sensors, snapshot->sensor_count, "O2-01");
    const SensorReading *co = find_reading_by_code(snapshot->sensors, snapshot->sensor_count, "CO-01");

    const char *mq4_code = (mq4 != NULL) ? mq4->asset_code : "MQ4-01";
    const char *o2_code = (o2 != NULL) ? o2->asset_code : "O2-01";
    const char *co_code = (co != NULL) ? co->asset_code : "CO-01";

    const char *methane_quality = (mq4 != NULL && mq4->online && mq4->quality != SENSOR_QUALITY_MISSING) ? "good" : "missing";
    const char *oxygen_quality = (o2 != NULL && o2->online && o2->quality != SENSOR_QUALITY_MISSING) ? "suspect" : "missing";
    const char *co_quality = (co != NULL && co->online && co->quality != SENSOR_QUALITY_MISSING) ? "suspect" : "missing";

    written = snprintf(frame, TELEMETRY_LINE_LIMIT,
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
      "{\"assetCode\":\"%s\",\"metric\":\"methane.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"methane.warning\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"oxygen.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"co.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"}]}\r\n",
      (unsigned long)sequence,
      mq4_code, (unsigned int)snapshot->gas_alarm, methane_quality,
      mq4_code, (unsigned int)snapshot->gas_warning, methane_quality,
      o2_code, (unsigned int)snapshot->oxygen_alarm, oxygen_quality,
      co_code, (unsigned int)snapshot->co_alarm, co_quality);
  } else {
    const char *oxygen_quality = snapshot->oxygen_online ? "suspect" : "missing";
    const char *methane_quality = snapshot->methane_online ? "good" : "missing";
    const char *co_quality = snapshot->co_online ? "suspect" : "missing";
    written = snprintf(frame, TELEMETRY_LINE_LIMIT,
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
      "{\"assetCode\":\"GAS-01\",\"metric\":\"methane.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"GAS-01\",\"metric\":\"methane.warning\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"GAS-01\",\"metric\":\"oxygen.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"GAS-01\",\"metric\":\"co.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"}]}\r\n",
      (unsigned long)sequence,
      (unsigned int)snapshot->gas_alarm, methane_quality,
      (unsigned int)snapshot->gas_warning, methane_quality,
      (unsigned int)snapshot->oxygen_alarm, oxygen_quality,
      (unsigned int)snapshot->co_alarm, co_quality);
  }
  write_frame(frame, length, written);
}

static void format_gas_raw_frame(char *frame, uint16_t *length, uint32_t sequence,
                                 const NodeATelemetrySnapshot *snapshot)
{
  int written;
  if (snapshot->sensors != NULL && snapshot->sensor_count > 0U) {
    const SensorReading *flame = find_reading_by_code(snapshot->sensors, snapshot->sensor_count, "FLAME-01");
    const SensorReading *mq4 = find_reading_by_code(snapshot->sensors, snapshot->sensor_count, "MQ4-01");
    const SensorReading *co = find_reading_by_code(snapshot->sensors, snapshot->sensor_count, "CO-01");

    const char *flame_code = (flame != NULL) ? flame->asset_code : "FLAME-01";
    const char *mq4_code = (mq4 != NULL) ? mq4->asset_code : "MQ4-01";
    const char *co_code = (co != NULL) ? co->asset_code : "CO-01";

    const char *flame_quality = (flame != NULL && flame->quality == SENSOR_QUALITY_GOOD) ? "good" : "missing";
    const char *methane_quality = (mq4 != NULL && mq4->online && mq4->quality != SENSOR_QUALITY_MISSING) ? "good" : "missing";
    const char *co_quality = (co != NULL && co->online && co->quality != SENSOR_QUALITY_MISSING) ? "suspect" : "missing";

    unsigned int flame_alarm = (flame != NULL && flame->alarm != 0U) ||
                               snapshot->flame_alarm != 0U;
    unsigned int mq4_raw = (mq4 != NULL) ? (unsigned int)mq4->raw : 0U;
    unsigned long mq4_uv = (mq4 != NULL) ? (unsigned long)mq4->microvolts : 0UL;
    unsigned int co_raw = (co != NULL) ? (unsigned int)co->raw : 0U;
    unsigned long co_uv = (co != NULL) ? (unsigned long)co->microvolts : 0UL;

    written = snprintf(frame, TELEMETRY_LINE_LIMIT,
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
      "{\"assetCode\":\"%s\",\"metric\":\"flame.rawLevel\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"methane.raw\",\"value\":%u,\"unit\":\"adc\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"methane.voltage\",\"value\":%lu.%03lu,\"unit\":\"mV\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"co.raw\",\"value\":%u,\"unit\":\"adc\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"%s\",\"metric\":\"co.voltage\",\"value\":%lu.%03lu,\"unit\":\"mV\",\"quality\":\"%s\"}]}\r\n",
      (unsigned long)sequence,
      flame_code, flame_alarm, flame_quality,
      mq4_code, mq4_raw, methane_quality,
      mq4_code, (unsigned long)(mq4_uv / 1000UL), (unsigned long)(mq4_uv % 1000UL), methane_quality,
      co_code, co_raw, co_quality,
      co_code, (unsigned long)(co_uv / 1000UL), (unsigned long)(co_uv % 1000UL), co_quality);
  } else {
    const char *methane_quality = snapshot->methane_online ? "good" : "missing";
    const char *co_quality = snapshot->co_online ? "suspect" : "missing";
    const char *flame_quality = snapshot->flame_sampled ? "good" : "missing";
    written = snprintf(frame, TELEMETRY_LINE_LIMIT,
      "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
      "{\"assetCode\":\"GAS-01\",\"metric\":\"flame.rawLevel\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"GAS-01\",\"metric\":\"methane.raw\",\"value\":%u,\"unit\":\"adc\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"GAS-01\",\"metric\":\"methane.voltage\",\"value\":%lu.%03lu,\"unit\":\"mV\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"GAS-01\",\"metric\":\"co.raw\",\"value\":%u,\"unit\":\"adc\",\"quality\":\"%s\"},"
      "{\"assetCode\":\"GAS-01\",\"metric\":\"co.voltage\",\"value\":%lu.%03lu,\"unit\":\"mV\",\"quality\":\"%s\"}]}\r\n",
      (unsigned long)sequence,
      (unsigned int)snapshot->flame_alarm, flame_quality,
      (unsigned int)snapshot->methane_raw, methane_quality,
      (unsigned long)(snapshot->methane_microvolts / 1000UL),
      (unsigned long)(snapshot->methane_microvolts % 1000UL), methane_quality,
      (unsigned int)snapshot->co_raw, co_quality,
      (unsigned long)(snapshot->co_microvolts / 1000UL),
      (unsigned long)(snapshot->co_microvolts % 1000UL), co_quality);
  }
  write_frame(frame, length, written);
}

static void format_actuator_frame(char *frame, uint16_t *length, uint32_t sequence,
                                  const NodeATelemetrySnapshot *snapshot)
{
  int written = snprintf(frame, TELEMETRY_LINE_LIMIT,
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
    "{\"assetCode\":\"CTRL-01\",\"metric\":\"led.mode\",\"value\":%u,\"unit\":\"enum\",\"quality\":\"good\"},"
    "{\"assetCode\":\"CTRL-01\",\"metric\":\"led.brightnessPercent\",\"value\":%u,\"unit\":\"percent\",\"quality\":\"good\"},"
    "{\"assetCode\":\"CTRL-01\",\"metric\":\"buzzer.active\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"CTRL-01\",\"metric\":\"buzzer.muted\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"}]}\r\n",
    (unsigned long)sequence,
    (unsigned int)snapshot->actuators.led_mode,
    (unsigned int)snapshot->actuators.led_brightness_percent,
    (unsigned int)snapshot->actuators.buzzer_on,
    (unsigned int)snapshot->actuators.buzzer_muted);
  write_frame(frame, length, written);
}

/* Writes frame `index` into `frame` and reports its length.  Shared by the
 * whole-cycle formatter the host tests and the vector generator drive, and by
 * the single-frame rotation step the board emits.  `index` is always the
 * rotation slot itself (0..NODE_A_TELEMETRY_FRAME_COUNT-1), which is why the
 * frame order here is the rotation order. */
static void append_sht_reading(char *frame, uint16_t *length,
                               const NodeATelemetrySnapshot *snapshot,
                               const char *code)
{
  const SensorReading *sht = find_reading_by_code(snapshot->sensors,
                                                snapshot->sensor_count, code);
  if (sht == NULL || *length < 4U) return;
  const uint16_t offset = (uint16_t)(*length - 4U); /* replace ]}\r\n */
  int32_t temperature = sht->temperature_centi_c;
  const char *sign = temperature < 0 ? "-" : "";
  if (temperature < 0) temperature = -temperature;
  const char *quality = sht->online && sht->quality == SENSOR_QUALITY_GOOD
                          ? "good" : "missing";
  const int n = snprintf(frame + offset, TELEMETRY_LINE_LIMIT - offset,
    ",{\"assetCode\":\"%s\",\"metric\":\"temperature\",\"value\":%s%ld.%02ld,\"unit\":\"degC\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"%s\",\"metric\":\"humidity\",\"value\":%u.%02u,\"unit\":\"%%RH\",\"quality\":\"%s\"}]}\r\n",
    code, sign, (long)(temperature / 100), (long)(temperature % 100), quality,
    code, (unsigned)(sht->humidity_centi_rh / 100U),
    (unsigned)(sht->humidity_centi_rh % 100U), quality);
  write_frame(frame, length, n < 0 ? n : (int)offset + n);
}

static void append_level_reading(char *frame, uint16_t *length,
                                 const NodeATelemetrySnapshot *snapshot,
                                 const char *code)
{
  const SensorReading *level = find_reading_by_code(snapshot->sensors,
                                                   snapshot->sensor_count, code);
  char item[160];
  char *end_readings;
  size_t offset;
  if (level == NULL || *length < 4U) return;
  const char *quality = level->quality == SENSOR_QUALITY_GOOD ? "good" : "missing";
  const unsigned int detected = level->quality == SENSOR_QUALITY_GOOD
                                    ? (unsigned int)level->alarm : 0U;
  const int n = snprintf(item, sizeof(item),
    ",{\"assetCode\":\"%s\",\"metric\":\"level.detected\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"%s\"}",
    code, detected, quality);
  if (n <= 0 || (size_t)n >= sizeof(item) ||
      (size_t)*length + (size_t)n >= TELEMETRY_LINE_LIMIT) return;
  end_readings = strchr(frame, ']');
  if (end_readings == NULL) return;
  offset = (size_t)(end_readings - frame);
  memmove(end_readings + n, end_readings, (size_t)*length - offset + 1U);
  memcpy(end_readings, item, (size_t)n);
  *length = (uint16_t)((size_t)*length + (size_t)n);
}

static void format_indexed_frame(char *frame, uint16_t *length, uint32_t sequence,
                                 const NodeATelemetrySnapshot *snapshot,
                                 uint8_t index)
{
  *length = 0U;
  frame[0] = '\0';
  switch (index) {
    case 0U:
      format_environment_frame(frame, length, sequence, snapshot);
      break;
    case 1U:
      format_fan_frame(frame, length, sequence, snapshot, 0U);
      append_level_reading(frame, length, snapshot, "LEVEL-02");
      break;
    case 2U:
      format_fan_frame(frame, length, sequence, snapshot, 1U);
      append_level_reading(frame, length, snapshot, "LEVEL-03");
      break;
    case 3U:
      format_gas_status_frame(frame, length, sequence, snapshot);
      append_sht_reading(frame, length, snapshot, "SHT-02");
      break;
    case 4U:
      format_gas_raw_frame(frame, length, sequence, snapshot);
      append_sht_reading(frame, length, snapshot, "SHT-03");
      break;
    default:
      format_actuator_frame(frame, length, sequence, snapshot);
      append_sht_reading(frame, length, snapshot, "SHT-04");
      break;
  }
}

void NodeATelemetry_FormatAll(uint32_t *sequence, const NodeATelemetrySnapshot *snapshot,
                              char frames[NODE_A_TELEMETRY_FRAME_COUNT][NODE_A_TELEMETRY_FRAME_SIZE],
                              uint16_t lengths[NODE_A_TELEMETRY_FRAME_COUNT])
{
  /* The caller always supplies both arrays; the scratch path lets a caller
   * advance the sequence (or re-derive the byte count) without staging two
   * full cycles of RAM on the stack. */
  char scratch_frame[NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t scratch_length = 0U;
  uint8_t index;

  if (snapshot == 0) return;

  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    char *frame = (frames != 0) ? frames[index] : scratch_frame;
    uint16_t *length = (lengths != 0) ? &lengths[index] : &scratch_length;
    const uint32_t current = next_sequence(sequence);

    format_indexed_frame(frame, length, current, snapshot, index);
  }
}

uint8_t NodeATelemetry_FormatFrame(uint32_t sequence,
                                   const NodeATelemetrySnapshot *snapshot,
                                   char *frame, uint16_t *length)
{
  if ((frame == 0) || (length == 0)) return 0U;

  /* Sequence 1 is the first rotation slot.  Subtraction deliberately wraps at
   * zero so the mapping remains deterministic across a uint32 rollover. */
  *length = 0U;
  frame[0] = '\0';
  if (snapshot == 0) return 0U;

  format_indexed_frame(frame, length, sequence, snapshot,
                       (uint8_t)((sequence - 1U) % NODE_A_TELEMETRY_FRAME_COUNT));
  if (*length == 0U) return 0U;
  return 1U;
}

uint8_t NodeATelemetry_FormatFlameEvent(uint32_t sequence, char *frame,
                                        uint16_t capacity, uint16_t *length)
{
  int written;
  if (frame == NULL || length == NULL || capacity == 0U) return 0U;
  written = snprintf(frame, capacity,
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
    "{\"assetCode\":\"FLAME-01\",\"metric\":\"flame.alarm\","
    "\"value\":1,\"unit\":\"bool\",\"quality\":\"good\"}]}\r\n",
    (unsigned long)sequence);
  if (written <= 0 || written >= capacity) { *length = 0U; return 0U; }
  *length = (uint16_t)written;
  return 1U;
}

uint8_t NodeATelemetry_QueueNext(uint32_t *sequence,
                                 const NodeATelemetrySnapshot *snapshot,
                                 NodeATelemetryEnqueueFn enqueue,
                                 void *context)
{
  char frame[NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t length = 0U;
  uint32_t candidate;

  if ((sequence == 0) || (snapshot == 0) || (enqueue == 0)) return 0U;
  candidate = *sequence + 1U;
  if (NodeATelemetry_FormatFrame(candidate, snapshot, frame, &length) == 0U)
    return 0U;
  if ((length == 0U) || (enqueue(context, frame, length) == 0U)) return 0U;

  *sequence = candidate;
  return 1U;
}

uint8_t NodeATelemetry_QueueSlot(uint32_t *sequence, uint8_t slot,
                                 const NodeATelemetrySnapshot *snapshot,
                                 NodeATelemetryEnqueueFn enqueue,
                                 void *context)
{
  char frame[NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t length = 0U;
  uint32_t candidate;
  if (sequence == NULL || snapshot == NULL || enqueue == NULL ||
      slot >= NODE_A_TELEMETRY_FRAME_COUNT) return 0U;
  candidate = *sequence + 1U;
  format_indexed_frame(frame, &length, candidate, snapshot, slot);
  if (length == 0U || enqueue(context, frame, length) == 0U) return 0U;
  *sequence = candidate;
  return 1U;
}

uint8_t NodeATelemetry_QueueFullRotation(uint32_t *sequence,
                                          const NodeATelemetrySnapshot *snapshot,
                                          NodeATelemetryEnqueueFn enqueue,
                                          void *context)
{
  uint8_t emitted;

  if ((sequence == 0) || (snapshot == 0) || (enqueue == 0)) return 0U;
  for (emitted = 0U; emitted < NODE_A_TELEMETRY_FRAME_COUNT; ++emitted) {
    if (NodeATelemetry_QueueNext(sequence, snapshot, enqueue, context) == 0U)
      return 0U;
  }
  return 1U;
}
