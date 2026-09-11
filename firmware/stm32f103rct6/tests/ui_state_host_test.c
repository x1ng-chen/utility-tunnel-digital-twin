#include <stdio.h>
#include <string.h>

#include "ui_state.h"

#define CHECK(condition) do { \
  if (!(condition)) { \
    (void)fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    return 1; \
  } \
} while (0)

static int start_critical_sending(UiState *state)
{
  UiEffect next;

  UiState_Init(state);
  UiState_SetControlAvailability(state, 1U, 0U);
  (void)UiState_Handle(state, UI_EVT_DOWN, 1U);
  (void)UiState_Handle(state, UI_EVT_DOWN, 2U);
  (void)UiState_Handle(state, UI_EVT_DOWN, 3U);
  (void)UiState_Handle(state, UI_EVT_PRESS, 4U);
  CHECK(state->page == UI_FANS);
  (void)UiState_Handle(state, UI_EVT_DOWN, 5U);
  next = UiState_Handle(state, UI_EVT_PRESS, 6U);
  CHECK(next.kind == UI_EFFECT_OPEN_CONFIRM);
  next = UiState_Handle(state, UI_EVT_PRESS, 7U);
  CHECK(next.kind == UI_EFFECT_SEND_COMMAND);
  CHECK(state->command_phase == UI_CMD_SENDING);
  return 0;
}

static int start_critical_command(UiState *state, const char *command_id)
{
  if (start_critical_sending(state) != 0) return 1;
  CHECK(UiState_CommandDispatched(state, command_id) == 1U);
  return 0;
}

static int move_to_critical_fans_row(UiState *state)
{
  UiState_Init(state);
  (void)UiState_Handle(state, UI_EVT_DOWN, 1U);
  (void)UiState_Handle(state, UI_EVT_DOWN, 2U);
  (void)UiState_Handle(state, UI_EVT_DOWN, 3U);
  (void)UiState_Handle(state, UI_EVT_PRESS, 4U);
  (void)UiState_Handle(state, UI_EVT_DOWN, 5U);
  CHECK(state->page == UI_FANS);
  CHECK(state->selected_row == 1U);
  return 0;
}

int main(void)
{
  UiState state;
  UiEffect next;
  static const char maximum_command_id[] = "012345678901234567890123456789012345678";
  static const char over_capacity_command_id[] = "0123456789012345678901234567890123456789";

  _Static_assert(sizeof(maximum_command_id) == 40U, "maximum command ID must be 39 characters");
  _Static_assert(sizeof(over_capacity_command_id) == 41U, "over-capacity command ID must be 40 characters");

  if (start_critical_command(&state, "keep-1") != 0) return 1;
  next = UiState_Handle(&state, UI_EVT_LONG_PRESS, 8U);
  CHECK(next.kind == UI_EFFECT_GO_HOME);
  CHECK(state.page == UI_HOME);
  CHECK(state.selected_row == 0U);
  CHECK(state.command_phase == UI_CMD_SENDING);
  CHECK(strcmp(state.active_command_id, "keep-1") == 0);
  CHECK(UiState_Handle(&state, UI_EVT_PRESS, 9U).kind == UI_EFFECT_NONE);
  CHECK(state.command_phase == UI_CMD_SENDING);

  CHECK(UiState_HandleAcknowledgement(&state, "other-1", 1U) == 0U);
  CHECK(state.command_phase == UI_CMD_SENDING);
  CHECK(UiState_HandleAcknowledgement(&state, "keep-1", 1U) == 1U);
  CHECK(state.command_phase == UI_CMD_ACCEPTED);

  if (start_critical_command(&state, "reject-1") != 0) return 1;
  CHECK(UiState_HandleAcknowledgement(&state, "reject-1", 0U) == 1U);
  CHECK(state.command_phase == UI_CMD_REJECTED);

  if (start_critical_command(&state, "timeout-1") != 0) return 1;
  UiState_Tick(&state, state.command_started_ms + 5000U);
  CHECK(state.command_phase == UI_CMD_TIMEOUT);
  CHECK(UiState_HandleAcknowledgement(&state, "timeout-1", 1U) == 0U);
  CHECK(state.command_phase == UI_CMD_TIMEOUT);

  if (start_critical_sending(&state) != 0) return 1;
  CHECK(UiState_CommandDispatched(&state, maximum_command_id) == 1U);
  CHECK(strcmp(state.active_command_id, maximum_command_id) == 0);
  CHECK(UiState_HandleAcknowledgement(&state, maximum_command_id, 1U) == 1U);
  CHECK(state.command_phase == UI_CMD_ACCEPTED);

  if (start_critical_sending(&state) != 0) return 1;
  CHECK(UiState_CommandDispatched(&state, over_capacity_command_id) == 0U);
  CHECK(state.active_command_id[0] == '\0');

  if (move_to_critical_fans_row(&state) != 0) return 1;
  next = UiState_Handle(&state, UI_EVT_PRESS, 6U);
  CHECK(next.kind == UI_EFFECT_DIRTY);
  CHECK(state.dialog == UI_DIALOG_NONE);
  CHECK(state.command_phase == UI_CMD_IDLE);

  if (move_to_critical_fans_row(&state) != 0) return 1;
  UiState_SetControlAvailability(&state, 1U, 1U);
  next = UiState_Handle(&state, UI_EVT_PRESS, 6U);
  CHECK(next.kind == UI_EFFECT_DIRTY);
  CHECK(state.dialog == UI_DIALOG_NONE);
  CHECK(state.command_phase == UI_CMD_IDLE);

  (void)puts("UiState host test: PASS");
  return 0;
}
