/* Host contract for the shared, bounded UART transmit queue.
 *
 * The queue exists because the boards used to serialise every diagnostic line
 * with a blocking HAL_UART_Transmit(..., 1000U) from the foreground loop.  The
 * properties that matter are therefore about time, not only about bytes:
 *
 *   1. a frame is queued whole or dropped whole - never half a line, which
 *      would leave the peer unable to split frames;
 *   2. a drain call moves at most its byte budget, so one loop iteration has a
 *      bounded transmit cost no matter how long the link takes;
 *   3. bytes leave in order, so the peer still sees well-formed lines;
 *   4. a link that stops accepting bytes is skipped for a backoff window
 *      instead of charging that budget to every subsequent iteration.
 *
 * HAL_UART_Transmit is modelled here rather than linked: it records the bytes
 * actually handed to the link and can be told to fail, which is what a stalled
 * or unplugged link does.
 */
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

/* --- HAL model ----------------------------------------------------------- */

static char link_bytes[8192];
static size_t link_length;
static uint8_t link_failing;
static unsigned long link_calls;
static uint32_t link_timeout;

HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *uart, uint8_t *data,
                                    uint16_t size, uint32_t timeout)
{
  (void)uart;
  link_timeout = timeout;
  ++link_calls;
  if (link_failing) return HAL_TIMEOUT;
  if (size != 1U) return HAL_ERROR;
  if (link_length + size > sizeof(link_bytes)) return HAL_ERROR;
  link_bytes[link_length++] = (char)data[0];
  return HAL_OK;
}

static void link_reset(void)
{
  (void)memset(link_bytes, 0, sizeof(link_bytes));
  link_length = 0U;
  link_failing = 0U;
  link_calls = 0UL;
  link_timeout = 0U;
}

static UART_HandleTypeDef kUart = {0};

static void test_a_single_byte_uses_a_nonzero_timeout(void)
{
  uint8_t byte = (uint8_t)'{';
  link_reset();

  CHECK(UartTx_WriteByte(&kUart, &byte) == HAL_OK);
  CHECK(link_timeout == 2U);
  CHECK(link_length == 1U && link_bytes[0] == '{');
}

/* A frame of `length` printable bytes, with a CRLF terminator. */
static void build_frame(char *frame, size_t capacity, size_t length, char fill)
{
  size_t index;
  if (length + 2U >= capacity) length = capacity - 3U;
  for (index = 0U; index < length; ++index) frame[index] = fill;
  frame[length] = '\r';
  frame[length + 1U] = '\n';
  frame[length + 2U] = '\0';
}

/* --- Tests --------------------------------------------------------------- */

/* A frame longer than the peer's line bound is refused whole: queueing it in
 * part would hand the peer a line it cannot terminate. */
static void test_oversized_and_non_fitting_frames_are_refused_whole(void)
{
  UartTxQueue queue;
  char frame[UART_TX_FRAME_LIMIT + 8U];
  size_t index;

  UartTx_Init(&queue);
  (void)memset(frame, 'x', sizeof(frame));
  CHECK(UartTx_Enqueue(&queue, frame, UART_TX_FRAME_LIMIT + 1U) == 0U);
  CHECK(UartTx_Pending(&queue) == 0U);

  /* Fill the queue with whole frames, then confirm the first frame that does
   * not fit is refused rather than split. */
  (void)memset(frame, 'y', sizeof(frame));
  for (index = 0U; index < UART_TX_CAPACITY / 512U; ++index) {
    CHECK(UartTx_Enqueue(&queue, frame, 512U) == 1U);
  }
  CHECK(UartTx_Pending(&queue) == 1U);
  CHECK(UartTx_Enqueue(&queue, frame, 512U) == 0U);
  CHECK(queue.dropped_frames == 2U);
}

/* One drain call moves at most its budget.  This is the property that keeps a
 * single loop iteration bounded whatever the link is doing. */
static void test_a_drain_call_never_exceeds_its_budget(void)
{
  UartTxQueue queue;
  char frame[256];
  uint16_t moved;

  link_reset();
  UartTx_Init(&queue);
  build_frame(frame, sizeof(frame), 200U, 'a');
  CHECK(UartTx_Enqueue(&queue, frame, 202U) == 1U);

  moved = UartTx_Drain(&queue, &kUart, 48U, 0U);
  CHECK(moved == 48U);
  CHECK(link_timeout == 2U);
  CHECK(link_length == 48U);
  CHECK(queue.used == 154U);

  /* And it never moves more than the frame that was queued. */
  moved = UartTx_Drain(&queue, &kUart, 400U, 0U);
  CHECK(moved == 154U);
  CHECK(link_length == 202U);
  CHECK(UartTx_Pending(&queue) == 0U);
}

/* Bytes leave in the order they were queued, so the peer reassembles the same
 * lines.  Two frames drained in one budget must not interleave. */
static void test_frames_leave_in_order_and_intact(void)
{
  UartTxQueue queue;
  char first[64];
  char second[64];

  link_reset();
  UartTx_Init(&queue);
  build_frame(first, sizeof(first), 20U, 'a');
  build_frame(second, sizeof(second), 20U, 'b');
  CHECK(UartTx_Enqueue(&queue, first, 22U) == 1U);
  CHECK(UartTx_Enqueue(&queue, second, 22U) == 1U);

  CHECK(UartTx_Drain(&queue, &kUart, 44U, 0U) == 44U);
  CHECK(link_length == 44U);
  CHECK(memcmp(link_bytes, first, 22U) == 0);
  CHECK(memcmp(link_bytes + 22U, second, 22U) == 0);
  CHECK(link_bytes[21] == '\n');
  CHECK(link_bytes[43] == '\n');
}

/* A queue drains oldest-first even after the ring wraps, so a long-running
 * board does not silently reorder its telemetry. */
static void test_ring_buffer_wrap_preserves_order(void)
{
  UartTxQueue queue;
  char frame[128];
  /* Eight frames of 42 bytes each, one per fill character. */
  char expected[8U * 42U];
  size_t expected_length = 0U;
  uint8_t step;

  link_reset();
  UartTx_Init(&queue);
  for (step = 0U; step < 8U; ++step) {
    const char fill = (char)('a' + step);
    build_frame(frame, sizeof(frame), 40U, fill);
    CHECK(UartTx_Enqueue(&queue, frame, 42U) == 1U);
    (void)memcpy(expected + expected_length, frame, 42U);
    expected_length += 42U;
    /* Drain in small pieces as the board's loop would, interleaved with the
     * enqueues, so head and tail wrap repeatedly. */
    CHECK(UartTx_Drain(&queue, &kUart, 13U, 0U) == 13U);
  }
  while (UartTx_Pending(&queue) != 0U) {
    (void)UartTx_Drain(&queue, &kUart, 64U, 0U);
  }
  CHECK(link_length == expected_length);
  CHECK(memcmp(link_bytes, expected, expected_length) == 0);
}

/* A link that stops accepting bytes must not keep charging the loop.  After a
 * few fully-blocked attempts the queue is skipped outright for a backoff
 * window, and it recovers when the link starts draining again. */
static void test_stalled_link_is_skipped_then_recovered(void)
{
  UartTxQueue queue;
  char frame[256];
  unsigned long calls_after_stall;
  uint32_t now_ms = 1000U;

  link_reset();
  UartTx_Init(&queue);
  build_frame(frame, sizeof(frame), 100U, 's');
  CHECK(UartTx_Enqueue(&queue, frame, 102U) == 1U);

  /* The link accepts nothing from here on. */
  link_failing = 1U;
  for (; now_ms < 1000U + UART_TX_STALL_ATTEMPTS; ++now_ms) {
    CHECK(UartTx_Drain(&queue, &kUart, 48U, now_ms) == 0U);
  }
  CHECK(queue.stall_until_ms != 0U);

  /* Inside the backoff the queue is not even offered to the link. */
  calls_after_stall = link_calls;
  CHECK(UartTx_Drain(&queue, &kUart, 48U, now_ms) == 0U);
  CHECK(UartTx_Drain(&queue, &kUart, 48U, now_ms + 10U) == 0U);
  CHECK(link_calls == calls_after_stall);
  /* The bytes are still queued: a stall delays output, it never loses it. */
  CHECK(UartTx_Pending(&queue) == 1U);

  /* The link recovers; the backoff still has to expire first. */
  link_failing = 0U;
  CHECK(UartTx_Drain(&queue, &kUart, 48U, now_ms + 1U) == 0U);
  CHECK(link_length == 0U);
  CHECK(UartTx_Drain(&queue, &kUart, 48U, queue.stall_until_ms) == 48U);
  CHECK(link_length == 48U);
  CHECK(queue.stall_until_ms == 0U);
}

/* A configured reserve is enforced at runtime: ordinary telemetry and
 * diagnostics stop before the reserve, while an ACK may use those bytes. */
static void test_normal_frames_leave_the_ack_reserve_available(void)
{
  UartTxQueue queue;
  char frame[UART_TX_FRAME_LIMIT];
  const uint16_t reserve = 350U;
  const uint16_t ordinary_limit = (uint16_t)(UART_TX_CAPACITY - reserve);

  UartTx_InitWithReserve(&queue, reserve);
  (void)memset(frame, 'n', sizeof(frame));
  while ((uint32_t)queue.used + UART_TX_FRAME_LIMIT <= ordinary_limit)
    CHECK(UartTx_Enqueue(&queue, frame, UART_TX_FRAME_LIMIT) == 1U);

  CHECK(queue.used <= ordinary_limit);
  CHECK(UartTx_Enqueue(&queue, frame,
                       (uint16_t)(ordinary_limit - queue.used)) == 1U);
  CHECK(UartTx_Enqueue(&queue, frame,
                       (uint16_t)(ordinary_limit - queue.used + 1U)) == 0U);
  CHECK(queue.used <= ordinary_limit);

  CHECK(UartTx_EnqueuePriority(&queue, frame, reserve) == 1U);
  CHECK(queue.used == UART_TX_CAPACITY);
}

/* Priority output is still bounded and non-blocking when the entire ring is
 * occupied; the caller can observe that an ACK was refused. */
static void test_priority_refusal_is_counted(void)
{
  UartTxQueue queue;
  char frame[UART_TX_FRAME_LIMIT];

  UartTx_InitWithReserve(&queue, 350U);
  (void)memset(frame, 'p', sizeof(frame));
  CHECK(UartTx_EnqueuePriority(&queue, frame, UART_TX_FRAME_LIMIT) == 1U);
  CHECK(UartTx_EnqueuePriority(&queue, frame, UART_TX_FRAME_LIMIT) == 1U);
  CHECK(UartTx_EnqueuePriority(&queue, frame, UART_TX_FRAME_LIMIT) == 1U);
  CHECK(UartTx_EnqueuePriority(&queue, frame, UART_TX_FRAME_LIMIT) == 1U);
  CHECK(UartTx_EnqueuePriority(&queue, frame, 4U) == 1U);
  CHECK(UartTx_EnqueuePriority(&queue, frame, 1U) == 0U);
  CHECK(queue.priority_dropped_frames == 1U);
  CHECK(queue.priority_dropped_bytes == 1U);
}

int main(void)
{
  test_a_single_byte_uses_a_nonzero_timeout();
  test_oversized_and_non_fitting_frames_are_refused_whole();
  test_a_drain_call_never_exceeds_its_budget();
  test_frames_leave_in_order_and_intact();
  test_ring_buffer_wrap_preserves_order();
  test_stalled_link_is_skipped_then_recovered();
  test_normal_frames_leave_the_ack_reserve_available();
  test_priority_refusal_is_counted();

  if (failures != 0) {
    (void)fprintf(stderr, "%d check(s) failed\n", failures);
    return 1;
  }
  (void)printf("uart_tx_queue_host_test: ok\n");
  return 0;
}
