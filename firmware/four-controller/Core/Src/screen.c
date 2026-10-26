#include "screen.h"
#include "board_config.h"
#include "st7735.h"
#include <stdio.h>

#define LINE_H 18

static const char *station_name(uint8_t board)
{
  switch (board)
  {
    case 1U: return "P3+P5";
    case 2U: return "P4";
    case 3U: return "P2";
    case 4U: return "P1";
    default: return "";
  }
}

void Screen_Init(void)
{
  ST7735_Init();
  ST7735_Clear(LCD_BLACK);
}

void Screen_Update(uint8_t board, uint16_t sequence, uint32_t uptime_s,
                   uint8_t alarm, const SensorSample *samples, uint8_t count)
{
  char line[40];
  int16_t temperature = 0;
  uint16_t humidity = 0;
  uint8_t has_temperature = 0;
  uint16_t co[2] = {0U, 0U};
  uint16_t mq4[2] = {0U, 0U};
  uint16_t mq2[2] = {0U, 0U};
  uint16_t flame[2] = {0U, 0U};
  uint16_t level = 0U;
  uint16_t o2_mv = 0U;
  uint8_t n_co = 0U, n_mq4 = 0U, n_mq2 = 0U, n_flame = 0U, n_level = 0U;
  uint8_t i;

  if ((samples == NULL) || (samples != BoardIo_Samples()) || count > 11U)
  {
    count = BoardIo_SampleCount();
    samples = BoardIo_Samples();
  }

  for (i = 0U; i < count; ++i)
  {
    const SensorDef *d = &board_config.sensors[i];
    switch (d->type)
    {
      case SENSOR_SHT:
        if (samples[i].status == SENSOR_STATUS_OK)
        {
          temperature = (int16_t)samples[i].value;
          humidity = samples[i].aux;
          has_temperature = 1U;
        }
        break;
      case SENSOR_CO:
        if (n_co < 2U) co[n_co++] = samples[i].value;
        break;
      case SENSOR_MQ4:
        if (n_mq4 < 2U) mq4[n_mq4++] = samples[i].value;
        break;
      case SENSOR_MQ2:
        if (n_mq2 < 2U) mq2[n_mq2++] = samples[i].value;
        break;
      case SENSOR_FLAME:
        if (n_flame < 2U) flame[n_flame++] = samples[i].value;
        break;
      case SENSOR_LEVEL:
        if (n_level == 0U) { level = samples[i].value; n_level = 1U; }
        break;
      case SENSOR_O2:
        o2_mv = samples[i].aux;
        break;
      default:
        break;
    }
  }

  /* 不整屏刷新：DrawString 自带背景色，逐行覆盖，避免 32 KB 清屏阻塞。 */
  snprintf(line, sizeof line, "CTRL-%u  %s", (unsigned)board, station_name(board));
  ST7735_DrawString(0, 0 * LINE_H, line, LCD_CYAN, LCD_BLACK);

  if (has_temperature)
  {
    int16_t abs_t = (temperature < 0) ? (int16_t)(-temperature) : temperature;
    snprintf(line, sizeof line, "SHT %s%ld.%ldC %lu%%",
             (temperature < 0) ? "-" : "",
             (long)(abs_t / 100), (long)(abs_t % 100 / 10),
             (unsigned long)(humidity / 100U));
  }
  else
  {
    snprintf(line, sizeof line, "SHT --");
  }
  ST7735_DrawString(0, 1 * LINE_H, line, LCD_WHITE, LCD_BLACK);

  snprintf(line, sizeof line, "CO %u/%u", co[0], co[1]);
  ST7735_DrawString(0, 2 * LINE_H, line, LCD_WHITE, LCD_BLACK);

  snprintf(line, sizeof line, "MQ4 %u/%u", mq4[0], mq4[1]);
  ST7735_DrawString(0, 3 * LINE_H, line, LCD_WHITE, LCD_BLACK);

  snprintf(line, sizeof line, "MQ2 %u/%u F %u/%u", mq2[0], mq2[1], flame[0], flame[1]);
  ST7735_DrawString(0, 4 * LINE_H, line, LCD_WHITE, LCD_BLACK);

  snprintf(line, sizeof line, "LVL %u  O2 %umV", level, o2_mv);
  ST7735_DrawString(0, 5 * LINE_H, line, LCD_WHITE, LCD_BLACK);

  snprintf(line, sizeof line, "ALM %s  %lus", alarm ? "Y" : "N",
           (unsigned long)uptime_s);
  ST7735_DrawString(0, 6 * LINE_H, line,
                    alarm ? LCD_RED : LCD_GREEN, LCD_BLACK);

  (void)sequence;
}
