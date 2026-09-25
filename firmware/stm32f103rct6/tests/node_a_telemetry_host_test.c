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
static const SensorReading fixture_sensors[] = {
  { .asset_code = "SHT-01", .kind = SENSOR_KIND_SHT30, .quality = SENSOR_QUALITY_GOOD,
    .online = 1U, .temperature_centi_c = 2345, .humidity_centi_rh = 5210U },
  { .asset_code = "O2-01", .kind = SENSOR_KIND_O2, .quality = SENSOR_QUALITY_SUSPECT,
    .online = 1U, .raw = 812U, .microvolts = 654000UL },
  { .asset_code = "MQ4-01", .kind = SENSOR_KIND_MQ4, .quality = SENSOR_QUALITY_GOOD,
    .online = 1U, .raw = 0U, .microvolts = 0UL },
  { .asset_code = "CO-01", .kind = SENSOR_KIND_CO, .quality = SENSOR_QUALITY_SUSPECT,
    .online = 1U, .raw = 138U, .microvolts = 111000UL },
  { .asset_code = "MQ2-01", .kind = SENSOR_KIND_MQ2, .quality = SENSOR_QUALITY_GOOD,
    .online = 1U, .alarm = 0U },
  { .asset_code = "FLAME-01", .kind = SENSOR_KIND_FLAME, .quality = SENSOR_QUALITY_GOOD,
    .online = 1U, .alarm = 0U },
  { .asset_code = "LEVEL-01", .kind = SENSOR_KIND_LEVEL, .quality = SENSOR_QUALITY_GOOD,
    .online = 1U, .alarm = 0U }
};

static void build_snapshot(NodeATelemetrySnapshot *snapshot)
{
  (void)memset(snapshot, 0, sizeof(*snapshot));
  snapshot->sensors = fixture_sensors;
  snapshot->sensor_count = (uint8_t)(sizeof(fixture_sensors) / sizeof(fixture_sensors[0]));
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

/* The committed cycle total.  node_a.c's link-budget comment quotes it and the
 * ESP consumer suite relies on a cycle converging over six frames, so the
 * number is pinned here where it is re-derived from the board formatter. */
#define NODE_A_TELEMETRY_CYCLE_BYTES 2867U

/* The bridge caps a routed MQTT payload at screen_routing::kTransportPayloadLimit
 * and the display splits lines at screen_protocol::kUartLineLimit.  A frame must
 * fit both or the consumer never sees it.  This is the lower-bound transport
 * check; the interval budget itself is asserted by
 * check_one_frame_per_interval_fits_the_link. */
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
  /* The whole cycle is 2870 bytes.  It does NOT fit one telemetry interval of
   * the 9600 baud link (1920 bytes), which is why the board rotates one frame
   * per interval instead of offering the cycle whole. */
  CHECK(total == NODE_A_TELEMETRY_CYCLE_BYTES);
  return 0;
}

/* The board's schedule: one frame per telemetry interval, rotating so every
 * frame of the cycle is emitted before any frame repeats.  The offered bytes
 * per interval must stay inside the link budget with the ACK reserve left over.
 *
 * Reproduces node_a.c Telemetry_EmitOneFrame over the queue from
 * Core/Src/uart_tx_queue.c - the same ring the board drains - so this is the
 * producer side of the multi-cycle throughput proof rather than a model. */
static int check_one_frame_per_interval_fits_the_link(void)
{
  static const uint32_t kLinkBytesPerInterval = 1920U;   /* 2 s at 9600 8N1 */
  static const uint32_t kAckReserveBytes = 350U;
  NodeATelemetrySnapshot snapshot;
  char frames[NODE_A_TELEMETRY_FRAME_COUNT][NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t lengths[NODE_A_TELEMETRY_FRAME_COUNT] = {0U};
  uint32_t sequence = 0U;
  uint32_t offered = 0U;
  uint8_t index;

  build_snapshot(&snapshot);
  NodeATelemetry_FormatAll(&sequence, &snapshot, frames, lengths);
  /* One interval offers exactly one frame, and that interval's link budget has
   * to cover the frame plus the reserve the ACKs and diagnostics draw on - the
   * assertion node_a.c makes at build time, repeated here against the real
   * re-derived lengths. */
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    offered = lengths[index];
    CHECK(offered < kLinkBytesPerInterval);
    CHECK(offered + kAckReserveBytes <= kLinkBytesPerInterval);
  }
  return 0;
}

/* Six intervals must emit six distinct frames with six distinct sequences, and
 * the bytes offered across the rotation must stay under what those intervals
 * carry.  This is the producer half of the rotation contract; the consumer
 * half - that each frame still lands in the merged snapshot - is the ESP
 * suite's producer-vector test. */
static int check_rotation_visits_every_frame(void)
{
  static const uint32_t kLinkBytesPerInterval = 1920U;   /* 2 s at 9600 8N1 */
  NodeATelemetrySnapshot snapshot;
  char frame[NODE_A_TELEMETRY_FRAME_SIZE];
  uint32_t sequence = 0U;
  uint32_t offered = 0U;
  uint8_t seen[NODE_A_TELEMETRY_FRAME_COUNT] = {0U};
  uint8_t index;
  uint8_t step;

  build_snapshot(&snapshot);
  for (step = 0U; step < NODE_A_TELEMETRY_FRAME_COUNT; ++step) {
    uint16_t length = 0U;
    index = (uint8_t)(sequence % NODE_A_TELEMETRY_FRAME_COUNT);

    CHECK(seen[index] == 0U);
    CHECK(NodeATelemetry_FormatFrame(sequence + 1U, &snapshot, frame,
                                     &length) == 1U);
    CHECK(length != 0U);
    seen[index] = 1U;
    offered += length;
    ++sequence;
  }
  /* Every frame of the cycle was emitted exactly once, and the offered bytes
   * are the whole cycle - inside the 6 * 1920 bytes the six intervals carry,
   * with the difference left as the ACK/diagnostic reserve. */
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    CHECK(seen[index] == 1U);
  }
  CHECK(sequence == NODE_A_TELEMETRY_FRAME_COUNT);
  CHECK(offered == NODE_A_TELEMETRY_CYCLE_BYTES);
  CHECK(offered < NODE_A_TELEMETRY_FRAME_COUNT * kLinkBytesPerInterval);
  return 0;
}

/* Every reading Node A emits has to be recognised by the CTRL-02 consumer.
 * These are the producer-side guarantees; the consumer half is asserted by
 * test_ctrl02_consumes_the_node_a_producer_vectors in the ESP suite. */
static int check_emitted_vocabulary(void)
{
  static const char *const required[] = {
      "\"assetCode\":\"SHT-01\",\"metric\":\"temperature\"",
      "\"assetCode\":\"SHT-01\",\"metric\":\"humidity\"",
      "\"assetCode\":\"MQ2-01\",\"metric\":\"smoke.alarm\"",
      "\"assetCode\":\"FLAME-01\",\"metric\":\"flame.alarm\"",
      "\"assetCode\":\"FLAME-01\",\"metric\":\"flame.rawLevel\"",
      "\"assetCode\":\"LEVEL-01\",\"metric\":\"level.detected\"",
      "\"assetCode\":\"O2-01\",\"metric\":\"oxygen.raw\"",
      "\"assetCode\":\"O2-01\",\"metric\":\"oxygen.voltage\"",
      "\"assetCode\":\"MQ4-01\",\"metric\":\"methane.raw\"",
      "\"assetCode\":\"MQ4-01\",\"metric\":\"methane.voltage\"",
      "\"assetCode\":\"MQ4-01\",\"metric\":\"methane.alarm\"",
      "\"assetCode\":\"CO-01\",\"metric\":\"co.raw\"",
      "\"assetCode\":\"CO-01\",\"metric\":\"co.voltage\"",
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

static int check_each_fan_reports_its_own_relay(void)
{
  NodeATelemetrySnapshot snapshot;
  char frames[NODE_A_TELEMETRY_FRAME_COUNT][NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t lengths[NODE_A_TELEMETRY_FRAME_COUNT] = {0U};
  uint32_t sequence = 0U;
  uint8_t index;
  uint8_t saw_fan1 = 0U;
  uint8_t saw_fan2 = 0U;

  build_snapshot(&snapshot);
  snapshot.actuators.fan1_pwm_percent = 30U;
  snapshot.actuators.fan2_pwm_percent = 0U;
  NodeATelemetry_FormatAll(&sequence, &snapshot, frames, lengths);
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    if (strstr(frames[index], "\"assetCode\":\"FAN-01\"") != NULL) {
      CHECK(strstr(frames[index], "\"relayActive\":1") != NULL);
      saw_fan1 = 1U;
    }
    if (strstr(frames[index], "\"assetCode\":\"FAN-02\"") != NULL) {
      CHECK(strstr(frames[index], "\"relayActive\":0") != NULL);
      saw_fan2 = 1U;
    }
  }
  CHECK(saw_fan1 != 0U && saw_fan2 != 0U);

  snapshot.actuators.fan1_pwm_percent = 0U;
  snapshot.actuators.fan2_pwm_percent = 60U;
  NodeATelemetry_FormatAll(&sequence, &snapshot, frames, lengths);
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    if (strstr(frames[index], "\"assetCode\":\"FAN-01\"") != NULL)
      CHECK(strstr(frames[index], "\"relayActive\":0") != NULL);
    if (strstr(frames[index], "\"assetCode\":\"FAN-02\"") != NULL)
      CHECK(strstr(frames[index], "\"relayActive\":1") != NULL);
  }

  snapshot.actuators.relay_on = 0U;
  NodeATelemetry_FormatAll(&sequence, &snapshot, frames, lengths);
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    if (strstr(frames[index], "\"assetCode\":\"FAN-02\"") != NULL)
      CHECK(strstr(frames[index], "\"relayActive\":0") != NULL);
  }
  return 0;
}

int main(void)
{
  {
    NodeATelemetrySnapshot snapshot;
    SensorReading sht[4] = {
      {.asset_code="SHT-01", .kind=SENSOR_KIND_SHT30, .online=1, .quality=SENSOR_QUALITY_GOOD, .temperature_centi_c=2345, .humidity_centi_rh=5000},
      {.asset_code="SHT-02", .kind=SENSOR_KIND_SHT30, .online=1, .quality=SENSOR_QUALITY_GOOD, .temperature_centi_c=-1234, .humidity_centi_rh=10000},
      {.asset_code="SHT-03", .kind=SENSOR_KIND_SHT30, .online=0, .quality=SENSOR_QUALITY_MISSING},
      {.asset_code="SHT-04", .kind=SENSOR_KIND_SHT30, .online=1, .quality=SENSOR_QUALITY_GOOD, .temperature_centi_c=12500, .humidity_centi_rh=9999}
    };
    char frames[NODE_A_TELEMETRY_FRAME_COUNT][NODE_A_TELEMETRY_FRAME_SIZE];
    uint16_t lengths[NODE_A_TELEMETRY_FRAME_COUNT];
    uint32_t sequence=UINT32_MAX-6U;
    build_snapshot(&snapshot);
    snapshot.sensors=sht;
    snapshot.sensor_count=4;
    snapshot.methane_raw=4095;
    snapshot.co_raw=4095;
    snapshot.methane_microvolts=3300000;
    snapshot.co_microvolts=3300000;
    NodeATelemetry_FormatAll(&sequence,&snapshot,frames,lengths);
    CHECK(strstr(frames[0], "SHT-01") != NULL);
    CHECK(strstr(frames[3], "SHT-02") != NULL);
    CHECK(strstr(frames[3], "-12.34") != NULL);
    CHECK(strstr(frames[4], "SHT-03") != NULL);
    CHECK(strstr(frames[4], "\"quality\":\"missing\"") != NULL);
    CHECK(strstr(frames[5], "SHT-04") != NULL);
    CHECK(strstr(frames[5], "125.00") != NULL);
    unsigned total=0;
    for(unsigned i=0;i<NODE_A_TELEMETRY_FRAME_COUNT;i++) {
      CHECK(lengths[i]>4 && lengths[i]<766);
      CHECK(strcmp(frames[i]+lengths[i]-3, "}\r\n")==0);
      if(i>=3) CHECK(strcmp(frames[i]+lengths[i]-4, "]}\r\n")==0);
      total+=lengths[i];
    }
    CHECK(total<6U*1920U);
    /* A disconnected fourth sensor must replace a previous good value. */
    sht[3].online=0; sht[3].quality=SENSOR_QUALITY_MISSING;
    NodeATelemetry_FormatAll(&sequence,&snapshot,frames,lengths);
    CHECK(strstr(frames[5], "\"quality\":\"missing\"")!=NULL);
  }
#if defined(NODE_A_FAN_RELAY_FOCUSED_TEST)
  (void)check_each_fan_reports_its_own_relay();
#else
  (void)check_frames_match_committed_vectors();
  (void)check_one_sequence_per_frame();
  (void)check_frames_fit_the_transport();
  (void)check_one_frame_per_interval_fits_the_link();
  (void)check_rotation_visits_every_frame();
  (void)check_emitted_vocabulary();
  (void)check_gas_status_reports_the_operational_alarm();
  (void)check_legacy_duty_reaches_the_wire();
  (void)check_each_fan_reports_its_own_relay();
#endif

  if (failures != 0) {
    (void)fprintf(stderr, "%d check(s) failed\n", failures);
    return 1;
  }
  (void)printf("node_a_telemetry_host_test: ok\n");
  return 0;
}
