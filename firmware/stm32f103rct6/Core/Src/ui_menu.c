#include "ui_menu.h"

#include <string.h>

#include "ui_renderer.h"
#include "ui_state.h"

/* Compatibility adapter for the original bench UI. Node B owns its UiState
 * and UiSnapshot directly; both paths use the same industrial renderer. */
static UiState menu_state;
static UiSnapshot menu_snapshot;
static uint32_t menu_now_ms;

void UI_MenuInit(void)
{
  (void)memset(&menu_snapshot, 0, sizeof(menu_snapshot));
  UiState_Init(&menu_state);
  menu_now_ms = 0U;
  UiRenderer_Init();
}

void UI_MenuSetTelemetry(const UiTelemetry *telemetry)
{
  if (telemetry == NULL) return;
  menu_snapshot.temperature_centi_c.value = (int32_t)telemetry->temperature * 100;
  menu_snapshot.temperature_centi_c.sampled_ms = menu_now_ms;
  menu_snapshot.temperature_centi_c.quality = telemetry->dhtOk ? UI_QUALITY_VALID : UI_QUALITY_INVALID;
  menu_snapshot.humidity_centi_rh.value = (int32_t)telemetry->humidity * 100;
  menu_snapshot.humidity_centi_rh.sampled_ms = menu_now_ms;
  menu_snapshot.humidity_centi_rh.quality = telemetry->dhtOk ? UI_QUALITY_VALID : UI_QUALITY_INVALID;
  menu_snapshot.water_level_raw.value = telemetry->waterRaw;
  menu_snapshot.water_level_raw.sampled_ms = menu_now_ms;
  menu_snapshot.water_level_raw.quality = UI_QUALITY_VALID;
  menu_snapshot.alarm_severity = telemetry->vibrationAlarm ? UI_ALARM_CRITICAL : UI_ALARM_NONE;
  menu_snapshot.alarm_sources = telemetry->vibrationAlarm ? 1U : 0U;
  menu_snapshot.connectivity.mqtt_online = telemetry->telemetryTxEnabled ? 1U : 0U;
  menu_snapshot.connectivity.updated_ms = menu_now_ms;
  UiState_SetControlAvailability(&menu_state, menu_snapshot.connectivity.mqtt_online, 0U);
}

void UI_MenuHandleInput(UiInput input)
{
  UiInputEvent event = UI_EVT_NONE;
  switch (input) {
    case UI_INPUT_UP: event = UI_EVT_UP; break;
    case UI_INPUT_DOWN: event = UI_EVT_DOWN; break;
    case UI_INPUT_LEFT:
    case UI_INPUT_BACK: event = UI_EVT_LEFT; break;
    case UI_INPUT_RIGHT: event = UI_EVT_RIGHT; break;
    case UI_INPUT_OK: event = UI_EVT_PRESS; break;
    case UI_INPUT_NONE:
    default: break;
  }
  if (event != UI_EVT_NONE) (void)UiState_Handle(&menu_state, event, menu_now_ms);
}

void UI_MenuTick(uint32_t nowMs)
{
  menu_now_ms = nowMs;
  UiState_Tick(&menu_state, nowMs);
  (void)UiRenderer_RenderFrame(&menu_state, &menu_snapshot, nowMs);
}

size_t UI_MenuDescribeLayout(char *output, size_t outputSize)
{
  return UiRenderer_DescribeLayout(&menu_state, &menu_snapshot, output, outputSize);
}
