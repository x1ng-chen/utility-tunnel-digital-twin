/**
 * @file    node_a_status_screen.c
 * @brief   CTRL-01 read-only status screen: five-second carousel plus a red
 *          alarm page that takes the panel over the moment an alarm latches.
 *
 * The screen renders Node A's local state plus validated peer sensor readings
 * supplied by ESP-01 over its serial link.  It has no command path: it
 * never parses MQTT JSON, never touches an actuator and never
 * reads the joystick (Node A has none).  The page model is HAL-free so the
 * carousel timing and the takeover rules are host-testable; only the drawing
 * helpers below touch the ST7735 driver.
 */
#include "node_a_status_screen.h"

#include <stdio.h>
#include <stdlib.h>
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

#define NODE_A_STATUS_CAROUSEL_PAGES 8U

/* Keep every installed sensor family on one page.  These are inventory
 * indexes, not display row numbers; Node A's three level inputs are local. */
#define PEER_INDEX(index) ((uint8_t)(0x80U | (index)))
static const uint8_t gas_co[] = {0U, 3U, 6U, PEER_INDEX(4U), PEER_INDEX(5U)};
static const uint8_t gas_mq4[] = {1U, 4U, PEER_INDEX(0U), PEER_INDEX(1U), PEER_INDEX(2U)};
static const uint8_t gas_o2[] = {2U, 5U, PEER_INDEX(3U)};
static const uint8_t smoke[] = {0U, 5U, 6U, PEER_INDEX(2U), PEER_INDEX(3U)};
static const uint8_t flame[] = {1U, 3U, 4U, PEER_INDEX(0U), PEER_INDEX(1U)};
static const uint8_t levels[] = {2U, 7U, 8U, PEER_INDEX(4U), PEER_INDEX(5U)};

#define COUNT_OF(array) ((uint8_t)(sizeof(array) / sizeof((array)[0])))

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

uint8_t NodeAStatus_ApplyPeerLine(NodeAStatusPeerState *peer,
                                  const char *line, uint32_t now_ms)
{
  NodeAStatusPeerState next;
  const char *cursor;
  uint8_t parsed = 0U;
  if (peer == NULL || line == NULL) return 0U;
  if (strcmp(line, "PEERDOWN") == 0)
  {
    for (uint8_t i = 0U; i < NODE_A_STATUS_PEER_COUNT; ++i)
      peer->readings[i].seen = 0U;
    return 1U;
  }
  if (strncmp(line, "PEER|", 5U) != 0) return 0U;
  next = *peer;
  cursor = line + 5U;
  do
  {
    char *end;
    unsigned long index, value, quality;
    if (*cursor < '0' || *cursor > '9') return 0U;
    index = strtoul(cursor, &end, 10);
    if (*end != ',' || index >= NODE_A_STATUS_PEER_COUNT) return 0U;
    cursor = end + 1;
    if (*cursor < '0' || *cursor > '9') return 0U;
    value = strtoul(cursor, &end, 10);
    if (*end != ',' || value > ((index < 6U) ? 4095UL : 1UL)) return 0U;
    cursor = end + 1;
    if (*cursor < '0' || *cursor > '3') return 0U;
    quality = strtoul(cursor, &end, 10);
    if (quality > 3UL || (*end != ';' && *end != '\0')) return 0U;
    next.readings[index].value = (uint16_t)value;
    next.readings[index].quality = (SensorQuality)quality;
    next.readings[index].received_at_ms = now_ms;
    next.readings[index].seen = 1U;
    ++parsed;
    cursor = end;
    if (*cursor == ';') ++cursor;
  } while (*cursor != '\0');
  if (parsed == 0U) return 0U;
  *peer = next;
  return 1U;
}

void NodeAStatus_CapturePeer(NodeAStatusSnapshot *snapshot,
                             const NodeAStatusPeerState *peer, uint32_t now_ms)
{
  if (snapshot == NULL || peer == NULL) return;
  for (uint8_t i = 0U; i < NODE_A_STATUS_PEER_COUNT; ++i)
  {
    const NodeAStatusPeerReading *reading = &peer->readings[i];
    const uint8_t fresh = (uint8_t)(reading->seen != 0U &&
        (uint32_t)(now_ms - reading->received_at_ms) <= NODE_A_STATUS_PEER_STALE_MS);
    if (i < NODE_A_STATUS_PEER_ANALOG_COUNT)
    {
      NodeAStatusAnalog *target = &snapshot->peer_analog[i];
      target->enabled = 1U;
      target->online = fresh;
      target->quality = fresh ? reading->quality : SENSOR_QUALITY_MISSING;
      target->raw = fresh ? reading->value : 0U;
    }
    else
    {
      NodeAStatusDigital *target = &snapshot->peer_digital[i - NODE_A_STATUS_PEER_ANALOG_COUNT];
      target->enabled = (uint8_t)(i != 11U); /* L05 is physically removed. */
      target->online = fresh;
      target->quality = fresh ? reading->quality : SENSOR_QUALITY_MISSING;
      target->active_low = fresh ? (uint8_t)reading->value : 0U;
    }
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
    case NODE_A_STATUS_PAGE_CO: return "CO";
    case NODE_A_STATUS_PAGE_MQ4: return "MQ4";
    case NODE_A_STATUS_PAGE_O2: return "O2";
    case NODE_A_STATUS_PAGE_MQ2: return "MQ2";
    case NODE_A_STATUS_PAGE_FLAME: return "FLAME";
    case NODE_A_STATUS_PAGE_LEVELS: return "LEVEL";
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
                    const uint8_t *indices, uint8_t count)
{
  static const char *const labels[NODE_A_STATUS_ANALOG_COUNT] = {
    "CO1", "M41", "O21", "CO2", "M42", "O22", "CO3"
  };
  static const char *const peer_labels[NODE_A_STATUS_PEER_ANALOG_COUNT] = {
    "M43", "M44", "M45", "O23", "CO4", "CO5"
  };
  char text[NODE_A_STATUS_VALUE_MAX];
  DrawHeader(page, &snapshot->clock);

  /* These channels are not calibrated to concentration units.  Display ADC
   * counts, never ppm or a misleading 'OK'.  Planned pins stay PLAN. */
  for (uint8_t row = 0U; row < count; ++row)
  {
    const uint8_t encoded = indices[row];
    const uint8_t remote = (uint8_t)((encoded & 0x80U) != 0U);
    const uint8_t i = (uint8_t)(encoded & 0x7FU);
    const NodeAStatusAnalog *reading = remote ? &snapshot->peer_analog[i] :
                                                &snapshot->analog[i];
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
      if (remote == 0U && i == 0U) color = AlarmColor(snapshot->co_alarm, snapshot->co_warning);
      if (remote == 0U && i == 1U) color = AlarmColor(snapshot->methane_alarm, snapshot->methane_warning);
      if (remote == 0U && i == 2U) color = AlarmColor(snapshot->oxygen_alarm, snapshot->oxygen_warning);
    }
    DrawRow(row, remote ? peer_labels[i] : labels[i], text, color);
  }
}

static void DrawInputs(const NodeAStatusSnapshot *snapshot, NodeAStatusPage page,
                       const uint8_t *indices, uint8_t count)
{
  static const char *const labels[NODE_A_STATUS_DIGITAL_COUNT] = {
    "M21", "FL1", "LV1", "FL2", "FL3", "M22", "M23", "LV2", "LV3"
  };
  static const char *const peer_labels[NODE_A_STATUS_PEER_DIGITAL_COUNT] = {
    "FL4", "FL5", "M24", "M25", "LV4", "LV5"
  };
  char text[NODE_A_STATUS_VALUE_MAX];
  DrawHeader(page, &snapshot->clock);
  for (uint8_t row = 0U; row < count; ++row)
  {
    const uint8_t encoded = indices[row];
    const uint8_t remote = (uint8_t)((encoded & 0x80U) != 0U);
    const uint8_t index = (uint8_t)(encoded & 0x7FU);
    const NodeAStatusDigital *reading = remote ? &snapshot->peer_digital[index] :
                                                 &snapshot->digital[index];
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
    DrawRow(row, remote ? peer_labels[index] : labels[index], text, color);
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
    case NODE_A_STATUS_PAGE_CO:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawGas(snapshot, NODE_A_STATUS_PAGE_CO, gas_co, COUNT_OF(gas_co));
      break;
    case NODE_A_STATUS_PAGE_MQ4:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawGas(snapshot, NODE_A_STATUS_PAGE_MQ4, gas_mq4, COUNT_OF(gas_mq4));
      break;
    case NODE_A_STATUS_PAGE_O2:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawGas(snapshot, NODE_A_STATUS_PAGE_O2, gas_o2, COUNT_OF(gas_o2));
      break;
    case NODE_A_STATUS_PAGE_MQ2:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawInputs(snapshot, NODE_A_STATUS_PAGE_MQ2, smoke, COUNT_OF(smoke));
      break;
    case NODE_A_STATUS_PAGE_FLAME:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawInputs(snapshot, NODE_A_STATUS_PAGE_FLAME, flame, COUNT_OF(flame));
      break;
    case NODE_A_STATUS_PAGE_LEVELS:
      ST7735_FillRect(0, 0, LCD_WIDTH, LCD_HEIGHT, NODE_A_STATUS_BG);
      DrawInputs(snapshot, NODE_A_STATUS_PAGE_LEVELS, levels, COUNT_OF(levels));
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

static uint8_t AnalogRowsChanged(const NodeAStatusSnapshot *before,
                                 const NodeAStatusSnapshot *after,
                                 const uint8_t *indices, uint8_t count)
{
  for (uint8_t row = 0U; row < count; ++row)
  {
    const uint8_t encoded = indices[row];
    const uint8_t index = (uint8_t)(encoded & 0x7FU);
    if ((encoded & 0x80U) != 0U)
    {
      if (memcmp(&before->peer_analog[index], &after->peer_analog[index],
                 sizeof(after->peer_analog[index])) != 0) return 1U;
    }
    else if (memcmp(&before->analog[index], &after->analog[index],
                    sizeof(after->analog[index])) != 0) return 1U;
  }
  return 0U;
}

static uint8_t DigitalRowsChanged(const NodeAStatusSnapshot *before,
                                  const NodeAStatusSnapshot *after,
                                  const uint8_t *indices, uint8_t count)
{
  for (uint8_t row = 0U; row < count; ++row)
  {
    const uint8_t encoded = indices[row];
    const uint8_t index = (uint8_t)(encoded & 0x7FU);
    if ((encoded & 0x80U) != 0U)
    {
      if (memcmp(&before->peer_digital[index], &after->peer_digital[index],
                 sizeof(after->peer_digital[index])) != 0) return 1U;
    }
    else if (memcmp(&before->digital[index], &after->digital[index],
                    sizeof(after->digital[index])) != 0) return 1U;
  }
  return 0U;
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
    case NODE_A_STATUS_PAGE_CO:
      return (uint8_t)(AnalogRowsChanged(before, after, gas_co,
                                         COUNT_OF(gas_co)) != 0U ||
                       before->co_alarm != after->co_alarm ||
                       before->co_warning != after->co_warning);
    case NODE_A_STATUS_PAGE_MQ4:
      return (uint8_t)(AnalogRowsChanged(before, after, gas_mq4,
                                         COUNT_OF(gas_mq4)) != 0U ||
                       before->methane_alarm != after->methane_alarm ||
                       before->methane_warning != after->methane_warning);
    case NODE_A_STATUS_PAGE_O2:
      return (uint8_t)(AnalogRowsChanged(before, after, gas_o2,
                                         COUNT_OF(gas_o2)) != 0U ||
                       before->oxygen_alarm != after->oxygen_alarm ||
                       before->oxygen_warning != after->oxygen_warning);
    case NODE_A_STATUS_PAGE_MQ2:
      return DigitalRowsChanged(before, after, smoke, COUNT_OF(smoke));
    case NODE_A_STATUS_PAGE_FLAME:
      return DigitalRowsChanged(before, after, flame, COUNT_OF(flame));
    case NODE_A_STATUS_PAGE_LEVELS:
      return DigitalRowsChanged(before, after, levels, COUNT_OF(levels));
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
