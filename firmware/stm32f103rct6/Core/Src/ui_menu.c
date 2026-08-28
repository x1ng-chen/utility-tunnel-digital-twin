#include "ui_menu.h"

#include <stdio.h>
#include <string.h>

#include "hmi_zh_font.h"
#include "st7735.h"

#define UI_BG             0x0841
#define UI_CARD           0x18C3
#define UI_CARD_BORDER    0x4A49
#define UI_SELECTED       0x235F
#define UI_SELECTED_EDGE  0x07FF
#define UI_TEXT           LCD_WHITE
#define UI_MUTED          0x9CF3
#define UI_HEADER_H       22
#define UI_FOOTER_Y       112
#define UI_MENU_COUNT     6U

typedef enum {
  UI_PAGE_DASHBOARD = 0,
  UI_PAGE_MENU,
  UI_PAGE_SENSORS,
  UI_PAGE_ALERTS,
  UI_PAGE_CONTROL,
  UI_PAGE_LINK,
  UI_PAGE_SETTINGS,
} UiPage;

static UiTelemetry telemetry;
static UiTelemetry renderedTelemetry;
static UiPage page = UI_PAGE_MENU;
static uint8_t menuIndex;
static uint8_t dirty = 1U;
static uint8_t telemetryDirty;
static uint8_t renderedTelemetryValid;

static const char *const menuItems[UI_MENU_COUNT] = {
  "监测", "传感", "报警", "控制", "通信", "设置",
};

static const HmiZhGlyph *find_zh_glyph(uint16_t codepoint)
{
  uint16_t index;
  for (index = 0U; index < HMI_ZH_GLYPH_COUNT; index++) {
    if (HMI_ZH_GLYPHS[index].codepoint == codepoint) return &HMI_ZH_GLYPHS[index];
  }
  return NULL;
}

static uint16_t decode_utf8(const uint8_t **cursor)
{
  const uint8_t *text = *cursor;
  uint16_t codepoint;
  if (text[0] < 0x80U) {
    *cursor = text + 1;
    return text[0];
  }
  if ((text[0] & 0xF0U) == 0xE0U && (text[1] & 0xC0U) == 0x80U && (text[2] & 0xC0U) == 0x80U) {
    codepoint = (uint16_t)(((text[0] & 0x0FU) << 12) | ((text[1] & 0x3FU) << 6) | (text[2] & 0x3FU));
    *cursor = text + 3;
    return codepoint;
  }
  *cursor = text + 1;
  return '?';
}

static int text_width(const char *text)
{
  const uint8_t *cursor = (const uint8_t *)text;
  int width = 0;
  while (*cursor != '\0') width += (decode_utf8(&cursor) < 0x80U) ? 8 : 16;
  return width;
}

static void draw_text(int x, int y, const char *text, uint16_t color, uint16_t background)
{
  const uint8_t *cursor = (const uint8_t *)text;
  while (*cursor != '\0') {
    const uint16_t codepoint = decode_utf8(&cursor);
    if (codepoint < 0x80U) {
      ST7735_DrawChar(x, y + 4, (char)codepoint, color, background);
      x += 8;
    } else {
      const HmiZhGlyph *glyph = find_zh_glyph(codepoint);
      if (glyph != NULL) ST7735_DrawGlyph16(x, y, glyph->bitmap, color, background);
      else ST7735_DrawChar(x + 4, y + 4, '?', color, background);
      x += 16;
    }
  }
}

static void draw_header(const char *title, uint16_t accent)
{
  const int width = text_width(title);
  ST7735_FillRect(0, 0, LCD_WIDTH, UI_HEADER_H, accent);
  ST7735_FillRect(0, UI_HEADER_H - 2, LCD_WIDTH, 2, UI_SELECTED_EDGE);
  draw_text((LCD_WIDTH - width) / 2, 3, title, LCD_WHITE, accent);
}

static void draw_footer(const char *hint)
{
  const int width = text_width(hint);
  ST7735_FillRect(0, UI_FOOTER_Y, LCD_WIDTH, LCD_HEIGHT - UI_FOOTER_Y, UI_CARD);
  draw_text((LCD_WIDTH - width) / 2, UI_FOOTER_Y, hint, UI_MUTED, UI_CARD);
}

static void draw_card(int x, int y, int width, int height, uint16_t fill, uint16_t edge)
{
  ST7735_FillRect(x, y, width, height, edge);
  ST7735_FillRect(x + 1, y + 1, width - 2, height - 2, fill);
}

static void draw_metric_card(int y, const char *label, const char *value, uint16_t valueColor)
{
  draw_card(4, y, 120, 18, UI_CARD, UI_CARD_BORDER);
  draw_text(9, y + 1, label, UI_TEXT, UI_CARD);
  draw_text(51, y + 1, value, valueColor, UI_CARD);
}

static uint8_t telemetry_changed(const UiTelemetry *left, const UiTelemetry *right)
{
  return (left->temperature != right->temperature) ||
         (left->humidity != right->humidity) ||
         (left->waterRaw != right->waterRaw) ||
         (left->dhtOk != right->dhtOk) ||
         (left->vibrationAlarm != right->vibrationAlarm) ||
         (left->telemetryTxEnabled != right->telemetryTxEnabled);
}

static void draw_sensor_value(int y, const char *label, const char *value, uint16_t color)
{
  draw_metric_card(y, label, value, color);
}

/* Only redraw the changing data rows.  The header, footer and other cards stay put. */
static void render_sensor_values_delta(const UiTelemetry *previous, uint8_t force)
{
  char value[12];

  if (force || (telemetry.temperature != previous->temperature) || (telemetry.dhtOk != previous->dhtOk)) {
    (void)snprintf(value, sizeof(value), "%02u C", telemetry.temperature);
    draw_sensor_value(27, "温度", value, telemetry.dhtOk ? LCD_GREEN : LCD_RED);
  }
  if (force || (telemetry.humidity != previous->humidity) || (telemetry.dhtOk != previous->dhtOk)) {
    (void)snprintf(value, sizeof(value), "%02u %%", telemetry.humidity);
    draw_sensor_value(48, "湿度", value, telemetry.dhtOk ? LCD_CYAN : LCD_RED);
  }
  if (force || (telemetry.waterRaw != previous->waterRaw)) {
    (void)snprintf(value, sizeof(value), "%04u", telemetry.waterRaw);
    draw_sensor_value(69, "水位", value, telemetry.waterRaw >= 1000U ? LCD_YELLOW : LCD_WHITE);
  }
  if (force || (telemetry.vibrationAlarm != previous->vibrationAlarm)) {
    draw_sensor_value(90, "震动", telemetry.vibrationAlarm ? "异常" : "正常",
                      telemetry.vibrationAlarm ? LCD_RED : LCD_GREEN);
  }
}

static void render_dashboard(void)
{
  char value[12];
  ST7735_Clear(UI_BG);
  draw_header("实时监测", LCD_BLUE);
  (void)snprintf(value, sizeof(value), "%02u C", telemetry.temperature);
  draw_metric_card(27, "温度", value, telemetry.dhtOk ? LCD_GREEN : LCD_RED);
  (void)snprintf(value, sizeof(value), "%02u %%", telemetry.humidity);
  draw_metric_card(48, "湿度", value, telemetry.dhtOk ? LCD_CYAN : LCD_RED);
  (void)snprintf(value, sizeof(value), "%04u", telemetry.waterRaw);
  draw_metric_card(69, "水位", value, telemetry.waterRaw >= 1000U ? LCD_YELLOW : LCD_WHITE);
  draw_metric_card(90, "震动", telemetry.vibrationAlarm ? "ALARM" : "NORMAL", telemetry.vibrationAlarm ? LCD_RED : LCD_GREEN);
  draw_footer("K4:长按返回");
}

static void render_menu_card(uint8_t index)
{
  const int x = 4 + (index % 2U) * 62;
  const int y = 27 + (index / 2U) * 27;
  const uint16_t fill = (index == menuIndex) ? UI_SELECTED : UI_CARD;
  const uint16_t edge = (index == menuIndex) ? UI_SELECTED_EDGE : UI_CARD_BORDER;
  const uint16_t color = (index == menuIndex) ? LCD_WHITE : UI_MUTED;
  draw_card(x, y, 58, 23, fill, edge);
  draw_text(x + 13, y + 3, menuItems[index], color, fill);
}

static void render_menu(void)
{
  uint8_t index;
  ST7735_Clear(UI_BG);
  draw_header("综合管廊", LCD_BLUE);
  for (index = 0U; index < UI_MENU_COUNT; index++) {
    render_menu_card(index);
  }
  draw_footer("K2/K3选择 K4确认");
}

static void render_sensors(void)
{
  ST7735_Clear(UI_BG);
  draw_header("传感状态", LCD_CYAN);
  render_sensor_values_delta(&telemetry, 1U);
  draw_footer("K4:长按返回");
}

static void render_alerts(void)
{
  const char *state = "当前无报警";
  uint16_t color = LCD_GREEN;
  if (telemetry.vibrationAlarm) { state = "震动异常"; color = LCD_RED; }
  else if (telemetry.waterRaw >= 1000U) { state = "水位异常"; color = LCD_YELLOW; }
  else if (!telemetry.dhtOk) { state = "采集异常"; color = LCD_RED; }
  ST7735_Clear(UI_BG);
  draw_header("报警中心", color);
  draw_card(8, 35, 112, 28, UI_CARD, color);
  draw_text((LCD_WIDTH - text_width(state)) / 2, 41, state, color, UI_CARD);
  draw_text(32, 78, "平台确认报警", UI_MUTED, UI_BG);
  draw_footer("K4:长按返回");
}

static void render_control(void)
{
  ST7735_Clear(UI_BG);
  draw_header("设备控制", LCD_YELLOW);
  draw_card(8, 30, 112, 24, UI_CARD, LCD_YELLOW);
  draw_text(24, 34, "本地安全锁定", LCD_YELLOW, UI_CARD);
  draw_text(24, 66, "设备未接入", UI_MUTED, UI_BG);
  draw_text(24, 88, "控制待接入", LCD_CYAN, UI_BG);
  draw_footer("K4:长按返回");
}

static void render_link(void)
{
  ST7735_Clear(UI_BG);
  draw_header("通信状态", LCD_CYAN);
  draw_metric_card(27, "串口", "9600", LCD_WHITE);
  draw_metric_card(48, "蓝牙", "JDY-31", LCD_CYAN);
  draw_metric_card(69, "网关", "本地", telemetry.telemetryTxEnabled ? LCD_GREEN : LCD_YELLOW);
  draw_metric_card(90, "云端", "待接入", LCD_YELLOW);
  draw_footer("K4:长按返回");
}

static void render_settings(void)
{
  ST7735_Clear(UI_BG);
  draw_header("系统设置", LCD_BLUE);
  draw_metric_card(27, "阈值", "1000", LCD_YELLOW);
  draw_metric_card(48, "上报", "2 SEC", LCD_CYAN);
  draw_metric_card(69, "摇杆", "待接入", LCD_YELLOW);
  draw_metric_card(90, "系统", "本地", LCD_GREEN);
  draw_footer("K4:长按返回");
}

static void render_current_page(void)
{
  switch (page) {
    case UI_PAGE_DASHBOARD: render_dashboard(); break;
    case UI_PAGE_SENSORS: render_sensors(); break;
    case UI_PAGE_ALERTS: render_alerts(); break;
    case UI_PAGE_CONTROL: render_control(); break;
    case UI_PAGE_LINK: render_link(); break;
    case UI_PAGE_SETTINGS: render_settings(); break;
    case UI_PAGE_MENU:
    default: render_menu(); break;
  }
}

void UI_MenuInit(void)
{
  (void)memset(&telemetry, 0, sizeof(telemetry));
  (void)memset(&renderedTelemetry, 0, sizeof(renderedTelemetry));
  page = UI_PAGE_MENU;
  menuIndex = 0U;
  dirty = 1U;
  telemetryDirty = 0U;
  renderedTelemetryValid = 0U;
}

void UI_MenuSetTelemetry(const UiTelemetry *nextTelemetry)
{
  if ((nextTelemetry != NULL) && telemetry_changed(&telemetry, nextTelemetry)) {
    telemetry = *nextTelemetry;
    telemetryDirty = 1U;
  }
}

void UI_MenuHandleInput(UiInput input)
{
  if (input == UI_INPUT_NONE) return;
  if (page == UI_PAGE_MENU) {
    const uint8_t previousIndex = menuIndex;
    if (input == UI_INPUT_UP) {
      menuIndex = (menuIndex == 0U) ? (UI_MENU_COUNT - 1U) : (menuIndex - 1U);
      render_menu_card(previousIndex);
      render_menu_card(menuIndex);
      return;
    } else if (input == UI_INPUT_DOWN) {
      menuIndex = (uint8_t)((menuIndex + 1U) % UI_MENU_COUNT);
      render_menu_card(previousIndex);
      render_menu_card(menuIndex);
      return;
    }
    else if (input == UI_INPUT_OK) {
      switch (menuIndex) {
        case 0U: page = UI_PAGE_DASHBOARD; break;
        case 1U: page = UI_PAGE_SENSORS; break;
        case 2U: page = UI_PAGE_ALERTS; break;
        case 3U: page = UI_PAGE_CONTROL; break;
        case 4U: page = UI_PAGE_LINK; break;
        case 5U: page = UI_PAGE_SETTINGS; break;
        default: break;
      }
    } else return;
    dirty = 1U;
    return;
  }
  if ((input == UI_INPUT_BACK) || (input == UI_INPUT_LEFT)) {
    page = UI_PAGE_MENU;
    dirty = 1U;
  }
}

void UI_MenuTick(uint32_t nowMs)
{
  (void)nowMs;
  if (dirty) {
    render_current_page();
    dirty = 0U;
    renderedTelemetry = telemetry;
    renderedTelemetryValid = 1U;
    telemetryDirty = 0U;
  } else if (telemetryDirty != 0U) {
    if (page == UI_PAGE_SENSORS) {
      render_sensor_values_delta(&renderedTelemetry, renderedTelemetryValid == 0U);
    }
    renderedTelemetry = telemetry;
    renderedTelemetryValid = 1U;
    telemetryDirty = 0U;
  }
}
