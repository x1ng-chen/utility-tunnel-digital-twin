#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "ui_renderer.h"
#include "st7735.h"

#define CHECK(condition) do { \
  if (!(condition)) { \
    (void)fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    return 1; \
  } \
} while (0)

typedef struct {
  int x;
  int y;
  int w;
  int h;
  uint16_t color;
} RecordedRect;

typedef struct {
  int x;
  int y;
  uint16_t color;
  char text[32];
} RecordedString;

static RecordedRect rects[256];
static uint16_t rect_count;
static uint16_t clear_count;
static uint16_t question_glyph_count;
static RecordedString drawn_strings[128];
static uint16_t drawn_string_count;
static int fail_after_draw_calls = -1;
static uint16_t draw_calls;
static uint8_t injected_frame_failed;

void ST7735_BeginFrame(void)
{
  draw_calls = 0U;
  injected_frame_failed = 0U;
}

uint8_t ST7735_FrameFailed(void)
{
  return injected_frame_failed;
}

static uint8_t reject_injected_draw(void)
{
  if (injected_frame_failed) return 1U;
  if ((fail_after_draw_calls >= 0) && (draw_calls >= (uint16_t)fail_after_draw_calls)) {
    injected_frame_failed = 1U;
    return 1U;
  }
  ++draw_calls;
  return 0U;
}

void ST7735_Clear(uint16_t color)
{
  if (reject_injected_draw()) return;
  (void)color;
  ++clear_count;
}

void ST7735_FillRect(int x, int y, int w, int h, uint16_t color)
{
  if (reject_injected_draw()) return;
  if (rect_count < (uint16_t)(sizeof(rects) / sizeof(rects[0]))) {
    rects[rect_count].x = x;
    rects[rect_count].y = y;
    rects[rect_count].w = w;
    rects[rect_count].h = h;
    rects[rect_count].color = color;
  }
  ++rect_count;
}

void ST7735_DrawGlyph16(int x, int y, const uint8_t glyph[32], uint16_t color, uint16_t bg)
{
  if (reject_injected_draw()) return;
  (void)x; (void)y; (void)glyph; (void)color; (void)bg;
}

void ST7735_DrawChar(int x, int y, char c, uint16_t color, uint16_t bg)
{
  if (reject_injected_draw()) return;
  if (c == '?') ++question_glyph_count;
  (void)x; (void)y; (void)c; (void)color; (void)bg;
}

void ST7735_DrawString(int x, int y, const char *str, uint16_t color, uint16_t bg)
{
  if (reject_injected_draw()) return;
  if ((str != NULL) && (drawn_string_count < (uint16_t)(sizeof(drawn_strings) / sizeof(drawn_strings[0])))) {
    drawn_strings[drawn_string_count].x = x;
    drawn_strings[drawn_string_count].y = y;
    drawn_strings[drawn_string_count].color = color;
    (void)snprintf(drawn_strings[drawn_string_count].text,
                   sizeof(drawn_strings[drawn_string_count].text), "%s", str);
  }
  ++drawn_string_count;
  (void)x; (void)y; (void)str; (void)color; (void)bg;
}

static void reset_display_recording(void)
{
  (void)memset(rects, 0, sizeof(rects));
  rect_count = 0U;
  clear_count = 0U;
  question_glyph_count = 0U;
  (void)memset(drawn_strings, 0, sizeof(drawn_strings));
  drawn_string_count = 0U;
  draw_calls = 0U;
  injected_frame_failed = 0U;
}

static int string_was_drawn(const char *expected)
{
  uint16_t index;
  const uint16_t stored = (drawn_string_count < (uint16_t)(sizeof(drawn_strings) / sizeof(drawn_strings[0])))
    ? drawn_string_count : (uint16_t)(sizeof(drawn_strings) / sizeof(drawn_strings[0]));
  for (index = 0U; index < stored; ++index) {
    if (strcmp(drawn_strings[index].text, expected) == 0) return 1;
  }
  return 0;
}

static int string_was_drawn_at(const char *expected, int y, uint16_t color)
{
  uint16_t index;
  const uint16_t stored = (drawn_string_count < (uint16_t)(sizeof(drawn_strings) / sizeof(drawn_strings[0])))
    ? drawn_string_count : (uint16_t)(sizeof(drawn_strings) / sizeof(drawn_strings[0]));
  for (index = 0U; index < stored; ++index) {
    if ((drawn_strings[index].y == y) && (drawn_strings[index].color == color) &&
        (strcmp(drawn_strings[index].text, expected) == 0)) return 1;
  }
  return 0;
}

static int has_rect(int x, int y, int w, int h)
{
  uint16_t index;
  for (index = 0U; index < rect_count && index < (uint16_t)(sizeof(rects) / sizeof(rects[0])); ++index) {
    if ((rects[index].x == x) && (rects[index].y == y) &&
        (rects[index].w == w) && (rects[index].h == h)) return 1;
  }
  return 0;
}

static int has_rect_color(int x, int y, int w, int h, uint16_t color)
{
  uint16_t index;
  for (index = 0U; index < rect_count && index < (uint16_t)(sizeof(rects) / sizeof(rects[0])); ++index) {
    if ((rects[index].x == x) && (rects[index].y == y) &&
        (rects[index].w == w) && (rects[index].h == h) &&
        (rects[index].color == color)) return 1;
  }
  return 0;
}

static int check_display_glyph_coverage(void)
{
  UiState state;
  UiSnapshot snapshot;
  uint8_t page;
  (void)memset(&snapshot, 0, sizeof(snapshot));
  for (page = (uint8_t)UI_HOME; page <= (uint8_t)UI_SETTINGS; ++page) {
    UiState_Init(&state);
    state.page = (UiPage)page;
    reset_display_recording();
    UiRenderer_Init();
    CHECK(UiRenderer_RenderFrame(&state, &snapshot, 0U) == 1U);
    CHECK(question_glyph_count == 0U);
  }
  return 0;
}

static int has_full_screen_rect(void)
{
  uint16_t index;
  for (index = 0U; index < rect_count && index < (uint16_t)(sizeof(rects) / sizeof(rects[0])); ++index) {
    if ((rects[index].x == 0) && (rects[index].y == 0) &&
        (rects[index].w == LCD_WIDTH) && (rects[index].h == LCD_HEIGHT)) return 1;
  }
  return 0;
}

static int has_page_viewport_rect(void)
{
  uint16_t index;
  for (index = 0U; index < rect_count && index < (uint16_t)(sizeof(rects) / sizeof(rects[0])); ++index) {
    if ((rects[index].x == 0) && (rects[index].y == 12) &&
        (rects[index].w == LCD_WIDTH) && (rects[index].h == 104)) return 1;
  }
  return 0;
}

static int check_layout_contract(void)
{
  typedef struct {
    UiPage page;
    const char *page_name;
    const char *title;
    uint8_t rows;
    const char *selected;
  } ExpectedLayout;
  static const ExpectedLayout expected[] = {
    {UI_HOME, "home", "main_menu", 7U, "safety_overview"},
    {UI_OVERVIEW, "overview", "safety_overview", 1U, "overall_status"},
    {UI_MONITOR, "monitor", "classified_monitoring", 4U, "environment"},
    {UI_ALERTS, "alerts", "alarm_center", 1U, "active_alarms"},
    {UI_FANS, "fans", "fan_control", 4U, "fan_1_start_stop_30_60_100"},
    {UI_LIGHT_SOUND, "light_sound", "led_and_buzzer", 3U, "led_modes_off_white_green_yellow_red_blue_breathe_flash"},
    {UI_NETWORK, "network", "communication_status", 1U, "link_summary"},
    {UI_SETTINGS, "settings", "system_settings", 2U, "display"},
  };
  UiState state;
  UiSnapshot snapshot;
  char line[320];
  size_t index;

  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  /* An observed-down link renders as offline.  Zero-initialising is not the
   * same state any more: unmeasured is UI_LINK_UNKNOWN and must not be shown
   * as a confident OFFLINE. */
  snapshot.connectivity.mqtt = (uint8_t)UI_LINK_OFFLINE;
  for (index = 0U; index < (sizeof(expected) / sizeof(expected[0])); ++index) {
    state.page = expected[index].page;
    state.selected_row = 0U;
    state.dialog = UI_DIALOG_NONE;
    CHECK(UiRenderer_DescribeLayout(&state, &snapshot, line, sizeof(line)) > 0U);
    CHECK(strstr(line, expected[index].page_name) != NULL);
    CHECK(strstr(line, expected[index].title) != NULL);
    {
      char rows[16];
      (void)snprintf(rows, sizeof(rows), "rows=%u", (unsigned int)expected[index].rows);
      CHECK(strstr(line, rows) != NULL);
    }
    CHECK(strstr(line, expected[index].selected) != NULL);
    CHECK(strstr(line, "time=--:--") != NULL);
    CHECK(strstr(line, "mqtt=offline") != NULL);
    CHECK(strstr(line, "dialog=none") != NULL);
  }

  snapshot.clock.synchronized = 1U;
  snapshot.clock.hour = 9U;
  snapshot.clock.minute = 7U;
  snapshot.connectivity.mqtt = (uint8_t)UI_LINK_ONLINE;
  state.page = UI_FANS;
  state.selected_row = 1U;
  state.dialog = UI_DIALOG_CONFIRM;
  CHECK(UiRenderer_DescribeLayout(&state, &snapshot, line, sizeof(line)) > 0U);
  CHECK(strstr(line, "selected=both_start") != NULL);
  CHECK(strstr(line, "time=09:07") != NULL);
  CHECK(strstr(line, "mqtt=online") != NULL);
  CHECK(strstr(line, "dialog=confirm") != NULL);

  /* A link that was never observed reads as unknown, not as offline. */
  snapshot.connectivity.mqtt = (uint8_t)UI_LINK_UNKNOWN;
  CHECK(UiRenderer_DescribeLayout(&state, &snapshot, line, sizeof(line)) > 0U);
  CHECK(strstr(line, "mqtt=unknown") != NULL);
  snapshot.connectivity.mqtt = (uint8_t)UI_LINK_ONLINE;

  state.page = UI_FANS;
  state.selected_row = 0U;
  state.fan_duty_option[0] = 60U;
  state.option_editing = 1U;
  CHECK(UiRenderer_DescribeLayout(&state, &snapshot, line, sizeof(line)) > 0U);
  CHECK(strstr(line, "option=fan1_duty") != NULL);
  CHECK(strstr(line, "value=60") != NULL);
  CHECK(strstr(line, "editing=1") != NULL);

  state.page = UI_LIGHT_SOUND;
  state.selected_row = 2U;
  state.buzzer_option = UI_BUZZER_RESTORE;
  state.option_editing = 0U;
  CHECK(UiRenderer_DescribeLayout(&state, &snapshot, line, sizeof(line)) > 0U);
  CHECK(strstr(line, "option=buzzer") != NULL);
  CHECK(strstr(line, "value=2") != NULL);
  CHECK(strstr(line, "editing=0") != NULL);

  state.page = UI_LIGHT_SOUND;
  state.selected_row = 1U;
  CHECK(UiRenderer_DescribeLayout(&state, &snapshot, line, sizeof(line)) > 0U);
  CHECK(strstr(line, "selected=brightness_25_50_75_100 time=") != NULL);
  state.selected_row = 2U;
  CHECK(UiRenderer_DescribeLayout(&state, &snapshot, line, sizeof(line)) > 0U);
  CHECK(strstr(line, "selected=buzzer_test_mute_restore time=") != NULL);
  return 0;
}

static int check_frame_failure_recovery_contract(void)
{
  UiState state;
  UiSnapshot snapshot;
  UiRendererStats stats;

  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  state.page = UI_MONITOR;
  snapshot.temperature_centi_c.value = 2100;
  snapshot.temperature_centi_c.quality = UI_QUALITY_VALID;
  UiRenderer_Init();
  reset_display_recording();
  fail_after_draw_calls = 3;
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 0U) == 0U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.failed_frames == 1U);
  CHECK(stats.rendered_frames == 0U);
  CHECK(draw_calls == 3U);

  fail_after_draw_calls = -1;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 1U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.full_screen_redraws == 1U);
  CHECK(has_full_screen_rect());
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 2U) == 0U);
  CHECK(!has_full_screen_rect());

  snapshot.temperature_centi_c.value = 2200;
  fail_after_draw_calls = 1;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 3U) == 0U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.failed_frames == 2U);
  fail_after_draw_calls = -1;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 4U) == 1U);
  CHECK(has_full_screen_rect());
  CHECK(string_was_drawn("TEMP 22.00C"));
  return 0;
}

static int check_selection_animation_merges_visible_telemetry(void)
{
  UiState state;
  UiSnapshot snapshot;
  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  state.page = UI_FANS;
  snapshot.fans[1].quality = UI_QUALITY_VALID;
  UiRenderer_Init();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 0U) == 1U);

  state.selected_row = 1U;
  state.animation_start_ms = 100U;
  state.animation_end_ms = 240U;
  snapshot.fans[1].running = 1U;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 100U) == 1U);
  CHECK(has_rect(8, 94, 116, 18));
  CHECK(string_was_drawn("F2 ON 0%"));
  return 0;
}

static int check_field_level_dirty_rectangles(void)
{
  UiState state;
  UiSnapshot snapshot;
  UiRendererStats stats;

  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  state.page = UI_LIGHT_SOUND;
  UiRenderer_Init();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 0U) == 1U);
  snapshot.actuators.led_brightness_percent = 50U;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 1U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_dirty_rectangles == 1U);
  CHECK(has_rect(8, 60, 116, 24));
  CHECK(!has_rect(2, 34, 122, 72));

  state.page = UI_NETWORK;
  state.animation_start_ms = 10U;
  state.animation_end_ms = 190U;
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 190U) == 1U);
  snapshot.connectivity.gateway = (uint8_t)UI_LINK_ONLINE;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 191U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_dirty_rectangles == 1U);
  CHECK(has_rect(8, 54, 116, 18));
  CHECK(string_was_drawn("GATEWAY ONLINE"));

  snapshot.connectivity.mqtt = (uint8_t)UI_LINK_ONLINE;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 192U) == 1U);
  CHECK(has_rect(8, 94, 116, 18));
  CHECK(string_was_drawn("MQTT ONLINE"));

  state.page = UI_OVERVIEW;
  state.animation_start_ms = 200U;
  state.animation_end_ms = 380U;
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 380U) == 1U);
  snapshot.warning_sources = UI_ALARM_SOURCE_METHANE;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 381U) == 1U);
  CHECK(has_rect(8, 35, 112, 22));
  CHECK(has_rect(10, 66, 100, 8));
  CHECK(has_rect(10, 82, 100, 8));
  CHECK(!has_rect(0, 34, 128, 82));
  return 0;
}

static int check_safety_lock_priority_and_control_style(void)
{
  UiState state;
  UiSnapshot snapshot;
  UiRendererStats stats;
  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  state.page = UI_FANS;
  UiState_SetControlAvailability(&state, 1U, 0U);
  UiRenderer_Init();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 0U) == 1U);

  UiState_SetControlAvailability(&state, 0U, 1U);
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 1U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(string_was_drawn("SAFETY LOCKED"));
  CHECK(string_was_drawn_at("F1 OFF 0%", 35, 0x8C71U));
  CHECK(has_rect(8, 34, 116, 18));
  CHECK(has_rect(8, 54, 116, 18));
  CHECK(has_rect(8, 74, 116, 18));
  CHECK(has_rect(8, 94, 116, 18));
  CHECK(stats.last_dirty_rectangles == 2U);

  UiState_SetControlAvailability(&state, 1U, 0U);
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 2U) == 1U);
  CHECK(string_was_drawn_at("F1 OFF 0%", 35, LCD_WHITE));
  return 0;
}

static int check_safety_locked_selection_animation_color(void)
{
  UiState state;
  UiSnapshot snapshot;
  UiRendererStats stats;
  const uint16_t danger = 0xF9A6U;

  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  state.page = UI_FANS;
  UiState_SetControlAvailability(&state, 0U, 1U);
  UiRenderer_Init();
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 0U) == 1U);
  CHECK(has_rect_color(2, 34, 3, 18, danger));

  state.selected_row = 1U;
  state.animation_start_ms = 100U;
  state.animation_end_ms = 240U;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 100U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(has_rect_color(2, stats.last_selection_y, 3, 18, danger));

  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 116U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_selection_y > 34 && stats.last_selection_y < 54);
  CHECK(has_rect_color(2, stats.last_selection_y, 3, 18, danger));

  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 240U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_selection_y == 54);
  CHECK(has_rect_color(2, 54, 3, 18, danger));
  return 0;
}

static int check_fan_control_visible_field_comparator(void)
{
  UiState state;
  UiSnapshot snapshot;

  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  state.page = UI_FANS;
  snapshot.fans[0].quality = UI_QUALITY_VALID;
  UiRenderer_Init();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 0U) == 1U);

  snapshot.fans[0].target_duty_percent = 60U;
  snapshot.fans[0].actual_rpm = 2400U;
  snapshot.fans[0].voltage_mv = 11900U;
  snapshot.fans[0].current_ma = 280U;
  snapshot.fans[0].quality = UI_QUALITY_STALE;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 1U) == 0U);
  CHECK(rect_count == 0U);

  snapshot.fans[0].running = 1U;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 2U) == 1U);
  CHECK(has_rect(8, 34, 116, 18));
  CHECK(string_was_drawn("F1 ON 0%"));

  state.page = UI_MONITOR;
  state.selected_row = 3U;
  state.animation_start_ms = 10U;
  state.animation_end_ms = 190U;
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 190U) == 1U);
  snapshot.fans[0].actual_rpm = 2500U;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 191U) == 1U);
  CHECK(has_rect(9, 52, 115, 14));
  snapshot.fans[0].current_ma = 300U;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 192U) == 1U);
  CHECK(has_rect(9, 68, 115, 14));
  return 0;
}

static int check_mixed_alarm_sources_and_names(void)
{
  UiState state;
  UiSnapshot snapshot;
  char line[320];
  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  snapshot.warning_sources = UI_ALARM_SOURCE_METHANE;
  snapshot.critical_sources = UI_ALARM_SOURCE_SMOKE;
  snapshot.alarm_severity = UI_ALARM_CRITICAL;
  state.page = UI_OVERVIEW;
  UiRenderer_Init();
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 0U) == 1U);
  CHECK(string_was_drawn("OK 6"));
  CHECK(string_was_drawn("WARN 1"));
  CHECK(string_was_drawn("ALARM 1"));
  CHECK(UiRenderer_DescribeLayout(&state, &snapshot, line, sizeof(line)) > 0U);
  CHECK(strstr(line, "warning=1") != NULL);
  CHECK(strstr(line, "critical=1") != NULL);

  state.page = UI_ALERTS;
  state.animation_start_ms = 10U;
  state.animation_end_ms = 190U;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 190U) == 1U);
  CHECK(string_was_drawn("CH4 WARNING"));
  CHECK(string_was_drawn("SMOKE CRITICAL"));

  snapshot.warning_sources = UI_ALARM_SOURCE_METHANE | UI_ALARM_SOURCE_SMOKE;
  reset_display_recording();
  state.page = UI_OVERVIEW;
  state.animation_start_ms = 200U;
  state.animation_end_ms = 380U;
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 380U) == 1U);
  CHECK(string_was_drawn("OK 6"));
  CHECK(string_was_drawn("WARN 1"));
  CHECK(string_was_drawn("ALARM 1"));
  return 0;
}

static int check_alarm_source_overflow_summary(void)
{
  UiState state;
  UiSnapshot snapshot;
  char line[320];

  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  state.page = UI_ALERTS;
  snapshot.warning_sources = UI_ALARM_SOURCE_MASK;
  snapshot.critical_sources = UI_ALARM_SOURCE_OXYGEN | UI_ALARM_SOURCE_SMOKE;
  snapshot.alarm_severity = UI_ALARM_CRITICAL;
  UiRenderer_Init();
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 0U) == 1U);
  CHECK(string_was_drawn("O2 CRITICAL"));
  CHECK(string_was_drawn("SMOKE CRITICAL"));
  CHECK(string_was_drawn("TEMP WARNING"));
  CHECK(string_was_drawn("+5 MORE"));
  CHECK(!string_was_drawn("O2 WARNING"));
  CHECK(!string_was_drawn("SMOKE WARNING"));
  CHECK(UiRenderer_DescribeLayout(&state, &snapshot, line, sizeof(line)) > 0U);
  CHECK(strstr(line, "warning=6") != NULL);
  CHECK(strstr(line, "critical=2") != NULL);
  return 0;
}

static int check_page_name_resolution(void)
{
  static const struct {
    const char *name;
    UiPage page;
  } expected[] = {
    {"home", UI_HOME}, {"overview", UI_OVERVIEW}, {"monitor", UI_MONITOR},
    {"alerts", UI_ALERTS}, {"fans", UI_FANS}, {"light_sound", UI_LIGHT_SOUND},
    {"network", UI_NETWORK}, {"settings", UI_SETTINGS},
  };
  UiPage page = UI_HOME;
  size_t index;
  for (index = 0U; index < (sizeof(expected) / sizeof(expected[0])); ++index) {
    CHECK(UiRenderer_PageFromName(expected[index].name, &page) == 1U);
    CHECK(page == expected[index].page);
  }
  CHECK(UiRenderer_PageFromName("fan", &page) == 0U);
  CHECK(UiRenderer_PageFromName("", &page) == 0U);
  CHECK(UiRenderer_PageFromName(NULL, &page) == 0U);
  CHECK(UiRenderer_PageFromName("home", NULL) == 0U);
  return 0;
}

static int check_interpolation_contract(void)
{
  CHECK(UiRenderer_InterpolatePixels(34, 54, 100U, 140U, 99U) == 34);
  CHECK(UiRenderer_InterpolatePixels(34, 54, 100U, 140U, 100U) == 34);
  CHECK(UiRenderer_InterpolatePixels(34, 54, 100U, 140U, 170U) == 44);
  CHECK(UiRenderer_InterpolatePixels(34, 54, 100U, 140U, 240U) == 54);
  CHECK(UiRenderer_InterpolatePixels(128, 0, 500U, 180U, 590U) == 64);
  CHECK(UiRenderer_InterpolatePixels(128, 0, 500U, 180U, 680U) == 0);
  CHECK(UiRenderer_InterpolatePixels(10, 30, UINT32_MAX - 20U, 40U, 19U) == 30);
  return 0;
}

static int check_dirty_and_cadence_contract(void)
{
  UiState state;
  UiSnapshot snapshot;
  UiRendererStats stats;
  uint32_t frames;

  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  state.page = UI_MONITOR;
  snapshot.temperature_centi_c.value = 2234;
  snapshot.temperature_centi_c.quality = UI_QUALITY_VALID;

  reset_display_recording();
  UiRenderer_Init();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 100U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.full_screen_redraws == 1U);
  CHECK(has_full_screen_rect());
  CHECK(clear_count == 0U);

  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 101U) == 0U);
  CHECK(rect_count == 0U);

  snapshot.temperature_centi_c.value = 2240;
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 102U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_dirty_rectangles == 1U);
  CHECK(stats.full_screen_redraws == 1U);
  CHECK(!has_full_screen_rect());

  snapshot.methane_ppm.value = 900;
  snapshot.methane_ppm.quality = UI_QUALITY_VALID;
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 103U) == 0U);

  UiState_Init(&state);
  UiRenderer_Init();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 150U) == 1U);
  state.selected_row = 1U;
  state.animation_start_ms = 200U;
  state.animation_end_ms = 340U;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 200U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_dirty_rectangles == 2U);
  CHECK(stats.last_selection_y == 34);
  CHECK(!has_full_screen_rect());
  CHECK(!has_page_viewport_rect());
  frames = stats.rendered_frames;

  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 215U) == 0U);
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 216U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.rendered_frames == frames + 1U);
  CHECK(stats.last_selection_y > 34 && stats.last_selection_y < 54);
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 232U) == 0U);
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 233U) == 1U);
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 333U) == 1U);
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 340U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_selection_y == 54);
  CHECK(stats.full_screen_redraws == 1U);
  return 0;
}

static int check_page_animation_and_header_delta(void)
{
  UiState state;
  UiSnapshot snapshot;
  UiRendererStats stats;

  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  UiRenderer_Init();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 0U) == 1U);

  snapshot.clock.hour = 12U;
  snapshot.clock.minute = 34U;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 1U) == 0U);
  CHECK(rect_count == 0U);

  snapshot.clock.synchronized = 1U;
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 2U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_dirty_rectangles == 1U);
  CHECK(stats.full_screen_redraws == 1U);

  snapshot.connectivity.mqtt = (uint8_t)UI_LINK_ONLINE;
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 3U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_dirty_rectangles == 1U);

  state.page = UI_OVERVIEW;
  state.animation_start_ms = 10U;
  state.animation_end_ms = 190U;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 10U) == 1U);
  CHECK(string_was_drawn("<BACK  OK"));
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_page_offset == 128);
  CHECK(!has_full_screen_rect());
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 100U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_page_offset == 64);
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 190U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_page_offset == 0);
  CHECK(stats.full_screen_redraws == 1U);

  state.page = UI_HOME;
  state.animation_start_ms = 200U;
  state.animation_end_ms = 380U;
  reset_display_recording();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 200U) == 1U);
  CHECK(string_was_drawn("UP/DN  OK>"));
  return 0;
}

static int check_page_specific_selection_geometry(void)
{
  UiState state;
  UiSnapshot snapshot;
  UiRendererStats stats;
  UiState_Init(&state);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  state.page = UI_LIGHT_SOUND;
  UiRenderer_Init();
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 400U) == 1U);
  state.selected_row = 1U;
  state.animation_start_ms = 500U;
  state.animation_end_ms = 640U;
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 500U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_selection_y == 34);
  CHECK(UiRenderer_RenderFrame(&state, &snapshot, 640U) == 1U);
  UiRenderer_GetStats(&stats);
  CHECK(stats.last_selection_y == 60);
  return 0;
}

static int check_confirmation_modal_names_critical_action(void)
{
  static const struct {
    UiPage page;
    uint8_t row;
    UiAction action;
    const char *label;
  } cases[] = {
    {UI_FANS, 1U, UI_ACTION_FANS_BOTH_START, "BOTH FANS"},
    {UI_FANS, 2U, UI_ACTION_FANS_ALL_STOP, "ALL STOP"},
    {UI_LIGHT_SOUND, 2U, UI_ACTION_BUZZER_MUTE, "BUZZ MUTE"},
  };
  UiState state;
  UiSnapshot snapshot;
  size_t index;

  (void)memset(&snapshot, 0, sizeof(snapshot));
  for (index = 0U; index < (sizeof(cases) / sizeof(cases[0])); ++index) {
    UiState_Init(&state);
    state.page = cases[index].page;
    state.selected_row = cases[index].row;
    state.dialog = UI_DIALOG_CONFIRM;
    state.command_phase = UI_CMD_CONFIRM;
    state.pending_action = (uint8_t)cases[index].action;
    reset_display_recording();
    UiRenderer_Init();
    CHECK(UiRenderer_RenderFrame(&state, &snapshot, 0U) == 1U);
    CHECK(string_was_drawn(cases[index].label));
  }
  return 0;
}

int main(void)
{
  if (check_layout_contract() != 0) return 1;
  if (check_display_glyph_coverage() != 0) return 1;
  if (check_page_name_resolution() != 0) return 1;
  if (check_interpolation_contract() != 0) return 1;
  if (check_dirty_and_cadence_contract() != 0) return 1;
  if (check_page_animation_and_header_delta() != 0) return 1;
  if (check_page_specific_selection_geometry() != 0) return 1;
  if (check_confirmation_modal_names_critical_action() != 0) return 1;
  if (check_frame_failure_recovery_contract() != 0) return 1;
  if (check_selection_animation_merges_visible_telemetry() != 0) return 1;
  if (check_field_level_dirty_rectangles() != 0) return 1;
  if (check_safety_lock_priority_and_control_style() != 0) return 1;
  if (check_safety_locked_selection_animation_color() != 0) return 1;
  if (check_fan_control_visible_field_comparator() != 0) return 1;
  if (check_mixed_alarm_sources_and_names() != 0) return 1;
  if (check_alarm_source_overflow_summary() != 0) return 1;
  (void)puts("UiRenderer host test: PASS");
  return 0;
}
