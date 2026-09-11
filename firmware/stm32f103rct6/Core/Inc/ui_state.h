#ifndef UI_STATE_H
#define UI_STATE_H

#include <stdint.h>

#include "ui_model.h"

typedef enum {
  UI_HOME = 0,
  UI_OVERVIEW,
  UI_MONITOR,
  UI_ALERTS,
  UI_FANS,
  UI_LIGHT_SOUND,
  UI_NETWORK,
  UI_SETTINGS,
} UiPage;

typedef enum {
  UI_EVT_NONE = 0,
  UI_EVT_UP,
  UI_EVT_DOWN,
  UI_EVT_LEFT,
  UI_EVT_RIGHT,
  UI_EVT_PRESS,
  UI_EVT_LONG_PRESS,
} UiInputEvent;

typedef enum {
  UI_CMD_IDLE = 0,
  UI_CMD_CONFIRM,
  UI_CMD_SENDING,
  UI_CMD_ACCEPTED,
  UI_CMD_REJECTED,
  UI_CMD_TIMEOUT,
} UiCommandPhase;

typedef enum {
  UI_EFFECT_NONE = 0,
  UI_EFFECT_DIRTY,
  UI_EFFECT_OPEN_CONFIRM,
  UI_EFFECT_SEND_COMMAND,
  UI_EFFECT_GO_HOME,
} UiEffectKind;

typedef enum {
  UI_DIALOG_NONE = 0,
  UI_DIALOG_CONFIRM,
} UiDialog;

typedef enum {
  UI_ACTION_NONE = 0,
  UI_ACTION_FAN_1_PRESET,
  UI_ACTION_FANS_BOTH_START,
  UI_ACTION_FANS_ALL_STOP,
  UI_ACTION_FAN_2_PRESET,
  UI_ACTION_LED_MODE,
  UI_ACTION_BUZZER_TEST,
  UI_ACTION_BUZZER_MUTE,
} UiAction;

typedef struct {
  UiEffectKind kind;
  uint8_t action;
  uint8_t value;
} UiEffect;

typedef struct {
  uint8_t mqtt_online;
  uint8_t safety_locked;
} UiControlAvailability;

typedef struct {
  UiPage page;
  uint8_t selected_row;
  UiDialog dialog;
  uint32_t animation_start_ms;
  uint32_t animation_end_ms;
  UiCommandPhase command_phase;
  uint32_t command_started_ms;
  uint8_t pending_action;
  uint8_t pending_value;
  UiControlAvailability control;
  char active_command_id[40];
} UiState;

void UiState_Init(UiState *state);
UiEffect UiState_Handle(UiState *state, UiInputEvent event, uint32_t now_ms);
void UiState_Tick(UiState *state, uint32_t now_ms);
void UiState_SetControlAvailability(UiState *state, uint8_t mqtt_online, uint8_t safety_locked);
uint8_t UiState_CommandDispatched(UiState *state, const char *command_id);
uint8_t UiState_HandleAcknowledgement(UiState *state, const char *command_id, uint8_t accepted);

#endif /* UI_STATE_H */
