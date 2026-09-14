/* Producer-side contract for the Node A telemetry wire format.
 *
 * The ESP suite (firmware/esp8266-01s/test/test_screen_routing) parses the
 * committed vectors in tests/vectors/node_a_telemetry_vectors.h with the real
 * CTRL-02 consumer.  This test owns the other half: it re-derives those
 * vectors from the formatter the board actually runs, so a producer change
 * cannot silently invalidate the payloads the consumer was verified against.
 */
#include "node_a_telemetry.h"

#include <stdio.h>
#include <string.h>

#include "vectors/node_a_telemetry_vectors.h"

static int failures = 0;

#define CHECK(condition)                                                      \
  do {                                                                        \
    if (!(condition)) {                                                       \
      (void)fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__,           \
                    #condition);                                              \
      ++failures;                                                             \
    }                                                                         \
  } while (0)

/* The same fixture the vector generator uses.  Kept in sync by the drift check
 * in tests/update_node_a_telemetry_vectors.sh. */
static void build_snapshot(NodeATelemetrySnapshot *snapshot)
{
  (void)memset(snapshot, 0, sizeof(*snapshot));
  snapshot->environment.online = 1U;
  snapshot->environment.temperature_centi_c = 2345;
  snapshot->environment.humidity_centi_rh = 5210U;
  snapshot->oxygen_raw = 812U;
  snapshot->oxygen_microvolts = 654000UL;
  snapshot->oxygen_online = 1U;
  snapshot->methane_raw = 0U;
  snapshot->methane_microvolts = 0UL;
  snapshot->methane_online = 1U;
  snapshot->co_raw = 138U;
  snapshot->co_microvolts = 111000UL;
  snapshot->co_online = 1U;
  snapshot->smoke_alarm = 0U;
  snapshot->flame_alarm = 0U;
  snapshot->level_detected = 0U;
  snapshot->smoke_sampled = 1U;
  snapshot->flame_sampled = 1U;
  snapshot->level_stable = 1U;
  snapshot->gas_warning = 0U;
  snapshot->gas_alarm = 0U;
  snapshot->oxygen_warning = 0U;
  snapshot->oxygen_alarm = 0U;
  snapshot->co_warning = 0U;
  snapshot->co_alarm = 0U;
  snapshot->fan1_power.online = 1U;
  snapshot->fan1_power.plausible = 1U;
  snapshot->fan1_power.fault = 0U;
  snapshot->fan1_power.bus_microvolts = 11900000UL;
  snapshot->fan1_power.current_microamps = 320000;
  snapshot->fan1_power.power_microwatts = 3808000;
  snapshot->fan2_power.online = 1U;
  snapshot->fan2_power.plausible = 1U;
  snapshot->fan2_power.fault = 0U;
  snapshot->fan2_power.bus_microvolts = 11800000UL;
  snapshot->fan2_power.current_microamps = 280000;
  snapshot->fan2_power.power_microwatts = 3304000;
  snapshot->fan1_rpm = 2400U;
  snapshot->fan2_rpm = 1600U;
  snapshot->actuators.fan1_pwm_percent = 60U;
  snapshot->actuators.fan2_pwm_percent = 60U;
  snapshot->actuators.relay_on = 1U;
  snapshot->actuators.buzzer_on = 0U;
  snapshot->actuators.buzzer_muted = 0U;
  snapshot->actuators.led_mode = 1U;
  snapshot->actuators.led_brightness_percent = 75U;
  snapshot->auto_ventilation_active = 0U;
  snapshot->cooldown_active = 0U;
}

static int check_frames_match_committed_vectors(void)
{
  NodeATelemetrySnapshot snapshot;
  char frames[NODE_A_TELEMETRY_FRAME_COUNT][NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t lengths[NODE_A_TELEMETRY_FRAME_COUNT] = {0U};
  uint32_t sequence = 0U;
  uint8_t index;

  build_snapshot(&snapshot);
  NodeATelemetry_FormatAll(&sequence, &snapshot, frames, lengths);

  CHECK(NODE_A_TELEMETRY_VECTOR_COUNT == NODE_A_TELEMETRY_FRAME_COUNT);
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    CHECK(lengths[index] > 0U);
    CHECK(lengths[index] < NODE_A_TELEMETRY_FRAME_SIZE);
    CHECK(strlen(kNodeATelemetryVectors[index]) == (size_t)lengths[index]);
    CHECK(memcmp(kNodeATelemetryVectors[index], frames[index], lengths[index]) == 0);
  }
  return 0;
}

/* One frame is one sequenced snapshot: the consumer drops a repeated sequence
 * as a duplicate, so two distinct frames may never share a value. */
static int check_one_sequence_per_frame(void)
{
  NodeATelemetrySnapshot snapshot;
  char frames[NODE_A_TELEMETRY_FRAME_COUNT][NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t lengths[NODE_A_TELEMETRY_FRAME_COUNT] = {0U};
  uint32_t sequence = 0U;
  unsigned long seen[NODE_A_TELEMETRY_FRAME_COUNT] = {0UL};
  uint8_t index;
  uint8_t other;

  build_snapshot(&snapshot);
  NodeATelemetry_FormatAll(&sequence, &snapshot, frames, lengths);
  CHECK(sequence == NODE_A_TELEMETRY_FRAME_COUNT);

  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    char needle[32];
    const char *found;
    (void)snprintf(needle, sizeof(needle), "\"seq\":%lu,", (unsigned long)(index + 1U));
    found = strstr(frames[index], needle);
    CHECK(found != NULL);
    seen[index] = (unsigned long)(index + 1U);
  }
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    for (other = (uint8_t)(index + 1U); other < NODE_A_TELEMETRY_FRAME_COUNT; ++other) {
      CHECK(seen[index] != seen[other]);
    }
  }
  return 0;
}

/* The bridge caps a routed MQTT payload at screen_routing::kTransportPayloadLimit
 * and the display splits lines at screen_protocol::kUartLineLimit.  A frame must
 * fit both or the consumer never sees it. */
static int check_frames_fit_the_transport(void)
{
  NodeATelemetrySnapshot snapshot;
  char frames[NODE_A_TELEMETRY_FRAME_COUNT][NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t lengths[NODE_A_TELEMETRY_FRAME_COUNT] = {0U};
  uint32_t sequence = 0U;
  uint32_t total = 0U;
  uint8_t index;

  build_snapshot(&snapshot);
  NodeATelemetry_FormatAll(&sequence, &snapshot, frames, lengths);
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    /* 1024 is the ESP transport limit; 768 is the display line limit.  The
     * frame includes its CRLF, so leave room for both terminators. */
    CHECK(lengths[index] <= 766U);
    total += lengths[index];
  }
  /* Two telemetry intervals at 9600 8N1 carry 10 bits per byte.  A cycle that
   * does not fit here would be dropped rather than delayed, so the nominal
   * payload has to stay inside the link budget. */
  CHECK(total <= 3840U);
  return 0;
}

/* Every reading Node A emits has to be recognised by the CTRL-02 consumer.
 * These are the producer-side guarantees; the consumer half is asserted by
 * test_ctrl02_consumes_the_node_a_producer_vectors in the ESP suite. */
static int check_emitted_vocabulary(void)
{
  static const char *const required[] = {
      "\"assetCode\":\"ENV-01\",\"metric\":\"temperature\"",
      "\"assetCode\":\"ENV-01\",\"metric\":\"humidity\"",
      "\"assetCode\":\"GAS-01\",\"metric\":\"smoke.alarm\"",
      "\"assetCode\":\"GAS-01\",\"metric\":\"flame.alarm\"",
      "\"assetCode\":\"GAS-01\",\"metric\":\"flame.rawLevel\"",
      "\"assetCode\":\"LEVEL-L01\",\"metric\":\"level.detected\"",
      "\"assetCode\":\"GAS-01\",\"metric\":\"oxygen.raw\"",
      "\"assetCode\":\"GAS-01\",\"metric\":\"oxygen.voltage\"",
      "\"assetCode\":\"GAS-01\",\"metric\":\"methane.raw\"",
      "\"assetCode\":\"GAS-01\",\"metric\":\"methane.voltage\"",
      "\"assetCode\":\"GAS-01\",\"metric\":\"methane.alarm\"",
      "\"assetCode\":\"GAS-01\",\"metric\":\"co.raw\"",
      "\"assetCode\":\"GAS-01\",\"metric\":\"co.voltage\"",
      "\"assetCode\":\"FAN-01\",\"metric\":\"supply.voltage\"",
      "\"assetCode\":\"FAN-01\",\"metric\":\"motor.current\"",
      "\"assetCode\":\"FAN-01\",\"metric\":\"rotational.speed\"",
      "\"assetCode\":\"FAN-02\",\"metric\":\"supply.voltage\"",
      "\"assetCode\":\"FAN-02\",\"metric\":\"motor.current\"",
      "\"assetCode\":\"FAN-02\",\"metric\":\"rotational.speed\"",
      "\"assetCode\":\"CTRL-01\",\"metric\":\"led.mode\"",
      "\"assetCode\":\"CTRL-01\",\"metric\":\"led.brightnessPercent\"",
      "\"assetCode\":\"CTRL-01\",\"metric\":\"buzzer.active\"",
      "\"assetCode\":\"CTRL-01\",\"metric\":\"buzzer.muted\"",
  };
  NodeATelemetrySnapshot snapshot;
  char frames[NODE_A_TELEMETRY_FRAME_COUNT][NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t lengths[NODE_A_TELEMETRY_FRAME_COUNT] = {0U};
  uint32_t sequence = 0U;
  size_t index;

  build_snapshot(&snapshot);
  NodeATelemetry_FormatAll(&sequence, &snapshot, frames, lengths);
  for (index = 0U; index < sizeof(required) / sizeof(required[0]); ++index) {
    uint8_t frame_index;
    int found = 0;
    for (frame_index = 0U; frame_index < NODE_A_TELEMETRY_FRAME_COUNT; ++frame_index) {
      if (strstr(frames[frame_index], required[index]) != NULL) found = 1;
    }
    CHECK(found);
  }
  return 0;
}

/* The gas-status frame is the only source of the methane alarm bit.  Without
 * it the consumer's warning/critical source sets stay empty for a gas alarm. */
static int check_gas_status_reports_the_operational_alarm(void)
{
  NodeATelemetrySnapshot snapshot;
  char frames[NODE_A_TELEMETRY_FRAME_COUNT][NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t lengths[NODE_A_TELEMETRY_FRAME_COUNT] = {0U};
  uint32_t sequence = 0U;

  build_snapshot(&snapshot);
  snapshot.gas_alarm = 1U;
  snapshot.gas_warning = 1U;
  NodeATelemetry_FormatAll(&sequence, &snapshot, frames, lengths);
  CHECK(strstr(frames[3], "\"metric\":\"methane.alarm\",\"value\":1,") != NULL);
  CHECK(strstr(frames[3], "\"metric\":\"methane.warning\",\"value\":1,") != NULL);

  build_snapshot(&snapshot);
  snapshot.gas_alarm = 0U;
  NodeATelemetry_FormatAll(&sequence, &snapshot, frames, lengths);
  CHECK(strstr(frames[3], "\"metric\":\"methane.alarm\",\"value\":0,") != NULL);
  return 0;
}

/* The legacy Web/IoTDA controller path may command any 0..100 duty.  The
 * producer must place that value verbatim in diag.pwmPercent: it is the only
 * ordered actual-duty signal the menu screen has. */
static int check_legacy_duty_reaches_the_wire(void)
{
  NodeATelemetrySnapshot snapshot;
  char frames[NODE_A_TELEMETRY_FRAME_COUNT][NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t lengths[NODE_A_TELEMETRY_FRAME_COUNT] = {0U};
  uint32_t sequence = 0U;

  build_snapshot(&snapshot);
  snapshot.actuators.fan1_pwm_percent = 45U;
  snapshot.actuators.fan2_pwm_percent = 7U;
  NodeATelemetry_FormatAll(&sequence, &snapshot, frames, lengths);
  CHECK(strstr(frames[1], "\"pwmPercent\":45") != NULL);
  CHECK(strstr(frames[2], "\"pwmPercent\":7") != NULL);
  return 0;
}

int main(void)
{
  (void)check_frames_match_committed_vectors();
  (void)check_one_sequence_per_frame();
  (void)check_frames_fit_the_transport();
  (void)check_emitted_vocabulary();
  (void)check_gas_status_reports_the_operational_alarm();
  (void)check_legacy_duty_reaches_the_wire();

  if (failures != 0) {
    (void)fprintf(stderr, "%d check(s) failed\n", failures);
    return 1;
  }
  (void)printf("node_a_telemetry_host_test: ok\n");
  return 0;
}
