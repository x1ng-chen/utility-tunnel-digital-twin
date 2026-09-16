#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "menu_command.h"
#include "network_time.h"
#include "screen_snapshot.h"
#include "ui_renderer.h"

void ST7735_Clear(uint16_t color) { (void)color; }
void ST7735_BeginFrame(void) {}
uint8_t ST7735_FrameFailed(void) { return 0U; }
void ST7735_FillRect(int x, int y, int w, int h, uint16_t color)
{ (void)x; (void)y; (void)w; (void)h; (void)color; }
void ST7735_DrawGlyph16(int x, int y, const uint8_t glyph[32], uint16_t color, uint16_t bg)
{ (void)x; (void)y; (void)glyph; (void)color; (void)bg; }
void ST7735_DrawChar(int x, int y, char c, uint16_t color, uint16_t bg)
{ (void)x; (void)y; (void)c; (void)color; (void)bg; }
void ST7735_DrawString(int x, int y, const char *str, uint16_t color, uint16_t bg)
{ (void)x; (void)y; (void)str; (void)color; (void)bg; }

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
  /* node_a, mqtt, gateway, iotda as UiLinkStatus ordinals.  The gateway is
   * UNKNOWN (0), not a false OFFLINE: nothing on this wire observes it. */
  "\"connectivity\":[1,1,0,0,1704067200000],"
  "\"lastCommand\":[\"menu-CTRL-02-1-2\",true,true,1704067204000]}";

static int test_snapshot_validation_and_atomicity(void)
{
  ScreenSnapshotContext context;
  UiSnapshot snapshot;
  UiSnapshot before;
  UiState state;
  char malformed[sizeof(kSnapshot)];
  const char truncated[] = "{ \"schema\": \"ut.screen.snapshot.v1\"";
  ScreenSnapshot_Init(&context);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  CHECK(ScreenSnapshot_Apply(&context, kSnapshot, strlen(kSnapshot), 100U, &snapshot) == 1U);
  CHECK(snapshot.temperature_centi_c.sampled_ms == 1704067205000ULL);
  CHECK(snapshot.connectivity.updated_ms == 1704067200000ULL);
  CHECK(snapshot.clock.synchronized == 0U);
  UiState_Init(&state);
  UiState_SetControlAvailability(&state, (uint8_t)(snapshot.connectivity.mqtt == UI_LINK_ONLINE), 0U);
  CHECK(state.control.mqtt_online == 1U);
  ScreenSnapshot_SetMqttAvailability(&snapshot, 0U, 100U);
  UiState_SetControlAvailability(&state, (uint8_t)(snapshot.connectivity.mqtt == UI_LINK_ONLINE), 0U);
  CHECK(state.control.mqtt_online == 0U);
  before = snapshot;
  (void)snprintf(malformed, sizeof(malformed), "%s", kSnapshot);
  CHECK(strstr(malformed, "\"seq\":7") != NULL);
  (void)memcpy(strstr(malformed, "\"seq\":7") + 8, ",\"seq\":7", 9U);
  CHECK(ScreenSnapshot_Apply(&context, malformed, strlen(malformed), 200U, &snapshot) == 0U);
  CHECK(memcmp(&before, &snapshot, sizeof(snapshot)) == 0);
  CHECK(ScreenSnapshot_Parse(kSnapshot, SCREEN_SNAPSHOT_LINE_SIZE + 1U, &snapshot) == 0U);
  CHECK(ScreenSnapshot_Apply(&context, truncated, strlen(truncated), 300U, &snapshot) == 0U);
  CHECK(ScreenSnapshot_Apply(&context, 0, 0U, 300U, &snapshot) == 0U);
  CHECK(ScreenSnapshot_Apply(0, kSnapshot, strlen(kSnapshot), 300U, &snapshot) == 0U);
  CHECK(ScreenSnapshot_Parse(0, 0U, &snapshot) == 0U);
  return 0;
}

static int test_sequence_staleness_wraparound_and_bounds(void)
{
  ScreenSnapshotContext context;
  UiSnapshot snapshot;
  char bounded[sizeof(kSnapshot)];
  const char *sequence_field;
  ScreenSnapshot_Init(&context);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  (void)snprintf(bounded, sizeof(bounded), "%s", kSnapshot);
  CHECK(ScreenSnapshot_Apply(&context, bounded, strlen(bounded), UINT32_MAX - 100U, &snapshot) == 1U);
  CHECK(ScreenSnapshot_Apply(&context, bounded, strlen(bounded), 100U, &snapshot) == 0U); /* duplicate */
  sequence_field = strstr(bounded, "\"seq\":7");
  CHECK(sequence_field != NULL);
  bounded[(size_t)(sequence_field - bounded) + 6U] = '6';
  CHECK(ScreenSnapshot_Apply(&context, bounded, strlen(bounded), 200U, &snapshot) == 0U); /* old */
  CHECK(ScreenSnapshot_IsStale(&context, 4898U) == 0U); /* 4999 ms across wrap */
  CHECK(ScreenSnapshot_IsStale(&context, 4899U) == 1U); /* 5000 ms across wrap */
  ScreenSnapshot_Tick(&context, 4899U, &snapshot);
  CHECK(snapshot.temperature_centi_c.quality == UI_QUALITY_STALE);
  CHECK(snapshot.connectivity.mqtt == (uint8_t)UI_LINK_UNKNOWN); /* Tick degrades an unobserved link to unknown */
  CHECK(snapshot.connectivity.updated_ms == 4899U);
  {
    UiState state;
    UiState_Init(&state);
    UiState_SetControlAvailability(&state, (uint8_t)(snapshot.connectivity.mqtt == UI_LINK_ONLINE), 0U);
    CHECK(state.control.mqtt_online == 0U);
    ScreenSnapshot_SetMqttAvailability(&snapshot, 1U, 4900U);
    UiState_SetControlAvailability(&state, (uint8_t)(snapshot.connectivity.mqtt == UI_LINK_ONLINE), 0U);
    CHECK(state.control.mqtt_online == 1U); /* MQTT UP recovery */
    ScreenSnapshot_SetMqttAvailability(&snapshot, 0U, 4901U);
    UiState_SetControlAvailability(&state, (uint8_t)(snapshot.connectivity.mqtt == UI_LINK_ONLINE), 0U);
    CHECK(state.control.mqtt_online == 0U); /* MQTT DOWN */
  }
  return 0;
}

static int test_time_and_mqtt_lifecycle(void)
{
  UiClock clock;
  UiClockSnapshot display;
  UiState state;
  UiSnapshot snapshot;
  char layout[320];
  const char line[] = "{ \"schema\" : \"ut.time.sync.v1\", \"source\" : \"ntp\", "
                      "\"state\" : \"synchronized\", \"epochSeconds\" : 1704067200, \"seq\" : 3 }";
  NetworkTime_Init(&clock);
  CHECK(NetworkTime_Update(&clock, line, strlen(line), 100U) == 1U);
  NetworkTime_ToSnapshot(&clock, 61000U, &display);
  /* Wire epochs are UTC; both panels display China Standard Time (UTC+8). */
  CHECK(display.synchronized == 1U && display.hour == 8U && display.minute == 1U);
  CHECK(NetworkTime_Update(0, line, strlen(line), 100U) == 0U);
  CHECK(NetworkTime_Update(&clock, 0, 0U, 100U) == 0U);
  CHECK(NetworkTime_Update(&clock, line, NETWORK_TIME_LINE_SIZE + 1U, 100U) == 0U);
  CHECK(NetworkTime_Update(&clock, "{\"schema\":\"ut.time.sync.v1\",\"source\":\"ntp\",\"state\":\"synchronized\",\"epochSeconds\":1,\"seq\":4}", 100U, 70000U) == 0U);
  UiState_Init(&state);
  UiState_SetControlAvailability(&state, 1U, 0U);
  CHECK(state.control.mqtt_online == 1U);
  UiState_SetControlAvailability(&state, 0U, 0U);
  CHECK(state.control.mqtt_online == 0U);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  CHECK(UiRenderer_DescribeLayout(&state, &snapshot, layout, sizeof(layout)) > 0U);
  CHECK(strstr(layout, "time=--:--") != NULL);
  ScreenSnapshot_SetMqttAvailability(&snapshot, 1U, 70100U);
  UiState_SetControlAvailability(&state, (uint8_t)(snapshot.connectivity.mqtt == UI_LINK_ONLINE), 0U);
  CHECK(state.control.mqtt_online == 1U);
  ScreenSnapshot_SetMqttAvailability(&snapshot, 0U, 70200U);
  UiState_SetControlAvailability(&state, (uint8_t)(snapshot.connectivity.mqtt == UI_LINK_ONLINE), 0U);
  CHECK(state.control.mqtt_online == 0U);
  return 0;
}

static int test_commands_and_ack_atomicity(void)
{
  MenuCommandContext context;
  MenuCommandAck ack;
  MenuCommandAck before;
  MenuCommandTxQueue queue;
  char line[MENU_COMMAND_LINE_SIZE];
  size_t length;
  const char valid_ack[] = "{\"schema\":\"ut.command.ack.v1\",\"cmdId\":\"menu-CTRL-02-7-3\",\"status\":\"accepted\",\"reason\":\"buzzer_muted\",\"appliedValue\":0}";
  MenuCommand_Init(&context, 7U);
  CHECK(MenuCommand_Begin(&context, UI_ACTION_BUZZER_MUTE, UI_BUZZER_MUTE, 1704067200000ULL,
                          line, sizeof(line), &length) == 1U);
  CHECK(strstr(line, "\"action\":\"buzzer_mute\"") != NULL);
  CHECK(strstr(line, "\"value\":0") != NULL);
  CHECK(strstr(line, "\"createdAtMs\":1704067200000") != NULL);
  CHECK(MenuCommand_Begin(&context, UI_ACTION_BUZZER_RESTORE, UI_BUZZER_RESTORE, 1704067200000ULL,
                          line, sizeof(line), &length) == 1U);
  CHECK(strstr(line, "\"action\":\"buzzer_restore\"") != NULL);
  CHECK(strstr(line, "\"value\":0") != NULL);
  CHECK(strstr(line, "\"ttlMs\":10000") != NULL);
  CHECK(strstr(line, "menu-CTRL-02-7-2") != NULL);
  CHECK(strncmp(line, "{\"schema\":\"ut.menu.command.v1\"",
                strlen("{\"schema\":\"ut.menu.command.v1\"")) == 0);
  CHECK(length <= MENU_COMMAND_LINE_SIZE);
  (void)memset(&ack, 0xA5, sizeof(ack));
  before = ack;
  CHECK(MenuCommand_ParseAck(valid_ack, strlen(valid_ack) - 1U, &ack) == 0U);
  CHECK(memcmp(&before, &ack, sizeof(ack)) == 0);
  CHECK(MenuCommand_ParseAck(0, 0U, &ack) == 0U);
  CHECK(MenuCommand_ParseAck(valid_ack, MENU_COMMAND_ACK_LINE_SIZE + 1U, &ack) == 0U);
  CHECK(MenuCommand_ParseAck(valid_ack, strlen(valid_ack), &ack) == 1U);
  CHECK(MenuCommand_AcceptAck(&context, &ack) == 0U); /* latest active id is restore */
  CHECK(MenuCommand_Begin(&context, UI_ACTION_BUZZER_MUTE, UI_BUZZER_MUTE, 1704067200000ULL,
                          line, sizeof(line), &length) == 1U);
  CHECK(strstr(line, "menu-CTRL-02-7-3") != NULL);
  CHECK(MenuCommand_ParseAck(valid_ack, strlen(valid_ack), &ack) == 1U);
  CHECK(MenuCommand_AcceptAck(&context, &ack) == 1U); /* positive match */
  CHECK(MenuCommand_AcceptAck(&context, &ack) == 0U); /* duplicate */
  CHECK(MenuCommand_NextBootId(0U, 0x12345678U) != MenuCommand_NextBootId(1U, 0x12345678U));
  MenuCommandTx_Init(&queue);
  CHECK(MenuCommandTx_Enqueue(&queue, "abc", 3U) == 1U);
  CHECK(MenuCommandTx_Enqueue(&queue, "def", 3U) == 0U); /* full/active */
  { uint8_t byte; CHECK(MenuCommandTx_Peek(&queue, &byte) == 1U && byte == 'a'); MenuCommandTx_Commit(&queue); CHECK(MenuCommandTx_Peek(&queue, &byte) == 1U && byte == 'b'); MenuCommandTx_Commit(&queue); MenuCommandTx_Commit(&queue); CHECK(MenuCommandTx_Peek(&queue, &byte) == 0U); }
  { char max_line[MENU_COMMAND_TX_CAPACITY]; uint8_t byte; (void)memset(max_line, 'x', sizeof(max_line)); CHECK(MenuCommandTx_Enqueue(&queue, max_line, sizeof(max_line)) == 1U); MenuCommandTx_Fail(&queue); CHECK(queue.failed == 1U); CHECK(queue.active == 0U); CHECK(MenuCommandTx_Enqueue(&queue, "z", 1U) == 1U); CHECK(queue.failed == 0U); CHECK(MenuCommandTx_Peek(&queue, &byte) == 1U && byte == 'z'); MenuCommandTx_Commit(&queue); CHECK(queue.active == 0U); }
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

/* The fan duty and LED brightness in a snapshot are the percent actually
 * applied, not a menu selection.  The legacy Web/IoTDA controller path can hold
 * a fan at 45 percent and the LED at 60, and Node B has to render that rather
 * than discard the whole line - which is what the old ladder check did, taking
 * every sensor and alarm in the snapshot down with it.  The menu ladder is
 * enforced on the command path, not here. */
static int test_non_preset_duty_and_brightness_are_telemetry(void)
{
  ScreenSnapshotContext context;
  UiSnapshot snapshot;
  char legacy[sizeof(kSnapshot)];
  const char *fan0;
  const char *fan1;

  ScreenSnapshot_Init(&context);
  (void)memset(&snapshot, 0, sizeof(snapshot));
  (void)snprintf(legacy, sizeof(legacy), "%s", kSnapshot);

  /* Rewrite the two fan duty fields (60 -> 45, 30 -> " 7") and the brightness
   * (75 -> 60), leaving every other byte of the committed line alone. */
  fan0 = strstr(legacy, "\"fans\":[[60,");
  fan1 = strstr(legacy, ",[30,");
  CHECK(fan0 != NULL);
  CHECK(fan1 != NULL);
  legacy[(size_t)(fan0 - legacy) + 9U] = '4';
  legacy[(size_t)(fan0 - legacy) + 10U] = '5';
  legacy[(size_t)(fan1 - legacy) + 2U] = '7';
  legacy[(size_t)(fan1 - legacy) + 3U] = ' ';
  legacy[(size_t)(fan1 - legacy) + 4U] = ',';
  {
    char *brightness = strstr(legacy, "\"actuators\":[true,3,");
    CHECK(brightness != NULL);
    legacy[(size_t)(brightness - legacy) + 20U] = '6';
    legacy[(size_t)(brightness - legacy) + 21U] = '0';
  }

  CHECK(ScreenSnapshot_Apply(&context, legacy, strlen(legacy), 100U, &snapshot) == 1U);
  CHECK(snapshot.fans[0].target_duty_percent == 45U);
  CHECK(snapshot.fans[1].target_duty_percent == 7U);
  CHECK(snapshot.actuators.led_brightness_percent == 60U);
  /* The readings that share the line are intact: the point of accepting the
   * duty is that the rest of the snapshot is not thrown away with it. */
  CHECK(snapshot.temperature_centi_c.value == 2234);
  CHECK(snapshot.fans[0].voltage_mv == 11900U);
  CHECK(snapshot.fans[0].actual_rpm == 2400U);
  CHECK(snapshot.actuators.led_mode == (uint8_t)UI_LED_YELLOW);
  return 0;
}

static int test_multi_sensor_snapshot_and_rotation(void)
{
  ScreenSnapshotContext context;
  UiSnapshot snapshot;
  const char snap1[] =
    "{\"schema\":\"ut.screen.snapshot.v1\",\"source\":\"CTRL-01\","
    "\"generatedAtMs\":1704067205000,\"seq\":1,"
    "\"sensors\":{\"temperature\":[2234,1704067205000,1],"
    "\"humidity\":[5210,1704067205000,1],\"oxygen\":[20900,1704067205000,1],"
    "\"methane\":[12,1704067205000,1],\"carbonMonoxide\":[4,1704067205000,1],"
    "\"smoke\":[0,1704067205000,1],\"water\":[0,1704067205000,1],"
    "\"flame\":[1,1704067205000,1]},\"alarm\":[2,0,2],"
    "\"fans\":[[60,1,2400,11900,320,1704067205000,1],"
    "[30,0,1600,11800,280,1704067205000,1]],"
    "\"actuators\":[true,3,75,true,false],"
    "\"connectivity\":[1,1,0,0,1704067200000],"
    "\"lastCommand\":[\"menu-1\",true,true,1704067204000],"
    "\"items\":["
    "{\"id\":\"FLAME-04\",\"k\":1,\"v\":1,\"sc\":1,\"q\":1,\"a\":1,\"s\":\"CTRL-02\",\"t\":1704067205000},"
    "{\"id\":\"MQ4-01\",\"k\":2,\"v\":120,\"sc\":1,\"q\":1,\"a\":0,\"s\":\"CTRL-01\",\"t\":1704067205000},"
    "{\"id\":\"SHT-03\",\"k\":0,\"v\":0,\"sc\":100,\"q\":4,\"a\":0,\"s\":\"CTRL-01\",\"t\":1704067205000}"
    "],\"alarmLabel\":\"FLAME-04\"}";

  const char dup_snap[] =
    "{\"schema\":\"ut.screen.snapshot.v1\",\"source\":\"CTRL-01\","
    "\"generatedAtMs\":1704067205000,\"seq\":2,"
    "\"sensors\":{\"temperature\":[2234,1704067205000,1],"
    "\"humidity\":[5210,1704067205000,1],\"oxygen\":[20900,1704067205000,1],"
    "\"methane\":[12,1704067205000,1],\"carbonMonoxide\":[4,1704067205000,1],"
    "\"smoke\":[0,1704067205000,1],\"water\":[0,1704067205000,1],"
    "\"flame\":[1,1704067205000,1]},\"alarm\":[2,0,2],"
    "\"fans\":[[60,1,2400,11900,320,1704067205000,1],"
    "[30,0,1600,11800,280,1704067205000,1]],"
    "\"actuators\":[true,3,75,true,false],"
    "\"connectivity\":[1,1,0,0,1704067200000],"
    "\"lastCommand\":[\"menu-1\",true,true,1704067204000],"
    "\"items\":["
    "{\"id\":\"FLAME-04\",\"k\":1,\"v\":1,\"sc\":1,\"q\":1,\"a\":1,\"s\":\"CTRL-02\",\"t\":1704067205000},"
    "{\"id\":\"FLAME-04\",\"k\":1,\"v\":1,\"sc\":1,\"q\":1,\"a\":1,\"s\":\"CTRL-02\",\"t\":1704067205000}"
    "]}";

  const char snap2_rotation[] =
    "{\"schema\":\"ut.screen.snapshot.v1\",\"source\":\"CTRL-01\","
    "\"generatedAtMs\":1704067206000,\"seq\":3,"
    "\"sensors\":{\"temperature\":[2234,1704067206000,1],"
    "\"humidity\":[5210,1704067206000,1],\"oxygen\":[20900,1704067206000,1],"
    "\"methane\":[12,1704067206000,1],\"carbonMonoxide\":[4,1704067206000,1],"
    "\"smoke\":[0,1704067206000,1],\"water\":[0,1704067206000,1],"
    "\"flame\":[0,1704067206000,1]},\"alarm\":[0,0,0],"
    "\"fans\":[[60,1,2400,11900,320,1704067206000,1],"
    "[30,0,1600,11800,280,1704067206000,1]],"
    "\"actuators\":[true,3,75,true,false],"
    "\"connectivity\":[1,1,0,0,1704067200000],"
    "\"lastCommand\":[\"menu-1\",true,true,1704067204000],"
    "\"items\":["
    "{\"id\":\"FLAME-04\",\"k\":1,\"v\":0,\"sc\":1,\"q\":1,\"a\":0,\"s\":\"CTRL-02\",\"t\":1704067206000},"
    "{\"id\":\"O2-01\",\"k\":4,\"v\":20900,\"sc\":1000,\"q\":1,\"a\":0,\"s\":\"CTRL-01\",\"t\":1704067206000}"
    "]}";

  ScreenSnapshot_Init(&context);
  (void)memset(&snapshot, 0, sizeof(snapshot));

  CHECK(ScreenSnapshot_Apply(&context, snap1, strlen(snap1), 1000U, &snapshot) == 1U);
  CHECK(snapshot.sensor_count == 3U);
  CHECK(strcmp(snapshot.sensors[0].asset_code, "FLAME-04") == 0);
  CHECK(strcmp(snapshot.sensors[0].source, "CTRL-02") == 0);
  CHECK(snapshot.sensors[0].alarm == 1U);
  CHECK(strcmp(snapshot.sensors[1].asset_code, "MQ4-01") == 0);
  CHECK(snapshot.sensors[1].quality == UI_QUALITY_VALID);
  CHECK(strcmp(snapshot.sensors[2].asset_code, "SHT-03") == 0);
  CHECK(snapshot.sensors[2].quality == UI_QUALITY_MISSING);
  CHECK(ScreenSnapshot_AlarmCount(&snapshot) == 1U);
  CHECK(ScreenSnapshot_WorstQuality(&snapshot) == UI_QUALITY_MISSING);
  CHECK(strcmp(ScreenSnapshot_AlarmLabel(&snapshot), "FLAME-04") == 0);

  /* Duplicate asset codes in one payload must be rejected */
  CHECK(ScreenSnapshot_Apply(&context, dup_snap, strlen(dup_snap), 1100U, &snapshot) == 0U);

  /* Next rotation merges: replaces FLAME-04, adds O2-01, keeps MQ4-01 and SHT-03 */
  CHECK(ScreenSnapshot_Apply(&context, snap2_rotation, strlen(snap2_rotation), 2000U, &snapshot) == 1U);
  CHECK(snapshot.sensor_count == 4U);
  CHECK(snapshot.sensors[0].alarm == 0U);
  CHECK(strcmp(snapshot.sensors[3].asset_code, "O2-01") == 0);
  CHECK(ScreenSnapshot_AlarmCount(&snapshot) == 0U);

  /* Individual expiration: after 5000ms from 2000ms, older readings expire to missing */
  ScreenSnapshot_Tick(&context, 8000U, &snapshot);
  CHECK(snapshot.sensors[1].quality == UI_QUALITY_MISSING);

  return 0;
}

int main(void)
{
  if (test_snapshot_validation_and_atomicity() != 0) return 1;
  if (test_multi_sensor_snapshot_and_rotation() != 0) return 1;
  if (test_sequence_staleness_wraparound_and_bounds() != 0) return 1;
  if (test_non_preset_duty_and_brightness_are_telemetry() != 0) return 1;
  if (test_time_and_mqtt_lifecycle() != 0) return 1;
  if (test_commands_and_ack_atomicity() != 0) return 1;
  if (test_send_failure_and_late_ack() != 0) return 1;
  (void)puts("Task 8 host test: PASS");
  return 0;
}
