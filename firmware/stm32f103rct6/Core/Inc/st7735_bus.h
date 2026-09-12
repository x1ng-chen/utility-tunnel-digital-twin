#ifndef ST7735_BUS_H
#define ST7735_BUS_H
#include <stdint.h>

#define ST7735_BUS_BUFFER_BYTES 256U
#define ST7735_BUS_TIMEOUT_MS 2U

typedef struct {
    uint32_t dma_frames; /* Completed pixel runs, not individual DMA chunks. */
    uint32_t dma_timeouts;
    uint32_t dma_errors;
    uint32_t worst_frame_us;
    uint32_t spi_hz;
} St7735BusStats;

/* Foreground-only, single producer. Async retains bytes until Wait succeeds.
 * A failed wait aborts the whole pixel run; start a fresh address window next.
 * IRQ only publishes completion/error; it never waits for SPI or SysTick. */
void St7735Bus_Init(void);
uint8_t St7735Bus_BeginData(void);
uint8_t St7735Bus_WriteAsync(const uint8_t *bytes, uint16_t length);
uint8_t St7735Bus_IsBusy(void);
void St7735Bus_Recover(void);
uint8_t St7735Bus_Wait(void);
uint8_t St7735Bus_WriteByte(uint8_t byte, uint8_t data);
void St7735Bus_DmaIrqHandler(void);
uint32_t St7735Bus_Cycles(void);
void St7735Bus_RecordFrame(uint32_t started_cycles);
void St7735Bus_GetStats(St7735BusStats *stats);
/* Foreground diagnostic hook; call only between completed drawing primitives. */
void St7735Bus_ResetStats(void);
#endif
