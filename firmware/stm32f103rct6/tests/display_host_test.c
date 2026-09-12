/* Real rasterizer with a transport double: capture byte runs and hold DMA
 * ownership until Wait(), so premature reuse of either line buffer fails. */
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include "st7735.h"

static uint8_t output[32768], saved[256];
static const uint8_t *pending;
static uint16_t pending_size;
static unsigned used, chunks, frames, fail_at;
static uint8_t commands[64];
static unsigned command_bytes;

void HAL_Delay(uint32_t delay) { (void)delay; }
void St7735Bus_Init(void) { }
uint32_t St7735Bus_Cycles(void) { return 0; }
void St7735Bus_RecordFrame(uint32_t start) { (void)start; frames++; }
uint8_t St7735Bus_Wait(void) {
    if (pending) {
        assert(memcmp(saved, pending, pending_size) == 0);
        if (fail_at && chunks == fail_at) { pending = NULL; return 0; }
        assert(used + pending_size <= sizeof(output));
        memcpy(output + used, pending, pending_size);
        used += pending_size;
        pending = NULL;
    }
    return 1;
}
uint8_t St7735Bus_BeginData(void) { return St7735Bus_Wait(); }
uint8_t St7735Bus_WriteByte(uint8_t byte, uint8_t data) {
    (void)data;
    assert(St7735Bus_Wait());
    assert(command_bytes < sizeof(commands));
    commands[command_bytes++] = byte;
    return 1;
}
uint8_t St7735Bus_WriteAsync(const uint8_t *bytes, uint16_t length) {
    assert(!pending && length && length <= 256);
    pending = bytes; pending_size = length;
    memcpy(saved, bytes, length); chunks++;
    return 1;
}
static void reset(void) {
    assert(!pending); used = chunks = frames = command_bytes = fail_at = 0;
    ST7735_BeginFrame();
}
int main(void) {
    assert(mmap((void *)0x40010000, 65536, PROT_READ|PROT_WRITE,
                MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED, -1, 0) != MAP_FAILED);
    ST7735_FillRect(-2, -1, 4, 3, 0x1234);
    assert(used == 8 && output[0] == 0x12 && output[1] == 0x34);
    assert(commands[2] == 2 && commands[4] == 3);
    assert(commands[7] == 3 && commands[9] == 4);
    reset();
    ST7735_FillRect(INT_MAX, 0, INT_MAX, 1, 0);
    ST7735_FillRect(INT_MIN, 0, INT_MAX, 1, 0);
    ST7735_FillRect(0, 0, -1, 1, 0);
    ST7735_FillRect(0, 0, 1, 0, 0);
    assert(!used && !command_bytes);
    ST7735_FillRect(127, 127, INT_MAX, INT_MAX, 0xABCD);
    assert(used == 2 && output[0] == 0xAB && output[1] == 0xCD);
    reset();
    ST7735_Clear(0xF81F);
    assert(used == 32768 && chunks == 128 && frames == 1);
    for (unsigned i = 0; i < used; i += 2) assert(output[i] == 0xF8 && output[i+1] == 0x1F);
    reset(); fail_at = 2;
    ST7735_Clear(0);
    assert(chunks == 2 && frames == 0);
    assert(ST7735_FrameFailed());
    ST7735_FillRect(0, 0, 1, 1, 0xFFFF);
    assert(chunks == 2 && used == 256);
    reset(); ST7735_FillRect(0, 0, 1, 1, 0xFFFF);
    assert(!ST7735_FrameFailed());
    assert(used == 2 && frames == 1);
    reset();
    const uint16_t tile[] = {0x0001, 0x0002, 0x0003, 0x0004,
                             0x1234, 0x5678, 0x9ABC, 0xDEF0,
                             0x1122, 0x3344, 0x5566, 0x7788};
    ST7735_BlitRgb565(-2, -1, 4, 3, tile);
    const uint8_t expected[] = {0x9A, 0xBC, 0xDE, 0xF0, 0x55, 0x66, 0x77, 0x88};
    assert(used == sizeof(expected) && memcmp(output, expected, sizeof(expected)) == 0);
    reset();
    ST7735_BlitRgb565(127, 127, 4, 3, tile);
    assert(used == 2 && output[0] == 0 && output[1] == 1);
    reset();
    ST7735_BlitRgb565(0, 0, 1, 1, NULL);
    ST7735_WritePixels(NULL, 1);
    ST7735_WritePixels(tile, 0);
    ST7735_WritePixels(tile, UINT32_MAX);
    assert(!used && !command_bytes);
    ST7735_WritePixels(tile + 4, 4);
    const uint8_t raw_expected[] = {0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0};
    assert(used == sizeof(raw_expected) && memcmp(output, raw_expected, sizeof(raw_expected)) == 0);
    reset();
    uint8_t glyph[32] = {0};
    glyph[31] = 1;
    ST7735_DrawGlyph16(-15, -15, glyph, 0xABCD, 0);
    assert(used == 2 && output[0] == 0xAB && output[1] == 0xCD);
    reset();
    ST7735_DrawChar(127, 127, ' ', 0, 0x0123);
    assert(used == 2 && output[0] == 1 && output[1] == 0x23);
    puts("Display raster test: PASS");
    return 0;
}
