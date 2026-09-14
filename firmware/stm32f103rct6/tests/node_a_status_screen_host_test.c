/* Host test for the Node A read-only status screen.
 *
 * The page model is exercised directly, and the renderer is exercised through
 * a recording double of the ST7735 driver so the test can assert what the
 * screen would actually show without a panel. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "node_a_status_screen.h"
#include "st7735.h"

#define CHECK(condition) do { \
  if (!(condition)) { \
    (void)fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    return 1; \
  } \
} while (0)

typedef struct {
  char text[16];
  uint16_t color;
} RecordedString;

static RecordedString drawn[256];
static uint16_t drawn_count;
static uint16_t fill_count;
static uint16_t alarm_fill_count;
static uint16_t normal_fill_count;

void ST7735_BeginFrame(void) { }
uint8_t ST7735_FrameFailed(void) { return 0U; }
void ST7735_Clear(uint16_t color) { (void)color; }
void ST7735_FillRect(int x, int y, int w, int h, uint16_t color)
{
  (void)x; (void)y; (void)w; (void)h;
  if (w == LCD_WIDTH && h == LCD_HEIGHT) {
    ++fill_count;
    if (color == NODE_A_STATUS_DANGER) ++alarm_fill_count;
    else ++normal_fill_count;
  }
}
void ST7735_DrawGlyph16(int x, int y, const uint8_t glyph[32], uint16_t color, uint16_t bg)
{
  (void)x; (void)y; (void)glyph; (void)color; (void)bg;
}
void ST7735_DrawChar(int x, int y, char c, uint16_t color, uint16_t bg)
{
  (void)x; (void)y; (void)c; (void)color; (void)bg;
}
void ST7735_DrawString(int x, int y, const char *str, uint16_t color, uint16_t bg)
{
  (void)x; (void)y; (void)bg;
  if (drawn_count >= (uint16_t)(sizeof(drawn) / sizeof(drawn[0]))) return;
  (void)snprintf(drawn[drawn_count].text, sizeof(drawn[drawn_count].text), "%s", str);
  drawn[drawn_count].color = color;
  ++drawn_count;
}

static void reset_recorder(void)
{
  drawn_count = 0U;
  fill_count = 0U;
  alarm_fill_count = 0U;
  normal_fill_count = 0U;
}

static uint8_t saw_text(const char *needle)
{
  for (uint16_t i = 0U; i < drawn_count; ++i) {
    if (strstr(drawn[i].text, needle) != NULL) return 1U;
  }
  return 0U;
}

static uint8_t saw_text_in_color(const char *needle, uint16_t color)
{
  for (uint16_t i = 0U; i < drawn_count; ++i) {
    if (drawn[i].color == color && strstr(drawn[i].text, needle) != NULL) return 1U;
  }
  return 0U;
}

static NodeAStatusSnapshot idle_snapshot(void)
{
  NodeAStatusSnapshot snapshot;
  memset(&snapshot, 0, sizeof(snapshot));
  snapshot.sht30_online = 1U;
  snapshot.temperature_centi_c = 2345;
  snapshot.humidity_centi_rh = 4560;
  snapshot.oxygen_online = 1U;
  snapshot.methane_online = 1U;
  snapshot.co_online = 1U;
  snapshot.oxygen_raw = 234U;
  snapshot.methane_raw = 210U;
  snapshot.co_raw = 512U;
  snapshot.fan1_pwm_percent = 60U;
  snapshot.fan2_pwm_percent = 100U;
  snapshot.fan1_rpm = 1240U;
  snapshot.fan2_rpm = 2380U;
  snapshot.fan1_power_online = 1U;
  snapshot.fan2_power_online = 1U;
  snapshot.fan1_millivolts = 12100U;
  snapshot.fan2_millivolts = 12000U;
  snapshot.fan1_milliamps = 420;
  snapshot.fan2_milliamps = 850;
  return snapshot;
}

static int check_page_sequence(void)
{
  /* Exactly the documented carousel: environment -> gas -> fans, 5000 ms each. */
  NodeAStatusScreen screen;
  const NodeAStatusSnapshot snapshot = idle_snapshot();
  NodeAStatus_Init(&screen, 0U);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ENVIRONMENT);
  NodeAStatus_Update(&screen, &snapshot, 0U, 0U);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ENVIRONMENT);
  NodeAStatus_Update(&screen, &snapshot, 0U, NODE_A_STATUS_DWELL_MS - 1U);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ENVIRONMENT);
  NodeAStatus_Update(&screen, &snapshot, 0U, NODE_A_STATUS_DWELL_MS);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_GAS);
  NodeAStatus_Update(&screen, &snapshot, 0U, 2U * NODE_A_STATUS_DWELL_MS - 1U);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_GAS);
  NodeAStatus_Update(&screen, &snapshot, 0U, 2U * NODE_A_STATUS_DWELL_MS);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_FANS);
  NodeAStatus_Update(&screen, &snapshot, 0U, 3U * NODE_A_STATUS_DWELL_MS);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ENVIRONMENT);
  CHECK(NODE_A_STATUS_DWELL_MS == 5000U);
  CHECK(strcmp(NodeAStatus_PageTitle(NODE_A_STATUS_PAGE_ENVIRONMENT), "ENV") == 0);
  CHECK(strcmp(NodeAStatus_PageTitle(NODE_A_STATUS_PAGE_GAS), "GAS") == 0);
  CHECK(strcmp(NodeAStatus_PageTitle(NODE_A_STATUS_PAGE_FANS), "FAN") == 0);
  CHECK(strcmp(NodeAStatus_PageTitle(NODE_A_STATUS_PAGE_ALARM), "ALARM") == 0);
  return 0;
}

static int check_alarm_takeover(void)
{
  /* A rising alarm must take the screen over immediately, from any page and
   * without waiting for the dwell, and must hold until the alarm clears. */
  NodeAStatusScreen screen;
  const NodeAStatusSnapshot snapshot = idle_snapshot();
  NodeAStatus_Init(&screen, 0U);
  NodeAStatus_Update(&screen, &snapshot, 0U, 0U);
  NodeAStatus_Update(&screen, &snapshot, 1U, 1U);   /* one tick after boot */
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ALARM);

  /* The carousel must not resume while the alarm stays asserted, even after
   * several dwell periods. */
  NodeAStatus_Update(&screen, &snapshot, 1U, 4U * NODE_A_STATUS_DWELL_MS);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ALARM);

  /* A takeover from the last carousel page behaves the same way. */
  NodeAStatus_Init(&screen, 0U);
  NodeAStatus_Update(&screen, &snapshot, 0U, 0U);
  NodeAStatus_Update(&screen, &snapshot, 0U, 2U * NODE_A_STATUS_DWELL_MS);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_FANS);
  NodeAStatus_Update(&screen, &snapshot, 1U, 2U * NODE_A_STATUS_DWELL_MS + 10U);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ALARM);

  /* Recovery restarts the carousel from the environment page and the dwell
   * restarts from the moment the alarm cleared. */
  NodeAStatus_Update(&screen, &snapshot, 0U, 2U * NODE_A_STATUS_DWELL_MS + 20U);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ENVIRONMENT);
  NodeAStatus_Update(&screen, &snapshot, 0U,
                     2U * NODE_A_STATUS_DWELL_MS + 20U + NODE_A_STATUS_DWELL_MS - 1U);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ENVIRONMENT);
  NodeAStatus_Update(&screen, &snapshot, 0U,
                     2U * NODE_A_STATUS_DWELL_MS + 20U + NODE_A_STATUS_DWELL_MS);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_GAS);
  return 0;
}

static int check_clock_placeholder(void)
{
  char text[NODE_A_STATUS_CLOCK_TEXT_SIZE];
  UiClockSnapshot clock;
  memset(&clock, 0, sizeof(clock));
  NodeAStatus_FormatClock(&clock, text, sizeof(text));
  CHECK(strcmp(text, "--:--") == 0);
  clock.synchronized = 1U;
  clock.hour = 9U;
  clock.minute = 5U;
  NodeAStatus_FormatClock(&clock, text, sizeof(text));
  CHECK(strcmp(text, "09:05") == 0);
  clock.hour = 23U;
  clock.minute = 59U;
  NodeAStatus_FormatClock(&clock, text, sizeof(text));
  CHECK(strcmp(text, "23:59") == 0);
  clock.hour = 24U;
  NodeAStatus_FormatClock(&clock, text, sizeof(text));
  CHECK(strcmp(text, "--:--") == 0);
  clock.hour = 1U;
  clock.minute = 60U;
  NodeAStatus_FormatClock(&clock, text, sizeof(text));
  CHECK(strcmp(text, "--:--") == 0);
  return 0;
}

static int check_alarm_sources(void)
{
  char text[NODE_A_STATUS_ALARM_TEXT_SIZE];
  NodeAStatusSnapshot snapshot = idle_snapshot();
  CHECK(NodeAStatus_DescribeAlarms(&snapshot, text, sizeof(text)) == 0U);
  CHECK(strcmp(text, "--") == 0);
  snapshot.methane_alarm = 1U;
  (void)NodeAStatus_DescribeAlarms(&snapshot, text, sizeof(text));
  CHECK(strstr(text, "CH4") != NULL);
  CHECK(strstr(text, "SMOKE") == NULL);
  CHECK(strstr(text, "FLAME") == NULL);
  snapshot.smoke_alarm = 1U;
  snapshot.flame_alarm = 1U;
  (void)NodeAStatus_DescribeAlarms(&snapshot, text, sizeof(text));
  CHECK(strstr(text, "CH4") != NULL);
  CHECK(strstr(text, "SMOKE") != NULL);
  CHECK(strstr(text, "FLAME") != NULL);
  return 0;
}

static int check_alarm_reaction_is_one_step(void)
{
  /* The gas path in node_a.c repaints with one Status_Tick() call placed
   * directly after the sample that latched the alarm, and that same call has to
   * carry both halves of the reaction: the takeover and the ventilation.  It is
   * the ordering contract test that keeps the call before the blocking INA226
   * read; this one pins what the call must show once it is there. */
  NodeAStatusScreen screen;
  NodeAStatusSnapshot snapshot = idle_snapshot();
  NodeAStatus_Init(&screen, 0U);
  reset_recorder();
  NodeAStatus_Update(&screen, &snapshot, 0U, 0U);
  CHECK(saw_text("ENV"));
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ENVIRONMENT);

  /* One dwell away from the environment page, then the fresh sample latches. */
  snapshot.methane_alarm = 1U;
  snapshot.gas_alarm = 1U;
  snapshot.relay_on = 1U;
  reset_recorder();
  NodeAStatus_Update(&screen, &snapshot, 1U,
                     NODE_A_STATUS_DWELL_MS - 1U);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ALARM);
  CHECK(alarm_fill_count == 1U && normal_fill_count == 0U);
  CHECK(saw_text("ALARM"));
  CHECK(saw_text("CH4"));
  CHECK(saw_text("VENT") && saw_text("ON"));
  CHECK(saw_text("BUZZ"));

  /* The takeover must not wait for the refresh interval either: a tick well
   * inside NODE_A_STATUS_REFRESH_MS still has to leave the alarm page up. */
  reset_recorder();
  NodeAStatus_Update(&screen, &snapshot, 1U, NODE_A_STATUS_DWELL_MS - 1U + 1U);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ALARM);
  CHECK(alarm_fill_count == 0U);

  /* Repainting the environment page while an alarm is up is never allowed, even
   * if a caller passes the data before the relay transition. */
  snapshot.relay_on = 0U;
  NodeAStatus_Update(&screen, &snapshot, 1U, 2U * NODE_A_STATUS_DWELL_MS);
  CHECK(NodeAStatus_CurrentPage(&screen) == NODE_A_STATUS_PAGE_ALARM);
  return 0;
}

static int check_render_pages(void)
{
  NodeAStatusScreen screen;
  NodeAStatusSnapshot snapshot = idle_snapshot();
  NodeAStatus_Init(&screen, 0U);

  reset_recorder();
  NodeAStatus_Update(&screen, &snapshot, 0U, 0U);
  CHECK(normal_fill_count == 1U && alarm_fill_count == 0U);
  CHECK(saw_text("ENV"));
  CHECK(saw_text("TEMP") && saw_text("23.45"));
  CHECK(saw_text("HUMI") && saw_text("45.60"));
  CHECK(saw_text("DRY"));
  CHECK(saw_text("--:--"));

  reset_recorder();
  NodeAStatus_Update(&screen, &snapshot, 0U, NODE_A_STATUS_DWELL_MS);
  CHECK(saw_text("GAS"));
  CHECK(saw_text("CH4") && saw_text("OK"));
  CHECK(saw_text("SMOKE") && saw_text("OK"));

  reset_recorder();
  NodeAStatus_Update(&screen, &snapshot, 0U, 2U * NODE_A_STATUS_DWELL_MS);
  CHECK(saw_text("FAN"));
  CHECK(saw_text("F1") && saw_text("1240"));
  CHECK(saw_text("F2") && saw_text("2380"));
  CHECK(saw_text("12.1") && saw_text("0.42"));

  /* An offline sensor must be reported, never rendered as a plausible value. */
  reset_recorder();
  snapshot.sht30_online = 0U;
  NodeAStatus_Init(&screen, 0U);
  NodeAStatus_Update(&screen, &snapshot, 0U, 0U);
  CHECK(!saw_text("23.4"));
  CHECK(saw_text("OFF"));

  /* The alarm page is red, names its sources and still shows the clock. */
  reset_recorder();
  NodeAStatusSnapshot alarming = idle_snapshot();
  alarming.methane_alarm = 1U;
  alarming.smoke_alarm = 1U;
  alarming.clock.synchronized = 1U;
  alarming.clock.hour = 8U;
  alarming.clock.minute = 7U;
  NodeAStatus_Init(&screen, 0U);
  NodeAStatus_Update(&screen, &alarming, 1U, 0U);
  CHECK(alarm_fill_count == 1U);
  CHECK(saw_text("ALARM"));
  CHECK(saw_text_in_color("CH4", NODE_A_STATUS_FG));
  CHECK(saw_text("SMOKE"));
  CHECK(saw_text("08:07"));
  return 0;
}

static int check_redraw_policy(void)
{
  /* The panel must not be repainted every loop iteration, but a page change or
   * fresh data must reach it immediately. */
  NodeAStatusScreen screen;
  NodeAStatusSnapshot snapshot = idle_snapshot();
  NodeAStatus_Init(&screen, 0U);
  reset_recorder();
  NodeAStatus_Update(&screen, &snapshot, 0U, 0U);
  CHECK(fill_count == 1U);
  NodeAStatus_Update(&screen, &snapshot, 0U, 1U);
  NodeAStatus_Update(&screen, &snapshot, 0U, 2U);
  CHECK(fill_count == 1U);
  snapshot.fan1_rpm = 1300U;
  NodeAStatus_Update(&screen, &snapshot, 0U, 3U);
  CHECK(fill_count == 2U);
  NodeAStatus_Update(&screen, &snapshot, 0U, 3U + NODE_A_STATUS_REFRESH_MS);
  CHECK(fill_count == 3U);
  return 0;
}

int main(void)
{
  if (check_page_sequence() != 0) return 1;
  if (check_alarm_takeover() != 0) return 1;
  if (check_clock_placeholder() != 0) return 1;
  if (check_alarm_sources() != 0) return 1;
  if (check_alarm_reaction_is_one_step() != 0) return 1;
  if (check_render_pages() != 0) return 1;
  if (check_redraw_policy() != 0) return 1;
  puts("Node A status screen host test: PASS");
  return 0;
}
