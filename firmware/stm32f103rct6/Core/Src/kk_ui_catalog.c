#include "kk_ui_catalog.h"

#include <stddef.h>

typedef struct {
  const char *label;
  const char *diagnostic_name;
  UiPage destination;
} KkUiHomeItem;

static const KkUiPageDescriptor pages[] = {
  {UI_HOME,        "home",        "main_menu",                7U, 1U},
  {UI_OVERVIEW,    "overview",    "safety_overview",          1U, 0U},
  {UI_MONITOR,     "monitor",     "classified_monitoring",    4U, 0U},
  {UI_ALERTS,      "alerts",      "alarm_center",              1U, 0U},
  {UI_FANS,        "fans",        "fan_control",               4U, 1U},
  {UI_LIGHT_SOUND, "light_sound", "led_and_buzzer",            3U, 1U},
  {UI_NETWORK,     "network",     "communication_status",     1U, 0U},
  {UI_SETTINGS,    "settings",    "system_settings",          2U, 0U},
};

static const KkUiHomeItem home_items[] = {
  {"安全总览",     "safety_overview",       UI_OVERVIEW},
  {"分类监测",     "classified_monitoring", UI_MONITOR},
  {"报警中心",     "alarm_center",           UI_ALERTS},
  {"风机控制",     "fan_control",            UI_FANS},
  {"灯带与蜂鸣器", "led_and_buzzer",         UI_LIGHT_SOUND},
  {"通信状态",     "communication_status",  UI_NETWORK},
  {"系统设置",     "system_settings",       UI_SETTINGS},
};

static const char *const monitor_items[] = {
  "environment", "gases", "water_and_fire", "fan_power",
};

static const char *const fan_items[] = {
  "fan_1_start_stop_30_60_100", "both_start", "all_stop",
  "fan_2_start_stop_30_60_100",
};

static const char *const light_items[] = {
  "led_modes_0_to_15",
  "brightness_25_50_75_100", "buzzer_test_mute_restore",
};

const KkUiPageDescriptor *KK_UI_CatalogPage(UiPage page)
{
  const uint8_t index = (uint8_t)page;
  if (index >= (uint8_t)(sizeof(pages) / sizeof(pages[0]))) return NULL;
  return &pages[index];
}

UiPage KK_UI_CatalogHomeDestination(uint8_t row)
{
  if (row >= (uint8_t)(sizeof(home_items) / sizeof(home_items[0]))) return UI_HOME;
  return home_items[row].destination;
}

const char *KK_UI_CatalogHomeLabel(uint8_t row)
{
  if (row >= (uint8_t)(sizeof(home_items) / sizeof(home_items[0]))) return "";
  return home_items[row].label;
}

const char *KK_UI_CatalogSelectedName(UiPage page, uint8_t row)
{
  switch (page) {
    case UI_HOME:
      return (row < (uint8_t)(sizeof(home_items) / sizeof(home_items[0])))
               ? home_items[row].diagnostic_name : "unknown";
    case UI_OVERVIEW: return "overall_status";
    case UI_MONITOR:
      return (row < (uint8_t)(sizeof(monitor_items) / sizeof(monitor_items[0])))
               ? monitor_items[row] : "unknown";
    case UI_ALERTS: return "active_alarms";
    case UI_FANS:
      return (row < (uint8_t)(sizeof(fan_items) / sizeof(fan_items[0])))
               ? fan_items[row] : "unknown";
    case UI_LIGHT_SOUND:
      return (row < (uint8_t)(sizeof(light_items) / sizeof(light_items[0])))
               ? light_items[row] : "unknown";
    case UI_NETWORK: return "link_summary";
    case UI_SETTINGS: return (row == 0U) ? "display" : "joystick";
    default: return "unknown";
  }
}
