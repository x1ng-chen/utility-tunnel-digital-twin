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
#define NODE_A_STATUS_ENV_VALUE_X 28
#define NODE_A_STATUS_ROW_TOP    26
#define NODE_A_STATUS_ROW_STEP   16
#define NODE_A_STATUS_CLOCK_X    (LCD_WIDTH - 5 * 8)

#define NODE_A_STATUS_VALUE_MAX  24

static int RowY(uint8_t row)
{
  return NODE_A_STATUS_ROW_TOP + ((int)row * NODE_A_STATUS_ROW_STEP);
}

#define NODE_A_STATUS_CAROUSEL_PAGES 6U

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

void NodeAStatus_CaptureInventory(NodeAStatusSnapshot *snapshot,
                                  const SensorReading *readings, uint8_t count)
{
  uint8_t index = 0U;
  if (snapshot == NULL || readings == NULL) return;
  (void)memset(snapshot->sht, 0, sizeof(snapshot->sht));
  (void)memset(snapshot->analog, 0, sizeof(snapshot->analog));
  (void)memset(snapshot->digital, 0, sizeof(snapshot->digital));

  for (uint8_t i = 0U; i < NODE_A_STATUS_SHT_COUNT && index < count; ++i, ++index)
  {
    const SensorReading *source = &readings[index];
    NodeAStatusSht *target = &snapshot->sht[i];
    target->enabled = source->enabled;
    target->online = source->online;
    target->quality = source->quality;
    target->temperature_centi_c = source->temperature_centi_c;
    target->humidity_centi_rh = source->humidity_centi_rh;
  }
  for (uint8_t i = 0U; i < NODE_A_STATUS_ANALOG_COUNT && index < count; ++i, ++index)
  {
    const SensorReading *source = &readings[index];
    NodeAStatusAnalog *target = &snapshot->analog[i];
    target->enabled = source->enabled;
    target->online = source->online;
    target->quality = source->quality;
    target->raw = source->raw;
  }
  for (uint8_t i = 0U; i < NODE_A_STATUS_DIGITAL_COUNT && index < count; ++i, ++index)
  {
    const SensorReading *source = &readings[index];
    NodeAStatusDigital *target = &snapshot->digital[i];
    target->enabled = source->enabled;
    target->online = source->online;
    target->quality = source->quality;
    target->active_low = source->digital_value;
  }
}

NodeAStatusPage NodeAStatus_CurrentPage(const NodeAStatusScreen *screen)
{
  return (screen == NULL) ? NODE_A_STATUS_PAGE_ENVIRONMENT : screen->model.page;
}

const char *NodeAStatus_PageTitle(NodeAStatusPage page)
{
  switch (page)
  {
    case NODE_A_STATUS_PAGE_GAS_1: return "GAS1";
    case NODE_A_STATUS_PAGE_GAS_2: return "GAS2";
    case NODE_A_STATUS_PAGE_INPUTS_1: return "INPUT1";
    case NODE_A_STATUS_PAGE_INPUTS_2: return "INPUT2";
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

static void FormatShtCompact(char *output, size_t size, int16_t temperature_centi_c,
                             uint16_t humidity_centi_rh)
{
  int32_t value = temperature_centi_c;
  const char *sign = "";
  if (value < 0) { sign = "-"; value = -value; }
  value = (value + 5) / 10; /* One decimal keeps four SHT rows legible. */
  (void)snprintf(output, size, "%s%u.%uC %u%%", sign,
                 (unsigned int)(value / 10), (unsigned int)(value % 10),
                 (unsigned int)((humidity_centi_rh + 50U) / 100U));
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
  char label[4];
  DrawHeader(NODE_A_STATUS_PAGE_ENVIRONMENT, &snapshot->clock);

  /* The actual panel is 128x128: four compact T/H rows fit without clipping. */
  for (uint8_t i = 0U; i < NODE_A_STATUS_SHT_COUNT; ++i)
  {
    const NodeAStatusSht *reading = &snapshot->sht[i];
    const uint16_t color = (reading->enabled != 0U && reading->online != 0U &&
                            reading->quality == SENSOR_QUALITY_GOOD &&
                            reading->temperature_centi_c >= -4500 &&
                            reading->temperature_centi_c <= 13000 &&
                            reading->humidity_centi_rh <= 10000U)
                               ? NODE_A_STATUS_FG : NODE_A_STATUS_MUTED;
    const char *unavailable = (reading->enabled == 0U) ? "PLAN" :
                              (reading->online == 0U || reading->quality == SENSOR_QUALITY_MISSING)
                                  ? "OFF" : "BAD";
    (void)snprintf(label, sizeof(label), "S%u", (unsigned int)(i + 1U));
    if (color == NODE_A_STATUS_FG)
      FormatShtCompact(text, sizeof(text), reading->temperature_centi_c,
                       reading->humidity_centi_rh);
    else (void)snprintf(text, sizeof(text), "%s", unavailable);
    ST7735_DrawString(NODE_A_STATUS_LABEL_X, RowY(i), label,
                      NODE_A_STATUS_MUTED, NODE_A_STATUS_BG);
    ST7735_DrawString(NODE_A_STATUS_ENV_VALUE_X, RowY(i), text,
                      color, NODE_A_STATUS_BG);
  }
}

static void DrawGas(const NodeAStatusSnapshot *snapshot, NodeAStatusPage page,
                    uint8_t first, uint8_t count)
{
  static const char *const labels[NODE_A_STATUS_ANALOG_COUNT] = {
    "CO1", "M41", "O21", "CO2", "M42", "O22", "CO3"
  };
  char text[NODE_A_STATUS_VALUE_MAX];
  DrawHeader(page, &snapshot->clock);

  /* These channels are not calibrated to concentration units.  Display ADC
   * counts, never ppm or a misleading 'OK'.  Planned pins stay PLAN. */
  for (uint8_t row = 0U; row < count; ++row)
  {
    const uint8_t i = (uint8_t)(first + row);
    const NodeAStatusAnalog *reading = &snapshot->analog[i];
    uint16_t color = NODE_A_STATUS_MUTED;
    if (reading->enabled == 0U) (void)snprintf(text, sizeof(text), "PLAN");
    else if (reading->online == 0U || reading->quality == SENSOR_QUALITY_MISSING)
      (void)snprintf(text, sizeof(text), "OFF");
    else if (reading->quality == SENSOR_QUALITY_BAD)
      (void)snprintf(text, sizeof(text), "BAD");
    else
    {
      (void)snprintf(text, sizeof(text), "%u RAW", (unsigned int)reading->raw);
      color = NODE_A_STATUS_FG;
      if (i == 0U) color = AlarmColor(snapshot->co_alarm, snapshot->co_warning);
      if (i == 1U) color = AlarmColor(snapshot->methane_alarm, snapshot->methane_warning);
      if (i == 2U) color = AlarmColor(snapshot->oxygen_alarm, snapshot->oxygen_warning);
    }
    DrawRow(row, labels[i], text, color);
  }
}

static void DrawInputs(const NodeAStatusSnapshot *snapshot, NodeAStatusPage page,
                       uint8_t first, uint8_t count)
{
  static const char *const labels[NODE_A_STATUS_DIGITAL_COUNT] = {
    "M21", "FL1", "LV1", "FL2", "FL3", "M22", "M23", "LV2", "LV3"
  };
  char text[NODE_A_STATUS_VALUE_MAX];
  DrawHeader(page, &snapshot->clock);
  for (uint8_t row = 0U; row < count; ++row)
  {
    const uint8_t index = (uint8_t)(first + row);
    const NodeAStatusDigital *reading = &snapshot->digital[index];
    uint16_t color = NODE_A_STATUS_MUTED;
    if (reading->enabled == 0U) (void)snprintf(text, sizeof(text), "PLAN");
    else if (reading->online == 0U || reading->quality == SENSOR_QUALITY_MISSING)
      (void)snprintf(text, sizeof(text), "OFF");
    else if (reading->quality == SENSOR_QUALITY_BAD)
      (void)snprintf(text, sizeof(text), "BAD");
    else
    {
      /* Report the electrical input state, not an unverified sensor verdict. */
      (void)snprintf(text, sizeof(text), "%s", reading->active_low ? "LOW" : "HIGH");
      color = reading->active_low ? NODE_A_STATUS_WARNING : NODE_A_STATUS_FG;
    }
    DrawRow(row, labels[index], text, color);
  }
}

static void FormatFanRow(char *output, size_t size, uint8_t pwm_percent, uint32_t rpm)
{
  (void)snprintf(output, size, "%3u%% %4uR", (unsigned int)pwm_percent,
                 (unsigned int)rpm);
}

/* The unsigned fields are reduced before formatting, not merely before the
 * division: -Wformat-truncation otherwise has to assume every one of them can
 * print all ten digits of a 32-bit value, and would flag this row as possibly
 * overflowing the 24-byte value buffer.  These ceilings are far above anything
 * a 0.01 V / 0.01 A fan meter on a 12 V rail can report, so no real reading is
 * altered; a reading that somehow exceeded them would show its low-order digits
 * rather than overrun the panel buffer. */
#define NODE_A_STATUS_VOLT_MAX_MV   1000000UL
#define NODE_A_STATUS_CURR_MAX_MA  10000000UL

static void FormatPowerRow(char *output, size_t size, uint32_t millivolts,
                           int32_t milliamps)
{
  const uint32_t magnitude =
      ((milliamps < 0) ? (uint32_t)(-(int64_t)milliamps) : (uint32_t)milliamps) %
      NODE_A_STATUS_CURR_MAX_MA;

  (void)snprintf(output, size, "%s%u.%uV %s%u.%02uA", (milliamps < 0) ? "-" : "",
                 (unsigned int)((millivolts % NODE_A_STATUS_VOLT_MAX_MV) / 1000U),
                 (unsigned int)((millivolts / 100U) % 10U),
                 (milliamps < 0) ? "-" : "",
                 (unsigned int)(magnitude / 1000U),
                 (unsigned int)((magnitude % 1000U) / 10U));
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
    case NODE_A_STATUS_PAGE_GAS_1:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawGas(snapshot, NODE_A_STATUS_PAGE_GAS_1, 0U, 4U);
      break;
    case NODE_A_STATUS_PAGE_GAS_2:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawGas(snapshot, NODE_A_STATUS_PAGE_GAS_2, 4U, 3U);
      break;
    case NODE_A_STATUS_PAGE_INPUTS_1:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawInputs(snapshot, NODE_A_STATUS_PAGE_INPUTS_1, 0U, 5U);
      break;
    case NODE_A_STATUS_PAGE_INPUTS_2:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawInputs(snapshot, NODE_A_STATUS_PAGE_INPUTS_2, 5U, 4U);
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

static uint8_t VisibleDataChanged(NodeAStatusPage page,
                                  const NodeAStatusSnapshot *before,
                                  const NodeAStatusSnapshot *after)
{
  if (before->clock.synchronized != after->clock.synchronized ||
      before->clock.hour != after->clock.hour ||
      before->clock.minute != after->clock.minute) return 1U;
  switch (page)
  {
    case NODE_A_STATUS_PAGE_ENVIRONMENT:
      return (uint8_t)(memcmp(before->sht, after->sht, sizeof(after->sht)) != 0);
    case NODE_A_STATUS_PAGE_GAS_1:
      return (uint8_t)(memcmp(before->analog, after->analog,
                             4U * sizeof(after->analog[0])) != 0 ||
                       before->co_alarm != after->co_alarm ||
                       before->co_warning != after->co_warning ||
                       before->methane_alarm != after->methane_alarm ||
                       before->methane_warning != after->methane_warning ||
                       before->oxygen_alarm != after->oxygen_alarm ||
                       before->oxygen_warning != after->oxygen_warning);
    case NODE_A_STATUS_PAGE_GAS_2:
      return (uint8_t)(memcmp(&before->analog[4], &after->analog[4],
                             3U * sizeof(after->analog[0])) != 0);
    case NODE_A_STATUS_PAGE_INPUTS_1:
      return (uint8_t)(memcmp(before->digital, after->digital,
                             5U * sizeof(after->digital[0])) != 0);
    case NODE_A_STATUS_PAGE_INPUTS_2:
      return (uint8_t)(memcmp(&before->digital[5], &after->digital[5],
                             4U * sizeof(after->digital[0])) != 0);
    case NODE_A_STATUS_PAGE_FANS:
      return (uint8_t)(before->fan1_pwm_percent != after->fan1_pwm_percent ||
                       before->fan2_pwm_percent != after->fan2_pwm_percent ||
                       before->fan1_rpm != after->fan1_rpm ||
                       before->fan2_rpm != after->fan2_rpm ||
                       before->fan1_power_online != after->fan1_power_online ||
                       before->fan2_power_online != after->fan2_power_online ||
                       before->fan1_millivolts != after->fan1_millivolts ||
                       before->fan2_millivolts != after->fan2_millivolts ||
                       before->fan1_milliamps != after->fan1_milliamps ||
                       before->fan2_milliamps != after->fan2_milliamps);
    case NODE_A_STATUS_PAGE_ALARM:
      return (uint8_t)(before->gas_alarm != after->gas_alarm ||
                       before->methane_alarm != after->methane_alarm ||
                       before->smoke_alarm != after->smoke_alarm ||
                       before->flame_alarm != after->flame_alarm ||
                       before->relay_on != after->relay_on ||
                       before->buzzer_muted != after->buzzer_muted);
    default:
      return 1U;
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
                           VisibleDataChanged(screen->model.page, &screen->rendered,
                                              snapshot));
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
