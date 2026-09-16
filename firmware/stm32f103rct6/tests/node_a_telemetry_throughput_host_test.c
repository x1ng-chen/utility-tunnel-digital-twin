/* Multi-cycle throughput and backpressure contract for the Node A telemetry
 * schedule.
 *
 * The producer used to offer a whole six-frame telemetry cycle (2870 bytes)
 * every TELEMETRY_INTERVAL_MS, while 9600 8N1 carries only 1920 bytes in that
 * window.  The link could never drain a cycle, so the queue refused whole
 * frames - and because the CTRL-02 accumulator merges partial frames, a
 * refused actuator or gas-status frame became a permanently stale field.
 *
 * This test drives the real production schedule and the real queue together:
 *
 *   - production is the board's rotation, one frame per interval through
 *     NodeATelemetry_QueueNext (the same helper the firmware calls);
 *   - transport is Core/Src/uart_tx_queue.c with the board's byte budget;
 *   - the drain clock is virtual, one byte per 10 bit times at 9600.  A byte
 *     budget of N therefore cannot finish before N bytes worth of wire time
 *     have passed, so waiting is modelled rather than assumed away.
 *
 * The properties proved over many cycles are the ones the review asked for:
 * every frame of the cycle keeps being delivered (no starvation), the offered
 * load never exceeds what the link drains (no unbounded backlog), and the
 * interval still leaves room for the ACK reserve.
 *
 * HAL_UART_Transmit is modelled here rather than linked, exactly as
 * uart_tx_queue_host_test.c does.
 */
#include "node_a_telemetry.h"
#include "uart_tx_queue.h"

#include <stdio.h>
#include <string.h>

static int failures = 0;

#define CHECK(condition)                                                      \
  do {                                                                        \
    if (!(condition)) {                                                       \
      (void)fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__,           \
                    #condition);                                              \
      ++failures;                                                             \
    }                                                                         \
  } while (0)

/* --- Link model ---------------------------------------------------------- */

/* The board's constants, restated the way node_a.c's _Static_asserts read
 * them. */
#define TEST_BAUD                  9600U
#define TEST_INTERVAL_MS           2000U
#define TEST_BITS_PER_BYTE            10U
#define TEST_DRAIN_BUDGET              48U   /* NODE_A_UART_TX_DRAIN_BYTES */
#define TEST_LINK_BYTES_PER_CYCLE \
  ((TEST_BAUD * (TEST_INTERVAL_MS / 1000U)) / TEST_BITS_PER_BYTE)
#define TEST_ACK_RESERVE_BYTES        350U   /* NODE_A_UART_ACK_RESERVE_BYTES */
#define TEST_CYCLE_BYTES             2867U
#define TEST_WIDEST_FRAME_BYTES       682U   /* the environmental frame */

/* Microseconds one byte occupies the wire at the modelled baud: 10 bit times
 * at 9600 is 1041 us.  The clock is kept in microseconds so the model runs at
 * the real link rate instead of a rounded-up one that would hide a shortfall. */
#define TEST_BYTE_TIME_US            1041U
_Static_assert((TEST_BITS_PER_BYTE * 1000000U) / TEST_BAUD == TEST_BYTE_TIME_US,
               "the modelled byte time must be 1041 us at 9600 8N1");
/* Microseconds one modelled interval covers. */
#define TEST_INTERVAL_US \
  ((uint32_t)TEST_INTERVAL_MS * 1000U)

/* Milliseconds of each interval that the foreground loop spends inside the
 * sensor block.  The drain is not called at all while sampling, so the wire is
 * idle and only TEST_INTERVAL_MS - TEST_BLOCKED_MS can carry bytes.  The
 * widest frame of the rotation has to drain inside that window or it would
 * take more than one interval and hold up the frames behind it; see
 * test_the_drain_window_bounds_the_schedule for the inequality. */
#define TEST_BLOCKED_MS               400U

static char link_bytes[262144];
static size_t link_length;
static unsigned long link_calls;
static uint32_t hw_now_us;

HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *uart, uint8_t *data,
                                    uint16_t size, uint32_t timeout)
{
  (void)uart;
  (void)timeout;
  ++link_calls;
  if (size != 1U) return HAL_ERROR;
  if (link_length + size > sizeof(link_bytes)) return HAL_ERROR;
  link_bytes[link_length++] = (char)data[0];
  return HAL_OK;
}

static UART_HandleTypeDef kUart = {0};

/* This is the same enqueue callback the board gives to the production
 * telemetry helper.  The host therefore drives the formatter, queue offer and
 * sequence commit as one transaction instead of copying that logic here. */
typedef struct {
  UartTxQueue *queue;
  char last_frame[NODE_A_TELEMETRY_FRAME_SIZE];
  uint16_t last_length;
} QueueOffer;

typedef struct {
  UartTxQueue *esp;
  UartTxQueue *debug;
} DualQueueOffer;

static uint8_t enqueue_to_uart_queue(void *context, const char *frame,
                                     uint16_t length)
{
  QueueOffer *offer = (QueueOffer *)context;
  (void)memcpy(offer->last_frame, frame, length);
  offer->last_length = length;
  return UartTx_Enqueue(offer->queue, frame, length);
}

static uint8_t enqueue_to_queue(void *context, const char *frame,
                                uint16_t length)
{
  return UartTx_Enqueue((UartTxQueue *)context, frame, length);
}

static uint8_t enqueue_to_dual_queue(void *context, const char *frame,
                                     uint16_t length)
{
  DualQueueOffer *offer = (DualQueueOffer *)context;

  if (UartTx_Enqueue(offer->esp, frame, length) == 0U) return 0U;
  /* ESP is the commit point.  The debug mirror is best-effort, exactly like
   * the board callback; this test uses equal queues so both copies fit. */
  (void)UartTx_Enqueue(offer->debug, frame, length);
  return 1U;
}

/* Moves at most `budget` bytes, charging the wire time of each one to the
 * virtual clock.  This is the board's drain call with the HAL's own baud
 * throttling made explicit: the loop cannot come back before the previous byte
 * has finished, so the transmittable rate is the link rate and not the loop
 * rate. */
static void drain_once(UartTxQueue *queue, uint16_t budget)
{
  uint16_t moved = 0U;
  while ((moved < budget) && (UartTx_Pending(queue) != 0U)) {
    /* The queue stamps its stall backoff in milliseconds; the virtual clock is
     * microseconds, so hand it the equivalent value. */
    if (UartTx_Drain(queue, &kUart, 1U, hw_now_us / 1000U) == 0U) break;
    hw_now_us += TEST_BYTE_TIME_US;
    ++moved;
  }
}

/* --- Producer fixture ---------------------------------------------------- */

/* The same fixture tests/node_a_telemetry_host_test.c pins against the
 * committed vectors, so the schedule below emits the real frames. */
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
  snapshot->methane_online = 1U;
  snapshot->co_raw = 138U;
  snapshot->co_microvolts = 111000UL;
  snapshot->co_online = 1U;
  snapshot->smoke_sampled = 1U;
  snapshot->flame_sampled = 1U;
  snapshot->level_stable = 1U;
  snapshot->fan1_power.online = 1U;
  snapshot->fan1_power.plausible = 1U;
  snapshot->fan1_power.bus_microvolts = 11900000UL;
  snapshot->fan1_power.current_microamps = 320000;
  snapshot->fan1_power.power_microwatts = 3808000;
  snapshot->fan2_power.online = 1U;
  snapshot->fan2_power.plausible = 1U;
  snapshot->fan2_power.bus_microvolts = 11800000UL;
  snapshot->fan2_power.current_microamps = 280000;
  snapshot->fan2_power.power_microwatts = 3304000;
  snapshot->fan1_rpm = 2400U;
  snapshot->fan2_rpm = 1600U;
  snapshot->actuators.fan1_pwm_percent = 60U;
  snapshot->actuators.fan2_pwm_percent = 60U;
  snapshot->actuators.relay_on = 1U;
  snapshot->actuators.led_mode = 1U;
  snapshot->actuators.led_brightness_percent = 75U;
}

/* --- Cycle model --------------------------------------------------------- */

typedef struct {
  unsigned delivered[NODE_A_TELEMETRY_FRAME_COUNT];
  unsigned offered;
  unsigned refused;
  size_t bytes;
  uint16_t peak_queue;
} RunResult;

/* Which rotation slot a delivered line belongs to.  Keyed on a metric that is
 * unique to each frame, so a partial or corrupted line cannot be miscounted. */
static int classify_line(const char *line, size_t length)
{
  static const char *const needles[NODE_A_TELEMETRY_FRAME_COUNT] = {
      "\"temperature\"", "\"FAN-01\"", "\"FAN-02\"",
      "\"methane.alarm\"", "\"methane.raw\"", "\"led.mode\"",
  };
  uint8_t index;
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    if (memmem(line, length, needles[index], strlen(needles[index])) != NULL) {
      return (int)index;
    }
  }
  return -1;
}

/* Collects whole CRLF-terminated lines from the link cursor onward. */
static void collect_lines(RunResult *result, size_t *cursor)
{
  size_t at = *cursor;
  while (at < link_length) {
    const size_t start = at;
    int which;
    while ((at < link_length) && (link_bytes[at] != '\n')) ++at;
    if (at >= link_length) break;   /* a partial line: leave it for next time */
    ++at;
    which = classify_line(link_bytes + start, at - start);
    if (which >= 0) ++result->delivered[which];
  }
  *cursor = at;
}

/* Runs the production schedule for `cycles` intervals and reports what the
 * link actually received. */
static void run_cycles(UartTxQueue *queue, const NodeATelemetrySnapshot *snapshot,
                       uint32_t cycles, uint32_t blocked_ms, RunResult *result)
{
  uint32_t sequence = 0U;
  uint32_t cycle;
  size_t cursor = 0U;

  (void)memset(result, 0, sizeof(*result));
  for (cycle = 0U; cycle < cycles; ++cycle) {
    const uint32_t interval_start = cycle * TEST_INTERVAL_US;
    const uint32_t interval_end = interval_start + TEST_INTERVAL_US;
    /* Sensor acquisition holds the foreground loop inside the sampling block,
     * so the drain is not called and the wire is idle.  Starting the model at
     * the end of the block is how that idle window is represented. */
    hw_now_us = interval_start + (blocked_ms * 1000U);

    /* One frame is offered per interval.  It is queued whole or refused whole,
     * and the sequence is committed only for a frame that was queued, so a
     * refused frame stays the next frame to offer. */
    ++result->offered;
    if (NodeATelemetry_QueueNext(&sequence, snapshot, enqueue_to_queue,
                                 queue) == 0U)
      ++result->refused;
    if (queue->peak_used > result->peak_queue) result->peak_queue = queue->peak_used;

    /* The rest of the interval is the fast loop, draining under the byte
     * budget until the interval's wire time is used up.  A queue that cannot
     * empty in time simply carries over to the next interval. */
    while ((hw_now_us < interval_end) && (UartTx_Pending(queue) != 0U)) {
      const uint32_t remaining_us = interval_end - hw_now_us;
      const uint32_t remaining_bytes = remaining_us / TEST_BYTE_TIME_US;
      const uint16_t budget = (remaining_bytes < TEST_DRAIN_BUDGET)
                                  ? (uint16_t)remaining_bytes
                                  : TEST_DRAIN_BUDGET;
      if (budget == 0U) break;
      drain_once(queue, budget);
    }
    hw_now_us = interval_end;

    collect_lines(result, &cursor);
  }
  result->bytes = cursor;
}

/* --- Tests --------------------------------------------------------------- */

/* One interval offers exactly one frame, and the interval's bytes cover it
 * with the ACK reserve left over.  This is what the old whole-cycle burst
 * violated: it offered the 2870-byte cycle into a 1920-byte window. */
static void test_one_frame_per_interval_fits_the_budget(void)
{
  NodeATelemetrySnapshot snapshot;
  char frame[NODE_A_TELEMETRY_FRAME_SIZE];
  uint32_t sequence = 0U;
  uint32_t offered = 0U;
  uint8_t index;

  build_snapshot(&snapshot);
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    uint16_t length = 0U;
    CHECK(NodeATelemetry_FormatFrame(sequence + 1U, &snapshot, frame,
                                     &length) == 1U);
    CHECK(length != 0U);
    CHECK((uint32_t)length < TEST_LINK_BYTES_PER_CYCLE);
    CHECK((uint32_t)length + TEST_ACK_RESERVE_BYTES <= TEST_LINK_BYTES_PER_CYCLE);
    offered += length;
    ++sequence;
  }
  /* The whole cycle is still offered - just spread over six intervals, and
   * every byte of it still leaves the board. */
  CHECK(offered == TEST_CYCLE_BYTES);
}

/* Long-run production must stay under what the link drains, or the queue would
 * grow without bound and start refusing frames.  Thirty cycles is five full
 * rotations: enough for a one-frame-per-rotation shortfall to show up as a
 * growing backlog or a growing refusal count. */
static void test_sustained_throughput_never_refuses_a_frame(void)
{
  NodeATelemetrySnapshot snapshot;
  UartTxQueue queue;
  RunResult result;
  const uint32_t cycles = 30U;

  build_snapshot(&snapshot);
  link_length = 0U;
  link_calls = 0UL;
  UartTx_Init(&queue);
  run_cycles(&queue, &snapshot, cycles, TEST_BLOCKED_MS, &result);

  /* No frame was refused, so no state-carrying frame could go stale. */
  CHECK(result.refused == 0U);
  CHECK(queue.dropped_frames == 0U);
  CHECK(queue.dropped_bytes == 0U);
  CHECK(result.offered == cycles);
  /* Every frame got its turn: five deliveries each across thirty cycles. */
  {
    uint8_t index;
    for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
      CHECK(result.delivered[index] == cycles / NODE_A_TELEMETRY_FRAME_COUNT);
    }
  }
  /* The delivered rate is a fraction of the link rate, which is what makes the
   * schedule sustainable rather than merely bounded. */
  {
    const uint32_t window_ms = cycles * TEST_INTERVAL_MS;
    const uint32_t delivered_per_second =
        (uint32_t)((result.bytes * 1000U) / window_ms);
    CHECK(delivered_per_second < (TEST_BAUD / TEST_BITS_PER_BYTE) / 2U);
  }
  /* The queue never held more than one frame of telemetry: the drain kept up
   * within the interval, so the ring is a burst buffer, not a backlog. */
  CHECK(result.peak_queue <= NODE_A_TELEMETRY_FRAME_SIZE);
}

/* A tighter interval: two thirds of the wire time is available instead of four
 * fifths.  Nothing may be refused, and every frame must still arrive exactly
 * once per rotation - the frames behind a slow one must not be skipped. */
static void test_a_tighter_interval_still_delivers_exactly(void)
{
  NodeATelemetrySnapshot snapshot;
  UartTxQueue queue;
  RunResult result;
  const uint32_t cycles = 60U;
  const uint32_t blocked_ms = 800U;
  uint32_t available_bytes;
  uint8_t index;

  build_snapshot(&snapshot);
  link_length = 0U;
  link_calls = 0UL;
  UartTx_Init(&queue);

  /* The widest frame still fits the wire time this interval leaves. */
  available_bytes = ((TEST_INTERVAL_MS - blocked_ms) * 1000U) / TEST_BYTE_TIME_US;
  CHECK(available_bytes > TEST_WIDEST_FRAME_BYTES);

  run_cycles(&queue, &snapshot, cycles, blocked_ms, &result);
  CHECK(result.refused == 0U);
  CHECK(queue.dropped_frames == 0U);
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    CHECK(result.delivered[index] == cycles / NODE_A_TELEMETRY_FRAME_COUNT);
  }
}

/* The inequality the whole schedule rests on: the drain window left after the
 * sampling block has to be able to carry the widest frame of the rotation, and
 * the rotation as a whole has to cost well under the link rate.  A build that
 * broke either of those would still pass the byte-budget assertion in
 * node_a.c, which only looks at the link, so it is checked against the real
 * re-derived lengths here. */
static void test_the_drain_window_bounds_the_schedule(void)
{
  NodeATelemetrySnapshot snapshot;
  char frame[NODE_A_TELEMETRY_FRAME_SIZE];
  uint32_t sequence = 0U;
  uint32_t widest = 0U;
  uint32_t cycle_bytes = 0U;
  const uint32_t window_us = (TEST_INTERVAL_MS - TEST_BLOCKED_MS) * 1000U;
  const uint32_t window_bytes = window_us / TEST_BYTE_TIME_US;
  uint8_t index;

  build_snapshot(&snapshot);
  for (index = 0U; index < NODE_A_TELEMETRY_FRAME_COUNT; ++index) {
    uint16_t length = 0U;
    CHECK(NodeATelemetry_FormatFrame(sequence + 1U, &snapshot, frame,
                                     &length) == 1U);
    if ((uint32_t)length > widest) widest = length;
    cycle_bytes += length;
    ++sequence;
  }
  CHECK(widest == TEST_WIDEST_FRAME_BYTES);
  /* One frame drains inside the interval; the sampling block may grow to
   * 1.29 s before that stopped being true. */
  CHECK(widest < window_bytes);
  CHECK(window_bytes - widest >= TEST_ACK_RESERVE_BYTES);
  /* The rotation costs a third of the six intervals it spans. */
  CHECK(cycle_bytes * 3U < TEST_LINK_BYTES_PER_CYCLE * NODE_A_TELEMETRY_FRAME_COUNT);
}

/* The caller supplies the sensor-block duration to the scheduler model.  A
 * 1300 ms block leaves fewer wire bytes than the 683-byte environment frame;
 * the model must therefore charge fewer than a full frame to the link.  A
 * hard-coded 400 ms model incorrectly drains the entire frame and would let
 * this regression through. */
static void test_blocked_ms_is_applied_to_the_drain_window(void)
{
  NodeATelemetrySnapshot snapshot;
  UartTxQueue queue;
  RunResult result;

  build_snapshot(&snapshot);
  link_length = 0U;
  link_calls = 0UL;
  UartTx_Init(&queue);
  run_cycles(&queue, &snapshot, 1U, 1300U, &result);

  CHECK(result.refused == 0U);
  CHECK(link_calls < TEST_WIDEST_FRAME_BYTES);
}

/* The ACK reserve has to be genuinely reserved on both output queues: normal
 * telemetry/diagnostics stop at the ordinary limit, while an ACK can use the
 * reserve.  A refused telemetry offer must leave the shared rotation cursor
 * unchanged and observable through the real helper. */
static void test_dual_queue_ack_and_diagnostics_compete(void)
{
  const char ack[] =
      "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"menu-CTRL-02-7-42\","
      "\"status\":\"accepted\",\"reason\":\"fan_pwm_set\",\"appliedValue\":60}"
      "\r\n";
  NodeATelemetrySnapshot snapshot;
  char diagnostics[UART_TX_FRAME_LIMIT];
  UartTxQueue esp_queue;
  UartTxQueue debug_queue;
  DualQueueOffer queues;
  uint32_t sequence = 0U;
  const uint16_t reserve = TEST_ACK_RESERVE_BYTES;

  build_snapshot(&snapshot);
  UartTx_InitWithReserve(&esp_queue, reserve);
  UartTx_InitWithReserve(&debug_queue, reserve);
  queues.esp = &esp_queue;
  queues.debug = &debug_queue;
  (void)memset(diagnostics, 'd', sizeof(diagnostics));

  /* The first frame goes through the exact dual-queue production callback. */
  CHECK(NodeATelemetry_QueueNext(&sequence, &snapshot,
                                 enqueue_to_dual_queue, &queues) == 1U);
  CHECK(sequence == 1U);
  CHECK((uint32_t)esp_queue.used + reserve <= UART_TX_CAPACITY);
  CHECK((uint32_t)debug_queue.used + reserve <= UART_TX_CAPACITY);

  /* Ordinary diagnostics may fill only the non-reserved portion. */
  while ((uint32_t)esp_queue.used + UART_TX_FRAME_LIMIT <=
         (uint32_t)(UART_TX_CAPACITY - reserve))
    CHECK(UartTx_Enqueue(&esp_queue, diagnostics, UART_TX_FRAME_LIMIT) == 1U);
  while ((uint32_t)debug_queue.used + UART_TX_FRAME_LIMIT <=
         (uint32_t)(UART_TX_CAPACITY - reserve))
    CHECK(UartTx_Enqueue(&debug_queue, diagnostics, UART_TX_FRAME_LIMIT) == 1U);
  CHECK(UartTx_Enqueue(&esp_queue, diagnostics,
                       (uint16_t)(UART_TX_CAPACITY - reserve - esp_queue.used)) == 1U);
  CHECK(UartTx_Enqueue(&debug_queue, diagnostics,
                       (uint16_t)(UART_TX_CAPACITY - reserve - debug_queue.used)) == 1U);
  CHECK((uint32_t)esp_queue.used + reserve <= UART_TX_CAPACITY);
  CHECK((uint32_t)debug_queue.used + reserve <= UART_TX_CAPACITY);

  /* A pending frame is refused by the ESP ordinary limit, so the sequence
   * remains parked. */
  CHECK(NodeATelemetry_QueueNext(&sequence, &snapshot,
                                 enqueue_to_dual_queue, &queues) == 0U);
  CHECK(sequence == 1U);

  /* The same ACK fits in both reserved spaces and does not block. */
  CHECK(UartTx_EnqueuePriority(&esp_queue, ack,
                               (uint16_t)(sizeof(ack) - 1U)) == 1U);
  CHECK(UartTx_EnqueuePriority(&debug_queue, ack,
                               (uint16_t)(sizeof(ack) - 1U)) == 1U);
  CHECK(esp_queue.used <= UART_TX_CAPACITY);
  CHECK(debug_queue.used <= UART_TX_CAPACITY);
}

/* A frame the queue refuses must not move the rotation on.  This is the
 * contract that replaces the old burst behaviour, where a full queue made the
 * frames behind the refused one wait for the whole next cycle.
 *
 * Driven through the queue the same way the board does it: format, try to
 * enqueue, and commit the sequence only on success.  The rotation is left
 * parked on the frame that could not be queued. */
static void test_a_refused_frame_does_not_advance_the_rotation(void)
{
  NodeATelemetrySnapshot snapshot;
  UartTxQueue queue;
  QueueOffer offer;
  char refused_frame[NODE_A_TELEMETRY_FRAME_SIZE];
  uint32_t sequence = 0U;
  uint32_t committed;
  uint16_t refused_length;

  build_snapshot(&snapshot);
  UartTx_Init(&queue);
  offer.queue = &queue;
  offer.last_length = 0U;

  /* Fill the ring with whole rotations, committing the sequence for each frame
   * that really went in - exactly the board's loop - until the frame the
   * rotation would offer next no longer fits.  The sequence stays uncommitted
   * for that frame. */
  for (;;) {
    const uint32_t before = sequence;
    if (NodeATelemetry_QueueNext(&sequence, &snapshot,
                                 enqueue_to_uart_queue, &offer) == 0U) {
      committed = before; /* the emitted sequence the caller still owes */
      refused_length = offer.last_length;
      (void)memcpy(refused_frame, offer.last_frame, refused_length);
      break;
    }
    CHECK(sequence == before + 1U);
  }
  CHECK(refused_length != 0U);
  CHECK((uint32_t)queue.used + (uint32_t)refused_length > UART_TX_CAPACITY);
  /* The frame really is refused, and refusing it did not move the rotation. */
  CHECK(sequence == committed);
  CHECK(queue.dropped_frames == 1U);
  CHECK(queue.dropped_bytes == refused_length);

  /* Drain the ring: the same rotation position is what goes out next, because
   * the refused frame never committed its sequence. */
  UartTx_Init(&queue);
  offer.queue = &queue;
  CHECK(NodeATelemetry_QueueNext(&sequence, &snapshot,
                                 enqueue_to_uart_queue, &offer) == 1U);
  CHECK(sequence == committed + 1U);
  CHECK(offer.last_length == refused_length);
  CHECK(memcmp(offer.last_frame, refused_frame, refused_length) == 0);
}

/* The node-test burst is one complete rotation request, not six independent
 * requests.  If the queue refuses a later slot, the request remains pending;
 * the next attempt starts at that exact slot and only a complete rotation
 * reports success. */
static void test_full_rotation_is_retryable_as_one_request(void)
{
  NodeATelemetrySnapshot snapshot;
  UartTxQueue queue;
  char filler[UART_TX_FRAME_LIMIT];
  uint32_t sequence = 0U;

  build_snapshot(&snapshot);
  (void)memset(filler, 'x', sizeof(filler));
  UartTx_Init(&queue);
  CHECK(UartTx_Enqueue(&queue, filler, 300U) == 1U);

  CHECK(NodeATelemetry_QueueFullRotation(&sequence, &snapshot,
                                         enqueue_to_queue, &queue) == 0U);
  CHECK(sequence == 5U);
  CHECK(queue.dropped_frames == 1U);

  /* A new forced interval retries the parked slot. */
  UartTx_Init(&queue);
  CHECK(NodeATelemetry_QueueFullRotation(&sequence, &snapshot,
                                         enqueue_to_queue, &queue) == 1U);
  CHECK(sequence == 5U + NODE_A_TELEMETRY_FRAME_COUNT);
}

int main(void)
{
  test_one_frame_per_interval_fits_the_budget();
  test_sustained_throughput_never_refuses_a_frame();
  test_a_tighter_interval_still_delivers_exactly();
  test_the_drain_window_bounds_the_schedule();
  test_blocked_ms_is_applied_to_the_drain_window();
  test_dual_queue_ack_and_diagnostics_compete();
  test_a_refused_frame_does_not_advance_the_rotation();
  test_full_rotation_is_retryable_as_one_request();

  if (failures != 0) {
    (void)fprintf(stderr, "%d check(s) failed\n", failures);
    return 1;
  }
  (void)printf("node_a_telemetry_throughput_host_test: ok\n");
  return 0;
}
