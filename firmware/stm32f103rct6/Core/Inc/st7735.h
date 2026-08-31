/**
 * @file    st7735.h
 * @brief   ST7735 IPS LCD 驱动（软件 SPI，128x128）
 *
 * 说明：SPI1 引脚（PA5/6/7）已被 ADC 占用，故用 GPIO 软件模拟 SPI，
 *       引脚可灵活指定，无需改动 CubeMX。
 *       屏幕只写不读（单向），CS 常使能、背光常亮，均不占 MCU 引脚。
 */
#ifndef __ST7735_H
#define __ST7735_H

#include "stm32f1xx_hal.h"

/* ============ 引脚定义（软件 SPI，按开发板 LCD 排针丝印） ============
 * 排针（左→右）：GND 3V3 SCL SDA RES DC CS BLK
 * STM32 引脚：   GND 3V3 PB4 PB5 PB6 PB7 PB8 PB9
 */
#define LCD_PORT        GPIOB
#define LCD_SCK_PIN     GPIO_PIN_4    /* SCL */
#define LCD_MOSI_PIN    GPIO_PIN_5    /* SDA */
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
