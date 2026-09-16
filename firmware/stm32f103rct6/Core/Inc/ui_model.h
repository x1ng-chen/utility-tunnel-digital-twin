#ifndef UI_MODEL_H
#define UI_MODEL_H

#include <stdint.h>

/* This display model is deliberately independent of Cube/HAL types. */
typedef enum {
  UI_QUALITY_UNKNOWN = 0,
  UI_QUALITY_VALID,
  UI_QUALITY_STALE,
  UI_QUALITY_INVALID,
  UI_QUALITY_MISSING,
} UiDataQuality;

#ifndef SCREEN_SENSOR_CAPACITY
#define SCREEN_SENSOR_CAPACITY 32U
#endif

typedef enum {
  SCREEN_SENSOR_KIND_SHT30 = 0,
  SCREEN_SENSOR_KIND_FLAME = 1,
  SCREEN_SENSOR_KIND_MQ4 = 2,
  SCREEN_SENSOR_KIND_MQ2 = 3,
  SCREEN_SENSOR_KIND_O2 = 4,
  SCREEN_SENSOR_KIND_CO = 5,
  SCREEN_SENSOR_KIND_LEVEL = 6,
} ScreenSensorKind;

typedef struct {
  char asset_code[12];
  uint8_t kind;
  int32_t value;
  int32_t scale;
  UiDataQuality quality;
  uint8_t alarm;
  char source[8];
  uint64_t updated_at_ms;
} ScreenSensorReading;

typedef enum {
  UI_ALARM_NONE = 0,
  UI_ALARM_WARNING,
  UI_ALARM_CRITICAL,
} UiAlarmSeverity;

typedef enum {
  UI_LED_OFF = 0,
  UI_LED_WHITE,
  UI_LED_GREEN,
  UI_LED_YELLOW,
  UI_LED_RED,
  UI_LED_BLUE,
  UI_LED_BREATHE,
  UI_LED_FLASH,
} UiLedMode;

typedef enum {
  UI_ALARM_SOURCE_TEMPERATURE = (1U << 0),
  UI_ALARM_SOURCE_HUMIDITY = (1U << 1),
  UI_ALARM_SOURCE_OXYGEN = (1U << 2),
  UI_ALARM_SOURCE_METHANE = (1U << 3),
  UI_ALARM_SOURCE_CARBON_MONOXIDE = (1U << 4),
  UI_ALARM_SOURCE_SMOKE = (1U << 5),
  UI_ALARM_SOURCE_WATER = (1U << 6),
  UI_ALARM_SOURCE_FLAME = (1U << 7),
} UiAlarmSource;

#define UI_ALARM_SOURCE_MASK 0xFFU

typedef struct {
  int32_t value;
  uint64_t sampled_ms;
  UiDataQuality quality;
} UiReading;

typedef struct {
  uint8_t target_duty_percent;
  uint8_t running;
  uint32_t actual_rpm;
  uint16_t voltage_mv;
  uint16_t current_ma;
  uint64_t sampled_ms;
  UiDataQuality quality;
} UiFanSnapshot;

typedef struct {
  uint8_t relay_on;
  UiLedMode led_mode;
  uint8_t led_brightness_percent;
  uint8_t buzzer_on;
  uint8_t buzzer_muted;
} UiActuatorSnapshot;

/* Mirrors screen_protocol::LinkStatus on the ESP side.  Unknown is a real
 * state: nothing in the current interface supplies an observed status for the
 * IoTDA gateway or the cloud session, so the network page must not render
 * those rows as OFFLINE. */
typedef enum {
  UI_LINK_UNKNOWN = 0,
  UI_LINK_ONLINE,
  UI_LINK_OFFLINE,
} UiLinkStatus;

typedef struct {
  uint8_t node_a;
  uint8_t mqtt;
  uint8_t gateway;
  uint8_t iotda;
  uint64_t updated_ms;
} UiConnectivitySnapshot;

typedef struct {
  char command_id[40];
  uint8_t accepted;
  uint8_t complete;
  uint64_t completed_ms;
} UiCommandResult;

typedef struct {
  uint8_t synchronized;
  uint8_t hour;
  uint8_t minute;
} UiClockSnapshot;

typedef struct {
  UiReading temperature_centi_c;
  UiReading humidity_centi_rh;
  UiReading oxygen_milli_percent;
  UiReading methane_ppm;
  UiReading carbon_monoxide_ppm;
  UiReading smoke;
  UiReading water_level_raw;
  UiReading flame;
  UiAlarmSeverity alarm_severity;
  /* warning_sources and critical_sources retain simultaneous severities.
   * alarm_sources is the legacy combined field accepted until Task 5. */
  uint32_t warning_sources;
  uint32_t critical_sources;
  uint32_t alarm_sources;
  UiFanSnapshot fans[2];
  UiActuatorSnapshot actuators;
  UiConnectivitySnapshot connectivity;
  UiCommandResult last_command;
  UiClockSnapshot clock;
  uint8_t sensor_count;
  ScreenSensorReading sensors[SCREEN_SENSOR_CAPACITY];
  char alarm_label[16];
} UiSnapshot;

#endif /* UI_MODEL_H */
