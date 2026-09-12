#include "ui_renderer.h"

#include <stdio.h>
#include <string.h>

#include "hmi_zh_font.h"
#include "st7735.h"

#define UI_COLOR_BACKGROUND 0x0841U
#define UI_COLOR_HEADER     0x1082U
#define UI_COLOR_PANEL      0x18C3U
#define UI_COLOR_BORDER     0x3186U
#define UI_COLOR_ACCENT     0x06BFU
#define UI_COLOR_MUTED      0x8C71U
#define UI_COLOR_WARNING    0xFD20U
#define UI_COLOR_DANGER     0xF9A6U
#define UI_HEADER_HEIGHT    12
#define UI_PAGE_TOP         12
#define UI_TITLE_HEIGHT     20
#define UI_ROWS_TOP         34
#define UI_ROW_HEIGHT       20
#define UI_FOOTER_TOP       116

typedef struct {
  int16_t x;
  int16_t y;
  int16_t width;
  int16_t height;
} UiDirtyRect;

typedef struct {
  uint8_t initialized;
  UiState state;
  UiSnapshot snapshot;
  UiRendererStats stats;
  uint8_t selection_animation;
  uint8_t page_animation;
  int16_t selection_from_y;
  int16_t selection_to_y;
  int16_t selection_drawn_y;
  UiPage previous_page;
  uint8_t previous_row;
  uint32_t animation_start_ms;
  uint32_t animation_duration_ms;
  uint32_t next_animation_ms;
  uint8_t cadence_remainder;
} UiRendererContext;

static UiRendererContext renderer;

static const char *const page_names[] = {
  "home", "overview", "monitor", "alerts", "fans", "light_sound", "network", "settings",
};

static const char *const page_titles[] = {
  "main_menu", "safety_overview", "classified_monitoring", "alarm_center",
  "fan_control", "led_and_buzzer", "communication_status", "system_settings",
};

static const char *const home_diagnostic_items[] = {
  "safety_overview", "classified_monitoring", "alarm_center", "fan_control",
  "led_and_buzzer", "communication_status", "system_settings",
};

static const char *const home_display_items[] = {
  "安全总览", "分类监测", "报警中心", "风机控制",
  "灯带与蜂鸣器", "通信状态", "系统设置",
};

static const char *const monitor_diagnostic_items[] = {
  "environment", "gases", "water_and_fire", "fan_power",
};

static const char *const fan_diagnostic_items[] = {
  "fan_1_start_stop_30_60_100", "both_start", "all_stop", "fan_2_start_stop_30_60_100",
};

static const char *const light_diagnostic_items[] = {
  "led_modes_off_white_green_yellow_red_blue_breathe_flash",
  "brightness_25_50_75_100_and_buzzer_test", "buzzer_mute_restore",
};

static uint8_t page_row_count(UiPage page)
{
  switch (page) {
    case UI_HOME: return 7U;
    case UI_MONITOR: return 4U;
    case UI_FANS: return 4U;
    case UI_LIGHT_SOUND: return 3U;
    case UI_SETTINGS: return 2U;
    case UI_OVERVIEW:
    case UI_ALERTS:
    case UI_NETWORK:
    default: return 1U;
  }
}

static const char *selected_name(UiPage page, uint8_t row)
{
  switch (page) {
    case UI_HOME:
      return (row < 7U) ? home_diagnostic_items[row] : "unknown";
    case UI_OVERVIEW: return "overall_status";
    case UI_MONITOR:
      return (row < 4U) ? monitor_diagnostic_items[row] : "unknown";
    case UI_ALERTS: return "active_alarms";
    case UI_FANS:
      return (row < 4U) ? fan_diagnostic_items[row] : "unknown";
    case UI_LIGHT_SOUND:
      return (row < 3U) ? light_diagnostic_items[row] : "unknown";
    case UI_NETWORK: return "link_summary";
    case UI_SETTINGS: return (row == 0U) ? "display" : "joystick";
    default: return "unknown";
  }
}

static const char *dialog_name(UiDialog dialog)
{
  return (dialog == UI_DIALOG_CONFIRM) ? "confirm" : "none";
}

uint8_t UiRenderer_PageFromName(const char *name, UiPage *page)
{
  uint8_t index;
  if ((name == NULL) || (page == NULL) || (name[0] == '\0')) return 0U;
  for (index = 0U; index < (uint8_t)(sizeof(page_names) / sizeof(page_names[0])); ++index) {
    if (strcmp(name, page_names[index]) == 0) {
      *page = (UiPage)index;
      return 1U;
    }
  }
  return 0U;
}

static const char *command_name(UiCommandPhase phase)
{
  static const char *const names[] = {
    "idle", "confirm", "sending", "accepted", "rejected", "timeout",
  };
  return ((uint8_t)phase < (uint8_t)(sizeof(names) / sizeof(names[0]))) ? names[phase] : "unknown";
}

static uint8_t clock_is_valid(const UiSnapshot *snapshot)
{
  return (snapshot->clock.synchronized != 0U) &&
         (snapshot->clock.hour < 24U) && (snapshot->clock.minute < 60U);
}

static void format_clock(const UiSnapshot *snapshot, char output[6])
{
  output[0] = '-'; output[1] = '-'; output[2] = ':';
  output[3] = '-'; output[4] = '-'; output[5] = '\0';
  if (!clock_is_valid(snapshot)) return;
  output[0] = (char)('0' + snapshot->clock.hour / 10U);
  output[1] = (char)('0' + snapshot->clock.hour % 10U);
  output[3] = (char)('0' + snapshot->clock.minute / 10U);
  output[4] = (char)('0' + snapshot->clock.minute % 10U);
}

size_t UiRenderer_DescribeLayout(const UiState *state, const UiSnapshot *snapshot,
                                 char *output, size_t output_size)
{
  char time_field[6];
  int length;
  if ((state == NULL) || (snapshot == NULL) || (output == NULL) || (output_size == 0U)) return 0U;
  format_clock(snapshot, time_field);
  length = snprintf(output, output_size,
                    "#UI page=%s row=%u dialog=%s command=%s title=%s rows=%u selected=%s time=%s mqtt=%s",
                    ((uint8_t)state->page < (uint8_t)(sizeof(page_names) / sizeof(page_names[0])))
                      ? page_names[state->page] : "unknown",
                    (unsigned int)state->selected_row, dialog_name(state->dialog),
                    command_name(state->command_phase),
                    ((uint8_t)state->page < (uint8_t)(sizeof(page_titles) / sizeof(page_titles[0])))
                      ? page_titles[state->page] : "unknown",
                    (unsigned int)page_row_count(state->page), selected_name(state->page, state->selected_row),
                    time_field, snapshot->connectivity.mqtt_online ? "online" : "offline");
  if (length < 0) {
    output[0] = '\0';
    return 0U;
  }
  if ((size_t)length >= output_size) return output_size - 1U;
  return (size_t)length;
}

int16_t UiRenderer_InterpolatePixels(int16_t from, int16_t to, uint32_t start_ms,
                                     uint32_t duration_ms, uint32_t now_ms)
{
  uint32_t elapsed;
  int32_t delta;
  int64_t scaled;
  if ((int32_t)(now_ms - start_ms) < 0) return from;
  elapsed = now_ms - start_ms;
  if ((duration_ms == 0U) || (elapsed >= duration_ms)) return to;
  delta = (int32_t)to - (int32_t)from;
  scaled = (int64_t)delta * (int64_t)elapsed;
  return (int16_t)((int32_t)from + (int32_t)(scaled / (int64_t)duration_ms));
}

static const HmiZhGlyph *find_zh_glyph(uint16_t codepoint)
{
  uint16_t index;
  for (index = 0U; index < HMI_ZH_GLYPH_COUNT; ++index) {
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
  if (((text[0] & 0xF0U) == 0xE0U) && ((text[1] & 0xC0U) == 0x80U) &&
      ((text[2] & 0xC0U) == 0x80U)) {
    codepoint = (uint16_t)(((text[0] & 0x0FU) << 12) |
                           ((text[1] & 0x3FU) << 6) | (text[2] & 0x3FU));
    *cursor = text + 3;
    return codepoint;
  }
  *cursor = text + 1;
  return (uint16_t)'?';
}

static int16_t text_width(const char *text)
{
  const uint8_t *cursor = (const uint8_t *)text;
  int16_t width = 0;
  while (*cursor != '\0') width = (int16_t)(width + ((decode_utf8(&cursor) < 0x80U) ? 8 : 16));
  return width;
}

static void draw_text(int16_t x, int16_t y, const char *text, uint16_t color, uint16_t background)
{
  const uint8_t *cursor = (const uint8_t *)text;
  while (*cursor != '\0') {
    const uint16_t codepoint = decode_utf8(&cursor);
    if (codepoint < 0x80U) {
      ST7735_DrawChar(x, (int)(y + 4), (char)codepoint, color, background);
      x = (int16_t)(x + 8);
    } else {
      const HmiZhGlyph *glyph = find_zh_glyph(codepoint);
      if (glyph != NULL) ST7735_DrawGlyph16(x, y, glyph->bitmap, color, background);
      else ST7735_DrawChar((int)(x + 4), (int)(y + 4), '?', color, background);
      x = (int16_t)(x + 16);
    }
  }
}

static void begin_frame(void)
{
  renderer.stats.last_dirty_rectangles = 0U;
  renderer.stats.last_dirty_pixels = 0U;
}

static void invalidate(UiDirtyRect rect)
{
  uint32_t pixels;
  if ((rect.width <= 0) || (rect.height <= 0)) return;
  pixels = (uint32_t)(uint16_t)rect.width * (uint32_t)(uint16_t)rect.height;
  ++renderer.stats.dirty_rectangles;
  ++renderer.stats.last_dirty_rectangles;
  renderer.stats.dirty_pixels += pixels;
  renderer.stats.last_dirty_pixels += pixels;
  if ((rect.x == 0) && (rect.y == 0) &&
      (rect.width == LCD_WIDTH) && (rect.height == LCD_HEIGHT)) {
    ++renderer.stats.full_screen_redraws;
  }
}

static uint8_t reading_changed(const UiReading *left, const UiReading *right)
{
  return (left->value != right->value) || (left->quality != right->quality);
}

static uint8_t fan_changed(const UiFanSnapshot *left, const UiFanSnapshot *right)
{
  return (left->target_duty_percent != right->target_duty_percent) ||
         (left->running != right->running) || (left->actual_rpm != right->actual_rpm) ||
         (left->voltage_mv != right->voltage_mv) || (left->current_ma != right->current_ma) ||
         (left->quality != right->quality);
}

static uint8_t time_changed(const UiSnapshot *left, const UiSnapshot *right)
{
  const uint8_t left_valid = clock_is_valid(left);
  const uint8_t right_valid = clock_is_valid(right);
  if (left_valid != right_valid) return 1U;
  if (!left_valid) return 0U;
  return (left->clock.hour != right->clock.hour) ||
         (left->clock.minute != right->clock.minute);
}

static int16_t row_y(UiPage page, uint8_t row, uint8_t selected_row)
{
  uint8_t first = 0U;
  if (page == UI_LIGHT_SOUND) {
    static const int16_t light_rows[] = {34, 60, 86};
    return (row < 3U) ? light_rows[row] : UI_ROWS_TOP;
  }
  if (page == UI_SETTINGS) return (row == 0U) ? 42 : 70;
  if ((page == UI_HOME) && (selected_row > 3U)) first = (uint8_t)(selected_row - 3U);
  if (row < first) return -UI_ROW_HEIGHT;
  return (int16_t)(UI_ROWS_TOP + ((int16_t)row - (int16_t)first) * UI_ROW_HEIGHT);
}

static int16_t selection_bar_height(UiPage page)
{
  if (page == UI_MONITOR) return 14;
  if (page == UI_LIGHT_SOUND) return 24;
  return UI_ROW_HEIGHT - 2;
}

static uint8_t popcount8(uint32_t value)
{
  uint8_t count = 0U;
  value &= 0xFFU;
  while (value != 0U) {
    count = (uint8_t)(count + (uint8_t)(value & 1U));
    value >>= 1U;
  }
  return count;
}

static const char *quality_suffix(UiDataQuality quality)
{
  if (quality == UI_QUALITY_STALE) return " STALE";
  if (quality == UI_QUALITY_INVALID) return " INVALID";
  if (quality == UI_QUALITY_UNKNOWN) return " --";
  return "";
}

static void format_reading(char *output, size_t size, const UiReading *reading,
                           int32_t scale, const char *unit)
{
  long value = (long)reading->value;
  long absolute;
  if (reading->quality == UI_QUALITY_UNKNOWN) {
    (void)snprintf(output, size, "--%s", unit);
    return;
  }
  if (scale <= 1) {
    (void)snprintf(output, size, "%ld%s%s", value, unit, quality_suffix(reading->quality));
    return;
  }
  absolute = (value < 0L) ? -value : value;
  (void)snprintf(output, size, "%s%ld.%02ld%s%s", value < 0L ? "-" : "",
                 absolute / (long)scale, absolute % (long)scale, unit,
                 quality_suffix(reading->quality));
}

static void draw_header(const UiSnapshot *snapshot)
{
  char time_field[6];
  ST7735_FillRect(0, 0, LCD_WIDTH, UI_HEADER_HEIGHT, UI_COLOR_HEADER);
  ST7735_DrawString(2, 2, "CTRL-02", LCD_WHITE, UI_COLOR_HEADER);
  ST7735_DrawString(61, 2, snapshot->connectivity.mqtt_online ? "M+" : "M-",
                    snapshot->connectivity.mqtt_online ? LCD_GREEN : UI_COLOR_DANGER,
                    UI_COLOR_HEADER);
  format_clock(snapshot, time_field);
  ST7735_DrawString(88, 2, time_field, LCD_WHITE, UI_COLOR_HEADER);
}

static void draw_footer(const UiState *state)
{
  const char *hint = (state->page == UI_HOME) ? "UP/DN  OK>" : "<BACK  OK";
  uint16_t color = UI_COLOR_MUTED;
  ST7735_FillRect(0, UI_FOOTER_TOP, LCD_WIDTH, LCD_HEIGHT - UI_FOOTER_TOP, UI_COLOR_HEADER);
  if ((state->control.mqtt_online == 0U) &&
      ((state->page == UI_FANS) || (state->page == UI_LIGHT_SOUND))) {
    hint = "MQTT LOCKED";
    color = UI_COLOR_WARNING;
  }
  ST7735_DrawString(20, UI_FOOTER_TOP + 2, hint, color, UI_COLOR_HEADER);
}

static void draw_title(int16_t offset, const char *title)
{
  const int16_t width = text_width(title);
  draw_text((int16_t)(offset + (LCD_WIDTH - width) / 2), UI_PAGE_TOP + 2,
            title, LCD_WHITE, UI_COLOR_BACKGROUND);
}

static void draw_list_row(int16_t offset, int16_t y, const char *label, uint8_t selected)
{
  if ((y >= UI_FOOTER_TOP) || ((y + UI_ROW_HEIGHT) <= UI_ROWS_TOP)) return;
  ST7735_FillRect(offset + 8, y, 116, UI_ROW_HEIGHT - 2,
                  selected ? 0x2145U : UI_COLOR_PANEL);
  if (selected) ST7735_FillRect(offset + 2, y, 3, UI_ROW_HEIGHT - 2, UI_COLOR_ACCENT);
  draw_text((int16_t)(offset + 12), (int16_t)(y + 1), label,
            selected ? LCD_WHITE : UI_COLOR_MUTED,
            selected ? 0x2145U : UI_COLOR_PANEL);
}

static void draw_home(int16_t offset, uint8_t selected)
{
  uint8_t row;
  uint8_t first = (selected > 3U) ? (uint8_t)(selected - 3U) : 0U;
  uint8_t last = (uint8_t)(first + 4U);
  if (last > 7U) last = 7U;
  draw_title(offset, "系统菜单");
  for (row = first; row < last; ++row) {
    draw_list_row(offset, row_y(UI_HOME, row, selected), home_display_items[row], row == selected);
  }
}

static const char *severity_text(UiAlarmSeverity severity)
{
  if (severity == UI_ALARM_CRITICAL) return "报警";
  if (severity == UI_ALARM_WARNING) return "预警";
  return "安全";
}

static uint16_t severity_color(UiAlarmSeverity severity)
{
  if (severity == UI_ALARM_CRITICAL) return UI_COLOR_DANGER;
  if (severity == UI_ALARM_WARNING) return UI_COLOR_WARNING;
  return LCD_GREEN;
}

static void draw_overview_body(int16_t offset, const UiSnapshot *snapshot)
{
  char value[24];
  const uint8_t active = popcount8(snapshot->alarm_sources);
  const uint8_t warning = (snapshot->alarm_severity == UI_ALARM_WARNING) ? active : 0U;
  const uint8_t alarm = (snapshot->alarm_severity == UI_ALARM_CRITICAL) ? active : 0U;
  ST7735_FillRect(offset + 8, 35, 112, 22, UI_COLOR_PANEL);
  draw_text((int16_t)(offset + 48), 38, severity_text(snapshot->alarm_severity),
            severity_color(snapshot->alarm_severity), UI_COLOR_PANEL);
  (void)snprintf(value, sizeof(value), "OK %u", (unsigned int)(8U - active));
  ST7735_DrawString(offset + 10, 66, value, LCD_GREEN, UI_COLOR_BACKGROUND);
  (void)snprintf(value, sizeof(value), "WARN %u", (unsigned int)warning);
  ST7735_DrawString(offset + 10, 82, value, UI_COLOR_WARNING, UI_COLOR_BACKGROUND);
  (void)snprintf(value, sizeof(value), "ALARM %u", (unsigned int)alarm);
  ST7735_DrawString(offset + 10, 98, value, UI_COLOR_DANGER, UI_COLOR_BACKGROUND);
}

static void draw_overview(int16_t offset, const UiSnapshot *snapshot)
{
  draw_title(offset, "安全总览");
  draw_overview_body(offset, snapshot);
}

static uint16_t reading_color(const UiReading *reading)
{
  return (reading->quality == UI_QUALITY_VALID) ? LCD_WHITE : UI_COLOR_MUTED;
}

static uint16_t fan_color(const UiFanSnapshot *fan)
{
  return (fan->quality == UI_QUALITY_VALID) ? LCD_WHITE : UI_COLOR_MUTED;
}

static void draw_monitor_metric(int16_t offset, uint8_t category, uint8_t metric,
                                const UiSnapshot *snapshot)
{
  char value[32];
  char line[40];
  const int16_t y = (int16_t)(52 + metric * 16U);
  uint16_t color = LCD_WHITE;
  line[0] = '\0';
  if (category == 0U) {
    const UiReading *reading = (metric == 0U) ? &snapshot->temperature_centi_c
                                              : &snapshot->humidity_centi_rh;
    format_reading(value, sizeof(value), reading, 100, metric == 0U ? "C" : "%");
    (void)snprintf(line, sizeof(line), "%s %s", metric == 0U ? "TEMP" : "HUM", value);
    color = reading_color(reading);
  } else if (category == 1U) {
    const UiReading *reading;
    const char *name;
    int32_t scale = 1;
    if (metric == 0U) { reading = &snapshot->oxygen_milli_percent; name = "O2"; scale = 1000; }
    else if (metric == 1U) { reading = &snapshot->methane_ppm; name = "CH4"; }
    else if (metric == 2U) { reading = &snapshot->carbon_monoxide_ppm; name = "CO"; }
    else { reading = &snapshot->smoke; name = "SMOKE"; }
    format_reading(value, sizeof(value), reading, scale, metric == 0U ? "%" : "");
    (void)snprintf(line, sizeof(line), "%s %s", name, value);
    color = reading_color(reading);
  } else if (category == 2U) {
    const UiReading *reading = (metric == 0U) ? &snapshot->water_level_raw : &snapshot->flame;
    format_reading(value, sizeof(value), reading, 1, "");
    (void)snprintf(line, sizeof(line), "%s %s", metric == 0U ? "LEVEL" : "FLAME", value);
    color = reading_color(reading);
  } else {
    const uint8_t fan_index = (metric >= 2U) ? 1U : 0U;
    const UiFanSnapshot *fan = &snapshot->fans[fan_index];
    if (fan->quality == UI_QUALITY_UNKNOWN) {
      (void)snprintf(line, sizeof(line), "F%u --", (unsigned int)(fan_index + 1U));
    } else if ((metric & 1U) == 0U) {
      (void)snprintf(line, sizeof(line), "F%u T%u%% R%lu", (unsigned int)(fan_index + 1U),
                     (unsigned int)fan->target_duty_percent, (unsigned long)fan->actual_rpm);
    } else {
      (void)snprintf(line, sizeof(line), "%uV %umA %s", (unsigned int)(fan->voltage_mv / 1000U),
                     (unsigned int)fan->current_ma, fan->running ? "RUN" : "STOP");
    }
    color = fan_color(fan);
  }
  ST7735_FillRect(offset + 9, y, 115, 14, UI_COLOR_BACKGROUND);
  ST7735_DrawString(offset + 10, y + 2, line, color, UI_COLOR_BACKGROUND);
}

static uint8_t monitor_metric_count(uint8_t category)
{
  if (category == 0U || category == 2U) return 2U;
  return 4U;
}

static void draw_monitor_detail(int16_t offset, uint8_t selected, const UiSnapshot *snapshot)
{
  static const char *const categories[] = {"环境", "气体", "积水火情", "风机供电"};
  uint8_t metric;
  ST7735_FillRect(offset + 2, UI_ROWS_TOP, 3, 78, UI_COLOR_BORDER);
  ST7735_FillRect(offset + 2, UI_ROWS_TOP + selected * UI_ROW_HEIGHT, 3, 14, UI_COLOR_ACCENT);
  draw_text((int16_t)(offset + 10), UI_ROWS_TOP, categories[selected], LCD_WHITE, UI_COLOR_BACKGROUND);
  for (metric = 0U; metric < monitor_metric_count(selected); ++metric) {
    draw_monitor_metric(offset, selected, metric, snapshot);
  }
}

static void draw_monitor(int16_t offset, uint8_t selected, const UiSnapshot *snapshot)
{
  draw_title(offset, "分类监测");
  draw_monitor_detail(offset, selected, snapshot);
}

static void draw_alert_body(int16_t offset, const UiSnapshot *snapshot)
{
  char sources[24];
  ST7735_FillRect(offset + 8, 38, 112, 34, UI_COLOR_PANEL);
  draw_text((int16_t)(offset + 48), 40, severity_text(snapshot->alarm_severity),
            severity_color(snapshot->alarm_severity), UI_COLOR_PANEL);
  (void)snprintf(sources, sizeof(sources), "SOURCES %08lX", (unsigned long)snapshot->alarm_sources);
  ST7735_DrawString(offset + 8, 82, sources, UI_COLOR_MUTED, UI_COLOR_BACKGROUND);
}

static void draw_alerts(int16_t offset, const UiSnapshot *snapshot)
{
  draw_title(offset, "报警中心");
  draw_alert_body(offset, snapshot);
}

static void draw_fan_row(int16_t offset, uint8_t row, const UiSnapshot *snapshot, uint8_t selected)
{
  char label[24];
  const int16_t y = (int16_t)(UI_ROWS_TOP + row * UI_ROW_HEIGHT);
  if (row == 0U || row == 3U) {
    const uint8_t fan_index = (row == 0U) ? 0U : 1U;
    const uint16_t fill = selected ? 0x2145U : UI_COLOR_PANEL;
    ST7735_FillRect(offset + 8, y, 116, UI_ROW_HEIGHT - 2, fill);
    if (selected) ST7735_FillRect(offset + 2, y, 3, UI_ROW_HEIGHT - 2, UI_COLOR_ACCENT);
    (void)snprintf(label, sizeof(label), "F%u %s RUN/STOP",
                   (unsigned int)(fan_index + 1U), snapshot->fans[fan_index].running ? "ON" : "OFF");
    ST7735_DrawString(offset + 12, y + 1, label, selected ? LCD_WHITE : UI_COLOR_MUTED, fill);
    ST7735_DrawString(offset + 12, y + 9, "30 60 100%", selected ? LCD_WHITE : UI_COLOR_MUTED, fill);
    return;
  } else if (row == 1U) {
    (void)snprintf(label, sizeof(label), "两台联动启动");
  } else {
    (void)snprintf(label, sizeof(label), "全部停止");
  }
  draw_list_row(offset, y, label, selected);
}

static void draw_fans(int16_t offset, uint8_t selected, const UiSnapshot *snapshot)
{
  uint8_t row;
  draw_title(offset, "风机控制");
  for (row = 0U; row < 4U; ++row) draw_fan_row(offset, row, snapshot, row == selected);
}

static void draw_light_row(int16_t offset, uint8_t row, uint8_t selected, const UiSnapshot *snapshot)
{
  char label[24];
  static const int16_t y[] = {34, 60, 86};
  const uint16_t fill = selected ? 0x2145U : UI_COLOR_PANEL;
  const uint16_t color = selected ? LCD_WHITE : UI_COLOR_MUTED;
  ST7735_FillRect(offset + 8, y[row], 116, 24, fill);
  if (selected) ST7735_FillRect(offset + 2, y[row], 3, 24, UI_COLOR_ACCENT);
  if (row == 0U) {
    (void)snprintf(label, sizeof(label), "L%u OFF W G Y",
                   (unsigned int)snapshot->actuators.led_mode);
    ST7735_DrawString(offset + 12, y[row] + 1, label, color, fill);
    ST7735_DrawString(offset + 12, y[row] + 11, "R B BRTH FLASH", color, fill);
  } else if (row == 1U) {
    (void)snprintf(label, sizeof(label), "L%u 25 50 75",
                   (unsigned int)snapshot->actuators.led_brightness_percent);
    ST7735_DrawString(offset + 12, y[row] + 1, label, color, fill);
    ST7735_DrawString(offset + 12, y[row] + 11, "100 BUZZ TEST", color, fill);
  } else {
    (void)snprintf(label, sizeof(label), "BUZZ %s MUTE",
                   snapshot->actuators.buzzer_muted ? "MUTED" : "ON");
    ST7735_DrawString(offset + 12, y[row] + 1, label, color, fill);
    ST7735_DrawString(offset + 12, y[row] + 11, "RESTORE ALARM", color, fill);
  }
}

static void draw_light_sound(int16_t offset, uint8_t selected, const UiSnapshot *snapshot)
{
  uint8_t row;
  draw_title(offset, "灯带与蜂鸣器");
  for (row = 0U; row < 3U; ++row) draw_light_row(offset, row, row == selected, snapshot);
}

static void draw_network_rows(int16_t offset, const UiSnapshot *snapshot)
{
  static const char *const labels[] = {"NODE-A", "GATEWAY", "IOTDA", "MQTT"};
  const uint8_t online[] = {
    snapshot->connectivity.node_a_online, snapshot->connectivity.gateway_online,
    snapshot->connectivity.iotda_online, snapshot->connectivity.mqtt_online,
  };
  uint8_t row;
  for (row = 0U; row < 4U; ++row) {
    char text[24];
    (void)snprintf(text, sizeof(text), "%s %s", labels[row], online[row] ? "ONLINE" : "OFFLINE");
    draw_list_row(offset, (int16_t)(UI_ROWS_TOP + row * UI_ROW_HEIGHT), text, 0U);
  }
}

static void draw_network(int16_t offset, const UiSnapshot *snapshot)
{
  draw_title(offset, "通信状态");
  draw_network_rows(offset, snapshot);
}

static void draw_settings_row(int16_t offset, uint8_t row, uint8_t selected)
{
  draw_list_row(offset, row == 0U ? 42 : 70,
                row == 0U ? "显示 128x128 18MHz" : "摇杆 ADC 200Hz", selected);
}

static void draw_settings(int16_t offset, uint8_t selected)
{
  draw_title(offset, "系统设置");
  draw_settings_row(offset, 0U, selected == 0U);
  draw_settings_row(offset, 1U, selected == 1U);
}

static void draw_page(UiPage page, uint8_t selected, const UiSnapshot *snapshot, int16_t offset)
{
  switch (page) {
    case UI_HOME: draw_home(offset, selected); break;
    case UI_OVERVIEW: draw_overview(offset, snapshot); break;
    case UI_MONITOR: draw_monitor(offset, selected, snapshot); break;
    case UI_ALERTS: draw_alerts(offset, snapshot); break;
    case UI_FANS: draw_fans(offset, selected, snapshot); break;
    case UI_LIGHT_SOUND: draw_light_sound(offset, selected, snapshot); break;
    case UI_NETWORK: draw_network(offset, snapshot); break;
    case UI_SETTINGS: draw_settings(offset, selected); break;
    default: break;
  }
}

static void draw_page_frame(const UiState *state, const UiSnapshot *snapshot, int16_t offset);

static void redraw_selection_rows(const UiState *state, const UiSnapshot *snapshot,
                                  uint8_t old_row, int16_t animated_y)
{
  const uint8_t new_row = state->selected_row;
  const int16_t target_y = row_y(state->page, new_row, new_row);
  const int16_t bar_height = selection_bar_height(state->page);
  if (state->page == UI_HOME) {
    const uint8_t old_first = (old_row > 3U) ? (uint8_t)(old_row - 3U) : 0U;
    const uint8_t new_first = (new_row > 3U) ? (uint8_t)(new_row - 3U) : 0U;
    if (old_first != new_first) {
      draw_page_frame(state, snapshot, 0);
      return;
    }
    draw_list_row(0, row_y(UI_HOME, old_row, new_row), home_display_items[old_row], 0U);
    draw_list_row(0, target_y, home_display_items[new_row], 1U);
  } else if (state->page == UI_MONITOR) {
    ST7735_FillRect(2, UI_ROWS_TOP, 122, UI_FOOTER_TOP - UI_ROWS_TOP, UI_COLOR_BACKGROUND);
    draw_monitor_detail(0, new_row, snapshot);
  } else if (state->page == UI_FANS) {
    draw_fan_row(0, old_row, snapshot, 0U);
    draw_fan_row(0, new_row, snapshot, 1U);
  } else if (state->page == UI_LIGHT_SOUND) {
    draw_light_row(0, old_row, 0U, snapshot);
    draw_light_row(0, new_row, 1U, snapshot);
  } else if (state->page == UI_SETTINGS) {
    draw_settings_row(0, old_row, 0U);
    draw_settings_row(0, new_row, 1U);
  }
  if (animated_y != target_y) {
    ST7735_FillRect(2, target_y, 3, bar_height, UI_COLOR_BACKGROUND);
    ST7735_FillRect(2, animated_y, 3, bar_height, UI_COLOR_ACCENT);
  }
}

static void draw_page_frame(const UiState *state, const UiSnapshot *snapshot, int16_t offset)
{
  ST7735_FillRect(0, UI_PAGE_TOP, LCD_WIDTH, UI_FOOTER_TOP - UI_PAGE_TOP, UI_COLOR_BACKGROUND);
  if (renderer.page_animation && offset > 0) {
    draw_page(renderer.previous_page, renderer.previous_row, &renderer.snapshot,
              (int16_t)(offset - LCD_WIDTH));
  }
  draw_page(state->page, state->selected_row, snapshot, offset);
}

static const char *confirmation_action_name(uint8_t action)
{
  switch ((UiAction)action) {
    case UI_ACTION_FANS_BOTH_START: return "BOTH FANS";
    case UI_ACTION_FANS_ALL_STOP: return "ALL STOP";
    case UI_ACTION_BUZZER_MUTE: return "BUZZ MUTE";
    default: return "COMMAND";
  }
}

static void draw_command_overlay(const UiState *state)
{
  const char *status = "";
  uint16_t color = UI_COLOR_ACCENT;
  if (state->dialog == UI_DIALOG_CONFIRM) {
    status = "确认操作";
    color = UI_COLOR_WARNING;
  } else {
    switch (state->command_phase) {
      case UI_CMD_SENDING: status = "发送中"; break;
      case UI_CMD_ACCEPTED: status = "已执行"; color = LCD_GREEN; break;
      case UI_CMD_REJECTED: status = "失败"; color = UI_COLOR_DANGER; break;
      case UI_CMD_TIMEOUT: status = "失败 TIMEOUT"; color = UI_COLOR_DANGER; break;
      default: return;
    }
  }
  ST7735_FillRect(8, 39, 112, 54, UI_COLOR_BORDER);
  ST7735_FillRect(10, 41, 108, 50, UI_COLOR_PANEL);
  draw_text((int16_t)((LCD_WIDTH - text_width(status)) / 2), 49, status, color, UI_COLOR_PANEL);
  if (state->dialog == UI_DIALOG_CONFIRM) {
    const char *action = confirmation_action_name(state->pending_action);
    const int16_t action_x = (int16_t)((LCD_WIDTH - (int16_t)(strlen(action) * 8U)) / 2);
    ST7735_DrawString(action_x, 68, action, LCD_WHITE, UI_COLOR_PANEL);
    ST7735_DrawString(20, 80, "<CANCEL  OK>", UI_COLOR_MUTED, UI_COLOR_PANEL);
  }
}

static uint8_t overlay_visible(const UiState *state)
{
  return (state->dialog == UI_DIALOG_CONFIRM) || (state->command_phase == UI_CMD_SENDING) ||
         (state->command_phase == UI_CMD_ACCEPTED) || (state->command_phase == UI_CMD_REJECTED) ||
         (state->command_phase == UI_CMD_TIMEOUT);
}

static void redraw_header_delta(const UiSnapshot *snapshot, uint8_t redraw_time, uint8_t redraw_mqtt)
{
  char time_field[6];
  if (redraw_mqtt) {
    invalidate((UiDirtyRect){56, 0, 30, UI_HEADER_HEIGHT});
    ST7735_FillRect(56, 0, 30, UI_HEADER_HEIGHT, UI_COLOR_HEADER);
    ST7735_DrawString(61, 2, snapshot->connectivity.mqtt_online ? "M+" : "M-",
                      snapshot->connectivity.mqtt_online ? LCD_GREEN : UI_COLOR_DANGER,
                      UI_COLOR_HEADER);
  }
  if (redraw_time) {
    invalidate((UiDirtyRect){86, 0, 42, UI_HEADER_HEIGHT});
    ST7735_FillRect(86, 0, 42, UI_HEADER_HEIGHT, UI_COLOR_HEADER);
    format_clock(snapshot, time_field);
    ST7735_DrawString(88, 2, time_field, LCD_WHITE, UI_COLOR_HEADER);
  }
}

static uint8_t redraw_snapshot_delta(const UiState *state, const UiSnapshot *snapshot)
{
  uint8_t redrawn = 0U;
  uint8_t row;
  if (state->page == UI_OVERVIEW) {
    if ((snapshot->alarm_severity != renderer.snapshot.alarm_severity) ||
        (snapshot->alarm_sources != renderer.snapshot.alarm_sources)) {
      invalidate((UiDirtyRect){0, UI_ROWS_TOP, LCD_WIDTH, UI_FOOTER_TOP - UI_ROWS_TOP});
      ST7735_FillRect(0, UI_ROWS_TOP, LCD_WIDTH, UI_FOOTER_TOP - UI_ROWS_TOP, UI_COLOR_BACKGROUND);
      draw_overview_body(0, snapshot);
      redrawn = 1U;
    }
  } else if (state->page == UI_MONITOR) {
    uint8_t changed[4] = {0U, 0U, 0U, 0U};
    const uint8_t selected = state->selected_row;
    if (selected == 0U) {
      changed[0] = reading_changed(&snapshot->temperature_centi_c, &renderer.snapshot.temperature_centi_c);
      changed[1] = reading_changed(&snapshot->humidity_centi_rh, &renderer.snapshot.humidity_centi_rh);
    } else if (selected == 1U) {
      changed[0] = reading_changed(&snapshot->oxygen_milli_percent, &renderer.snapshot.oxygen_milli_percent);
      changed[1] = reading_changed(&snapshot->methane_ppm, &renderer.snapshot.methane_ppm);
      changed[2] = reading_changed(&snapshot->carbon_monoxide_ppm, &renderer.snapshot.carbon_monoxide_ppm);
      changed[3] = reading_changed(&snapshot->smoke, &renderer.snapshot.smoke);
    } else if (selected == 2U) {
      changed[0] = reading_changed(&snapshot->water_level_raw, &renderer.snapshot.water_level_raw);
      changed[1] = reading_changed(&snapshot->flame, &renderer.snapshot.flame);
    } else {
      changed[0] = (snapshot->fans[0].target_duty_percent != renderer.snapshot.fans[0].target_duty_percent) ||
                   (snapshot->fans[0].actual_rpm != renderer.snapshot.fans[0].actual_rpm) ||
                   (snapshot->fans[0].quality != renderer.snapshot.fans[0].quality);
      changed[1] = (snapshot->fans[0].voltage_mv != renderer.snapshot.fans[0].voltage_mv) ||
                   (snapshot->fans[0].current_ma != renderer.snapshot.fans[0].current_ma) ||
                   (snapshot->fans[0].running != renderer.snapshot.fans[0].running) ||
                   (snapshot->fans[0].quality != renderer.snapshot.fans[0].quality);
      changed[2] = (snapshot->fans[1].target_duty_percent != renderer.snapshot.fans[1].target_duty_percent) ||
                   (snapshot->fans[1].actual_rpm != renderer.snapshot.fans[1].actual_rpm) ||
                   (snapshot->fans[1].quality != renderer.snapshot.fans[1].quality);
      changed[3] = (snapshot->fans[1].voltage_mv != renderer.snapshot.fans[1].voltage_mv) ||
                   (snapshot->fans[1].current_ma != renderer.snapshot.fans[1].current_ma) ||
                   (snapshot->fans[1].running != renderer.snapshot.fans[1].running) ||
                   (snapshot->fans[1].quality != renderer.snapshot.fans[1].quality);
    }
    for (row = 0U; row < monitor_metric_count(selected); ++row) {
      if (changed[row]) {
        invalidate((UiDirtyRect){9, (int16_t)(52 + row * 16U), 115, 14});
        draw_monitor_metric(0, selected, row, snapshot);
        redrawn = 1U;
      }
    }
  } else if (state->page == UI_ALERTS) {
    if ((snapshot->alarm_severity != renderer.snapshot.alarm_severity) ||
        (snapshot->alarm_sources != renderer.snapshot.alarm_sources)) {
      invalidate((UiDirtyRect){8, 38, 112, 60});
      ST7735_FillRect(8, 38, 112, 60, UI_COLOR_BACKGROUND);
      draw_alert_body(0, snapshot);
      redrawn = 1U;
    }
  } else if (state->page == UI_FANS) {
    for (row = 0U; row < 2U; ++row) {
      if (fan_changed(&snapshot->fans[row], &renderer.snapshot.fans[row])) {
        const uint8_t display_row = (row == 0U) ? 0U : 3U;
        invalidate((UiDirtyRect){2, (int16_t)(UI_ROWS_TOP + display_row * UI_ROW_HEIGHT),
                                 122, UI_ROW_HEIGHT - 2});
        draw_fan_row(0, display_row, snapshot, display_row == state->selected_row);
        redrawn = 1U;
      }
    }
  } else if (state->page == UI_LIGHT_SOUND) {
    if ((snapshot->actuators.led_mode != renderer.snapshot.actuators.led_mode) ||
        (snapshot->actuators.led_brightness_percent != renderer.snapshot.actuators.led_brightness_percent) ||
        (snapshot->actuators.buzzer_on != renderer.snapshot.actuators.buzzer_on) ||
        (snapshot->actuators.buzzer_muted != renderer.snapshot.actuators.buzzer_muted)) {
      invalidate((UiDirtyRect){2, UI_ROWS_TOP, 122, 72});
      ST7735_FillRect(2, UI_ROWS_TOP, 122, 72, UI_COLOR_BACKGROUND);
      for (row = 0U; row < 3U; ++row) {
        draw_light_row(0, row, row == state->selected_row, snapshot);
      }
      redrawn = 1U;
    }
  } else if (state->page == UI_NETWORK) {
    if ((snapshot->connectivity.node_a_online != renderer.snapshot.connectivity.node_a_online) ||
        (snapshot->connectivity.gateway_online != renderer.snapshot.connectivity.gateway_online) ||
        (snapshot->connectivity.iotda_online != renderer.snapshot.connectivity.iotda_online)) {
      invalidate((UiDirtyRect){2, UI_ROWS_TOP, 122, 78});
      ST7735_FillRect(2, UI_ROWS_TOP, 122, 78, UI_COLOR_BACKGROUND);
      draw_network_rows(0, snapshot);
      redrawn = 1U;
    }
  }
  return redrawn;
}

static uint8_t time_reached(uint32_t now_ms, uint32_t deadline_ms)
{
  return (int32_t)(now_ms - deadline_ms) >= 0;
}

static void start_cadence(uint32_t now_ms)
{
  renderer.next_animation_ms = now_ms + 16U;
  renderer.cadence_remainder = 40U;
}

static void advance_cadence(uint32_t now_ms)
{
  do {
    uint32_t interval = 16U;
    renderer.cadence_remainder = (uint8_t)(renderer.cadence_remainder + 40U);
    if (renderer.cadence_remainder >= 60U) {
      renderer.cadence_remainder = (uint8_t)(renderer.cadence_remainder - 60U);
      ++interval;
    }
    renderer.next_animation_ms += interval;
  } while (time_reached(now_ms, renderer.next_animation_ms));
}

void UiRenderer_Init(void)
{
  (void)memset(&renderer, 0, sizeof(renderer));
}

void UiRenderer_GetStats(UiRendererStats *stats)
{
  if (stats != NULL) *stats = renderer.stats;
}

uint8_t UiRenderer_RenderFrame(const UiState *state, const UiSnapshot *snapshot, uint32_t now_ms)
{
  uint8_t frame_needed = 0U;
  uint8_t header_time;
  uint8_t header_mqtt;
  uint8_t overlay_delta;
  uint8_t footer_delta;
  uint8_t snapshot_delta_drawn = 0U;
  if ((state == NULL) || (snapshot == NULL)) return 0U;

  if (!renderer.initialized) {
    begin_frame();
    invalidate((UiDirtyRect){0, 0, LCD_WIDTH, LCD_HEIGHT});
    ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, UI_COLOR_BACKGROUND);
    draw_header(snapshot);
    draw_page(state->page, state->selected_row, snapshot, 0);
    draw_footer(state);
    if (overlay_visible(state)) draw_command_overlay(state);
    renderer.state = *state;
    renderer.snapshot = *snapshot;
    renderer.selection_drawn_y = row_y(state->page, state->selected_row, state->selected_row);
    renderer.stats.last_selection_y = renderer.selection_drawn_y;
    renderer.stats.last_page_offset = 0;
    renderer.initialized = 1U;
    ++renderer.stats.rendered_frames;
    return 1U;
  }

  if (state->page != renderer.state.page) {
    renderer.page_animation = 1U;
    renderer.selection_animation = 0U;
    renderer.previous_page = renderer.state.page;
    renderer.previous_row = renderer.state.selected_row;
    renderer.animation_start_ms = state->animation_start_ms;
    renderer.animation_duration_ms = UI_RENDERER_PAGE_MS;
    start_cadence(now_ms);
    frame_needed = 1U;
  } else if (state->selected_row != renderer.state.selected_row) {
    renderer.selection_animation = 1U;
    renderer.page_animation = 0U;
    renderer.selection_from_y = renderer.selection_drawn_y;
    renderer.selection_to_y = row_y(state->page, state->selected_row, state->selected_row);
    renderer.animation_start_ms = state->animation_start_ms;
    renderer.animation_duration_ms = UI_RENDERER_SELECTION_MS;
    start_cadence(now_ms);
    frame_needed = 1U;
  } else if ((renderer.page_animation || renderer.selection_animation) &&
             (time_reached(now_ms, renderer.next_animation_ms) ||
              time_reached(now_ms, renderer.animation_start_ms + renderer.animation_duration_ms))) {
    frame_needed = 1U;
    advance_cadence(now_ms);
  }

  header_time = time_changed(snapshot, &renderer.snapshot);
  header_mqtt = snapshot->connectivity.mqtt_online != renderer.snapshot.connectivity.mqtt_online;
  overlay_delta = (state->dialog != renderer.state.dialog) ||
                  (state->command_phase != renderer.state.command_phase) ||
                  (state->pending_action != renderer.state.pending_action) ||
                  (state->pending_value != renderer.state.pending_value);
  footer_delta = (state->page != renderer.state.page) ||
                 (state->control.mqtt_online != renderer.state.control.mqtt_online) ||
                 (state->control.safety_locked != renderer.state.control.safety_locked);
  if (header_time || header_mqtt || overlay_delta || footer_delta) frame_needed = 1U;

  if (!frame_needed) {
    /* Snapshot fields not visible on this page do not schedule a transfer. */
    begin_frame();
    snapshot_delta_drawn = redraw_snapshot_delta(state, snapshot);
    if (snapshot_delta_drawn) frame_needed = 1U;
    if (!frame_needed) {
      ++renderer.stats.skipped_frames;
      renderer.snapshot = *snapshot;
      return 0U;
    }
  } else {
    begin_frame();
  }

  if (state->page != renderer.state.page || renderer.page_animation) {
    const int16_t offset = UiRenderer_InterpolatePixels(128, 0, renderer.animation_start_ms,
                                                        renderer.animation_duration_ms, now_ms);
    invalidate((UiDirtyRect){0, UI_PAGE_TOP, LCD_WIDTH, UI_FOOTER_TOP - UI_PAGE_TOP});
    draw_page_frame(state, snapshot, offset);
    renderer.stats.last_page_offset = offset;
    if (offset == 0) renderer.page_animation = 0U;
  } else if (state->selected_row != renderer.state.selected_row || renderer.selection_animation) {
    const int16_t next_y = UiRenderer_InterpolatePixels(renderer.selection_from_y,
                                                        renderer.selection_to_y,
                                                        renderer.animation_start_ms,
                                                        renderer.animation_duration_ms, now_ms);
    if (state->selected_row != renderer.state.selected_row) {
      const int16_t old_y = row_y(state->page, renderer.state.selected_row, renderer.state.selected_row);
      const int16_t new_y = row_y(state->page, state->selected_row, state->selected_row);
      const int16_t bar_height = selection_bar_height(state->page);
      const uint8_t home_scroll = (state->page == UI_HOME) &&
        (((renderer.state.selected_row > 3U) ? (renderer.state.selected_row - 3U) : 0U) !=
         ((state->selected_row > 3U) ? (state->selected_row - 3U) : 0U));
      if (state->page == UI_MONITOR) {
        invalidate((UiDirtyRect){2, UI_ROWS_TOP, 122, UI_FOOTER_TOP - UI_ROWS_TOP});
      } else if (home_scroll) {
        invalidate((UiDirtyRect){0, UI_PAGE_TOP, LCD_WIDTH, UI_FOOTER_TOP - UI_PAGE_TOP});
      } else {
        invalidate((UiDirtyRect){2, old_y, 122, bar_height});
        invalidate((UiDirtyRect){2, new_y, 122, bar_height});
      }
      redraw_selection_rows(state, snapshot, renderer.state.selected_row, next_y);
    } else {
      const int16_t bar_height = selection_bar_height(state->page);
      invalidate((UiDirtyRect){2, renderer.selection_drawn_y, 3, bar_height});
      invalidate((UiDirtyRect){2, next_y, 3, bar_height});
      ST7735_FillRect(2, renderer.selection_drawn_y, 3, bar_height, UI_COLOR_BACKGROUND);
      ST7735_FillRect(2, next_y, 3, bar_height, UI_COLOR_ACCENT);
    }
    renderer.selection_drawn_y = next_y;
    renderer.stats.last_selection_y = next_y;
    if (next_y == renderer.selection_to_y) renderer.selection_animation = 0U;
  } else if (!snapshot_delta_drawn) {
    (void)redraw_snapshot_delta(state, snapshot);
  }

  redraw_header_delta(snapshot, header_time, header_mqtt);
  if (footer_delta) {
    invalidate((UiDirtyRect){0, UI_FOOTER_TOP, LCD_WIDTH, LCD_HEIGHT - UI_FOOTER_TOP});
    draw_footer(state);
  }
  if (overlay_delta) {
    if (overlay_visible(state)) {
      invalidate((UiDirtyRect){8, 39, 112, 54});
      draw_command_overlay(state);
    } else {
      invalidate((UiDirtyRect){0, UI_PAGE_TOP, LCD_WIDTH, UI_FOOTER_TOP - UI_PAGE_TOP});
      draw_page_frame(state, snapshot, 0);
    }
  } else if (overlay_visible(state)) {
    draw_command_overlay(state);
  }

  renderer.state = *state;
  renderer.snapshot = *snapshot;
  ++renderer.stats.rendered_frames;
  return 1U;
}
