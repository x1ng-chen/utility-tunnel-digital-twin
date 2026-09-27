#ifndef NODE_A_STATUS_SCREEN_H
#define NODE_A_STATUS_SCREEN_H

/* CTRL-01 (Node A) read-only status screen.
 *
 * The secondary display is a pure observer: it renders one atomic snapshot of
 * both boards' sensors and Node A's safety and actuator state, never parses MQTT and never
 * accepts joystick or control input.  The page model below is HAL-free so the
 * carousel, the alarm takeover and the clock placeholder are host-testable;
 * only NodeAStatus_Refresh() touches the ST7735 driver. */

#include <stddef.h>
#include <stdint.h>

#include "multi_sensor.h"
#include "ui_model.h"

/* Normal pages rotate every five seconds; the alarm page preempts them. */
#define NODE_A_STATUS_DWELL_MS        5000U
/* A page is also repainted at least this often so the clock keeps advancing
 * and a sensor that stopped changing still shows its current age. */
#define NODE_A_STATUS_REFRESH_MS      1000U
#define NODE_A_STATUS_CLOCK_TEXT_SIZE    6U
#define NODE_A_STATUS_ALARM_TEXT_SIZE   32U
#define NODE_A_STATUS_SHT_COUNT          4U
#define NODE_A_STATUS_ANALOG_COUNT       7U
#define NODE_A_STATUS_DIGITAL_COUNT      9U
#define NODE_A_STATUS_PEER_ANALOG_COUNT  6U
#define NODE_A_STATUS_PEER_DIGITAL_COUNT 6U
#define NODE_A_STATUS_PEER_COUNT         12U
#define NODE_A_STATUS_PEER_STALE_MS      30000U

/* Page palette (RGB565). Declared here, not in the driver, so the host test
 * can assert what the renderer actually asked the panel to show. */
#define NODE_A_STATUS_BG            0x0000U
#define NODE_A_STATUS_FG            0xFFFFU
#define NODE_A_STATUS_ACCENT        0x07FFU
#define NODE_A_STATUS_MUTED         0x8C71U
#define NODE_A_STATUS_WARNING       0xFFE0U
#define NODE_A_STATUS_DANGER        0xF800U

typedef enum {
  NODE_A_STATUS_PAGE_ENVIRONMENT = 0,
  NODE_A_STATUS_PAGE_CO,
  NODE_A_STATUS_PAGE_MQ4,
  NODE_A_STATUS_PAGE_O2,
  NODE_A_STATUS_PAGE_MQ2,
  NODE_A_STATUS_PAGE_FLAME,
  NODE_A_STATUS_PAGE_LEVELS,
  NODE_A_STATUS_PAGE_FANS,
  NODE_A_STATUS_PAGE_ALARM
} NodeAStatusPage;

typedef struct {
  uint8_t enabled;
  uint8_t online;
  SensorQuality quality;
  int16_t temperature_centi_c;
  uint16_t humidity_centi_rh;
} NodeAStatusSht;

typedef struct {
  uint8_t enabled;
  uint8_t online;
  SensorQuality quality;
  uint16_t raw;
} NodeAStatusAnalog;

typedef struct {
  uint8_t enabled;
  uint8_t online;
  SensorQuality quality;
  /* The planned digital modules are active-low: 1 means the pin is LOW. */
  uint8_t active_low;
} NodeAStatusDigital;

/* One atomic view of the local bank, cached peer sensors, and Node A's
 * safety/actuator state. */
typedef struct {
  /* Environment */
  NodeAStatusSht sht[NODE_A_STATUS_SHT_COUNT];
  NodeAStatusAnalog analog[NODE_A_STATUS_ANALOG_COUNT];
  NodeAStatusDigital digital[NODE_A_STATUS_DIGITAL_COUNT];
  NodeAStatusAnalog peer_analog[NODE_A_STATUS_PEER_ANALOG_COUNT];
  NodeAStatusDigital peer_digital[NODE_A_STATUS_PEER_DIGITAL_COUNT];
  uint8_t level_detected;
  uint8_t flame_alarm;
  /* Gas */
  uint8_t oxygen_online;
  uint8_t methane_online;
  uint8_t co_online;
  uint16_t oxygen_raw;
  uint16_t methane_raw;
  uint16_t co_raw;
  uint8_t oxygen_warning;
  uint8_t oxygen_alarm;
  uint8_t methane_warning;
  uint8_t methane_alarm;
  uint8_t co_warning;
  uint8_t co_alarm;
  uint8_t smoke_alarm;
  uint8_t gas_warning;
  uint8_t gas_alarm;
  /* Fans */
  uint8_t fan1_pwm_percent;
  uint8_t fan2_pwm_percent;
  uint32_t fan1_rpm;
  uint32_t fan2_rpm;
  uint8_t fan1_power_online;
  uint8_t fan2_power_online;
  uint32_t fan1_millivolts;
  uint32_t fan2_millivolts;
  int32_t fan1_milliamps;
  int32_t fan2_milliamps;
  /* Actuators */
  uint8_t relay_on;
  uint8_t buzzer_muted;
  /* Shared network time (ut.time.sync.v1 through network_time) */
  UiClockSnapshot clock;
} NodeAStatusSnapshot;

typedef struct {
  uint16_t value;
  SensorQuality quality;
  uint32_t received_at_ms;
  uint8_t seen;
} NodeAStatusPeerReading;

typedef struct {
  NodeAStatusPeerReading readings[NODE_A_STATUS_PEER_COUNT];
} NodeAStatusPeerState;

typedef struct {
  NodeAStatusPage page;
  uint8_t alarm_active;
  /* Phase origin of the carousel.  Clearing an alarm resets it so the
   * carousel always resumes with a full dwell on the first page. */
  uint32_t carousel_epoch_ms;
} NodeAStatusModel;

typedef struct {
  NodeAStatusModel model;
  NodeAStatusSnapshot rendered;
  uint32_t rendered_at_ms;
  /* Bench diagnostics, reported by the #NODETEST DISPLAY probe. */
  uint32_t renders;
  uint32_t page_changes;
  uint8_t rendered_once;
} NodeAStatusScreen;

void NodeAStatus_Init(NodeAStatusScreen *screen, uint32_t now_ms);

/* Copy the local 4 + 7 + 9 sensor inventory into one display snapshot; no
 * sensor bus access or actuator operation occurs in this helper. */
void NodeAStatus_CaptureInventory(NodeAStatusSnapshot *snapshot,
                                  const SensorReading *readings, uint8_t count);
uint8_t NodeAStatus_ApplyPeerLine(NodeAStatusPeerState *peer,
                                  const char *line, uint32_t now_ms);
void NodeAStatus_CapturePeer(NodeAStatusSnapshot *snapshot,
                             const NodeAStatusPeerState *peer, uint32_t now_ms);

/* Select the page for this tick and repaint when the page, the snapshot or the
 * refresh interval changed.  Waiting for the dwell is never allowed to delay
 * an alarm: a rising alarm_active takes the screen over in the same call. */
void NodeAStatus_Update(NodeAStatusScreen *screen,
                        const NodeAStatusSnapshot *snapshot,
                        uint8_t alarm_active, uint32_t now_ms);

NodeAStatusPage NodeAStatus_CurrentPage(const NodeAStatusScreen *screen);
const char *NodeAStatus_PageTitle(NodeAStatusPage page);
/* Writes "HH:MM", or the "--:--" placeholder until the first valid sync. */
void NodeAStatus_FormatClock(const UiClockSnapshot *clock, char *output,
                             size_t size);
/* Space-separated list of the sources currently in alarm, or "--" if none. */
size_t NodeAStatus_DescribeAlarms(const NodeAStatusSnapshot *snapshot,
                                  char *output, size_t size);

#endif /* NODE_A_STATUS_SCREEN_H */
