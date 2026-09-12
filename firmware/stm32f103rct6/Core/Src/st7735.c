/**
 * @file    st7735.c
 * @brief   ST7735 IPS LCD 驱动实现（软件 SPI）
 *
 * 软件 SPI：GPIO 翻转模拟 SCK/MOSI 时序，写命令/数据。
 * 颜色 RGB565（16 位，先高字节后低字节）。
 */
#include "st7735.h"
#include "st7735_font.h"
#include <stddef.h>
#ifdef NODE_B_FIRMWARE
#include "st7735_bus.h"
static uint8_t line_buffers[2][ST7735_BUS_BUFFER_BYTES];
#endif
static uint8_t frame_failed;

void ST7735_BeginFrame(void)
{
    frame_failed = 0U;
}

uint8_t ST7735_FrameFailed(void)
{
    return frame_failed;
}

/* Direct BSRR writes replace HAL_GPIO_WritePin in the pixel hot path. */
static inline __attribute__((always_inline)) void gpio_set(uint16_t pin)
{
    LCD_PORT->BSRR = pin;
}

static inline __attribute__((always_inline)) void gpio_reset(uint16_t pin)
{
    LCD_PORT->BSRR = (uint32_t)pin << 16U;
}

/* ============ GPIO 初始化 ============ */
static void ST7735_GPIO_Init(void)
{
#ifdef NODE_B_FIRMWARE
    St7735Bus_Init();
#else
    __HAL_RCC_GPIOB_CLK_ENABLE();
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin   = LCD_SCK_PIN | LCD_MOSI_PIN | LCD_DC_PIN | LCD_RES_PIN
               | LCD_CS_PIN | LCD_BLK_PIN;
    gpio.Mode  = GPIO_MODE_OUTPUT_PP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(LCD_PORT, &gpio);

    /* CS 拉低常使能，BLK 拉高背光亮 */
    HAL_GPIO_WritePin(LCD_PORT, LCD_CS_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(LCD_PORT, LCD_BLK_PIN, GPIO_PIN_SET);
#endif
}

/* ============ 软件 SPI ============ */
#ifndef NODE_B_FIRMWARE
static void spi_write_byte(uint8_t b)
{
    for (int i = 0; i < 8; i++) {
        gpio_reset(LCD_SCK_PIN);
        if (b & 0x80U) gpio_set(LCD_MOSI_PIN);
        else gpio_reset(LCD_MOSI_PIN);
        b <<= 1;
        gpio_set(LCD_SCK_PIN);
    }
}
#endif

/* ============ 写命令 / 写数据 ============ */
static void ST7735_Cmd(uint8_t cmd)
{
#ifdef NODE_B_FIRMWARE
    if (!frame_failed && !St7735Bus_WriteByte(cmd, 0U)) frame_failed = 1U;
#else
    gpio_reset(LCD_DC_PIN);   /* DC=0 命令 */
    spi_write_byte(cmd);
#endif
}

static void ST7735_Data(uint8_t data)
{
#ifdef NODE_B_FIRMWARE
    if (!frame_failed && !St7735Bus_WriteByte(data, 1U)) frame_failed = 1U;
#else
    gpio_set(LCD_DC_PIN);     /* DC=1 数据 */
    spi_write_byte(data);
#endif
}

/* ============ 复位 ============ */
static void ST7735_Reset(void)
{
    gpio_reset(LCD_RES_PIN);
    HAL_Delay(20);
    gpio_set(LCD_RES_PIN);
    HAL_Delay(120);
}

/* ============ 设置地址窗口 ============ */
static void ST7735_SetWindow(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1)
{
    uint16_t xs = x0 + LCD_X_OFFSET, xe = x1 + LCD_X_OFFSET;
    uint16_t ys = y0 + LCD_Y_OFFSET, ye = y1 + LCD_Y_OFFSET;

    ST7735_Cmd(0x2A);                       /* CASET 列地址 */
    ST7735_Data(xs >> 8); ST7735_Data(xs & 0xFF);
    ST7735_Data(xe >> 8); ST7735_Data(xe & 0xFF);

    ST7735_Cmd(0x2B);                       /* RASET 行地址 */
    ST7735_Data(ys >> 8); ST7735_Data(ys & 0xFF);
    ST7735_Data(ye >> 8); ST7735_Data(ye & 0xFF);

    ST7735_Cmd(0x2C);                       /* RAMWR 写显存 */
}

typedef struct {
    int x, y, w, h;
    uint32_t source_x, source_y;
} ClipRect;

static uint8_t Clip(int x, int y, int w, int h, ClipRect *r)
{
    /* Widen before adding: negative origins and INT_MAX dimensions are legal. */
    int64_t right = (int64_t)x + w, bottom = (int64_t)y + h;
    if (w <= 0 || h <= 0 || x >= LCD_WIDTH || y >= LCD_HEIGHT || right <= 0 || bottom <= 0)
        return 0U;
    r->x = x < 0 ? 0 : x;
    r->y = y < 0 ? 0 : y;
    r->w = (int)(right > LCD_WIDTH ? LCD_WIDTH : right) - r->x;
    r->h = (int)(bottom > LCD_HEIGHT ? LCD_HEIGHT : bottom) - r->y;
    r->source_x = (uint32_t)((int64_t)r->x - x);
    r->source_y = (uint32_t)((int64_t)r->y - y);
    return 1U;
}

typedef struct {
    const uint16_t *pixels;
    const uint8_t *glyph;
    uint32_t stride, source_x, source_y, width;
    uint16_t color, bg;
    uint8_t glyph_bytes;
} PixelSource;

static uint16_t PixelAt(const PixelSource *source, uint32_t col, uint32_t row)
{
    const size_t x = source->source_x + col;
    const size_t y = source->source_y + row;
    if (source->pixels) return source->pixels[y * source->stride + x];
    if (source->glyph) return (source->glyph[y * source->glyph_bytes + x / 8U] &
                              (0x80U >> (x % 8U))) ? source->color : source->bg;
    return source->color;
}

static void StreamPixels(const PixelSource *source, uint32_t count)
{
    uint32_t col = 0U, row = 0U;
#ifdef NODE_B_FIRMWARE
    uint32_t offset = 0U;
    unsigned buffer = 0U;
    if (frame_failed) return;
    if (!St7735Bus_BeginData()) { frame_failed = 1U; return; }
    while (offset < count) {
        const uint32_t n = count - offset > 128U ? 128U : count - offset;
        /* Prepare the other buffer while DMA retains ownership of this one. */
        for (uint32_t i = 0; i < n; ++i) {
            const uint16_t pixel = PixelAt(source, col, row);
            if (++col == source->width) { col = 0U; ++row; }
            line_buffers[buffer][2U * i] = (uint8_t)(pixel >> 8U);
            line_buffers[buffer][2U * i + 1U] = (uint8_t)pixel;
        }
        if (!St7735Bus_Wait() || !St7735Bus_WriteAsync(line_buffers[buffer], (uint16_t)(n * 2U))) {
            frame_failed = 1U;
            return;
        }
        offset += n;
        buffer ^= 1U;
    }
    if (!St7735Bus_Wait()) frame_failed = 1U;
#else
    for (uint32_t i = 0; i < count; ++i) {
        const uint16_t pixel = PixelAt(source, col, row);
        if (++col == source->width) { col = 0U; ++row; }
        ST7735_Data((uint8_t)(pixel >> 8U));
        ST7735_Data((uint8_t)pixel);
    }
#endif
}

static void DrawSource(const ClipRect *rect, PixelSource *source)
{
    if (frame_failed) return;
#ifdef NODE_B_FIRMWARE
    const uint32_t started = St7735Bus_Cycles();
#endif
    source->source_x = rect->source_x;
    source->source_y = rect->source_y;
    source->width = (uint32_t)rect->w;
    ST7735_SetWindow((uint16_t)rect->x, (uint16_t)rect->y,
                    (uint16_t)(rect->x + rect->w - 1), (uint16_t)(rect->y + rect->h - 1));
    StreamPixels(source, (uint32_t)rect->w * (uint32_t)rect->h);
#ifdef NODE_B_FIRMWARE
    if (!frame_failed) St7735Bus_RecordFrame(started);
#endif
}

void ST7735_WritePixels(const uint16_t *pixels, uint32_t count)
{
    PixelSource source = {0};
    if (!pixels || !count || count > (uint32_t)LCD_WIDTH * LCD_HEIGHT) return;
    source.pixels = pixels;
    source.width = source.stride = count;
#ifdef NODE_B_FIRMWARE
    const uint32_t started = St7735Bus_Cycles();
#endif
    StreamPixels(&source, count);
#ifdef NODE_B_FIRMWARE
    if (!frame_failed) St7735Bus_RecordFrame(started);
#endif
}

void ST7735_FillRect(int x, int y, int w, int h, uint16_t color)
{
    ClipRect rect;
    PixelSource source = {0};
    if (!Clip(x, y, w, h, &rect)) return;
    source.color = color;
    DrawSource(&rect, &source);
}

void ST7735_BlitRgb565(int x, int y, int w, int h, const uint16_t *pixels)
{
    ClipRect rect;
    PixelSource source = {0};
    if (!pixels || !Clip(x, y, w, h, &rect)) return;
    if ((size_t)w > SIZE_MAX / sizeof(*pixels) / (size_t)h) return;
    source.pixels = pixels;
    source.stride = (uint32_t)w;
    DrawSource(&rect, &source);
}

/* ============ 初始化 ============ */
void ST7735_Init(void)
{
    ST7735_BeginFrame();
    ST7735_GPIO_Init();
    ST7735_Reset();

    /* 初始化命令序列（ST7735 128x160，竖屏） */
    ST7735_Cmd(0x01);                       /* SWRESET 软复位 */
    HAL_Delay(120);
    ST7735_Cmd(0x11);                       /* SLPOUT 退出睡眠 */
    HAL_Delay(120);

    ST7735_Cmd(0xB1);                       /* FRMCTR1 帧率 */
    ST7735_Data(0x01); ST7735_Data(0x2C); ST7735_Data(0x2D);
    ST7735_Cmd(0xB2);                       /* FRMCTR2 */
    ST7735_Data(0x01); ST7735_Data(0x2C); ST7735_Data(0x2D);
    ST7735_Cmd(0xB3);                       /* FRMCTR3 */
    ST7735_Data(0x01); ST7735_Data(0x2C); ST7735_Data(0x2D);
    ST7735_Data(0x01); ST7735_Data(0x2C); ST7735_Data(0x2D);
    ST7735_Cmd(0xB4);                       /* INVCTR 反相控制 */
    ST7735_Data(0x07);
    ST7735_Cmd(0xC0);                       /* PWCTR1 电源控制 */
    ST7735_Data(0xA2); ST7735_Data(0x02); ST7735_Data(0x84);
    ST7735_Cmd(0xC1);                       /* PWCTR2 */
    ST7735_Data(0xC5);
    ST7735_Cmd(0xC2);                       /* PWCTR3 */
    ST7735_Data(0x0A); ST7735_Data(0x00);
    ST7735_Cmd(0xC3);                       /* PWCTR4 */
    ST7735_Data(0x8A); ST7735_Data(0x2A);
    ST7735_Cmd(0xC4);                       /* PWCTR5 */
    ST7735_Data(0x8A); ST7735_Data(0xEE);
    ST7735_Cmd(0xC5);                       /* VMCTR1 VCOM */
    ST7735_Data(0x0E);
    ST7735_Cmd(0x20);                       /* INVOFF 不反相 */
    ST7735_Cmd(0x36);                       /* MADCTL 方向 */
    ST7735_Data(0xC8);                      /* 竖屏 */
    ST7735_Cmd(0x3A);                       /* COLMOD 颜色格式 */
    ST7735_Data(0x05);                      /* 16 位 RGB565 */
    ST7735_Cmd(0x13);                       /* NORON 正常显示 */
    ST7735_Cmd(0x29);                       /* DISPON 显示开 */
    HAL_Delay(100);

    ST7735_Clear(LCD_BLACK);
}

/* ============ 清屏 ============ */
void ST7735_Clear(uint16_t color)
{
    ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, color);
}

void ST7735_DrawGlyph16(int x, int y, const uint8_t glyph[32], uint16_t color, uint16_t bg)
{
    ClipRect rect;
    PixelSource source = {0};
    if (!glyph || !Clip(x, y, 16, 16, &rect)) return;
    source.glyph = glyph;
    source.glyph_bytes = 2U;
    source.color = color;
    source.bg = bg;
    DrawSource(&rect, &source);
}

/* ============ 显示字符（8x16，带背景色） ============ */
void ST7735_DrawChar(int x, int y, char c, uint16_t color, uint16_t bg)
{
    if (c < 0x20 || c > 0x7E) {
        c = ' ';                            /* 非 ASCII 用空格替代 */
    }
    ClipRect rect;
    PixelSource source = {0};
    if (!Clip(x, y, 8, 8, &rect)) return;
    source.glyph = FONT8x8[c - 0x20];
    source.glyph_bytes = 1U;
    source.color = color;
    source.bg = bg;
    DrawSource(&rect, &source);
}

/* ============ 显示字符串 ============ */
void ST7735_DrawString(int x, int y, const char *str, uint16_t color, uint16_t bg)
{
    int cx = x, cy = y;
    while (*str) {
        if (frame_failed) break;
        if (*str == '\n') {
            cx = x;
            cy += 8;
            str++;
            continue;
        }
        if (cx + 8 > LCD_WIDTH) {           /* 超宽自动换行 */
            cx = x;
            cy += 8;
        }
        if (cy + 8 > LCD_HEIGHT) {
            break;                          /* 超出屏幕停止 */
        }
        ST7735_DrawChar(cx, cy, *str, color, bg);
        cx += 8;
        str++;
    }
}
