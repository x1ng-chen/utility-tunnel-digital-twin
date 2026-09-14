#ifndef TEST_NATIVE_STM32F1XX_HAL_H
#define TEST_NATIVE_STM32F1XX_HAL_H

/* Minimal HAL surface for host tests of the pieces that talk to a UART: the
 * transmit queue (uart_tx_queue.c) and the Node A telemetry formatter's
 * consumers.  Only the symbols those translation units actually name are
 * declared here; the real board build uses the CubeMX HAL headers.
 *
 * HAL_UART_Transmit has no definition: each test binary provides the model it
 * needs, so the queue's pacing and stall behaviour can be driven
 * deterministically. */

#include <stdint.h>

typedef enum
{
  HAL_OK       = 0x00U,
  HAL_ERROR    = 0x01U,
  HAL_BUSY     = 0x02U,
  HAL_TIMEOUT  = 0x03U
} HAL_StatusTypeDef;

typedef struct
{
  uint32_t instance;
} UART_TypeDef;

typedef struct
{
  UART_TypeDef *Instance;
  uint32_t BaudRate;
} UART_HandleTypeDef;

/* Declared, not defined: each host test links the model it needs. */
HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *uart, uint8_t *data,
                                    uint16_t size, uint32_t timeout);

#endif
