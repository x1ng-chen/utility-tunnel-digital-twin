#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "menu_command.h"
#include "network_time.h"
#include "screen_snapshot.h"

#define CHECK(condition) do { \
  if (!(condition)) { \
    (void)fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
    return 1; \
  } \
} while (0)

static const char kSnapshot[] =
  "{\"schema\":\"ut.screen.snapshot.v1\",\"source\":\"CTRL-01\","
  "\"generatedAtMs\":1704067205000,\"seq\":7,"
  "\"sensors\":{\"temperature\":[2234,1704067205000,1],"
  "\"humidity\":[5210,1704067205000,1],\"oxygen\":[20900,1704067205000,3],"
  "\"methane\":[12,1704067205000,1],\"carbonMonoxide\":[4,1704067205000,1],"
  "\"smoke\":[1,1704067205000,1],\"water\":[1,1704067205000,1],"
  "\"flame\":[0,1704067205000,1]},\"alarm\":[2,0,2],"
  "\"fans\":[[60,1,2400,11900,320,1704067205000,1],"
  "[30,0,1600,11800,280,1704067205000,1]],"
  "\"actuators\":[true,3,75,true,false],"
  "\"connectivity\":[true,true,false,true,1704067200000],"
  "\"lastCommand\":[\"menu-CTRL-02-1-2\",true,true,1704067204000]}";

static int test_snapshot_validation_and_atomicity(void)
{
  ScreenSnapshotContext context;
  UiSnapshot snapshot;
  UiSnapshot before;
  char malformed[sizeof(kSnapshot)];
  ScreenSnapshot_Init(&context);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  CHECK(ScreenSnapshot_Apply(&context, kSnapshot, strlen(kSnapshot), 100U, &snapshot) == 1U);
  CHECK(snapshot.temperature_centi_c.sampled_ms == 1704067205000ULL);
  CHECK(snapshot.connectivity.updated_ms == 1704067200000ULL);
  CHECK(snapshot.clock.synchronized == 0U);
  before = snapshot;
  (void)snprintf(malformed, sizeof(malformed), "%s", kSnapshot);
  CHECK(strstr(malformed, "\"seq\":7") != NULL);
  (void)memcpy(strstr(malformed, "\"seq\":7") + 8, ",\"seq\":7", 9U);
  CHECK(ScreenSnapshot_Apply(&context, malformed, strlen(malformed), 200U, &snapshot) == 0U);
  CHECK(memcmp(&before, &snapshot, sizeof(snapshot)) == 0);
  CHECK(ScreenSnapshot_Parse(kSnapshot, SCREEN_SNAPSHOT_LINE_SIZE + 1U, &snapshot) == 0U);
  CHECK(ScreenSnapshot_Apply(&context, "{ \"schema\": \"ut.screen.snapshot.v1\"", 39U, 300U, &snapshot) == 0U);
  return 0;
}

static int test_sequence_staleness_wraparound_and_bounds(void)
{
  ScreenSnapshotContext context;
  UiSnapshot snapshot;
  char bounded[sizeof(kSnapshot)];
  ScreenSnapshot_Init(&context);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  (void)snprintf(bounded, sizeof(bounded), "%s", kSnapshot);
  CHECK(ScreenSnapshot_Apply(&context, bounded, strlen(bounded), UINT32_MAX - 100U, &snapshot) == 1U);
  CHECK(ScreenSnapshot_IsStale(&context, 4800U) == 0U);
  CHECK(ScreenSnapshot_IsStale(&context, 4900U) == 1U);
  ScreenSnapshot_Tick(&context, 4900U, &snapshot);
  CHECK(snapshot.temperature_centi_c.quality == UI_QUALITY_STALE);
  return 0;
}

static int test_time_and_mqtt_lifecycle(void)
{
  UiClock clock;
  UiClockSnapshot display;
  UiState state;
  const char line[] = "{ \"schema\" : \"ut.time.sync.v1\", \"source\" : \"ntp\", "
                      "\"state\" : \"synchronized\", \"epochSeconds\" : 1704067200, \"seq\" : 3 }";
  NetworkTime_Init(&clock);
  CHECK(NetworkTime_Update(&clock, line, strlen(line), 100U) == 1U);
  NetworkTime_ToSnapshot(&clock, 61000U, &display);
  CHECK(display.synchronized == 1U && display.hour == 0U && display.minute == 1U);
  CHECK(NetworkTime_Update(&clock, "{\"schema\":\"ut.time.sync.v1\",\"source\":\"ntp\",\"state\":\"synchronized\",\"epochSeconds\":1,\"seq\":4}", 100U, 70000U) == 0U);
  UiState_Init(&state);
  UiState_SetControlAvailability(&state, 1U, 0U);
  CHECK(state.control.mqtt_online == 1U);
  UiState_SetControlAvailability(&state, 0U, 0U);
  CHECK(state.control.mqtt_online == 0U);
  return 0;
}

static int test_commands_and_ack_atomicity(void)
{
  MenuCommandContext context;
  MenuCommandAck ack;
  MenuCommandAck before;
  char line[MENU_COMMAND_LINE_SIZE];
  size_t length;
  const char valid_ack[] = "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"menu-CTRL-02-7-1\",\"status\":\"accepted\",\"reason\":\"buzzer_muted\",\"appliedValue\":0}";
  MenuCommand_Init(&context, 7U);
  CHECK(MenuCommand_Begin(&context, UI_ACTION_BUZZER_MUTE, UI_BUZZER_MUTE, 1704067200000ULL,
                          line, sizeof(line), &length) == 1U);
  CHECK(strstr(line, "\"action\":\"buzzer_mute\"") != NULL);
  CHECK(strstr(line, "\"value\":0") != NULL);
  CHECK(MenuCommand_Begin(&context, UI_ACTION_BUZZER_RESTORE, UI_BUZZER_RESTORE, 1704067200000ULL,
                          line, sizeof(line), &length) == 1U);
  CHECK(strstr(line, "\"action\":\"buzzer_restore\"") != NULL);
  CHECK(strstr(line, "\"value\":0") != NULL);
  (void)memset(&ack, 0xA5, sizeof(ack));
  before = ack;
  CHECK(MenuCommand_ParseAck(valid_ack, strlen(valid_ack) - 1U, &ack) == 0U);
  CHECK(memcmp(&before, &ack, sizeof(ack)) == 0);
  CHECK(MenuCommand_ParseAck(valid_ack, strlen(valid_ack), &ack) == 1U);
  CHECK(MenuCommand_AcceptAck(&context, &ack) == 0U); /* latest active id is restore */
  CHECK(MenuCommand_NextBootId(0U, 0x12345678U) != MenuCommand_NextBootId(1U, 0x12345678U));
  return 0;
}

static int test_send_failure_and_late_ack(void)
{
  UiState state;
  UiState_Init(&state);
  state.command_phase = UI_CMD_SENDING;
  CHECK(UiState_CommandSendFailed(&state) == 1U);
  CHECK(state.command_phase == UI_CMD_REJECTED);
  state.command_phase = UI_CMD_SENDING;
  CHECK(UiState_CommandDispatched(&state, "menu-CTRL-02-1-1") == 1U);
  UiState_Tick(&state, 5000U);
  CHECK(state.command_phase == UI_CMD_TIMEOUT);
  CHECK(UiState_HandleAcknowledgement(&state, "menu-CTRL-02-1-1", 1U) == 0U);
  return 0;
}

int main(void)
{
  if (test_snapshot_validation_and_atomicity() != 0) return 1;
  if (test_sequence_staleness_wraparound_and_bounds() != 0) return 1;
  if (test_time_and_mqtt_lifecycle() != 0) return 1;
  if (test_commands_and_ack_atomicity() != 0) return 1;
  if (test_send_failure_and_late_ack() != 0) return 1;
  (void)puts("Task 8 host test: PASS");
  return 0;
}
