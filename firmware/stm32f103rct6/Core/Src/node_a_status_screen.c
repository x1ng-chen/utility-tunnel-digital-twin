/**
 * @file    node_a_status_screen.c
 * @brief   CTRL-01 read-only status screen: five-second carousel plus a red
 *          alarm page that takes the panel over the moment an alarm latches.
 *
 * The screen renders Node A's own local state.  It has no command path: it
 * never parses the ESP-01 MQTT stream, never touches an actuator and never
 * reads the joystick (Node A has none).  The page model is HAL-free so the
 * carousel timing and the takeover rules are host-testable; only the drawing
 * helpers below touch the ST7735 driver.
 */
#include "node_a_status_screen.h"

#include <stdio.h>
#include <string.h>

#include "st7735.h"

#define NODE_A_STATUS_LABEL_X     4
#define NODE_A_STATUS_VALUE_X    36
#define NODE_A_STATUS_ROW_TOP    26
#define NODE_A_STATUS_ROW_STEP   16
#define NODE_A_STATUS_CLOCK_X    (LCD_WIDTH - 5 * 8)

#define NODE_A_STATUS_VALUE_MAX  24

static int RowY(uint8_t row)
{
  return NODE_A_STATUS_ROW_TOP + ((int)row * NODE_A_STATUS_ROW_STEP);
}

#define NODE_A_STATUS_CAROUSEL_PAGES 3U

static void SelectPage(NodeAStatusModel *model, uint8_t alarm_active, uint32_t now_ms)
{
  uint32_t index;

  if (alarm_active != 0U)
  {
    /* A rising alarm takes the panel over in the same call; while it stays
     * asserted the carousel is frozen, however long ago a dwell expired. */
    if ((model->alarm_active == 0U) || (model->page != NODE_A_STATUS_PAGE_ALARM))
      model->page = NODE_A_STATUS_PAGE_ALARM;
    model->alarm_active = 1U;
    return;
  }

  if (model->alarm_active != 0U)
  {
    /* The carousel resumes only once the alarm has cleared, and it resumes
     * from a full dwell on the first page. */
    model->alarm_active = 0U;
    model->carousel_epoch_ms = now_ms;
  }

  /* The carousel keeps an absolute five-second phase from the last restart, so
   * a main loop delayed by a slow sensor read can neither stretch a page nor
   * make it skip one. */
  index = ((uint32_t)(now_ms - model->carousel_epoch_ms) /
           NODE_A_STATUS_DWELL_MS) % NODE_A_STATUS_CAROUSEL_PAGES;
  model->page = (NodeAStatusPage)index;
}

void NodeAStatus_Init(NodeAStatusScreen *screen, uint32_t now_ms)
{
  if (screen == NULL) return;
  (void)memset(screen, 0, sizeof(*screen));
  screen->model.page = NODE_A_STATUS_PAGE_ENVIRONMENT;
  screen->model.carousel_epoch_ms = now_ms;
  screen->rendered_at_ms = now_ms;
}

NodeAStatusPage NodeAStatus_CurrentPage(const NodeAStatusScreen *screen)
{
  return (screen == NULL) ? NODE_A_STATUS_PAGE_ENVIRONMENT : screen->model.page;
}

const char *NodeAStatus_PageTitle(NodeAStatusPage page)
{
  switch (page)
  {
    case NODE_A_STATUS_PAGE_GAS: return "GAS";
    case NODE_A_STATUS_PAGE_FANS: return "FAN";
    case NODE_A_STATUS_PAGE_ALARM: return "ALARM";
    case NODE_A_STATUS_PAGE_ENVIRONMENT:
    default: return "ENV";
  }
}

void NodeAStatus_FormatClock(const UiClockSnapshot *clock, char *output, size_t size)
{
  if ((output == NULL) || (size == 0U)) return;
  if ((clock == NULL) || (clock->synchronized == 0U) ||
      (clock->hour > 23U) || (clock->minute > 59U))
  {
    /* No valid ut.time.sync.v1 has been accepted yet: never invent a time. */
    (void)snprintf(output, size, "--:--");
    return;
  }
  (void)snprintf(output, size, "%02u:%02u", (unsigned int)clock->hour,
                 (unsigned int)clock->minute);
}

static size_t AppendAlarm(char *output, size_t size, size_t used, const char *name)
{
  const int written = snprintf(output + used, size - used, "%s%s",
                               (used != 0U) ? " " : "", name);
  const size_t grown = used + ((written > 0) ? (size_t)written : 0U);
  return (grown < size) ? grown : (size - 1U);
}

size_t NodeAStatus_DescribeAlarms(const NodeAStatusSnapshot *snapshot,
                                  char *output, size_t size)
{
  size_t used = 0U;
  size_t count = 0U;

  if ((output == NULL) || (size == 0U)) return 0U;
  output[0] = '\0';
  if (snapshot == NULL)
  {
    (void)snprintf(output, size, "--");
    return 0U;
  }

  /* Only the channels that drive Node A's safety response are listed.  Oxygen
   * and CO stay telemetry-only until their front ends are calibrated, so they
   * can never open the alarm page. */
  if ((snapshot->gas_alarm != 0U) || (snapshot->methane_alarm != 0U))
  {
    used = AppendAlarm(output, size, used, "CH4");
    ++count;
  }
  if (snapshot->smoke_alarm != 0U)
  {
    used = AppendAlarm(output, size, used, "SMOKE");
    ++count;
  }
  if (snapshot->flame_alarm != 0U)
  {
    used = AppendAlarm(output, size, used, "FLAME");
    ++count;
  }
  if (count == 0U) (void)snprintf(output, size, "--");
  return count;
}

/* ---------- drawing ---------- */

static void FormatDecimal(char *output, size_t size, int32_t tenths, const char *suffix)
{
  int64_t value = tenths;
  const char *sign = "";
  if (value < 0) { sign = "-"; value = -value; }
  (void)snprintf(output, size, "%s%u.%u%s", sign, (unsigned int)(value / 10),
                 (unsigned int)(value % 10), suffix);
}

static uint16_t AlarmColor(uint8_t alarm, uint8_t warning)
{
  if (alarm != 0U) return NODE_A_STATUS_DANGER;
  if (warning != 0U) return NODE_A_STATUS_WARNING;
  return NODE_A_STATUS_FG;
}

static void DrawRow(uint8_t row, const char *label, const char *value, uint16_t color)
{
  ST7735_DrawString(NODE_A_STATUS_LABEL_X, RowY(row), label, NODE_A_STATUS_MUTED,
                    NODE_A_STATUS_BG);
  ST7735_DrawString(NODE_A_STATUS_VALUE_X, RowY(row), value, color, NODE_A_STATUS_BG);
}

static void DrawHeader(NodeAStatusPage page, const UiClockSnapshot *clock)
{
  char text[NODE_A_STATUS_CLOCK_TEXT_SIZE];
  NodeAStatus_FormatClock(clock, text, sizeof(text));
  ST7735_DrawString(NODE_A_STATUS_LABEL_X, 4, NodeAStatus_PageTitle(page),
                    NODE_A_STATUS_ACCENT, NODE_A_STATUS_BG);
  ST7735_DrawString(NODE_A_STATUS_CLOCK_X, 4, text, NODE_A_STATUS_FG, NODE_A_STATUS_BG);
}

static void DrawEnvironment(const NodeAStatusSnapshot *snapshot)
{
  char text[NODE_A_STATUS_VALUE_MAX];
  DrawHeader(NODE_A_STATUS_PAGE_ENVIRONMENT, &snapshot->clock);

  if (snapshot->sht30_online == 0U)
  {
    (void)snprintf(text, sizeof(text), "OFF");
    DrawRow(0U, "TEMP", text, NODE_A_STATUS_MUTED);
    DrawRow(1U, "HUMI", text, NODE_A_STATUS_MUTED);
  }
  else
  {
    /* Node A has no temperature alarm threshold, so the reading is reported
     * as data and never coloured as a warning the firmware did not raise. */
    FormatDecimal(text, sizeof(text), snapshot->temperature_centi_c, " C");
    DrawRow(0U, "TEMP", text, NODE_A_STATUS_FG);
    FormatDecimal(text, sizeof(text), (int32_t)snapshot->humidity_centi_rh, " %");
    DrawRow(1U, "HUMI", text, NODE_A_STATUS_FG);
  }

  (void)snprintf(text, sizeof(text), "%s",
                 (snapshot->level_detected != 0U) ? "WET" : "DRY");
  DrawRow(2U, "LVL", text,
          (snapshot->level_detected != 0U) ? NODE_A_STATUS_WARNING : NODE_A_STATUS_FG);

  (void)snprintf(text, sizeof(text), "%s",
                 (snapshot->flame_alarm != 0U) ? "FIRE" : "OK");
  DrawRow(3U, "FLAM", text,
          (snapshot->flame_alarm != 0U) ? NODE_A_STATUS_DANGER : NODE_A_STATUS_FG);
}

static void DrawGas(const NodeAStatusSnapshot *snapshot)
{
  char text[NODE_A_STATUS_VALUE_MAX];
  DrawHeader(NODE_A_STATUS_PAGE_GAS, &snapshot->clock);

  /* The oxygen and CO front ends are not calibrated, so their raw counts are
   * shown as data only; the methane and smoke channels are the ones that can
   * raise the alarm page. */
  if (snapshot->oxygen_online == 0U) (void)snprintf(text, sizeof(text), "OFF");
  else (void)snprintf(text, sizeof(text), "%u RAW", (unsigned int)snapshot->oxygen_raw);
  DrawRow(0U, "O2", text,
          (snapshot->oxygen_online == 0U) ? NODE_A_STATUS_MUTED
          : AlarmColor(snapshot->oxygen_alarm, snapshot->oxygen_warning));

  if (snapshot->methane_online == 0U) (void)snprintf(text, sizeof(text), "OFF");
  else if (snapshot->methane_alarm != 0U) (void)snprintf(text, sizeof(text), "ALARM");
  else if (snapshot->methane_warning != 0U) (void)snprintf(text, sizeof(text), "WARN");
  else (void)snprintf(text, sizeof(text), "OK");
  DrawRow(1U, "CH4", text,
          (snapshot->methane_online == 0U) ? NODE_A_STATUS_MUTED
          : AlarmColor(snapshot->methane_alarm, snapshot->methane_warning));

  if (snapshot->co_online == 0U) (void)snprintf(text, sizeof(text), "OFF");
  else (void)snprintf(text, sizeof(text), "%u RAW", (unsigned int)snapshot->co_raw);
  DrawRow(2U, "CO", text,
          (snapshot->co_online == 0U) ? NODE_A_STATUS_MUTED
          : AlarmColor(snapshot->co_alarm, snapshot->co_warning));

  (void)snprintf(text, sizeof(text), "%s",
                 (snapshot->smoke_alarm != 0U) ? "ALARM" : "OK");
  DrawRow(3U, "SMOKE", text,
          (snapshot->smoke_alarm != 0U) ? NODE_A_STATUS_DANGER : NODE_A_STATUS_FG);
}

static void FormatFanRow(char *output, size_t size, uint8_t pwm_percent, uint32_t rpm)
{
  (void)snprintf(output, size, "%3u%% %4uR", (unsigned int)pwm_percent,
                 (unsigned int)rpm);
}

static void FormatPowerRow(char *output, size_t size, uint32_t millivolts,
                           int32_t milliamps)
{
  const int64_t current = (milliamps < 0) ? -(int64_t)milliamps : (int64_t)milliamps;
  (void)snprintf(output, size, "%s%u.%uV %s%u.%02uA", (milliamps < 0) ? "-" : "",
                 (unsigned int)(millivolts / 1000U),
                 (unsigned int)((millivolts / 100U) % 10U),
                 (milliamps < 0) ? "-" : "",
                 (unsigned int)(current / 1000),
                 (unsigned int)((current % 1000) / 10U));
}

static void DrawFans(const NodeAStatusSnapshot *snapshot)
{
  char text[NODE_A_STATUS_VALUE_MAX];
  DrawHeader(NODE_A_STATUS_PAGE_FANS, &snapshot->clock);

  FormatFanRow(text, sizeof(text), snapshot->fan1_pwm_percent, snapshot->fan1_rpm);
  DrawRow(0U, "F1", text, NODE_A_STATUS_FG);
  FormatFanRow(text, sizeof(text), snapshot->fan2_pwm_percent, snapshot->fan2_rpm);
  DrawRow(1U, "F2", text, NODE_A_STATUS_FG);

  if (snapshot->fan1_power_online == 0U) (void)snprintf(text, sizeof(text), "OFF");
  else FormatPowerRow(text, sizeof(text), snapshot->fan1_millivolts,
                      snapshot->fan1_milliamps);
  DrawRow(2U, "P1", text,
          (snapshot->fan1_power_online == 0U) ? NODE_A_STATUS_MUTED : NODE_A_STATUS_FG);

  if (snapshot->fan2_power_online == 0U) (void)snprintf(text, sizeof(text), "OFF");
  else FormatPowerRow(text, sizeof(text), snapshot->fan2_millivolts,
                      snapshot->fan2_milliamps);
  DrawRow(3U, "P2", text,
          (snapshot->fan2_power_online == 0U) ? NODE_A_STATUS_MUTED : NODE_A_STATUS_FG);
}

static void DrawAlarm(const NodeAStatusSnapshot *snapshot)
{
  char text[NODE_A_STATUS_ALARM_TEXT_SIZE];
  char clock[NODE_A_STATUS_CLOCK_TEXT_SIZE];

  ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_DANGER);
  NodeAStatus_FormatClock(&snapshot->clock, clock, sizeof(clock));
  ST7735_DrawString(NODE_A_STATUS_LABEL_X, 4, NodeAStatus_PageTitle(NODE_A_STATUS_PAGE_ALARM),
                    NODE_A_STATUS_FG, NODE_A_STATUS_DANGER);
  ST7735_DrawString(NODE_A_STATUS_CLOCK_X, 4, clock, NODE_A_STATUS_FG,
                    NODE_A_STATUS_DANGER);

  (void)NodeAStatus_DescribeAlarms(snapshot, text, sizeof(text));
  ST7735_DrawString(NODE_A_STATUS_LABEL_X, RowY(0U), text, NODE_A_STATUS_FG,
                    NODE_A_STATUS_DANGER);

  /* The local safety link runs without MQTT, so its state belongs on the page
   * that the alarm opened. */
  (void)snprintf(text, sizeof(text), "%s", (snapshot->relay_on != 0U) ? "ON" : "OFF");
  ST7735_DrawString(NODE_A_STATUS_LABEL_X, RowY(1U), "VENT", NODE_A_STATUS_FG,
                    NODE_A_STATUS_DANGER);
  ST7735_DrawString(NODE_A_STATUS_VALUE_X, RowY(1U), text, NODE_A_STATUS_FG,
                    NODE_A_STATUS_DANGER);
  (void)snprintf(text, sizeof(text), "%s",
                 (snapshot->buzzer_muted != 0U) ? "MUTED" : "ON");
  ST7735_DrawString(NODE_A_STATUS_LABEL_X, RowY(2U), "BUZZ", NODE_A_STATUS_FG,
                    NODE_A_STATUS_DANGER);
  ST7735_DrawString(NODE_A_STATUS_VALUE_X, RowY(2U), text, NODE_A_STATUS_FG,
                    NODE_A_STATUS_DANGER);
}

static void RenderPage(const NodeAStatusModel *model, const NodeAStatusSnapshot *snapshot)
{
  ST7735_BeginFrame();
  switch (model->page)
  {
    case NODE_A_STATUS_PAGE_GAS:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawGas(snapshot);
      break;
    case NODE_A_STATUS_PAGE_FANS:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawFans(snapshot);
      break;
    case NODE_A_STATUS_PAGE_ALARM:
      DrawAlarm(snapshot);
      break;
    case NODE_A_STATUS_PAGE_ENVIRONMENT:
    default:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawEnvironment(snapshot);
      break;
  }
}

void NodeAStatus_Update(NodeAStatusScreen *screen, const NodeAStatusSnapshot *snapshot,
                        uint8_t alarm_active, uint32_t now_ms)
{
  NodeAStatusPage previous;
  uint8_t page_changed, data_changed, refresh_due;

  if ((screen == NULL) || (snapshot == NULL)) return;
  previous = screen->model.page;
  SelectPage(&screen->model, alarm_active, now_ms);

  /* Repaint for a new page, for fresh data, or once per refresh interval.  The
   * comparison is kept cheap enough to run every main-loop iteration. */
  page_changed = (uint8_t)((screen->model.page != previous) || (screen->rendered_once == 0U));
  data_changed = (uint8_t)((screen->rendered_once == 0U) ||
                           (memcmp(&screen->rendered, snapshot, sizeof(*snapshot)) != 0));
  refresh_due = (uint8_t)((screen->rendered_once == 0U) ||
                          ((uint32_t)(now_ms - screen->rendered_at_ms) >=
                           NODE_A_STATUS_REFRESH_MS));
  if ((page_changed == 0U) && (data_changed == 0U) && (refresh_due == 0U)) return;

  RenderPage(&screen->model, snapshot);
  screen->rendered = *snapshot;
  screen->rendered_at_ms = now_ms;
  ++screen->renders;
  if (page_changed != 0U) ++screen->page_changes;
  screen->rendered_once = 1U;
}
