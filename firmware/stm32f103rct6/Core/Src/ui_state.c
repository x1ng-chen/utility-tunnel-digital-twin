#include "ui_state.h"

#include <string.h>

#define UI_COMMAND_TIMEOUT_MS 5000U
#define UI_SELECTION_ANIMATION_MS 140U
#define UI_PAGE_ANIMATION_MS 180U

static UiEffect effect(UiEffectKind kind, uint8_t action, uint8_t value)
{
  UiEffect next;
  next.kind = kind;
  next.action = action;
  next.value = value;
  return next;
}

static uint8_t page_row_count(UiPage page)
{
  switch (page) {
    case UI_HOME: return 7U;
    case UI_MONITOR: return 4U;
    case UI_FANS: return 4U;
    case UI_LIGHT_SOUND: return 3U;
    case UI_SETTINGS: return 2U;
    case UI_OVERVIEW:
    case UI_ALERTS:
    case UI_NETWORK:
    default: return 1U;
  }
}

static uint8_t page_wraps(UiPage page)
{
  return (page == UI_HOME) || (page == UI_FANS) || (page == UI_LIGHT_SOUND);
}

static UiPage home_destination(uint8_t selected_row)
{
  static const UiPage destinations[] = {
    UI_OVERVIEW, UI_MONITOR, UI_ALERTS, UI_FANS,
    UI_LIGHT_SOUND, UI_NETWORK, UI_SETTINGS,
  };
  return destinations[selected_row];
}

static uint8_t action_requires_confirmation(UiAction action)
{
  return (action == UI_ACTION_FANS_BOTH_START) ||
         (action == UI_ACTION_FANS_ALL_STOP) ||
         (action == UI_ACTION_BUZZER_MUTE);
}

static UiAction action_for_selection(const UiState *state)
{
  if (state->page == UI_FANS) {
    switch (state->selected_row) {
      case 0U: return UI_ACTION_FAN_1_PRESET;
      case 1U: return UI_ACTION_FANS_BOTH_START;
      case 2U: return UI_ACTION_FANS_ALL_STOP;
      case 3U: return UI_ACTION_FAN_2_PRESET;
      default: return UI_ACTION_NONE;
    }
  }
  if (state->page == UI_LIGHT_SOUND) {
    switch (state->selected_row) {
      case 0U: return UI_ACTION_LED_MODE;
      case 1U: return UI_ACTION_BUZZER_TEST;
      case 2U: return UI_ACTION_BUZZER_MUTE;
      default: return UI_ACTION_NONE;
    }
  }
  return UI_ACTION_NONE;
}

static void start_selection_animation(UiState *state, uint32_t now_ms)
{
  state->animation_start_ms = now_ms;
  state->animation_end_ms = now_ms + UI_SELECTION_ANIMATION_MS;
}

static void start_page_animation(UiState *state, uint32_t now_ms)
{
  state->animation_start_ms = now_ms;
  state->animation_end_ms = now_ms + UI_PAGE_ANIMATION_MS;
}

static void return_home(UiState *state, uint32_t now_ms)
{
  state->page = UI_HOME;
  state->selected_row = 0U;
  state->dialog = UI_DIALOG_NONE;
  state->command_phase = UI_CMD_IDLE;
  state->pending_action = UI_ACTION_NONE;
  state->pending_value = 0U;
  start_page_animation(state, now_ms);
}

static UiEffect send_pending_command(UiState *state, uint32_t now_ms)
{
  state->dialog = UI_DIALOG_NONE;
  state->command_phase = UI_CMD_SENDING;
  state->command_started_ms = now_ms;
  return effect(UI_EFFECT_SEND_COMMAND, state->pending_action, state->pending_value);
}

void UiState_Init(UiState *state)
{
  if (state == 0) return;
  (void)memset(state, 0, sizeof(*state));
  state->page = UI_HOME;
  state->dialog = UI_DIALOG_NONE;
  state->command_phase = UI_CMD_IDLE;
  state->pending_action = UI_ACTION_NONE;
}

UiEffect UiState_Handle(UiState *state, UiInputEvent event, uint32_t now_ms)
{
  UiAction selected_action;
  uint8_t row_count;

  if ((state == 0) || (event == UI_EVT_NONE)) return effect(UI_EFFECT_NONE, 0U, 0U);

  if (event == UI_EVT_LONG_PRESS) {
    return_home(state, now_ms);
    return effect(UI_EFFECT_GO_HOME, 0U, 0U);
  }

  if (state->dialog == UI_DIALOG_CONFIRM) {
    if ((event == UI_EVT_LEFT) || (event == UI_EVT_UP) || (event == UI_EVT_DOWN)) {
      state->dialog = UI_DIALOG_NONE;
      state->command_phase = UI_CMD_IDLE;
      state->pending_action = UI_ACTION_NONE;
      return effect(UI_EFFECT_DIRTY, 0U, 0U);
    }
    if ((event == UI_EVT_PRESS) || (event == UI_EVT_RIGHT)) return send_pending_command(state, now_ms);
    return effect(UI_EFFECT_NONE, 0U, 0U);
  }

  if (state->command_phase == UI_CMD_SENDING) return effect(UI_EFFECT_NONE, 0U, 0U);

  if (event == UI_EVT_LEFT) {
    if (state->page != UI_HOME) {
      return_home(state, now_ms);
      return effect(UI_EFFECT_GO_HOME, 0U, 0U);
    }
    return effect(UI_EFFECT_NONE, 0U, 0U);
  }

  row_count = page_row_count(state->page);
  if (event == UI_EVT_UP) {
    if (state->selected_row > 0U) {
      --state->selected_row;
    } else if (page_wraps(state->page)) {
      state->selected_row = (uint8_t)(row_count - 1U);
    } else {
      return effect(UI_EFFECT_NONE, 0U, 0U);
    }
    start_selection_animation(state, now_ms);
    return effect(UI_EFFECT_DIRTY, 0U, 0U);
  }
  if (event == UI_EVT_DOWN) {
    if ((uint8_t)(state->selected_row + 1U) < row_count) {
      ++state->selected_row;
    } else if (page_wraps(state->page)) {
      state->selected_row = 0U;
    } else {
      return effect(UI_EFFECT_NONE, 0U, 0U);
    }
    start_selection_animation(state, now_ms);
    return effect(UI_EFFECT_DIRTY, 0U, 0U);
  }

  if ((event != UI_EVT_RIGHT) && (event != UI_EVT_PRESS)) return effect(UI_EFFECT_NONE, 0U, 0U);

  if (state->page == UI_HOME) {
    state->page = home_destination(state->selected_row);
    state->selected_row = 0U;
    start_page_animation(state, now_ms);
    return effect(UI_EFFECT_DIRTY, 0U, 0U);
  }

  selected_action = action_for_selection(state);
  if (selected_action == UI_ACTION_NONE) return effect(UI_EFFECT_NONE, 0U, 0U);

  state->pending_action = (uint8_t)selected_action;
  state->pending_value = 0U;
  if (action_requires_confirmation(selected_action)) {
    state->dialog = UI_DIALOG_CONFIRM;
    state->command_phase = UI_CMD_CONFIRM;
    return effect(UI_EFFECT_OPEN_CONFIRM, state->pending_action, state->pending_value);
  }
  return send_pending_command(state, now_ms);
}

void UiState_Tick(UiState *state, uint32_t now_ms)
{
  if ((state != 0) && (state->command_phase == UI_CMD_SENDING) &&
      ((uint32_t)(now_ms - state->command_started_ms) >= UI_COMMAND_TIMEOUT_MS)) {
    state->command_phase = UI_CMD_TIMEOUT;
  }
}
