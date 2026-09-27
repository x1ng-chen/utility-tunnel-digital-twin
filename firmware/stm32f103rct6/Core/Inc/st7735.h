/**
 * @file    st7735.h
 * @brief   ST7735 IPS LCD 驱动（128x128）
 *
 * Node B 使用 SPI1：PA5=SCK、PA7=MOSI；PA6 不接。
 * bench 固件保留原 PB4/PB5 软件 SPI 接线。
 */
#ifndef __ST7735_H
#define __ST7735_H

#include "stm32f1xx_hal.h"

/* ============ 引脚定义（按开发板 LCD 排针丝印） ============
 * 排针（左→右）：GND 3V3 SCL SDA RES DC CS BLK
 * Node B：       GND 3V3 PA5 PA7 PB6 PB7 PB8 PB9
 */
#define LCD_CTRL_PORT   GPIOB
#ifdef NODE_B_FIRMWARE
#define LCD_SPI_PORT    GPIOA
#define LCD_SCK_PIN     GPIO_PIN_5    /* SPI1_SCK */
#define LCD_MOSI_PIN    GPIO_PIN_7    /* SPI1_MOSI */
#else
#define LCD_SPI_PORT    GPIOB
#define LCD_SCK_PIN     GPIO_PIN_4    /* legacy software SCL */
#define LCD_MOSI_PIN    GPIO_PIN_5    /* legacy software SDA */
#endif
#define LCD_DC_PIN      GPIO_PIN_7    /* DC  */
#define LCD_RES_PIN     GPIO_PIN_6    /* RES */
#define LCD_CS_PIN      GPIO_PIN_8    /* CS  */
#define LCD_BLK_PIN     GPIO_PIN_9    /* BLK 背光 */

/* 屏幕分辨率（1.44 寸 128x128） */
#define LCD_WIDTH   128
#define LCD_HEIGHT  128

/* 显示 RAM 偏移（画面偏移/有黑边时按模块微调；1.44 寸常见 Y 偏移 3） */
#define LCD_X_OFFSET 2
#define LCD_Y_OFFSET 3

/* 颜色 RGB565 */
#define LCD_BLACK   0x0000
#define LCD_WHITE   0xFFFF
#define LCD_RED     0xF800
#define LCD_GREEN   0x07E0
#define LCD_BLUE    0x001F
#define LCD_YELLOW  0xFFE0
#define LCD_CYAN    0x07FF
#define LCD_MAGENTA 0xF81F

void ST7735_Init(void);                                              /* 初始化 + 清屏 */
void ST7735_Clear(uint16_t color);                                   /* 清屏 */
void ST7735_FillRect(int x, int y, int w, int h, uint16_t color);   /* 填充矩形 */
void ST7735_DrawGlyph16(int x, int y, const uint8_t glyph[32], uint16_t color, uint16_t bg);
void ST7735_DrawChar(int x, int y, char c, uint16_t color, uint16_t bg);          /* 显示字符 8x16 */
void ST7735_DrawString(int x, int y, const char *str, uint16_t color, uint16_t bg); /* 显示字符串 */

#endif /* __ST7735_H */
