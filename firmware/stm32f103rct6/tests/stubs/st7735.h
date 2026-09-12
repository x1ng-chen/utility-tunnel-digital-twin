#ifndef TEST_ST7735_H
#define TEST_ST7735_H

#include <stdint.h>

#define LCD_WIDTH 128
#define LCD_HEIGHT 128
#define LCD_BLACK 0x0000U
#define LCD_WHITE 0xFFFFU
#define LCD_RED 0xF800U
#define LCD_GREEN 0x07E0U
#define LCD_BLUE 0x001FU
#define LCD_YELLOW 0xFFE0U
#define LCD_CYAN 0x07FFU
#define LCD_MAGENTA 0xF81FU

void ST7735_Clear(uint16_t color);
void ST7735_FillRect(int x, int y, int w, int h, uint16_t color);
void ST7735_DrawGlyph16(int x, int y, const uint8_t glyph[32], uint16_t color, uint16_t bg);
void ST7735_DrawChar(int x, int y, char c, uint16_t color, uint16_t bg);
void ST7735_DrawString(int x, int y, const char *str, uint16_t color, uint16_t bg);

#endif
