#ifndef NODE_A_TELEMETRY_H
#define NODE_A_TELEMETRY_H

#include "node_a_command.h"

#include <stdint.h>

/* The sensor readings the Node A producer formats.  They live here rather than
 * in node_a.c so the host test can drive the same formatter the board runs. */
typedef struct
{
  uint8_t online;
  int16_t temperature_centi_c;
  uint16_t humidity_centi_rh;
} Sht30Reading;

typedef struct
{
  uint8_t online;
  uint8_t plausible;
  uint8_t fault;
  uint16_t manufacturer_id;
  uint16_t die_id;
  uint16_t config_raw;
  uint16_t bus_raw;
  int16_t shunt_raw;
  int16_t current_raw;
  uint16_t power_raw;
  uint16_t calibration_raw;
  uint32_t bus_microvolts;
  int32_t current_microamps;
  int32_t power_microwatts;
} Ina226Reading;

/* Node A's wire contract for the local MQTT bridge and the local screen.
 *
 * The frames are pure formatting over one immutable sample block so a host
 * test can reproduce the exact bytes the board transmits.  Keep every frame
 * comfortably below NODE_A_TELEMETRY_FRAME_SIZE: the ESP bridge accepts at
 * most screen_routing::kTransportPayloadLimit (1024) bytes and a frame must
 * fit screen_protocol::kUartLineLimit (768) once the bridge has added its
 * line terminator.
 *
 * A whole cycle does NOT fit the 9600 baud link inside one telemetry interval
 * (see the budget arithmetic in node_a.c), so the board emits ONE frame per
 * telemetry interval and rotates: sequence 1 is slot 0 (slot = (sequence - 1)
 * % NODE_A_TELEMETRY_FRAME_COUNT), and the sequence only advances for frames
 * that were really queued.
 * The CTRL-02 accumulator merges every accepted frame into the snapshot it
 * already holds, so the whole state converges over NODE_A_TELEMETRY_FRAME_COUNT
 * intervals and no field is ever dropped - only aged, by a bounded and
 * documented amount. */
#define NODE_A_TELEMETRY_FRAME_COUNT 6U
#define NODE_A_TELEMETRY_FRAME_SIZE 768U

/* Slot 1 is the physically installed SHT30; the other slots are reserved
 * buses and must not create fabricated zero-value readings. */
typedef struct {
  Sht30Reading environment;
  uint16_t oxygen_raw;
  uint32_t oxygen_microvolts;
  uint8_t oxygen_online;
  uint16_t methane_raw;
  uint32_t methane_microvolts;
  uint8_t methane_online;
  uint16_t co_raw;
  uint32_t co_microvolts;
  uint8_t co_online;
  uint8_t smoke_alarm;
  uint8_t flame_alarm;
  uint8_t level_detected;
  /* Smoke and flame report "missing" until a sample has been latched, exactly
   * as the pre-extraction producer did with its *_last_sample_at stamps. */
  uint8_t smoke_sampled;
  uint8_t flame_sampled;
  uint8_t level_stable;
  /* The local safety model that already drives the audible alarm.  Only the
   * methane bits are operational; the oxygen and CO bits are telemetry-only
   * and must never drive an actuator. */
  uint8_t gas_warning;
  uint8_t gas_alarm;
  uint8_t oxygen_warning;
  uint8_t oxygen_alarm;
  uint8_t co_warning;
  uint8_t co_alarm;
  Ina226Reading fan1_power;
  Ina226Reading fan2_power;
  uint32_t fan1_rpm;
  uint32_t fan2_rpm;
  NodeAActuatorState actuators;
  uint8_t auto_ventilation_active;
  uint8_t cooldown_active;
} NodeATelemetrySnapshot;

/* Formats all NODE_A_TELEMETRY_FRAME_COUNT frames of one cycle.
 *
 * `sequence` is in/out: every emitted frame takes the next value, so one
 * frame is exactly one sequenced snapshot on the wire.  A consumer that
 * de-duplicates by sequence must never see two different frames share a
 * value.  `lengths` and `frames` may be NULL when a caller only needs the
 * sequence advance. */
void NodeATelemetry_FormatAll(uint32_t *sequence, const NodeATelemetrySnapshot *snapshot,
                              char frames[NODE_A_TELEMETRY_FRAME_COUNT][NODE_A_TELEMETRY_FRAME_SIZE],
                              uint16_t lengths[NODE_A_TELEMETRY_FRAME_COUNT]);

/* Formats one frame for its wire sequence.  This function is pure with
 * respect to rotation state: it does not advance a cursor or commit anything
 * to a transport.  Sequence 1 is rotation slot 0, sequence 2 is slot 1, and
 * so on. */
uint8_t NodeATelemetry_FormatFrame(uint32_t sequence,
                                   const NodeATelemetrySnapshot *snapshot,
                                   char *frame, uint16_t *length);

/* Transport callback used by the production offer path and by host tests.  It
 * must enqueue the complete frame without blocking and return 1 only when the
 * destination accepted it. */
typedef uint8_t (*NodeATelemetryEnqueueFn)(void *context, const char *frame,
                                          uint16_t length);

/* Formats and offers the next rotation frame as one transaction.  The
 * sequence is committed only after `enqueue` accepts the complete frame, so a
 * refused frame is retried with the same sequence and slot. */
uint8_t NodeATelemetry_QueueNext(uint32_t *sequence,
                                 const NodeATelemetrySnapshot *snapshot,
                                 NodeATelemetryEnqueueFn enqueue,
                                 void *context);

/* Offers exactly one complete rotation request.  A refusal leaves the cursor
 * parked at the first unaccepted slot and returns 0; retrying the request
 * resumes there and returns 1 only after all six slots are accepted. */
uint8_t NodeATelemetry_QueueFullRotation(uint32_t *sequence,
                                          const NodeATelemetrySnapshot *snapshot,
                                          NodeATelemetryEnqueueFn enqueue,
                                          void *context);

#endif
