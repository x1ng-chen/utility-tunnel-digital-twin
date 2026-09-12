#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "ui_menu.h"

#define CHECK(condition) do { \
  if (!(condition)) { \
    (void)fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    return 1; \
  } \
} while (0)

void ST7735_Clear(uint16_t color) { (void)color; }
void ST7735_FillRect(int x, int y, int w, int h, uint16_t color)
{ (void)x; (void)y; (void)w; (void)h; (void)color; }
void ST7735_DrawGlyph16(int x, int y, const uint8_t glyph[32], uint16_t color, uint16_t bg)
{ (void)x; (void)y; (void)glyph; (void)color; (void)bg; }
void ST7735_DrawChar(int x, int y, char c, uint16_t color, uint16_t bg)
{ (void)x; (void)y; (void)c; (void)color; (void)bg; }
void ST7735_DrawString(int x, int y, const char *str, uint16_t color, uint16_t bg)
{ (void)x; (void)y; (void)str; (void)color; (void)bg; }

int main(void)
{
  UiTelemetry telemetry = {0};
  char layout[320];
  uint32_t now = 0U;
  uint8_t index;

  UI_MenuInit();
  UI_MenuTick(now++);
  CHECK(UI_MenuDescribeLayout(layout, sizeof(layout)) > 0U);
  CHECK(strstr(layout, "page=home") != NULL);
  CHECK(strstr(layout, "rows=7") != NULL);

  for (index = 0U; index < 3U; ++index) {
    UI_MenuHandleInput(UI_INPUT_DOWN);
    UI_MenuTick(now++);
  }
  UI_MenuHandleInput(UI_INPUT_OK);
  UI_MenuTick(now++);
  CHECK(UI_MenuDescribeLayout(layout, sizeof(layout)) > 0U);
  CHECK(strstr(layout, "page=fans") != NULL);
  CHECK(strstr(layout, "selected=fan_1_start_stop_30_60_100") != NULL);

  telemetry.telemetryTxEnabled = 1U;
  telemetry.temperature = 23U;
  telemetry.humidity = 55U;
  telemetry.dhtOk = 1U;
  UI_MenuSetTelemetry(&telemetry);
  UI_MenuTick(now++);
  CHECK(UI_MenuDescribeLayout(layout, sizeof(layout)) > 0U);
  CHECK(strstr(layout, "mqtt=online") != NULL);
  CHECK(UI_MenuDescribeLayout(NULL, sizeof(layout)) == 0U);

  (void)puts("UI menu adapter host test: PASS");
  return 0;
}
