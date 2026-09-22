#include "ui_state.h"

#include <string.h>

#include "kk_ui_catalog.h"

#define UI_COMMAND_TIMEOUT_MS 5000U
#define UI_COMMAND_RESULT_DISPLAY_MS 1500U
#define UI_COMMAND_ID_SIZE 40U

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
  const KkUiPageDescriptor *descriptor = KK_UI_CatalogPage(page);
  return (descriptor != NULL) ? descriptor->row_count : 1U;
}

static uint8_t page_wraps(UiPage page)
{
  const KkUiPageDescriptor *descriptor = KK_UI_CatalogPage(page);
  return (descriptor != NULL) ? descriptor->wraps : 0U;
}

static UiPage home_destination(uint8_t selected_row)
{
  return KK_UI_CatalogHomeDestination(selected_row);
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
      case 0U: return UI_ACTION_FAN_1_SET_DUTY;
      case 1U: return UI_ACTION_FANS_BOTH_START;
      case 2U: return UI_ACTION_FANS_ALL_STOP;
      case 3U: return UI_ACTION_FAN_2_SET_DUTY;
      default: return UI_ACTION_NONE;
    }
  }
  if (state->page == UI_LIGHT_SOUND) {
    switch (state->selected_row) {
      case 0U: return UI_ACTION_LED_MODE;
      case 1U: return UI_ACTION_LED_BRIGHTNESS;
      case 2U:
        if (state->buzzer_option == UI_BUZZER_MUTE) return UI_ACTION_BUZZER_MUTE;
        if (state->buzzer_option == UI_BUZZER_RESTORE) return UI_ACTION_BUZZER_RESTORE;
        return UI_ACTION_BUZZER_TEST;
      default: return UI_ACTION_NONE;
    }
  }
  return UI_ACTION_NONE;
}

static uint8_t selection_has_options(const UiState *state)
{
  return ((state->page == UI_FANS) &&
          ((state->selected_row == 0U) || (state->selected_row == 3U))) ||
         ((state->page == UI_LIGHT_SOUND) && (state->selected_row < 3U));
}

static uint8_t next_fan_duty(uint8_t duty, int8_t direction)
{
  static const uint8_t choices[] = {0U, 30U, 60U, 100U};
  uint8_t index;
  for (index = 0U; index < 4U; ++index) {
    if (choices[index] == duty) break;
  }
  if (index >= 4U) index = 0U;
  index = (direction > 0) ? (uint8_t)((index + 1U) % 4U)
                          : (uint8_t)((index + 3U) % 4U);
  return choices[index];
}

static uint8_t next_brightness(uint8_t brightness, int8_t direction)
{
  static const uint8_t choices[] = {25U, 50U, 75U, 100U};
  uint8_t index;
  for (index = 0U; index < 4U; ++index) {
    if (choices[index] == brightness) break;
  }
  if (index >= 4U) index = 0U;
  index = (direction > 0) ? (uint8_t)((index + 1U) % 4U)
                          : (uint8_t)((index + 3U) % 4U);
  return choices[index];
}

static void step_selected_option(UiState *state, int8_t direction)
{
  if (state->page == UI_FANS) {
    const uint8_t fan = (state->selected_row == 0U) ? 0U : 1U;
    state->fan_duty_option[fan] = next_fan_duty(state->fan_duty_option[fan], direction);
  } else if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 0U)) {
    const int16_t next = (int16_t)state->led_mode_option + direction + 16;
    state->led_mode_option = (UiLedMode)(next % 16);
  } else if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 1U)) {
    state->led_brightness_option = next_brightness(state->led_brightness_option, direction);
  } else if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 2U)) {
    const int16_t next = (int16_t)state->buzzer_option + direction + 3;
    state->buzzer_option = (UiBuzzerOption)(next % 3);
  }
}

static uint8_t selected_option_value(const UiState *state)
{
  if ((state->page == UI_FANS) && (state->selected_row == 0U)) return state->fan_duty_option[0];
  if ((state->page == UI_FANS) && (state->selected_row == 3U)) return state->fan_duty_option[1];
  if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 0U)) {
    return (uint8_t)state->led_mode_option;
  }
  if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 1U)) {
    return state->led_brightness_option;
  }
  return 0U;
}

static uint8_t editable_option_value(const UiState *state)
{
  if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 2U)) {
    return (uint8_t)state->buzzer_option;
  }
  return selected_option_value(state);
}

static void restore_editable_option(UiState *state)
{
  if ((state->page == UI_FANS) && (state->selected_row == 0U)) {
    state->fan_duty_option[0] = state->option_original_value;
  } else if ((state->page == UI_FANS) && (state->selected_row == 3U)) {
    state->fan_duty_option[1] = state->option_original_value;
  } else if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 0U)) {
    state->led_mode_option = (UiLedMode)state->option_original_value;
  } else if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 1U)) {
    state->led_brightness_option = state->option_original_value;
  } else if ((state->page == UI_LIGHT_SOUND) && (state->selected_row == 2U)) {
    state->buzzer_option = (UiBuzzerOption)state->option_original_value;
  }
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

static void clear_command_lifecycle(UiState *state)
{
  state->command_phase = UI_CMD_IDLE;
  state->command_started_ms = 0U;
  state->command_result_started_ms = 0U;
  state->pending_action = UI_ACTION_NONE;
  state->pending_value = 0U;
  state->active_command_id[0] = '\0';
}

static uint8_t command_send_allowed(const UiState *state)
{
  return (state->control.mqtt_online != 0U) && (state->control.safety_locked == 0U);
}

static void return_home(UiState *state, uint32_t now_ms)
{
  state->page = UI_HOME;
  state->selected_row = 0U;
  state->dialog = UI_DIALOG_NONE;
  state->option_editing = 0U;
  if (state->command_phase != UI_CMD_SENDING) clear_command_lifecycle(state);
  start_page_animation(state, now_ms);
}

static UiEffect send_pending_command(UiState *state, uint32_t now_ms)
{
  if (!command_send_allowed(state)) {
    clear_command_lifecycle(state);
    state->dialog = UI_DIALOG_NONE;
    return effect(UI_EFFECT_DIRTY, 0U, 0U);
  }
  state->dialog = UI_DIALOG_NONE;
  state->option_editing = 0U;
  state->command_phase = UI_CMD_SENDING;
  state->command_started_ms = now_ms;
  state->active_command_id[0] = '\0';
  return effect(UI_EFFECT_SEND_COMMAND, state->pending_action, state->pending_value);
}

void UiState_Init(UiState *state)
{
  if (state == 0) return;
  (void)memset(state, 0, sizeof(*state));
  state->page = UI_HOME;
  state->dialog = UI_DIALOG_NONE;
  state->led_brightness_option = 25U;
  clear_command_lifecycle(state);
}

UiEffect UiState_Handle(UiState *state, UiInputEvent event, uint32_t now_ms)
{
  UiAction selected_action;
  uint8_t row_count;

  if ((state == 0) || (event == UI_EVT_NONE)) return effect(UI_EFFECT_NONE, 0U, 0U);

  if (event == UI_EVT_LONG_PRESS) {
    if (state->option_editing) restore_editable_option(state);
    return_home(state, now_ms);
    return effect(UI_EFFECT_GO_HOME, 0U, 0U);
  }

  if (state->dialog == UI_DIALOG_CONFIRM) {
    if (event == UI_EVT_LEFT) {
      state->dialog = UI_DIALOG_NONE;
      clear_command_lifecycle(state);
      return effect(UI_EFFECT_DIRTY, 0U, 0U);
    }
    if ((event == UI_EVT_PRESS) || (event == UI_EVT_RIGHT)) return send_pending_command(state, now_ms);
    return effect(UI_EFFECT_NONE, 0U, 0U);
  }

  if ((state->command_phase == UI_CMD_SENDING) &&
      ((event == UI_EVT_PRESS) || (event == UI_EVT_RIGHT))) return effect(UI_EFFECT_NONE, 0U, 0U);

  if (state->option_editing) {
    if (event == UI_EVT_UP) {
      step_selected_option(state, 1);
      return effect(UI_EFFECT_DIRTY, 0U, 0U);
    }
    if (event == UI_EVT_DOWN) {
      step_selected_option(state, -1);
      return effect(UI_EFFECT_DIRTY, 0U, 0U);
    }
    if (event == UI_EVT_LEFT) {
      restore_editable_option(state);
      state->option_editing = 0U;
      return effect(UI_EFFECT_DIRTY, 0U, 0U);
    }
    if ((event != UI_EVT_RIGHT) && (event != UI_EVT_PRESS)) {
      return effect(UI_EFFECT_NONE, 0U, 0U);
    }

    state->option_editing = 0U;
    selected_action = action_for_selection(state);
    state->pending_action = (uint8_t)selected_action;
    state->pending_value = selected_option_value(state);
    if (action_requires_confirmation(selected_action)) {
      state->dialog = UI_DIALOG_CONFIRM;
      state->command_phase = UI_CMD_CONFIRM;
      return effect(UI_EFFECT_OPEN_CONFIRM, state->pending_action, state->pending_value);
    }
    return send_pending_command(state, now_ms);
  }

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
    state->option_editing = 0U;
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
    state->option_editing = 0U;
    start_selection_animation(state, now_ms);
    return effect(UI_EFFECT_DIRTY, 0U, 0U);
  }

  if ((event != UI_EVT_RIGHT) && (event != UI_EVT_PRESS)) return effect(UI_EFFECT_NONE, 0U, 0U);

  if (state->page == UI_HOME) {
    state->page = home_destination(state->selected_row);
    state->selected_row = 0U;
    state->option_editing = 0U;
    start_page_animation(state, now_ms);
    return effect(UI_EFFECT_DIRTY, 0U, 0U);
  }

  selected_action = action_for_selection(state);
  if (selected_action == UI_ACTION_NONE) return effect(UI_EFFECT_NONE, 0U, 0U);
  if (!command_send_allowed(state)) return effect(UI_EFFECT_DIRTY, 0U, 0U);

  if (selection_has_options(state)) {
    state->option_editing = 1U;
    state->option_original_value = editable_option_value(state);
    return effect(UI_EFFECT_DIRTY, 0U, 0U);
  }

  state->pending_action = (uint8_t)selected_action;
  state->pending_value = selected_option_value(state);
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
    state->command_result_started_ms = now_ms;
  } else if ((state != 0) &&
             ((state->command_phase == UI_CMD_ACCEPTED) ||
              (state->command_phase == UI_CMD_REJECTED) ||
              (state->command_phase == UI_CMD_TIMEOUT)) &&
             ((uint32_t)(now_ms - state->command_result_started_ms) >=
              UI_COMMAND_RESULT_DISPLAY_MS)) {
    clear_command_lifecycle(state);
  }
}

void UiState_SetControlAvailability(UiState *state, uint8_t mqtt_online, uint8_t safety_locked)
{
  if (state == 0) return;
  state->control.mqtt_online = mqtt_online ? 1U : 0U;
  state->control.safety_locked = safety_locked ? 1U : 0U;
}

uint8_t UiState_CommandDispatched(UiState *state, const char *command_id)
{
  uint8_t index;

  if ((state == 0) || (command_id == 0) || (state->command_phase != UI_CMD_SENDING) ||
      (state->active_command_id[0] != '\0') || (command_id[0] == '\0')) return 0U;

  for (index = 0U; index < (UI_COMMAND_ID_SIZE - 1U); ++index) {
    state->active_command_id[index] = command_id[index];
    if (command_id[index] == '\0') return 1U;
  }
  state->active_command_id[UI_COMMAND_ID_SIZE - 1U] = '\0';
  if (command_id[UI_COMMAND_ID_SIZE - 1U] == '\0') return 1U;
  state->active_command_id[0] = '\0';
  return 0U;
}

uint8_t UiState_CommandSendFailed(UiState *state, uint32_t now_ms)
{
  if ((state == 0) || (state->command_phase != UI_CMD_SENDING)) return 0U;
  state->command_phase = UI_CMD_REJECTED;
  state->command_result_started_ms = now_ms;
  return 1U;
}

uint8_t UiState_HandleAcknowledgement(UiState *state, const char *command_id, uint8_t accepted,
                                      uint32_t now_ms)
{
  if ((state == 0) || (command_id == 0) || (state->command_phase != UI_CMD_SENDING) ||
      (state->active_command_id[0] == '\0') || (strcmp(state->active_command_id, command_id) != 0)) {
    return 0U;
  }

  state->command_phase = accepted ? UI_CMD_ACCEPTED : UI_CMD_REJECTED;
  state->command_result_started_ms = now_ms;
  return 1U;
}
