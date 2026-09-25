#include "uart_tx_queue.h"

#include <string.h>

void UartTx_Init(UartTxQueue *queue)
{
  UartTx_InitWithReserve(queue, 0U);
}

void UartTx_InitWithReserve(UartTxQueue *queue, uint16_t reserved_bytes)
{
  if (queue == 0) return;
  (void)memset(queue, 0, sizeof(*queue));
  queue->capacity = UART_TX_CAPACITY;
  queue->reserved_bytes = (reserved_bytes < UART_TX_CAPACITY)
                              ? reserved_bytes : UART_TX_CAPACITY;
}

static uint8_t enqueue_frame(UartTxQueue *queue, const char *line,
                             uint16_t length, uint8_t priority)
{
  uint16_t index;
  uint16_t limit;
  if ((queue == 0) || (line == 0) || (length == 0U)) return 0U;
  limit = priority ? queue->capacity
                   : (uint16_t)(queue->capacity - queue->reserved_bytes);
  /* A partial frame would leave the peer unable to split lines, so an
   * oversized or non-fitting frame is refused whole and never queued. */
  if ((length > UART_TX_FRAME_LIMIT) ||
      ((uint32_t)queue->used + (uint32_t)length > (uint32_t)limit)) {
    ++queue->dropped_frames;
    queue->dropped_bytes = queue->dropped_bytes + length;
    if (priority != 0U) {
      ++queue->priority_dropped_frames;
      queue->priority_dropped_bytes = queue->priority_dropped_bytes + length;
    }
    return 0U;
  }
  for (index = 0U; index < length; ++index) {
    queue->bytes[queue->tail] = (uint8_t)line[index];
    queue->tail = (uint16_t)((queue->tail + 1U) % queue->capacity);
  }
  queue->used = (uint16_t)(queue->used + length);
  ++queue->frames;
  ++queue->enqueued_frames;
  if (queue->used > queue->peak_used) queue->peak_used = queue->used;
  if (queue->frames > queue->peak_frames) queue->peak_frames = queue->frames;
  return 1U;
}

uint8_t UartTx_Enqueue(UartTxQueue *queue, const char *line, uint16_t length)
{
  return enqueue_frame(queue, line, length, 0U);
}

uint8_t UartTx_EnqueuePriority(UartTxQueue *queue, const char *line,
                               uint16_t length)
{
  return enqueue_frame(queue, line, length, 1U);
}

uint8_t UartTx_EnqueuePriorityNext(UartTxQueue *queue, const char *line,
                                   uint16_t length)
{
  uint16_t insert_at = 0U;
  uint16_t index;
  if ((queue == 0) || (line == 0) || (length == 0U)) return 0U;
  if ((length > UART_TX_FRAME_LIMIT) ||
      ((uint32_t)queue->used + (uint32_t)length > queue->capacity)) {
    ++queue->dropped_frames;
    queue->dropped_bytes += length;
    ++queue->priority_dropped_frames;
    queue->priority_dropped_bytes += length;
    return 0U;
  }
  /* The head may already be halfway through a telemetry frame.  Always wait
   * for its newline; inserting earlier would splice two JSON documents. */
  for (index = 0U; index < queue->used; ++index) {
    if (queue->bytes[(queue->head + index) % queue->capacity] == (uint8_t)'\n') {
      insert_at = (uint16_t)(index + 1U);
      break;
    }
  }
  if (index == queue->used) insert_at = queue->used;
  for (index = queue->used; index > insert_at; --index) {
    queue->bytes[(queue->head + index + length - 1U) % queue->capacity] =
        queue->bytes[(queue->head + index - 1U) % queue->capacity];
  }
  for (index = 0U; index < length; ++index) {
    queue->bytes[(queue->head + insert_at + index) % queue->capacity] =
        (uint8_t)line[index];
  }
  queue->tail = (uint16_t)((queue->tail + length) % queue->capacity);
  queue->used = (uint16_t)(queue->used + length);
  ++queue->frames;
  ++queue->enqueued_frames;
  if (queue->used > queue->peak_used) queue->peak_used = queue->used;
  if (queue->frames > queue->peak_frames) queue->peak_frames = queue->frames;
  return 1U;
}

HAL_StatusTypeDef UartTx_WriteByte(UART_HandleTypeDef *uart, uint8_t *byte)
{
  if ((uart == 0) || (byte == 0)) return HAL_ERROR;
  /* STM32F1 HAL writes DR before waiting for TC.  A zero timeout can therefore
   * return HAL_TIMEOUT for a byte that was already transmitted, which makes a
   * caller retry the same byte forever. */
  return HAL_UART_Transmit(uart, byte, 1U, 2U);
}

uint16_t UartTx_Drain(UartTxQueue *queue, UART_HandleTypeDef *uart,
                      uint16_t budget, uint32_t now_ms)
{
  uint16_t written = 0U;
  if ((queue == 0) || (uart == 0)) return 0U;
  /* A stalled link is skipped without spending the budget: the HAL would fail
   * every byte anyway, and the loop has sampling and input to get back to. */
  if ((queue->stall_until_ms != 0U) &&
      ((int32_t)(queue->stall_until_ms - now_ms) > 0)) {
    return 0U;
  }
  while ((queue->used != 0U) && (written < budget)) {
    const uint8_t byte = queue->bytes[queue->head];
    /* Do not use a zero timeout here.  STM32F1 HAL writes the byte to DR and
     * then waits for TC; with timeout == 0 it reports HAL_TIMEOUT after the
     * byte has already left DR.  Treating that result as "not sent" kept the
     * queue head fixed and retransmitted its first byte forever.  Two ticks
     * comfortably cover one 9600-8N1 character while still bounding a
     * genuinely stalled link. */
    if (UartTx_WriteByte(uart, (uint8_t *)&byte) != HAL_OK) break;
    queue->head = (uint16_t)((queue->head + 1U) % queue->capacity);
    --queue->used;
    ++written;
  }
  if (written != 0U) {
    queue->blocked_attempts = 0U;
    queue->stall_until_ms = 0U;
  } else if (queue->used != 0U) {
    /* Bytes are waiting and none of them moved: count the attempt and back the
     * link off once it is clearly not draining. */
    if (queue->blocked_attempts < UART_TX_STALL_ATTEMPTS) ++queue->blocked_attempts;
    if ((queue->blocked_attempts >= UART_TX_STALL_ATTEMPTS) &&
        (queue->stall_until_ms == 0U)) {
      queue->stall_until_ms = now_ms + UART_TX_STALL_BACKOFF_MS;
    }
  }
  return written;
}

uint8_t UartTx_Pending(const UartTxQueue *queue)
{
  return ((queue != 0) && (queue->used != 0U)) ? 1U : 0U;
}
