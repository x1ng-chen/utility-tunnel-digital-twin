#ifndef UART_TX_QUEUE_H
#define UART_TX_QUEUE_H

#include "stm32f1xx_hal.h"

#include <stdint.h>

/* Byte-oriented, non-blocking transmit queue shared by both controller images.
 *
 * The boards used to serialise every diagnostic line with a blocking
 * HAL_UART_Transmit(..., 1000U).  A full telemetry cycle or a burst of debug
 * echo is far longer than any single loop iteration should take, so those
 * calls stalled the foreground loop - and with it sampling, command handling
 * and joystick polling - for seconds at a time.
 *
 * The queue never blocks: it accepts a whole frame or refuses it, and the
 * caller drains it from the main loop one byte at a time inside a fixed
 * per-iteration byte budget.  The short non-zero HAL timeout is required on
 * STM32F1 because a zero timeout can report failure after writing the byte.
 *
 * A link that stops accepting bytes must not keep charging the drain budget
 * every iteration, so a queue whose head cannot move for a while is treated as
 * stalled and skipped entirely until the backoff expires.  Node B needs this:
 * a debug console with no reader attached would otherwise consume the whole
 * budget that the ESP link and the 60 FPS UI loop share. */
#define UART_TX_FRAME_LIMIT 767U
/* Holds the largest frame either image queues plus the reserve its ACK and
 * diagnostic lines draw on, so a frame is refused only when the link really
 * has not drained.  It is deliberately NOT sized to hold a whole Node A
 * telemetry cycle: a cycle does not fit the 9600 baud link inside one
 * telemetry interval, so Node A emits one frame per interval and rotates
 * (node_a.c derives that budget and asserts the reserve this constant has to
 * cover).  Sizing the ring to a whole cycle would only let ~1.5 intervals of
 * frames pile up before the whole cycle was refused. */
#define UART_TX_CAPACITY 3072U
/* Consecutive fully-blocked drain calls after which a queue is considered
 * stalled.  At the Node A loop rate this is a small fraction of a second. */
#define UART_TX_STALL_ATTEMPTS 4U
/* How long a stalled queue is skipped before the link is retried. */
#define UART_TX_STALL_BACKOFF_MS 1000U

typedef struct {
  uint8_t bytes[UART_TX_CAPACITY];
  uint16_t capacity;
  uint16_t reserved_bytes;
  uint16_t head;
  uint16_t tail;
  uint16_t used;
  uint8_t frames;
  uint8_t blocked_attempts;
  uint32_t stall_until_ms;
  uint32_t enqueued_frames;
  uint32_t dropped_frames;
  uint32_t dropped_bytes;
  uint32_t priority_dropped_frames;
  uint32_t priority_dropped_bytes;
  uint16_t peak_used;
  uint16_t peak_frames;
} UartTxQueue;

void UartTx_Init(UartTxQueue *queue);

/* Initializes a queue with `reserved_bytes` unavailable to ordinary output.
 * The reserve is a runtime admission limit, not merely a capacity assertion;
 * priority output may consume it without waiting. */
void UartTx_InitWithReserve(UartTxQueue *queue, uint16_t reserved_bytes);

/* Copies `length` bytes when the whole frame fits, otherwise drops the frame.
 * Returns 1 when queued.  A frame longer than UART_TX_FRAME_LIMIT is always
 * refused: the peer splits lines at that bound. */
uint8_t UartTx_Enqueue(UartTxQueue *queue, const char *line, uint16_t length);

/* Enqueues an urgent frame (for example a command ACK).  It remains bounded
 * by the physical queue capacity but may use the configured reserve. */
uint8_t UartTx_EnqueuePriority(UartTxQueue *queue, const char *line,
                               uint16_t length);

/* Insert an urgent line after the first queued line terminator.  This keeps
 * any partially sent frame intact while avoiding a wait behind later frames. */
uint8_t UartTx_EnqueuePriorityNext(UartTxQueue *queue, const char *line,
                                   uint16_t length);

/* Sends exactly one byte with the STM32F1-safe short timeout shared by every
 * foreground UART producer. */
HAL_StatusTypeDef UartTx_WriteByte(UART_HandleTypeDef *uart, uint8_t *byte);

/* Pushes at most `budget` bytes to `uart` with a two-tick per-byte timeout.
 * `now_ms` stamps the stall backoff.  Returns the bytes written; a stalled
 * queue writes none. */
uint16_t UartTx_Drain(UartTxQueue *queue, UART_HandleTypeDef *uart,
                      uint16_t budget, uint32_t now_ms);

uint8_t UartTx_Pending(const UartTxQueue *queue);

#endif
