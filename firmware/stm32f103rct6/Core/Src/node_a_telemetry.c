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

/* The AG-02 channels feed the cloud contract as raw ADC codes plus the
 * derived millivolts; the alarm states are reported separately by the gas
 * status frame. */
static void format_environment_frame(char *frame, uint16_t *length, uint32_t sequence,
                                     const NodeATelemetrySnapshot *snapshot)
{
  const Sht30Reading *environment = &snapshot->environment;
  int32_t temperature_abs = environment->temperature_centi_c;
  const char *temperature_sign = "";
  const char *quality = sht30_quality(environment);
  const char *oxygen_quality = snapshot->oxygen_online ? "suspect" : "missing";
  const char *smoke_quality = snapshot->smoke_sampled ? "good" : "missing";
  const char *flame_quality = snapshot->flame_sampled ? "good" : "missing";
  const char *level_quality = snapshot->level_stable ? "good" : "suspect";
  int written;

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
  write_frame(frame, length, written);
}

/* One fan frame carries the electrical readings the screen shows plus the
 * bounded diagnostic block.  The INA226 register dumps that used to pad this
 * frame are gone: they pushed it past the bridge's 1024-byte transport limit
 * and no consumer reads them. */
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
    asset, (unsigned long)rpm, quality,
    (unsigned int)snapshot->actuators.relay_on, (unsigned int)duty,
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
  const char *oxygen_quality = snapshot->oxygen_online ? "suspect" : "missing";
  const char *methane_quality = snapshot->methane_online ? "good" : "missing";
  const char *co_quality = snapshot->co_online ? "suspect" : "missing";
  int written = snprintf(frame, TELEMETRY_LINE_LIMIT,
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
  write_frame(frame, length, written);
}

/* The residual analog channels.  Oxygen and CO already reported their alarm
 * states; this frame carries the raw evidence the cloud contract keeps for
 * traceability. */
static void format_gas_raw_frame(char *frame, uint16_t *length, uint32_t sequence,
                                 const NodeATelemetrySnapshot *snapshot)
{
  const char *methane_quality = snapshot->methane_online ? "good" : "missing";
  const char *co_quality = snapshot->co_online ? "suspect" : "missing";
  const char *flame_quality = snapshot->flame_sampled ? "good" : "missing";
  int written = snprintf(frame, TELEMETRY_LINE_LIMIT,
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

    *length = 0U;
    frame[0] = '\0';
    switch (index) {
      case 0U:
        format_environment_frame(frame, length, current, snapshot);
        break;
      case 1U:
        format_fan_frame(frame, length, current, snapshot, 0U);
        break;
      case 2U:
        format_fan_frame(frame, length, current, snapshot, 1U);
        break;
      case 3U:
        format_gas_status_frame(frame, length, current, snapshot);
        break;
      case 4U:
        format_gas_raw_frame(frame, length, current, snapshot);
        break;
      default:
        format_actuator_frame(frame, length, current, snapshot);
        break;
    }
  }
}
