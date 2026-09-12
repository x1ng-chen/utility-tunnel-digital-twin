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
} RecordedRect;

static RecordedRect rects[256];
static uint16_t rect_count;
static uint16_t clear_count;
static uint16_t question_glyph_count;
static char drawn_strings[64][32];
static uint16_t drawn_string_count;

void ST7735_Clear(uint16_t color)
{
  (void)color;
  ++clear_count;
}

void ST7735_FillRect(int x, int y, int w, int h, uint16_t color)
{
  (void)color;
  if (rect_count < (uint16_t)(sizeof(rects) / sizeof(rects[0]))) {
    rects[rect_count].x = x;
    rects[rect_count].y = y;
    rects[rect_count].w = w;
    rects[rect_count].h = h;
  }
  ++rect_count;
}

void ST7735_DrawGlyph16(int x, int y, const uint8_t glyph[32], uint16_t color, uint16_t bg)
{
  (void)x; (void)y; (void)glyph; (void)color; (void)bg;
}

void ST7735_DrawChar(int x, int y, char c, uint16_t color, uint16_t bg)
{
  if (c == '?') ++question_glyph_count;
  (void)x; (void)y; (void)c; (void)color; (void)bg;
}

void ST7735_DrawString(int x, int y, const char *str, uint16_t color, uint16_t bg)
{
  if ((str != NULL) && (drawn_string_count < (uint16_t)(sizeof(drawn_strings) / sizeof(drawn_strings[0])))) {
    (void)snprintf(drawn_strings[drawn_string_count], sizeof(drawn_strings[drawn_string_count]), "%s", str);
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
}

static int string_was_drawn(const char *expected)
{
  uint16_t index;
  const uint16_t stored = (drawn_string_count < (uint16_t)(sizeof(drawn_strings) / sizeof(drawn_strings[0])))
    ? drawn_string_count : (uint16_t)(sizeof(drawn_strings) / sizeof(drawn_strings[0]));
  for (index = 0U; index < stored; ++index) {
    if (strcmp(drawn_strings[index], expected) == 0) return 1;
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
  snapshot.connectivity.mqtt_online = 1U;
  state.page = UI_FANS;
  state.selected_row = 1U;
  state.dialog = UI_DIALOG_CONFIRM;
  CHECK(UiRenderer_DescribeLayout(&state, &snapshot, line, sizeof(line)) > 0U);
  CHECK(strstr(line, "selected=both_start") != NULL);
  CHECK(strstr(line, "time=09:07") != NULL);
  CHECK(strstr(line, "mqtt=online") != NULL);
  CHECK(strstr(line, "dialog=confirm") != NULL);
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

  snapshot.connectivity.mqtt_online = 1U;
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
  (void)puts("UiRenderer host test: PASS");
  return 0;
}
