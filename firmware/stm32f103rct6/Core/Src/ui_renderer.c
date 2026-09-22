#include "ui_renderer.h"

#include "kk_ui_catalog.h"
#include "kk_ui_motion.h"

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
  uint8_t force_full_redraw;
} UiRendererContext;

static UiRendererContext renderer;

static const char *const kLedModeNames[] = {
  "OFF", "WHITE", "GREEN", "YELLOW", "RED", "BLUE", "2 METEOR", "RED ALT",
  "FIRE", "ENERGY", "POLICE", "AURORA", "LASER", "LIGHTNING", "STARS", "CONVERGE",
};

static const char *led_mode_name(uint8_t mode)
{
  return kLedModeNames[(mode < 16U) ? mode : 0U];
}
static uint8_t popcount8(uint32_t value);

static uint8_t page_row_count(UiPage page)
{
  const KkUiPageDescriptor *descriptor = KK_UI_CatalogPage(page);
  return (descriptor != NULL) ? descriptor->row_count : 1U;
}

static const char *selected_name(UiPage page, uint8_t row)
{
  return KK_UI_CatalogSelectedName(page, row);
}

static const char *dialog_name(UiDialog dialog)
{
  return (dialog == UI_DIALOG_CONFIRM) ? "confirm" : "none";
}

static uint32_t warning_sources(const UiSnapshot *snapshot)
{
  const uint32_t explicit_sources = snapshot->warning_sources & UI_ALARM_SOURCE_MASK;
  if ((explicit_sources != 0U) || (snapshot->critical_sources != 0U)) return explicit_sources;
  return (snapshot->alarm_severity == UI_ALARM_WARNING)
           ? (snapshot->alarm_sources & UI_ALARM_SOURCE_MASK) : 0U;
}

static uint32_t critical_sources(const UiSnapshot *snapshot)
{
  const uint32_t explicit_sources = snapshot->critical_sources & UI_ALARM_SOURCE_MASK;
  if ((explicit_sources != 0U) || (snapshot->warning_sources != 0U)) return explicit_sources;
  return (snapshot->alarm_severity == UI_ALARM_CRITICAL)
           ? (snapshot->alarm_sources & UI_ALARM_SOURCE_MASK) : 0U;
}

static uint32_t warning_only_sources(const UiSnapshot *snapshot)
{
  return warning_sources(snapshot) & ~critical_sources(snapshot) & UI_ALARM_SOURCE_MASK;
}

static UiAlarmSeverity effective_severity(const UiSnapshot *snapshot)
{
  if (critical_sources(snapshot) != 0U) return UI_ALARM_CRITICAL;
  if (warning_sources(snapshot) != 0U) return UI_ALARM_WARNING;
  return snapshot->alarm_severity;
}

static const char *selected_option_name(const UiState *state)
{
  if ((state->page == UI_FANS) && (state->selected_row == 0U)) return "fan1_duty";
  if ((state->page == UI_FANS) && (state->selected_row == 3U)) return "fan2_duty";
  if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 0U)) return "led_mode";
  if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 1U)) return "brightness";
  if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 2U)) return "buzzer";
  return "none";
}

static uint8_t selected_option_value(const UiState *state)
{
  if ((state->page == UI_FANS) && (state->selected_row == 0U)) return state->fan_duty_option[0];
  if ((state->page == UI_FANS) && (state->selected_row == 3U)) return state->fan_duty_option[1];
  if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 0U)) {
    return (uint8_t)state->led_mode_option;
  }
  if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 1U)) {
    return state->led_brightness_option;
  }
  if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 2U)) {
    return (uint8_t)state->buzzer_option;
  }
  return 0U;
}

uint8_t UiRenderer_PageFromName(const char *name, UiPage *page)
{
  uint8_t index;
  if ((name == NULL) || (page == NULL) || (name[0] == '\0')) return 0U;
  for (index = 0U; index <= (uint8_t)UI_SETTINGS; ++index) {
    const KkUiPageDescriptor *descriptor = KK_UI_CatalogPage((UiPage)index);
    if ((descriptor != NULL) && (strcmp(name, descriptor->name) == 0)) {
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

static uint8_t stale_reading_count(const UiSnapshot *snapshot)
{
  const UiReading *readings = &snapshot->temperature_centi_c;
  uint8_t count = 0U;
  size_t index;
  for (index = 0U; index < 8U; ++index) {
    if (readings[index].quality == UI_QUALITY_STALE) ++count;
  }
  if (snapshot->fans[0].quality == UI_QUALITY_STALE) ++count;
  if (snapshot->fans[1].quality == UI_QUALITY_STALE) ++count;
  return count;
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
                    "#UI page=%s row=%u dialog=%s command=%s title=%s rows=%u selected=%s time=%s mqtt=%s option=%s value=%u editing=%u warning=%u critical=%u stale=%u",
                    (KK_UI_CatalogPage(state->page) != NULL)
                      ? KK_UI_CatalogPage(state->page)->name : "unknown",
                    (unsigned int)state->selected_row, dialog_name(state->dialog),
                    command_name(state->command_phase),
                    (KK_UI_CatalogPage(state->page) != NULL)
                      ? KK_UI_CatalogPage(state->page)->diagnostic_title : "unknown",
                    (unsigned int)page_row_count(state->page), selected_name(state->page, state->selected_row),
                    time_field, (snapshot->connectivity.mqtt == UI_LINK_ONLINE) ? "online" : ((snapshot->connectivity.mqtt == UI_LINK_OFFLINE) ? "offline" : "unknown"),
                    selected_option_name(state), (unsigned int)selected_option_value(state),
                    (unsigned int)state->option_editing,
                    (unsigned int)popcount8(warning_only_sources(snapshot)),
                    (unsigned int)popcount8(critical_sources(snapshot)),
                    (unsigned int)stale_reading_count(snapshot));
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
  if ((int32_t)(now_ms - start_ms) < 0) return from;
  elapsed = now_ms - start_ms;
  if ((duration_ms == 0U) || (elapsed >= duration_ms)) return to;
  return (int16_t)KK_UI_MotionLerpQ12(from, to,
                                      KK_UI_MotionEaseQ12(elapsed, duration_ms));
}

/* Page slides need an even visual velocity.  The selection easing curve is
 * intentionally front-loaded, but on the physical ST7735 that made a page
 * transition cover most of its distance before the second rendered frame and
 * therefore look like an instantaneous cut. */
static int16_t page_slide_offset(uint32_t start_ms, uint32_t duration_ms,
                                 uint32_t now_ms)
{
  uint32_t elapsed;
  if ((int32_t)(now_ms - start_ms) < 0) return LCD_WIDTH;
  elapsed = now_ms - start_ms;
  if ((duration_ms == 0U) || (elapsed >= duration_ms)) return 0;
  return (int16_t)(LCD_WIDTH -
      (int32_t)(((uint64_t)LCD_WIDTH * elapsed) / duration_ms));
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
  ST7735_BeginFrame();
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

static uint8_t fan_control_row_changed(const UiFanSnapshot *left, const UiFanSnapshot *right)
{
  return left->running != right->running;
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
  if (quality == UI_QUALITY_MISSING) return " OFF";
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
  if (reading->quality == UI_QUALITY_MISSING) {
    (void)snprintf(output, size, "OFF");
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

/* The header's MQTT indicator, drawn from the same tri-state the NETWORK page
 * spells out.  An unobserved link reads as unknown rather than as a confirmed
 * failure: OFFLINE is only shown when the ESP observed it, and UNKNOWN gets the
 * same muted treatment the network rows give an unobserved link. */
static const char *mqtt_indicator(uint8_t status)
{
  if (status == (uint8_t)UI_LINK_ONLINE) return "M+";
  if (status == (uint8_t)UI_LINK_OFFLINE) return "M-";
  return "M?";
}

static uint16_t mqtt_indicator_color(uint8_t status)
{
  if (status == (uint8_t)UI_LINK_ONLINE) return LCD_GREEN;
  if (status == (uint8_t)UI_LINK_OFFLINE) return UI_COLOR_DANGER;
  return UI_COLOR_MUTED;
}

static void draw_header(const UiSnapshot *snapshot)
{
  char time_field[6];
  ST7735_FillRect(0, 0, LCD_WIDTH, UI_HEADER_HEIGHT, UI_COLOR_HEADER);
  ST7735_DrawString(2, 2, "CTRL-02", LCD_WHITE, UI_COLOR_HEADER);
  ST7735_DrawString(61, 2, mqtt_indicator(snapshot->connectivity.mqtt),
                    mqtt_indicator_color(snapshot->connectivity.mqtt), UI_COLOR_HEADER);
  format_clock(snapshot, time_field);
  ST7735_DrawString(88, 2, time_field, LCD_WHITE, UI_COLOR_HEADER);
}

static void draw_footer(const UiState *state)
{
  const char *hint = (state->page == UI_HOME) ? "UP/DN  OK>" : "<BACK  OK";
  uint16_t color = UI_COLOR_MUTED;
  ST7735_FillRect(0, UI_FOOTER_TOP, LCD_WIDTH, LCD_HEIGHT - UI_FOOTER_TOP, UI_COLOR_HEADER);
  if ((state->control.safety_locked != 0U) &&
      ((state->page == UI_FANS) || (state->page == UI_LIGHT_SOUND))) {
    hint = "SAFETY LOCKED";
    color = UI_COLOR_DANGER;
  } else if ((state->control.mqtt_online == 0U) &&
      ((state->page == UI_FANS) || (state->page == UI_LIGHT_SOUND))) {
    hint = "MQTT LOCKED";
    color = UI_COLOR_WARNING;
  }
  ST7735_DrawString(20, UI_FOOTER_TOP + 2, hint, color, UI_COLOR_HEADER);
}

static uint8_t controls_disabled(const UiState *state)
{
  return ((state->control.mqtt_online == 0U) || (state->control.safety_locked != 0U)) &&
         ((state->page == UI_FANS) || (state->page == UI_LIGHT_SOUND));
}

static uint16_t selection_bar_color(const UiState *state)
{
  if (controls_disabled(state)) return UI_COLOR_DANGER;
  if (state->option_editing) return UI_COLOR_WARNING;
  return UI_COLOR_ACCENT;
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

static void draw_control_list_row(int16_t offset, int16_t y, const char *label,
                                  uint8_t selected, const UiState *state)
{
  const uint8_t disabled = controls_disabled(state);
  const uint16_t fill = (selected && !disabled) ? 0x2145U : UI_COLOR_PANEL;
  const uint16_t color = disabled ? UI_COLOR_MUTED : (selected ? LCD_WHITE : UI_COLOR_MUTED);
  ST7735_FillRect(offset + 8, y, 116, UI_ROW_HEIGHT - 2, fill);
  if (selected) {
    ST7735_FillRect(offset + 2, y, 3, UI_ROW_HEIGHT - 2, selection_bar_color(state));
  }
  draw_text((int16_t)(offset + 12), (int16_t)(y + 1), label, color, fill);
}

static uint16_t home_accent(uint8_t selected)
{
  static const uint16_t colors[] = {
    LCD_GREEN, UI_COLOR_ACCENT, UI_COLOR_DANGER, 0x7DFFU,
    UI_COLOR_WARNING, 0x5D7FU, 0xC69FU,
  };
  return (selected < 7U) ? colors[selected] : UI_COLOR_ACCENT;
}

static void draw_home_icon(int16_t x, int16_t y, uint8_t selected, uint16_t color)
{
  ST7735_FillRect(x, y, 26, 26, UI_COLOR_BACKGROUND);
  ST7735_FillRect(x, y, 26, 2, color);
  ST7735_FillRect(x, y + 24, 26, 2, color);
  ST7735_FillRect(x, y, 2, 26, color);
  ST7735_FillRect(x + 24, y, 2, 26, color);
  switch (selected) {
    case 0U: /* safety shield */
      ST7735_FillRect(x + 7, y + 6, 12, 3, color);
      ST7735_FillRect(x + 9, y + 9, 8, 8, color);
      ST7735_FillRect(x + 11, y + 17, 4, 4, color);
      break;
    case 1U: /* monitoring bars */
      ST7735_FillRect(x + 6, y + 15, 3, 6, color);
      ST7735_FillRect(x + 11, y + 10, 3, 11, color);
      ST7735_FillRect(x + 16, y + 6, 3, 15, color);
      break;
    case 2U: /* alarm */
      ST7735_FillRect(x + 11, y + 5, 4, 11, color);
      ST7735_FillRect(x + 11, y + 19, 4, 3, color);
      break;
    case 3U: /* fan */
      ST7735_FillRect(x + 11, y + 5, 4, 16, color);
      ST7735_FillRect(x + 5, y + 11, 16, 4, color);
      break;
    case 4U: /* light and sound */
      ST7735_FillRect(x + 9, y + 7, 8, 10, color);
      ST7735_FillRect(x + 7, y + 10, 2, 4, color);
      ST7735_FillRect(x + 17, y + 10, 2, 4, color);
      ST7735_FillRect(x + 11, y + 19, 4, 2, color);
      break;
    case 5U: /* network */
      ST7735_FillRect(x + 6, y + 17, 3, 4, color);
      ST7735_FillRect(x + 11, y + 12, 3, 9, color);
      ST7735_FillRect(x + 16, y + 7, 3, 14, color);
      break;
    default: /* settings */
      ST7735_FillRect(x + 6, y + 6, 5, 5, color);
      ST7735_FillRect(x + 15, y + 6, 5, 5, color);
      ST7735_FillRect(x + 6, y + 15, 5, 5, color);
      ST7735_FillRect(x + 15, y + 15, 5, 5, color);
      break;
  }
}

static void draw_home_heading(int16_t offset)
{
  ST7735_DrawString(offset + 3, UI_PAGE_TOP + 2, "KK", UI_COLOR_ACCENT,
                    UI_COLOR_BACKGROUND);
  draw_title(offset, "系统菜单");
}

static void draw_home_card(int16_t offset, uint8_t selected)
{
  char index_text[8];
  uint8_t dot;
  const uint16_t accent = home_accent(selected);
  const char *label = KK_UI_CatalogHomeLabel(selected);
  const int16_t label_x = (int16_t)(offset + (LCD_WIDTH - text_width(label)) / 2);

  ST7735_FillRect(offset + 8, 34, 112, 70, UI_COLOR_PANEL);
  ST7735_FillRect(offset + 8, 34, 112, 2, accent);
  ST7735_FillRect(offset + 8, 102, 112, 2, accent);
  ST7735_FillRect(offset + 8, 34, 2, 70, accent);
  ST7735_FillRect(offset + 118, 34, 2, 70, accent);
  draw_home_icon((int16_t)(offset + 51), 39, selected, accent);
  draw_text(label_x, 68, label, LCD_WHITE, UI_COLOR_PANEL);
  (void)snprintf(index_text, sizeof(index_text), "%02u/07", (unsigned int)(selected + 1U));
  ST7735_DrawString(offset + 44, 88, index_text, accent, UI_COLOR_PANEL);
  for (dot = 0U; dot < 7U; ++dot) {
    ST7735_FillRect(offset + 43 + (int16_t)dot * 6, 107, 3, 3,
                    (dot == selected) ? accent : UI_COLOR_BORDER);
  }
}

static void draw_home(int16_t offset, uint8_t selected)
{
  draw_home_heading(offset);
  draw_home_card(offset, selected);
}

static int8_t home_slide_direction(uint8_t old_row, uint8_t new_row)
{
  if ((old_row == 6U) && (new_row == 0U)) return 1;
  if ((old_row == 0U) && (new_row == 6U)) return -1;
  return (new_row > old_row) ? 1 : -1;
}

static void draw_home_transition(uint8_t old_row, uint8_t new_row, uint16_t progress)
{
  const int8_t direction = home_slide_direction(old_row, new_row);
  const int16_t travel = (int16_t)(((int32_t)LCD_WIDTH * progress) /
                                   (int32_t)KK_UI_MOTION_Q12_ONE);
  const int16_t old_offset = (int16_t)(-direction * travel);
  const int16_t new_offset = (int16_t)(direction * (LCD_WIDTH - travel));
  draw_home_heading(0);
  draw_home_card(old_offset, old_row);
  draw_home_card(new_offset, new_row);
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

static uint8_t overview_ok_count(const UiSnapshot *snapshot)
{
  return (uint8_t)(8U - popcount8(warning_sources(snapshot) | critical_sources(snapshot)));
}

static void draw_overview_status(int16_t offset, const UiSnapshot *snapshot)
{
  const UiAlarmSeverity severity = effective_severity(snapshot);
  ST7735_FillRect(offset + 8, 35, 112, 22, UI_COLOR_PANEL);
  draw_text((int16_t)(offset + 48), 38, severity_text(severity),
            severity_color(severity), UI_COLOR_PANEL);
}

static void draw_overview_count(int16_t offset, uint8_t row, const UiSnapshot *snapshot)
{
  char value[24];
  uint8_t count;
  const char *label;
  uint16_t color;
  const int16_t y = (int16_t)(66 + row * 16U);
  if (row == 0U) {
    label = "OK";
    count = overview_ok_count(snapshot);
    color = LCD_GREEN;
  } else if (row == 1U) {
    label = "WARN";
    count = popcount8(warning_only_sources(snapshot));
    color = UI_COLOR_WARNING;
  } else {
    label = "ALARM";
    count = popcount8(critical_sources(snapshot));
    color = UI_COLOR_DANGER;
  }
  ST7735_FillRect(offset + 10, y, 100, 8, UI_COLOR_BACKGROUND);
  (void)snprintf(value, sizeof(value), "%s %u", label, (unsigned int)count);
  ST7735_DrawString(offset + 10, y, value, color, UI_COLOR_BACKGROUND);
}

static void draw_overview_body(int16_t offset, const UiSnapshot *snapshot)
{
  uint8_t row;
  draw_overview_status(offset, snapshot);
  for (row = 0U; row < 3U; ++row) draw_overview_count(offset, row, snapshot);
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

static const ScreenSensorReading *find_sensor(const UiSnapshot *snapshot, const char *asset_code)
{
  size_t i;
  for (i = 0U; i < snapshot->sensor_count; ++i) {
    if (strcmp(snapshot->sensors[i].asset_code, asset_code) == 0) {
      return &snapshot->sensors[i];
    }
  }
  return NULL;
}

static void draw_monitor_metric(int16_t offset, uint8_t category, uint8_t metric,
                                const UiSnapshot *snapshot)
{
  char value[32];
  char line[40];
  const int16_t y = (int16_t)(52 + metric * 16U);
  uint16_t color = LCD_WHITE;
  line[0] = '\0';

  if ((snapshot->sensor_count > 0U) && (category < 3U)) {
    static const char *const env_assets[] = {"SHT-01", "SHT-02", "SHT-03", "SHT-04"};
    static const char *const gas_assets[] = {"MQ4-01", "O2-01", "CO-01", "MQ4-02"};
    static const char *const water_fire_assets[] = {"FLAME-01", "FLAME-04", "LEVEL-01", "MQ2-01"};
    const char *target_asset = NULL;
    if (category == 0U && metric < 4U) target_asset = env_assets[metric];
    else if (category == 1U && metric < 4U) target_asset = gas_assets[metric];
    else if (category == 2U && metric < 4U) target_asset = water_fire_assets[metric];

    if (target_asset != NULL) {
      const ScreenSensorReading *s = find_sensor(snapshot, target_asset);
      if (s == NULL) {
        (void)snprintf(line, sizeof(line), "%s --", target_asset);
        color = UI_COLOR_MUTED;
      } else if (s->quality == UI_QUALITY_MISSING) {
        (void)snprintf(line, sizeof(line), "%s OFF", s->asset_code);
        color = UI_COLOR_MUTED;
      } else if (s->quality == UI_QUALITY_UNKNOWN) {
        (void)snprintf(line, sizeof(line), "%s --", s->asset_code);
        color = UI_COLOR_MUTED;
      } else {
        if (s->kind == SCREEN_SENSOR_KIND_FLAME || s->kind == SCREEN_SENSOR_KIND_LEVEL || s->kind == SCREEN_SENSOR_KIND_MQ2) {
          (void)snprintf(line, sizeof(line), "%s %s", s->asset_code, (s->alarm != 0U) ? "ALARM" : "OK");
          color = (s->alarm != 0U) ? UI_COLOR_DANGER : LCD_GREEN;
        } else if (s->scale > 1) {
          long val = (long)s->value;
          long abs_val = (val < 0L) ? -val : val;
          (void)snprintf(line, sizeof(line), "%s %s%ld.%02ld", s->asset_code,
                         (val < 0L) ? "-" : "", abs_val / s->scale, abs_val % s->scale);
          color = (s->alarm != 0U) ? UI_COLOR_DANGER : LCD_WHITE;
        } else {
          (void)snprintf(line, sizeof(line), "%s %ld", s->asset_code, (long)s->value);
          color = (s->alarm != 0U) ? UI_COLOR_DANGER : LCD_WHITE;
        }
      }
      ST7735_FillRect(offset + 9, y, 115, 14, UI_COLOR_BACKGROUND);
      ST7735_DrawString(offset + 10, y + 2, line, color, UI_COLOR_BACKGROUND);
      return;
    }
  }

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

static void draw_alert_status(int16_t offset, const UiSnapshot *snapshot)
{
  const UiAlarmSeverity severity = effective_severity(snapshot);
  ST7735_FillRect(offset + 8, 38, 112, 26, UI_COLOR_PANEL);
  draw_text((int16_t)(offset + 48), 40, severity_text(severity),
            severity_color(severity), UI_COLOR_PANEL);
}

static void draw_alert_sources(int16_t offset, const UiSnapshot *snapshot)
{
  static const char *const names[] = {
    "TEMP", "HUM", "O2", "CH4", "CO", "SMOKE", "WATER", "FLAME",
  };
  uint32_t critical = critical_sources(snapshot);
  uint32_t warning = warning_only_sources(snapshot);
  const uint8_t total_sources = popcount8(critical | warning);
  const uint8_t detail_limit = (total_sources > 4U) ? 3U : 4U;
  uint8_t source;
  uint8_t row = 0U;
  size_t i;
  ST7735_FillRect(offset + 8, 70, 112, 42, UI_COLOR_BACKGROUND);

  /* Specific sensor alarms from catalog */
  for (i = 0U; (i < snapshot->sensor_count) && (row < detail_limit); ++i) {
    if (snapshot->sensors[i].alarm != 0U) {
      char line[32];
      (void)snprintf(line, sizeof(line), "%s CRITICAL", snapshot->sensors[i].asset_code);
      ST7735_DrawString(offset + 8, (int)(72 + row * 10U), line,
                        UI_COLOR_DANGER, UI_COLOR_BACKGROUND);
      ++row;
    }
  }
  if (row == 0U && snapshot->alarm_label[0] != '\0') {
    char line[32];
    (void)snprintf(line, sizeof(line), "%s CRITICAL", snapshot->alarm_label);
    ST7735_DrawString(offset + 8, 72, line, UI_COLOR_DANGER, UI_COLOR_BACKGROUND);
    row = 1U;
  }
  if (row == 0U) {
    for (source = 0U; (source < 8U) && (row < detail_limit); ++source) {
      char line[24];
      const uint32_t bit = 1UL << source;
      if ((critical & bit) == 0U) continue;
      (void)snprintf(line, sizeof(line), "%s CRITICAL", names[source]);
      ST7735_DrawString(offset + 8, (int)(72 + row * 10U), line,
                        UI_COLOR_DANGER, UI_COLOR_BACKGROUND);
      ++row;
    }
    for (source = 0U; (source < 8U) && (row < detail_limit); ++source) {
      char line[24];
      const uint32_t bit = 1UL << source;
      if ((warning & bit) == 0U) continue;
      (void)snprintf(line, sizeof(line), "%s WARNING", names[source]);
      ST7735_DrawString(offset + 8, (int)(72 + row * 10U), line,
                        UI_COLOR_WARNING, UI_COLOR_BACKGROUND);
      ++row;
    }
    if (row < total_sources) {
      char line[24];
      (void)snprintf(line, sizeof(line), "+%u MORE", (unsigned int)(total_sources - row));
      ST7735_DrawString(offset + 8, (int)(72 + row * 10U), line,
                        UI_COLOR_WARNING, UI_COLOR_BACKGROUND);
    }
  }
  if (row == 0U) {
    ST7735_DrawString(offset + 8, 82, "NO ACTIVE ALARM", LCD_GREEN, UI_COLOR_BACKGROUND);
  }
}

static void draw_alert_body(int16_t offset, const UiSnapshot *snapshot)
{
  draw_alert_status(offset, snapshot);
  draw_alert_sources(offset, snapshot);
}

static void draw_alerts(int16_t offset, const UiSnapshot *snapshot)
{
  draw_title(offset, "报警中心");
  draw_alert_body(offset, snapshot);
}

static void draw_fan_row(int16_t offset, uint8_t row, const UiState *state,
                         const UiSnapshot *snapshot, uint8_t selected)
{
  char label[24];
  const int16_t y = (int16_t)(UI_ROWS_TOP + row * UI_ROW_HEIGHT);
  const uint8_t disabled = controls_disabled(state);
  if (row == 0U || row == 3U) {
    const uint8_t fan_index = (row == 0U) ? 0U : 1U;
    const uint16_t fill = (selected && !disabled) ? 0x2145U : UI_COLOR_PANEL;
    const uint16_t color = disabled ? UI_COLOR_MUTED : (selected ? LCD_WHITE : UI_COLOR_MUTED);
    ST7735_FillRect(offset + 8, y, 116, UI_ROW_HEIGHT - 2, fill);
    if (selected) {
      ST7735_FillRect(offset + 2, y, 3, UI_ROW_HEIGHT - 2, selection_bar_color(state));
    }
    (void)snprintf(label, sizeof(label), "F%u %s %u%%",
                   (unsigned int)(fan_index + 1U), snapshot->fans[fan_index].running ? "ON" : "OFF",
                   (unsigned int)state->fan_duty_option[fan_index]);
    ST7735_DrawString(offset + 12, y + 1, label, color, fill);
    ST7735_DrawString(offset + 12, y + 9, "0 30 60 100", color, fill);
    return;
  } else if (row == 1U) {
    (void)snprintf(label, sizeof(label), "两台联动启动");
  } else {
    (void)snprintf(label, sizeof(label), "全部停止");
  }
  draw_control_list_row(offset, y, label, selected, state);
}

static void draw_fans(int16_t offset, const UiState *state, const UiSnapshot *snapshot)
{
  uint8_t row;
  draw_title(offset, "风机控制");
  for (row = 0U; row < 4U; ++row) {
    draw_fan_row(offset, row, state, snapshot, row == state->selected_row);
  }
}

static void draw_light_row(int16_t offset, uint8_t row, uint8_t selected,
                           const UiState *state, const UiSnapshot *snapshot)
{
  char label[24];
  static const char *const buzzer_actions[] = {"TEST", "MUTE", "RESTORE"};
  static const int16_t y[] = {34, 60, 86};
  const uint8_t disabled = controls_disabled(state);
  const uint16_t fill = (selected && !disabled) ? 0x2145U : UI_COLOR_PANEL;
  const uint16_t color = disabled ? UI_COLOR_MUTED : (selected ? LCD_WHITE : UI_COLOR_MUTED);
  ST7735_FillRect(offset + 8, y[row], 116, 24, fill);
  if (selected) {
    ST7735_FillRect(offset + 2, y[row], 3, 24, selection_bar_color(state));
  }
  if (row == 0U) {
    const uint8_t mode = ((uint8_t)state->led_mode_option < 16U) ? (uint8_t)state->led_mode_option : 0U;
    (void)snprintf(label, sizeof(label), "MODE %s", led_mode_name(mode));
    ST7735_DrawString(offset + 12, y[row] + 1, label, color, fill);
    (void)snprintf(label, sizeof(label), "NOW %u  0..15",
                   (unsigned int)snapshot->actuators.led_mode);
    ST7735_DrawString(offset + 12, y[row] + 11, label, color, fill);
  } else if (row == 1U) {
    (void)snprintf(label, sizeof(label), "BRIGHT %u%%",
                   (unsigned int)state->led_brightness_option);
    ST7735_DrawString(offset + 12, y[row] + 1, label, color, fill);
    (void)snprintf(label, sizeof(label), "NOW %u 25..100",
                   (unsigned int)snapshot->actuators.led_brightness_percent);
    ST7735_DrawString(offset + 12, y[row] + 11, label, color, fill);
  } else {
    const uint8_t action = ((uint8_t)state->buzzer_option < 3U) ? (uint8_t)state->buzzer_option : 0U;
    (void)snprintf(label, sizeof(label), "BUZZ %s", buzzer_actions[action]);
    ST7735_DrawString(offset + 12, y[row] + 1, label, color, fill);
    (void)snprintf(label, sizeof(label), "NOW %s/%s", snapshot->actuators.buzzer_on ? "ON" : "OFF",
                   snapshot->actuators.buzzer_muted ? "MUTED" : "READY");
    ST7735_DrawString(offset + 12, y[row] + 11, label, color, fill);
  }
}

static void draw_light_sound(int16_t offset, const UiState *state, const UiSnapshot *snapshot)
{
  uint8_t row;
  draw_title(offset, "灯带与蜂鸣器");
  for (row = 0U; row < 3U; ++row) {
    draw_light_row(offset, row, row == state->selected_row, state, snapshot);
  }
}

static uint8_t network_row_status(const UiSnapshot *snapshot, uint8_t row)
{
  if (row == 0U) return (uint8_t)snapshot->connectivity.node_a;
  if (row == 1U) return (uint8_t)snapshot->connectivity.gateway;
  if (row == 2U) return (uint8_t)snapshot->connectivity.iotda;
  return (uint8_t)snapshot->connectivity.mqtt;
}

static void draw_network_row(int16_t offset, uint8_t row, const UiSnapshot *snapshot)
{
  static const char *const labels[] = {"NODE-A", "GATEWAY", "IOTDA", "MQTT"};
  static const char *const status_text[] = {"UNKNOWN", "ONLINE", "OFFLINE"};
  char text[24];
  const int16_t y = (int16_t)(UI_ROWS_TOP + row * UI_ROW_HEIGHT);
  const uint8_t status = network_row_status(snapshot, row);
  const char *label = (status <= (uint8_t)UI_LINK_OFFLINE)
                          ? status_text[status]
                          : status_text[0];
  /* Only an observed link is worth a green row.  An unobserved one has to read
   * as unknown: the IoTDA gateway and cloud session have no status source on
   * this screen, and claiming OFFLINE would be a known falsehood. */
  (void)snprintf(text, sizeof(text), "%s %s", labels[row], label);
  ST7735_FillRect(offset + 8, y, 116, UI_ROW_HEIGHT - 2, UI_COLOR_PANEL);
  ST7735_DrawString(offset + 12, y + 5, text,
                    (status == (uint8_t)UI_LINK_ONLINE) ? LCD_GREEN
                                                        : UI_COLOR_MUTED,
                    UI_COLOR_PANEL);
}

static void draw_network_rows(int16_t offset, const UiSnapshot *snapshot)
{
  uint8_t row;
  for (row = 0U; row < 4U; ++row) {
    draw_network_row(offset, row, snapshot);
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

static void draw_page(const UiState *state, const UiSnapshot *snapshot, int16_t offset)
{
  switch (state->page) {
    case UI_HOME: draw_home(offset, state->selected_row); break;
    case UI_OVERVIEW: draw_overview(offset, snapshot); break;
    case UI_MONITOR: draw_monitor(offset, state->selected_row, snapshot); break;
    case UI_ALERTS: draw_alerts(offset, snapshot); break;
    case UI_FANS: draw_fans(offset, state, snapshot); break;
    case UI_LIGHT_SOUND: draw_light_sound(offset, state, snapshot); break;
    case UI_NETWORK: draw_network(offset, snapshot); break;
    case UI_SETTINGS: draw_settings(offset, state->selected_row); break;
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
    draw_list_row(0, row_y(UI_HOME, old_row, new_row), KK_UI_CatalogHomeLabel(old_row), 0U);
    draw_list_row(0, target_y, KK_UI_CatalogHomeLabel(new_row), 1U);
  } else if (state->page == UI_MONITOR) {
    ST7735_FillRect(2, UI_ROWS_TOP, 122, UI_FOOTER_TOP - UI_ROWS_TOP, UI_COLOR_BACKGROUND);
    draw_monitor_detail(0, new_row, snapshot);
  } else if (state->page == UI_FANS) {
    draw_fan_row(0, old_row, state, snapshot, 0U);
    draw_fan_row(0, new_row, state, snapshot, 1U);
  } else if (state->page == UI_LIGHT_SOUND) {
    draw_light_row(0, old_row, 0U, state, snapshot);
    draw_light_row(0, new_row, 1U, state, snapshot);
  } else if (state->page == UI_SETTINGS) {
    draw_settings_row(0, old_row, 0U);
    draw_settings_row(0, new_row, 1U);
  }
  if (animated_y != target_y) {
    ST7735_FillRect(2, target_y, 3, bar_height, UI_COLOR_BACKGROUND);
    ST7735_FillRect(2, animated_y, 3, bar_height, selection_bar_color(state));
  }
}

static void draw_page_frame(const UiState *state, const UiSnapshot *snapshot, int16_t offset)
{
  ST7735_FillRect(0, UI_PAGE_TOP, LCD_WIDTH, UI_FOOTER_TOP - UI_PAGE_TOP, UI_COLOR_BACKGROUND);
  if (renderer.page_animation && offset > 0) {
    UiState previous_state = renderer.state;
    previous_state.page = renderer.previous_page;
    previous_state.selected_row = renderer.previous_row;
    draw_page(&previous_state, &renderer.snapshot, (int16_t)(offset - LCD_WIDTH));
  }
  draw_page(state, snapshot, offset);
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

static void draw_option_overlay(const UiState *state)
{
  static const char *const buzzer_actions[] = {"TEST", "MUTE", "RESTORE"};
  const char *title = "SELECT";
  const char *value_text = "";
  char value[20];
  int16_t value_x;

  if (state->page == UI_FANS) {
    const uint8_t fan = (state->selected_row == 0U) ? 0U : 1U;
    title = (fan == 0U) ? "FAN 1 SPEED" : "FAN 2 SPEED";
    (void)snprintf(value, sizeof(value), "%u%%", (unsigned int)state->fan_duty_option[fan]);
    value_text = value;
  } else if (state->page == UI_LIGHT_SOUND && state->selected_row == 0U) {
    const uint8_t mode = ((uint8_t)state->led_mode_option < 16U) ?
        (uint8_t)state->led_mode_option : 0U;
    title = "LED EFFECT";
    value_text = led_mode_name(mode);
  } else if (state->page == UI_LIGHT_SOUND && state->selected_row == 1U) {
    title = "LED BRIGHT";
    (void)snprintf(value, sizeof(value), "%u%%",
                   (unsigned int)state->led_brightness_option);
    value_text = value;
  } else if (state->page == UI_LIGHT_SOUND && state->selected_row == 2U) {
    const uint8_t action = ((uint8_t)state->buzzer_option < 3U) ?
        (uint8_t)state->buzzer_option : 0U;
    title = "BUZZER";
    value_text = buzzer_actions[action];
  }

  ST7735_FillRect(5, 22, 118, 94, UI_COLOR_BORDER);
  ST7735_FillRect(7, 24, 114, 90, UI_COLOR_BACKGROUND);
  draw_text((int16_t)((LCD_WIDTH - text_width(title)) / 2), 29,
            title, LCD_WHITE, UI_COLOR_BACKGROUND);
  ST7735_FillRect(12, 41, 104, 2, LCD_WHITE);
  ST7735_FillRect(17, 49, 78, 31, LCD_WHITE);
  value_x = (int16_t)(17 + (78 - (int16_t)(strlen(value_text) * 8U)) / 2);
  if (value_x < 19) value_x = 19;
  ST7735_DrawString(value_x, 61, value_text, LCD_BLACK, LCD_WHITE);
  ST7735_DrawString(104, 50, "^", LCD_WHITE, UI_COLOR_BACKGROUND);
  ST7735_DrawString(104, 69, "v", LCD_WHITE, UI_COLOR_BACKGROUND);
  ST7735_DrawString(14, 94, "< BACK", UI_COLOR_MUTED, UI_COLOR_BACKGROUND);
  ST7735_DrawString(82, 94, "OK >", UI_COLOR_ACCENT, UI_COLOR_BACKGROUND);
}

static void draw_active_overlay(const UiState *state)
{
  if (state->option_editing) draw_option_overlay(state);
  else draw_command_overlay(state);
}

static uint8_t command_feedback_visible(const UiState *state)
{
  const UiAction action = (UiAction)state->pending_action;
  const uint8_t critical = (action == UI_ACTION_FANS_BOTH_START) ||
                           (action == UI_ACTION_FANS_ALL_STOP) ||
                           (action == UI_ACTION_BUZZER_MUTE);
  if ((state->command_phase == UI_CMD_REJECTED) ||
      (state->command_phase == UI_CMD_TIMEOUT)) return 1U;
  return critical && ((state->command_phase == UI_CMD_SENDING) ||
                      (state->command_phase == UI_CMD_ACCEPTED));
}

static uint8_t overlay_visible(const UiState *state)
{
  return state->option_editing || (state->dialog == UI_DIALOG_CONFIRM) ||
         command_feedback_visible(state);
}

static void redraw_header_delta(const UiSnapshot *snapshot, uint8_t redraw_time, uint8_t redraw_mqtt)
{
  char time_field[6];
  if (redraw_mqtt) {
    invalidate((UiDirtyRect){56, 0, 30, UI_HEADER_HEIGHT});
    ST7735_FillRect(56, 0, 30, UI_HEADER_HEIGHT, UI_COLOR_HEADER);
    ST7735_DrawString(61, 2, mqtt_indicator(snapshot->connectivity.mqtt),
                      mqtt_indicator_color(snapshot->connectivity.mqtt), UI_COLOR_HEADER);
  }
  if (redraw_time) {
    invalidate((UiDirtyRect){86, 0, 42, UI_HEADER_HEIGHT});
    ST7735_FillRect(86, 0, 42, UI_HEADER_HEIGHT, UI_COLOR_HEADER);
    format_clock(snapshot, time_field);
    ST7735_DrawString(88, 2, time_field, LCD_WHITE, UI_COLOR_HEADER);
  }
}

static uint8_t redraw_snapshot_delta(const UiState *state, const UiSnapshot *snapshot,
                                     uint8_t already_drawn_rows)
{
  uint8_t redrawn = 0U;
  uint8_t row;
  if (state->page == UI_OVERVIEW) {
    if (effective_severity(snapshot) != effective_severity(&renderer.snapshot)) {
      invalidate((UiDirtyRect){8, 35, 112, 22});
      draw_overview_status(0, snapshot);
      redrawn = 1U;
    }
    if (overview_ok_count(snapshot) != overview_ok_count(&renderer.snapshot)) {
      invalidate((UiDirtyRect){10, 66, 100, 8});
      draw_overview_count(0, 0U, snapshot);
      redrawn = 1U;
    }
    if (popcount8(warning_only_sources(snapshot)) !=
        popcount8(warning_only_sources(&renderer.snapshot))) {
      invalidate((UiDirtyRect){10, 82, 100, 8});
      draw_overview_count(0, 1U, snapshot);
      redrawn = 1U;
    }
    if (popcount8(critical_sources(snapshot)) != popcount8(critical_sources(&renderer.snapshot))) {
      invalidate((UiDirtyRect){10, 98, 100, 8});
      draw_overview_count(0, 2U, snapshot);
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
      if (changed[row] && ((already_drawn_rows & (1U << row)) == 0U)) {
        invalidate((UiDirtyRect){9, (int16_t)(52 + row * 16U), 115, 14});
        draw_monitor_metric(0, selected, row, snapshot);
        redrawn = 1U;
      }
    }
  } else if (state->page == UI_ALERTS) {
    if (effective_severity(snapshot) != effective_severity(&renderer.snapshot)) {
      invalidate((UiDirtyRect){8, 38, 112, 26});
      draw_alert_status(0, snapshot);
      redrawn = 1U;
    }
    if ((warning_sources(snapshot) != warning_sources(&renderer.snapshot)) ||
        (critical_sources(snapshot) != critical_sources(&renderer.snapshot))) {
      invalidate((UiDirtyRect){8, 70, 112, 42});
      draw_alert_sources(0, snapshot);
      redrawn = 1U;
    }
  } else if (state->page == UI_FANS) {
    for (row = 0U; row < 2U; ++row) {
      if (fan_control_row_changed(&snapshot->fans[row], &renderer.snapshot.fans[row])) {
        const uint8_t display_row = (row == 0U) ? 0U : 3U;
        if ((already_drawn_rows & (1U << display_row)) != 0U) continue;
        invalidate((UiDirtyRect){2, (int16_t)(UI_ROWS_TOP + display_row * UI_ROW_HEIGHT),
                                 122, UI_ROW_HEIGHT - 2});
        draw_fan_row(0, display_row, state, snapshot, display_row == state->selected_row);
        redrawn = 1U;
      }
    }
  } else if (state->page == UI_LIGHT_SOUND) {
    if ((snapshot->actuators.led_mode != renderer.snapshot.actuators.led_mode) &&
        ((already_drawn_rows & 1U) == 0U)) {
      invalidate((UiDirtyRect){2, 34, 122, 24});
      draw_light_row(0, 0U, state->selected_row == 0U, state, snapshot);
      redrawn = 1U;
    }
    if ((snapshot->actuators.led_brightness_percent !=
         renderer.snapshot.actuators.led_brightness_percent) &&
        ((already_drawn_rows & 2U) == 0U)) {
      invalidate((UiDirtyRect){2, 60, 122, 24});
      draw_light_row(0, 1U, state->selected_row == 1U, state, snapshot);
      redrawn = 1U;
    }
    if (((snapshot->actuators.buzzer_on != renderer.snapshot.actuators.buzzer_on) ||
         (snapshot->actuators.buzzer_muted != renderer.snapshot.actuators.buzzer_muted)) &&
        ((already_drawn_rows & 4U) == 0U)) {
      invalidate((UiDirtyRect){2, 86, 122, 24});
      draw_light_row(0, 2U, state->selected_row == 2U, state, snapshot);
      redrawn = 1U;
    }
  } else if (state->page == UI_NETWORK) {
    for (row = 0U; row < 4U; ++row) {
      if (network_row_status(snapshot, row) != network_row_status(&renderer.snapshot, row)) {
        invalidate((UiDirtyRect){2, (int16_t)(UI_ROWS_TOP + row * UI_ROW_HEIGHT),
                                 122, UI_ROW_HEIGHT - 2});
        draw_network_row(0, row, snapshot);
        redrawn = 1U;
      }
    }
  }
  return redrawn;
}

static uint8_t option_state_changed(const UiState *state)
{
  return (state->option_editing != renderer.state.option_editing) ||
         (state->fan_duty_option[0] != renderer.state.fan_duty_option[0]) ||
         (state->fan_duty_option[1] != renderer.state.fan_duty_option[1]) ||
         (state->led_mode_option != renderer.state.led_mode_option) ||
         (state->led_brightness_option != renderer.state.led_brightness_option) ||
         (state->buzzer_option != renderer.state.buzzer_option);
}

static uint8_t redraw_option_delta(const UiState *state, const UiSnapshot *snapshot)
{
  uint8_t redrawn = 0U;
  if (state->page == UI_FANS) {
    if ((state->fan_duty_option[0] != renderer.state.fan_duty_option[0]) ||
        ((state->selected_row == 0U) &&
         (state->option_editing != renderer.state.option_editing))) {
      invalidate((UiDirtyRect){2, 34, 122, 18});
      draw_fan_row(0, 0U, state, snapshot, state->selected_row == 0U);
      redrawn |= 1U;
    }
    if ((state->fan_duty_option[1] != renderer.state.fan_duty_option[1]) ||
        ((state->selected_row == 3U) &&
         (state->option_editing != renderer.state.option_editing))) {
      invalidate((UiDirtyRect){2, 94, 122, 18});
      draw_fan_row(0, 3U, state, snapshot, state->selected_row == 3U);
      redrawn |= 8U;
    }
  } else if (state->page == UI_LIGHT_SOUND) {
    if ((state->led_mode_option != renderer.state.led_mode_option) ||
        ((state->selected_row == 0U) &&
         (state->option_editing != renderer.state.option_editing))) {
      invalidate((UiDirtyRect){2, 34, 122, 24});
      draw_light_row(0, 0U, state->selected_row == 0U, state, snapshot);
      redrawn |= 1U;
    }
    if ((state->led_brightness_option != renderer.state.led_brightness_option) ||
        ((state->selected_row == 1U) &&
         (state->option_editing != renderer.state.option_editing))) {
      invalidate((UiDirtyRect){2, 60, 122, 24});
      draw_light_row(0, 1U, state->selected_row == 1U, state, snapshot);
      redrawn |= 2U;
    }
    if ((state->buzzer_option != renderer.state.buzzer_option) ||
        ((state->selected_row == 2U) &&
         (state->option_editing != renderer.state.option_editing))) {
      invalidate((UiDirtyRect){2, 86, 122, 24});
      draw_light_row(0, 2U, state->selected_row == 2U, state, snapshot);
      redrawn |= 4U;
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
  uint8_t option_delta;
  uint8_t control_style_delta;
  uint8_t snapshot_delta_drawn = 0U;
  uint8_t already_drawn_rows = 0U;
  uint8_t page_content_current = 0U;
  UiRendererStats stats_before;
  if ((state == NULL) || (snapshot == NULL)) return 0U;
  stats_before = renderer.stats;

  if (!renderer.initialized) {
    begin_frame();
    invalidate((UiDirtyRect){0, 0, LCD_WIDTH, LCD_HEIGHT});
    ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, UI_COLOR_BACKGROUND);
    draw_header(snapshot);
    draw_page(state, snapshot, 0);
    draw_footer(state);
    if (overlay_visible(state)) draw_active_overlay(state);
    if (ST7735_FrameFailed()) {
      renderer.stats = stats_before;
      ++renderer.stats.failed_frames;
      renderer.force_full_redraw = 1U;
      return 0U;
    }
    renderer.state = *state;
    renderer.snapshot = *snapshot;
    renderer.selection_drawn_y = row_y(state->page, state->selected_row, state->selected_row);
    renderer.stats.last_selection_y = renderer.selection_drawn_y;
    renderer.stats.last_page_offset = 0;
    renderer.initialized = 1U;
    renderer.force_full_redraw = 0U;
    ++renderer.stats.rendered_frames;
    return 1U;
  }

  if (renderer.force_full_redraw) {
    begin_frame();
    invalidate((UiDirtyRect){0, 0, LCD_WIDTH, LCD_HEIGHT});
    ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, UI_COLOR_BACKGROUND);
    draw_header(snapshot);
    draw_page(state, snapshot, 0);
    draw_footer(state);
    if (overlay_visible(state)) draw_active_overlay(state);
    if (ST7735_FrameFailed()) {
      renderer.stats = stats_before;
      ++renderer.stats.failed_frames;
      renderer.force_full_redraw = 1U;
      return 0U;
    }
    renderer.state = *state;
    renderer.snapshot = *snapshot;
    renderer.selection_animation = 0U;
    renderer.page_animation = 0U;
    renderer.selection_drawn_y = row_y(state->page, state->selected_row, state->selected_row);
    renderer.stats.last_selection_y = renderer.selection_drawn_y;
    renderer.stats.last_page_offset = 0;
    renderer.force_full_redraw = 0U;
    ++renderer.stats.rendered_frames;
    return 1U;
  }

  if (state->page != renderer.state.page) {
    renderer.page_animation = 1U;
    renderer.selection_animation = 0U;
    renderer.previous_page = renderer.state.page;
    renderer.previous_row = renderer.state.selected_row;
    renderer.animation_start_ms = state->animation_start_ms;
    renderer.animation_duration_ms = state->animation_end_ms - state->animation_start_ms;
    if (renderer.animation_duration_ms == 0U)
      renderer.animation_duration_ms = UI_RENDERER_PAGE_MS;
    start_cadence(now_ms);
    frame_needed = 1U;
  } else if (state->selected_row != renderer.state.selected_row) {
    renderer.selection_animation = 1U;
    renderer.page_animation = 0U;
    renderer.previous_row = renderer.state.selected_row;
    renderer.selection_from_y = renderer.selection_drawn_y;
    renderer.selection_to_y = row_y(state->page, state->selected_row, state->selected_row);
    renderer.animation_start_ms = state->animation_start_ms;
    renderer.animation_duration_ms = state->animation_end_ms - state->animation_start_ms;
    if (renderer.animation_duration_ms == 0U)
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
  header_mqtt = snapshot->connectivity.mqtt != renderer.snapshot.connectivity.mqtt;
  overlay_delta = (state->dialog != renderer.state.dialog) ||
                  (state->option_editing != renderer.state.option_editing) ||
                  (command_feedback_visible(state) != command_feedback_visible(&renderer.state)) ||
                  ((command_feedback_visible(state) || command_feedback_visible(&renderer.state)) &&
                   ((state->command_phase != renderer.state.command_phase) ||
                    (state->pending_action != renderer.state.pending_action) ||
                    (state->pending_value != renderer.state.pending_value)));
  footer_delta = (state->page != renderer.state.page) ||
                 (state->control.mqtt_online != renderer.state.control.mqtt_online) ||
                 (state->control.safety_locked != renderer.state.control.safety_locked);
  option_delta = option_state_changed(state);
  control_style_delta = (state->page == renderer.state.page) &&
                        ((state->page == UI_FANS) || (state->page == UI_LIGHT_SOUND)) &&
                        (controls_disabled(state) != controls_disabled(&renderer.state));
  if (header_time || header_mqtt || overlay_delta || footer_delta || option_delta ||
      control_style_delta) frame_needed = 1U;

  if (!frame_needed) {
    /* Snapshot fields not visible on this page do not schedule a transfer. */
    begin_frame();
    snapshot_delta_drawn = redraw_snapshot_delta(state, snapshot, 0U);
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
    const int16_t offset = page_slide_offset(renderer.animation_start_ms,
                                             renderer.animation_duration_ms,
                                             now_ms);
    invalidate((UiDirtyRect){0, UI_PAGE_TOP, LCD_WIDTH, UI_FOOTER_TOP - UI_PAGE_TOP});
    draw_page_frame(state, snapshot, offset);
    page_content_current = 1U;
    renderer.stats.last_page_offset = offset;
    if (offset == 0) renderer.page_animation = 0U;
  } else if (state->selected_row != renderer.state.selected_row || renderer.selection_animation) {
    const int16_t next_y = UiRenderer_InterpolatePixels(renderer.selection_from_y,
                                                        renderer.selection_to_y,
                                                        renderer.animation_start_ms,
                                                        renderer.animation_duration_ms, now_ms);
    if (state->page == UI_HOME) {
      const uint32_t elapsed = now_ms - renderer.animation_start_ms;
      const uint16_t progress = KK_UI_MotionEaseQ12(elapsed, renderer.animation_duration_ms);
      invalidate((UiDirtyRect){0, UI_PAGE_TOP, LCD_WIDTH, UI_FOOTER_TOP - UI_PAGE_TOP});
      ST7735_FillRect(0, UI_PAGE_TOP, LCD_WIDTH, UI_FOOTER_TOP - UI_PAGE_TOP,
                      UI_COLOR_BACKGROUND);
      draw_home_transition(renderer.previous_row, state->selected_row, progress);
      page_content_current = 1U;
      renderer.selection_drawn_y = next_y;
      renderer.stats.last_selection_y = next_y;
      if (progress == KK_UI_MOTION_Q12_ONE) renderer.selection_animation = 0U;
    } else if (state->selected_row != renderer.state.selected_row) {
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
      if (state->page == UI_MONITOR) {
        page_content_current = 1U;
      } else if ((state->page == UI_FANS) || (state->page == UI_LIGHT_SOUND)) {
        already_drawn_rows = (uint8_t)((1U << renderer.state.selected_row) |
                                       (1U << state->selected_row));
      }
    } else {
      const int16_t bar_height = selection_bar_height(state->page);
      invalidate((UiDirtyRect){2, renderer.selection_drawn_y, 3, bar_height});
      invalidate((UiDirtyRect){2, next_y, 3, bar_height});
      ST7735_FillRect(2, renderer.selection_drawn_y, 3, bar_height, UI_COLOR_BACKGROUND);
      ST7735_FillRect(2, next_y, 3, bar_height, selection_bar_color(state));
    }
    if (state->page != UI_HOME) {
      renderer.selection_drawn_y = next_y;
      renderer.stats.last_selection_y = next_y;
      if (next_y == renderer.selection_to_y) renderer.selection_animation = 0U;
    }
  }

  if (control_style_delta && !page_content_current) {
    const int16_t height = (state->page == UI_FANS) ? 78 : 76;
    uint8_t row;
    invalidate((UiDirtyRect){2, UI_ROWS_TOP, 122, height});
    if (state->page == UI_FANS) {
      for (row = 0U; row < 4U; ++row) {
        draw_fan_row(0, row, state, snapshot, row == state->selected_row);
      }
    } else {
      for (row = 0U; row < 3U; ++row) {
        draw_light_row(0, row, row == state->selected_row, state, snapshot);
      }
    }
    page_content_current = 1U;
  } else if (option_delta && !page_content_current) {
    already_drawn_rows |= redraw_option_delta(state, snapshot);
  }

  if (!snapshot_delta_drawn && !page_content_current) {
    (void)redraw_snapshot_delta(state, snapshot, already_drawn_rows);
  }

  redraw_header_delta(snapshot, header_time, header_mqtt);
  if (footer_delta) {
    invalidate((UiDirtyRect){0, UI_FOOTER_TOP, LCD_WIDTH, LCD_HEIGHT - UI_FOOTER_TOP});
    draw_footer(state);
  }
  if (overlay_delta) {
    if (overlay_visible(state)) {
      invalidate((UiDirtyRect){5, 22, 118, 94});
      draw_active_overlay(state);
    } else {
      invalidate((UiDirtyRect){0, UI_PAGE_TOP, LCD_WIDTH, UI_FOOTER_TOP - UI_PAGE_TOP});
      draw_page_frame(state, snapshot, 0);
    }
  } else if (overlay_visible(state)) {
    draw_active_overlay(state);
  }

  if (ST7735_FrameFailed()) {
    renderer.stats = stats_before;
    ++renderer.stats.failed_frames;
    renderer.force_full_redraw = 1U;
    return 0U;
  }

  renderer.state = *state;
  renderer.snapshot = *snapshot;
  ++renderer.stats.rendered_frames;
  return 1U;
}
