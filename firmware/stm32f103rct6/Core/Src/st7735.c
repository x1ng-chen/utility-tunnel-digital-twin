/**
 * @file    st7735.c
 * @brief   ST7735 IPS LCD 驱动实现（软件 SPI）
 *
 * 软件 SPI：GPIO 翻转模拟 SCK/MOSI 时序，写命令/数据。
 * 颜色 RGB565（16 位，先高字节后低字节）。
 */
#include "st7735.h"
#include "st7735_font.h"

/* ============ GPIO 初始化 ============ */
static void ST7735_GPIO_Init(void)
{
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
}

/* ============ 软件 SPI ============ */
static void spi_write_byte(uint8_t b)
{
    for (int i = 0; i < 8; i++) {
        HAL_GPIO_WritePin(LCD_PORT, LCD_SCK_PIN, GPIO_PIN_RESET);
        HAL_GPIO_WritePin(LCD_PORT, LCD_MOSI_PIN,
                          (b & 0x80) ? GPIO_PIN_SET : GPIO_PIN_RESET);
        b <<= 1;
        HAL_GPIO_WritePin(LCD_PORT, LCD_SCK_PIN, GPIO_PIN_SET);
    }
}

/* ============ 写命令 / 写数据 ============ */
static void ST7735_Cmd(uint8_t cmd)
{
    HAL_GPIO_WritePin(LCD_PORT, LCD_DC_PIN, GPIO_PIN_RESET);   /* DC=0 命令 */
    spi_write_byte(cmd);
}

static void ST7735_Data(uint8_t data)
{
    HAL_GPIO_WritePin(LCD_PORT, LCD_DC_PIN, GPIO_PIN_SET);     /* DC=1 数据 */
    spi_write_byte(data);
}

/* ============ 复位 ============ */
static void ST7735_Reset(void)
{
    HAL_GPIO_WritePin(LCD_PORT, LCD_RES_PIN, GPIO_PIN_RESET);
    HAL_Delay(20);
    HAL_GPIO_WritePin(LCD_PORT, LCD_RES_PIN, GPIO_PIN_SET);
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

/* ============ 填充矩形 ============ */
static void ST7735_FillRect(int x, int y, int w, int h, uint16_t color)
{
    ST7735_SetWindow(x, y, x + w - 1, y + h - 1);
    uint32_t n = (uint32_t)w * h;
    for (uint32_t i = 0; i < n; i++) {
        ST7735_Data(color >> 8);
        ST7735_Data(color & 0xFF);
    }
}

/* ============ 初始化 ============ */
void ST7735_Init(void)
{
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

/* ============ 显示字符（8x16，带背景色） ============ */
void ST7735_DrawChar(int x, int y, char c, uint16_t color, uint16_t bg)
{
    if (c < 0x20 || c > 0x7E) {
        c = ' ';                            /* 非 ASCII 用空格替代 */
    }
    const unsigned char *glyph = FONT8x8[c - 0x20];

    ST7735_SetWindow(x, y, x + 7, y + 7);
    for (int row = 0; row < 8; row++) {
        unsigned char bits = glyph[row];
        for (int col = 0; col < 8; col++) {
            uint16_t c2 = (bits & (0x80 >> col)) ? color : bg;
            ST7735_Data(c2 >> 8);
            ST7735_Data(c2 & 0xFF);
        }
    }
}

/* ============ 显示字符串 ============ */
void ST7735_DrawString(int x, int y, const char *str, uint16_t color, uint16_t bg)
{
    int cx = x, cy = y;
    while (*str) {
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
