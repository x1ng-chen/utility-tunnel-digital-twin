#include "main.h"
#include "joystick.h"
#include "st7735.h"
#include "st7735_bus.h"
#include "ui_renderer.h"
#include "ui_state.h"
#include "screen_snapshot.h"
#include "network_time.h"
#include "menu_command.h"
#include "uart_tx_queue.h"
#include "node_b_sensor_bank.h"
#include "sensor_telemetry.h"
#include "link_lease.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NODE_ID "node-b"
#define ESP_HEARTBEAT_INTERVAL_MS 2000U
#define TELEMETRY_INTERVAL_MS 2000U
/* ESP-02 emits LINK heartbeats every two seconds.  Allow seven missed frames
 * so brief UART congestion cannot flap the status display or disable menu
 * controls; a real outage still makes both fail closed after 15 seconds. */
#define LINK_OFFLINE_TIMEOUT_MS 15000U
/* Bytes moved per UART per UI-loop iteration.  The loop must keep parsing the
 * ESP snapshot and polling the joystick at the 60 FPS cadence, so the transmit
 * work of one iteration is bounded in bytes (and therefore in milliseconds)
 * rather than by how long the link takes to accept a frame. */
#define NODE_B_UART_TX_DRAIN_BYTES 48U
#define LED_INTERVAL_MS 500U
#define ESP_RX_LINE_SIZE SCREEN_SNAPSHOT_LINE_SIZE
/* Completed ESP lines wait in a ring instead of one shared slot.  The ESP can
 * emit a snapshot, a LINK frame and a time sync back to back; with the old
 * single-line buffer every line but the last was silently lost. */
#define ESP_RX_QUEUE_CAPACITY 4U
#define UI_TEST_LINE_SIZE 48U
#define DISPLAY_TEST_DIRTY_COUNT 1000U
#define DISPLAY_TEST_COLOR_COUNT 3U
#define DISPLAY_TEST_PRIMITIVE_COUNT (DISPLAY_TEST_DIRTY_COUNT + DISPLAY_TEST_COLOR_COUNT)

typedef struct
{
  uint8_t online;
  int16_t temperature_centi_c;
  uint16_t humidity_centi_rh;
} PeerReading;

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;
static uint8_t esp_rx_character;
static volatile char esp_rx_lines[ESP_RX_QUEUE_CAPACITY][ESP_RX_LINE_SIZE];
static volatile uint16_t esp_rx_lengths[ESP_RX_QUEUE_CAPACITY];
static volatile uint16_t esp_rx_length;
static volatile uint8_t esp_rx_head;
static volatile uint8_t esp_rx_tail;
static volatile uint8_t esp_rx_count;
static volatile uint8_t esp_rx_discarding;
static volatile uint32_t esp_rx_dropped_lines;
static UiState ui_state;
static UiSnapshot ui_snapshot;
static ScreenSnapshotContext snapshot_context;
static UiClock ui_clock;
static MenuCommandContext command_context;
static char ui_test_line[UI_TEST_LINE_SIZE];
static uint8_t ui_test_length;
static uint16_t display_test_completed;
static uint8_t display_test_active;
/* Both UARTs keep their own queue so a stalled debug console can never hold
 * back the ESP link, and neither can hold back the UI loop.  Every ESP-bound
 * frame, including menu commands, shares esp_tx_queue so JSON lines cannot be
 * interleaved on USART2. */
static UartTxQueue esp_tx_queue;
static UartTxQueue debug_tx_queue;
static NodeBSensorBank sensor_bank;
static uint32_t last_gateway_online_ms;
/* A LINK frame reporting MQTT down is only an instantaneous ESP sample.  Do
 * not let one short reconnect make the UI and command availability flap.
 * Positive evidence (LINK up, snapshot, peer frame or acknowledgement) renews
 * this lease; only expiry in the main loop declares MQTT offline. */
static uint32_t last_mqtt_online_ms;
/* Diagnostic source for the most recent positive MQTT evidence:
 * 1=snapshot, 2=LINK heartbeat, 3=command acknowledgement, 4=peer reading,
 * 5=UART UI test.  The transition logger is debug-UART-only. */
static uint8_t mqtt_evidence_source;
static uint8_t mqtt_last_reported_status = 0xFFU;
static uint32_t last_node_a_online_ms;
static SensorTelemetryCursor telemetry_cursor;
ADC_HandleTypeDef hadc1;

static void MX_ADC1_Init(void);
static void SendTelemetry(void);

void SystemClock_Config(void);
void Error_Handler(void);
static void MX_GPIO_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_USART2_UART_Init(void);
static void SendHeartbeat(void);
static void PollEsp(uint32_t *received_count, PeerReading *peer);
static void PollUiTest(void);
static void HandleUiEffect(UiEffect effect, uint32_t now_ms);

/* Queues one already-formatted line for both UARTs.  Nothing on the diagnostic
 * or heartbeat path writes a UART directly any more: the UI loop drains both
 * queues under a fixed byte budget and parses the ESP snapshot either way. */
static void Tx_EnqueueLine(const char *line, uint16_t length)
{
  if ((line == 0) || (length == 0U)) return;
  (void)UartTx_Enqueue(&esp_tx_queue, line, length);
  (void)UartTx_Enqueue(&debug_tx_queue, line, length);
}

static void Tx_DrainBoth(uint32_t now_ms)
{
  (void)UartTx_Drain(&esp_tx_queue, &huart2, NODE_B_UART_TX_DRAIN_BYTES, now_ms);
  (void)UartTx_Drain(&debug_tx_queue, &huart1, NODE_B_UART_TX_DRAIN_BYTES, now_ms);
}

static void ReportMqttStateTransition(uint32_t now_ms)
{
  char message[64];
  const uint8_t status = ui_snapshot.connectivity.mqtt;
  const char *label;
  int length;
  if (status == mqtt_last_reported_status) return;
  label = (status == (uint8_t)UI_LINK_ONLINE) ? "online" :
          ((status == (uint8_t)UI_LINK_OFFLINE) ? "offline" : "unknown");
  length = snprintf(message, sizeof(message),
                    "#MQTTSTATE|%s|age=%lu|source=%u\r\n", label,
                    (unsigned long)(now_ms - last_mqtt_online_ms),
                    (unsigned int)mqtt_evidence_source);
  if ((length > 0) && (length < (int)sizeof(message))) {
    (void)UartTx_Enqueue(&debug_tx_queue, message, (uint16_t)length);
  }
  mqtt_last_reported_status = status;
}

static uint32_t NextBootId(void)
{
  uint16_t persisted;
  uint32_t uid_mix;
  /* BKP->DR1 survives reset while VBAT powers the backup domain. The UID
   * prevents collisions between boards; the persisted counter separates
   * successive boots of one board. Hardware VBAT persistence is a deferred
   * bench check, not assumed by host tests. */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_RCC_BKP_CLK_ENABLE();
  HAL_PWR_EnableBkUpAccess();
  persisted = BKP->DR1;
  ++persisted;
  if (persisted == 0U) persisted = 1U;
  BKP->DR1 = persisted;
  uid_mix = HAL_GetUIDw0() ^ HAL_GetUIDw1() ^ HAL_GetUIDw2();
  return MenuCommand_NextBootId((uint16_t)(persisted - 1U), uid_mix);
}

/* Minimal JSON field readers for the peer frame.  Only the requested key's
 * value is walked, so field order and whitespace no longer matter the way they
 * did for the fixed-order sscanf this replaces. */
static uint8_t Json_FindValue(const char *json, const char *key, const char **value)
{
  const size_t key_length = strlen(key);
  const char *cursor = json;

  while ((cursor = strchr(cursor, '"')) != NULL)
  {
    if ((strncmp(cursor + 1, key, key_length) == 0) &&
        (cursor[key_length + 1U] == '"'))
    {
      cursor += key_length + 2U;
      while ((*cursor == ' ') || (*cursor == '\t')) ++cursor;
      if (*cursor != ':') return 0U;
      ++cursor;
      while ((*cursor == ' ') || (*cursor == '\t')) ++cursor;
      *value = cursor;
      return 1U;
    }
    ++cursor;
  }
  return 0U;
}

static uint8_t Json_CopyString(const char *value, char *out, uint16_t out_size)
{
  uint16_t written = 0U;

  if (*value != '"') return 0U;
  ++value;
  while (*value != '"')
  {
    char character = *value;
    if (character == '\0') return 0U;
    ++value;
    if (character == '\\')
    {
      character = *value;
      if (character == '\0') return 0U;
      ++value;
    }
    if (written < (out_size - 1U)) out[written++] = character;
  }
  out[written] = '\0';
  return 1U;
}

static uint8_t Json_ParseLong(const char *value, long *out)
{
  char *end = NULL;
  long parsed;

  if ((*value != '-') && ((*value < '0') || (*value > '9'))) return 0U;
  parsed = strtol(value, &end, 10);
  if (end == value) return 0U;
  *out = parsed;
  return 1U;
}

static uint8_t DecodePeerReading(const char *line, PeerReading *peer)
{
  const char *payload = strchr(line, '|');
  const char *value;
  char schema[24];
  char source[16];
  long online;
  long temperature;
  long humidity;

  if (payload == NULL) return 0U;
  payload = strchr(payload + 1, '|');
  if (payload == NULL) return 0U;
  ++payload;
  if (!Json_FindValue(payload, "schema", &value) ||
      !Json_CopyString(value, schema, (uint16_t)sizeof(schema)) ||
      (strcmp(schema, "ut.node-b.peer.v1") != 0))
    return 0U;
  if (!Json_FindValue(payload, "source", &value) ||
      !Json_CopyString(value, source, (uint16_t)sizeof(source)) ||
      (strcmp(source, "node-a") != 0))
    return 0U;
  if (!Json_FindValue(payload, "online", &value) ||
      !Json_ParseLong(value, &online) ||
      !Json_FindValue(payload, "temperatureCentiC", &value) ||
      !Json_ParseLong(value, &temperature) ||
      !Json_FindValue(payload, "humidityCentiRH", &value) ||
      !Json_ParseLong(value, &humidity))
    return 0U;
  if ((online != 0L) && (online != 1L)) return 0U;
  if ((temperature < -4500L) || (temperature > 13000L) ||
      (humidity < 0L) || (humidity > 10000L))
    return 0U;
  peer->online = (online != 0L) ? 1U : 0U;
  peer->temperature_centi_c = (int16_t)temperature;
  peer->humidity_centi_rh = (uint16_t)humidity;
  return 1U;
}

static void SendHeartbeat(void)
{
  char message[128];
  static uint32_t sequence;
  const int length = snprintf(message, sizeof(message),
    "{\"schema\":\"ut.node-b.status.v1\",\"nodeId\":\"%s\",\"seq\":%lu,\"display\":\"online\"}\r\n",
    NODE_ID, (unsigned long)++sequence);

  if ((length > 0) && (length < (int)sizeof(message)))
  {
    Tx_EnqueueLine(message, (uint16_t)length);
  }
}

static void PollEsp(uint32_t *received_count, PeerReading *peer)
{
  char line[ESP_RX_LINE_SIZE];
  uint16_t length;
  uint32_t now_ms;

  /* Drain every completed line, not just one per call: a burst that queued
   * several frames must not take several loop iterations to parse. */
  for (;;)
  {
    __disable_irq();
    if (esp_rx_count == 0U)
    {
      __enable_irq();
      return;
    }
    length = esp_rx_lengths[esp_rx_head];
    if (length >= sizeof(line)) length = sizeof(line) - 1U;
    (void)memcpy(line, (const void *)esp_rx_lines[esp_rx_head], length);
    esp_rx_head = (uint8_t)((esp_rx_head + 1U) % ESP_RX_QUEUE_CAPACITY);
    --esp_rx_count;
    __enable_irq();
    line[length] = '\0';

    if (length == 0U) continue;
    {
    now_ms = HAL_GetTick();
    /* The echo is a diagnostic, not an input to the UI: it is queued behind a
     * bounded budget so a slow console can never delay the parse and render
     * below, and it is dropped rather than delayed if the queue is full.  It is
     * queued in its three parts so no second copy of the line is needed. */
    (void)UartTx_Enqueue(&debug_tx_queue, "#ESP ", 5U);
    (void)UartTx_Enqueue(&debug_tx_queue, line, length);
    (void)UartTx_Enqueue(&debug_tx_queue, "\r\n", 2U);
    if (ScreenSnapshot_Apply(&snapshot_context, line, length, now_ms, &ui_snapshot))
    {
      /* A valid Node A snapshot has crossed Node A -> MQTT broker -> ESP-02,
       * so it is also direct positive evidence for every displayed link.
       * Count it as a heartbeat instead of requiring a separate LINK frame. */
      last_gateway_online_ms = now_ms;
      last_mqtt_online_ms = now_ms;
      mqtt_evidence_source = 1U;
      last_node_a_online_ms = now_ms;
      ui_snapshot.connectivity.node_a = (uint8_t)UI_LINK_ONLINE;
      ui_snapshot.connectivity.gateway = (uint8_t)UI_LINK_ONLINE;
      ui_snapshot.connectivity.mqtt = (uint8_t)UI_LINK_ONLINE;
      ui_snapshot.connectivity.iotda = (uint8_t)UI_LINK_ONLINE;
      ++*received_count;
      UiState_SetControlAvailability(&ui_state, (uint8_t)(ui_snapshot.connectivity.mqtt == UI_LINK_ONLINE),
                                     ui_state.control.safety_locked);
    }
    else if (NetworkTime_Update(&ui_clock, line, length, now_ms))
    {
      /* The parser accepts compact and whitespace-bearing JSON. */
    }
    else if (strncmp(line, "LINK|", 5U) == 0)
    {
      unsigned int wifi_up;
      unsigned int mqtt_up;
      unsigned int node_a_up = 0U;
      const int fields = sscanf(line, "LINK|%u|%u|%u", &wifi_up, &mqtt_up,
                                &node_a_up);
      if (fields >= 2 && wifi_up <= 1U && mqtt_up <= 1U &&
          (fields < 3 || node_a_up <= 1U)) {
        /* Like MQTT, Wi-Fi can momentarily report down while the ESP roams or
         * renews its hotspot association.  A down sample does not revoke the
         * displayed lease; only a full timeout without positive evidence does. */
        if (wifi_up) {
          last_gateway_online_ms = now_ms;
          ui_snapshot.connectivity.gateway = (uint8_t)UI_LINK_ONLINE;
        }
        if (mqtt_up) {
          last_mqtt_online_ms = now_ms;
          mqtt_evidence_source = 2U;
          ui_snapshot.connectivity.mqtt = (uint8_t)UI_LINK_ONLINE;
          ui_snapshot.connectivity.iotda = (uint8_t)UI_LINK_ONLINE;
        }
        if (fields == 3 && node_a_up) {
          last_node_a_online_ms = now_ms;
          ui_snapshot.connectivity.node_a = (uint8_t)UI_LINK_ONLINE;
        }
        ui_snapshot.connectivity.updated_ms = now_ms;
      }
    }
    else if (strcmp(line, "NODEA|1") == 0)
    {
      last_node_a_online_ms = now_ms;
      ui_snapshot.connectivity.node_a = (uint8_t)UI_LINK_ONLINE;
      ui_snapshot.connectivity.updated_ms = now_ms;
    }
    else
    {
      MenuCommandAck acknowledgement;
      if (MenuCommand_ParseAck(line, length, &acknowledgement) &&
          MenuCommand_AcceptAck(&command_context, &acknowledgement))
      {
        last_mqtt_online_ms = now_ms;
        mqtt_evidence_source = 3U;
        ui_snapshot.connectivity.mqtt = (uint8_t)UI_LINK_ONLINE;
        ui_snapshot.connectivity.iotda = (uint8_t)UI_LINK_ONLINE;
        (void)UiState_HandleAcknowledgement(&ui_state, acknowledgement.command_id,
                                            acknowledgement.accepted, now_ms);
      }
      if ((strncmp(line, "MQTT|", 5U) == 0) && DecodePeerReading(line, peer))
      {
        ++*received_count;
        ui_snapshot.temperature_centi_c.value = peer->temperature_centi_c;
        ui_snapshot.temperature_centi_c.sampled_ms = now_ms;
        ui_snapshot.temperature_centi_c.quality = UI_QUALITY_VALID;
        ui_snapshot.humidity_centi_rh.value = peer->humidity_centi_rh;
        ui_snapshot.humidity_centi_rh.sampled_ms = now_ms;
        ui_snapshot.humidity_centi_rh.quality = UI_QUALITY_VALID;
        ui_snapshot.connectivity.node_a = peer->online ? (uint8_t)UI_LINK_ONLINE : (uint8_t)UI_LINK_OFFLINE;
        if (peer->online) last_node_a_online_ms = now_ms;
        last_mqtt_online_ms = now_ms;
        mqtt_evidence_source = 4U;
        ScreenSnapshot_SetMqttAvailability(&ui_snapshot, 1U, now_ms);
        UiState_SetControlAvailability(&ui_state, 1U, ui_state.control.safety_locked);
      }
    }
    }
  }
}

static const char *Joystick_EventName(UiInputEvent event)
{
  static const char *const names[] = {
    "NONE", "UP", "DOWN", "LEFT", "RIGHT", "PRESS", "LONG_PRESS",
  };
  return ((uint8_t)event < (sizeof(names) / sizeof(names[0]))) ? names[event] : "NONE";
}

static void JoystickTest_Report(UiInputEvent event)
{
  char message[32];
  const int length = snprintf(message, sizeof(message), "#JOY %s\r\n", Joystick_EventName(event));

  if ((length > 0) && (length < (int)sizeof(message))) {
    Tx_EnqueueLine(message, (uint16_t)length);
  }
}

static void UiTest_Report(void)
{
  char message[320];
  size_t length = UiRenderer_DescribeLayout(&ui_state, &ui_snapshot, message, sizeof(message) - 2U);

  if ((length > 0U) && (length < (sizeof(message) - 2U))) {
    message[length++] = '\r';
    message[length++] = '\n';
    Tx_EnqueueLine(message, (uint16_t)length);
  }
}

static void DisplayTest_Report(void)
{
  St7735BusStats stats;
  char message[180];
  St7735Bus_GetStats(&stats);
  const int length = snprintf(message, sizeof(message),
    "#DISPLAY sysclk=%lu spi_hz=%lu dma_frames=%lu dma_timeouts=%lu worst_frame_us=%lu dma_errors=%lu\r\n",
    (unsigned long)HAL_RCC_GetSysClockFreq(), (unsigned long)stats.spi_hz,
    (unsigned long)stats.dma_frames, (unsigned long)stats.dma_timeouts,
    (unsigned long)stats.worst_frame_us, (unsigned long)stats.dma_errors);
  if (length > 0 && length < (int)sizeof(message))
    Tx_EnqueueLine(message, (uint16_t)length);
}

static void DisplayTest_BeginRun(void)
{
  St7735Bus_ResetStats();
  display_test_completed = 0U;
  display_test_active = 1U;
}

/* Return true when this run is complete or has failed. Only an exact one-frame
 * transition with no new transport fault earns progress. */
static uint8_t DisplayTest_RecordPrimitive(const St7735BusStats *before,
                                           const St7735BusStats *after)
{
  const uint8_t succeeded =
    ((uint32_t)(after->dma_frames - before->dma_frames) == 1U) &&
    ((uint32_t)(after->dma_timeouts - before->dma_timeouts) == 0U) &&
    ((uint32_t)(after->dma_errors - before->dma_errors) == 0U);

  if (succeeded) ++display_test_completed;
  if (!succeeded || (display_test_completed == DISPLAY_TEST_PRIMITIVE_COUNT)) {
    display_test_active = 0U;
    return 1U;
  }
  return 0U;
}

static void UiTest_HandleLine(void)
{
  UiInputEvent event = UI_EVT_NONE;
  unsigned long elapsed_ms;
  unsigned int enabled;
  unsigned int x;
  unsigned int y;
  unsigned int switch_released;
  unsigned long now_ms;
  char command_id[40];
  char acknowledgement[16];
  char page_name[16];
  UiPage target_page;

  if (strcmp(ui_test_line, "#DISPLAYTEST RUN") == 0) {
    DisplayTest_BeginRun();
    return;
  } else if (strcmp(ui_test_line, "#DISPLAYTEST") == 0) {
    DisplayTest_Report();
    return;
  } else if (strcmp(ui_test_line, "#JOYTEST RESET") == 0) {
    Joystick_TestReset(2048U, 2048U);
    JoystickTest_Report(UI_EVT_NONE);
    return;
  } else if (sscanf(ui_test_line, "#JOYTEST %u %u %u %lu", &x, &y, &switch_released, &now_ms) == 4) {
    if ((x > 4095U) || (y > 4095U) || (switch_released > 1U)) return;
    JoystickTest_Report(Joystick_TestProcessSample((uint16_t)x, (uint16_t)y,
                                                   (uint8_t)switch_released, (uint32_t)now_ms));
    return;
  } else if (strcmp(ui_test_line, "#UITEST RESET") == 0) {
    UiState_Init(&ui_state);
    (void)memset(&ui_snapshot, 0, sizeof(ui_snapshot));
    ScreenSnapshot_Init(&snapshot_context);
    NetworkTime_Init(&ui_clock);
    MenuCommand_Init(&command_context, HAL_GetTick());
    UiRenderer_Init();
  } else if (sscanf(ui_test_line, "#UITEST GOTO %15s", page_name) == 1) {
    if (!UiRenderer_PageFromName(page_name, &target_page)) return;
    ui_state.page = target_page;
    ui_state.selected_row = 0U;
    ui_state.dialog = UI_DIALOG_NONE;
    ui_state.animation_start_ms = HAL_GetTick();
    ui_state.animation_end_ms = ui_state.animation_start_ms + UI_RENDERER_PAGE_MS;
  } else if (sscanf(ui_test_line, "#UITEST TICK %lu", &elapsed_ms) == 1) {
    /* TICK is a deterministic elapsed interval for the diagnostic adapter. */
    UiState_Tick(&ui_state, ui_state.command_started_ms + (uint32_t)elapsed_ms);
  } else if (sscanf(ui_test_line, "#UITEST BIND %39s", command_id) == 1) {
    (void)UiState_CommandDispatched(&ui_state, command_id);
  } else if (sscanf(ui_test_line, "#UITEST ACK %39s %15s", command_id, acknowledgement) == 2) {
    if (strcmp(acknowledgement, "ACCEPT") == 0) {
      (void)UiState_HandleAcknowledgement(&ui_state, command_id, 1U, HAL_GetTick());
    } else if (strcmp(acknowledgement, "REJECT") == 0) {
      (void)UiState_HandleAcknowledgement(&ui_state, command_id, 0U, HAL_GetTick());
    }
  } else if (sscanf(ui_test_line, "#UITEST MQTT %u", &enabled) == 1) {
    ui_snapshot.connectivity.mqtt = enabled ? (uint8_t)UI_LINK_ONLINE : (uint8_t)UI_LINK_OFFLINE;
    if (enabled) {
      last_mqtt_online_ms = HAL_GetTick();
      mqtt_evidence_source = 5U;
    }
    UiState_SetControlAvailability(&ui_state, enabled ? 1U : 0U, ui_state.control.safety_locked);
  } else if (sscanf(ui_test_line, "#UITEST SAFETY %u", &enabled) == 1) {
    UiState_SetControlAvailability(&ui_state, ui_state.control.mqtt_online, enabled ? 1U : 0U);
  } else if (strcmp(ui_test_line, "#UITEST UP") == 0) {
    event = UI_EVT_UP;
  } else if (strcmp(ui_test_line, "#UITEST DOWN") == 0) {
    event = UI_EVT_DOWN;
  } else if (strcmp(ui_test_line, "#UITEST LEFT") == 0) {
    event = UI_EVT_LEFT;
  } else if (strcmp(ui_test_line, "#UITEST RIGHT") == 0) {
    event = UI_EVT_RIGHT;
  } else if (strcmp(ui_test_line, "#UITEST PRESS") == 0) {
    event = UI_EVT_PRESS;
  } else if (strcmp(ui_test_line, "#UITEST LONG_PRESS") == 0) {
    event = UI_EVT_LONG_PRESS;
  } else {
    return;
  }

  if (event != UI_EVT_NONE) {
    const UiEffect effect = UiState_Handle(&ui_state, event, HAL_GetTick());
    HandleUiEffect(effect, HAL_GetTick());
  }
  UiTest_Report();
}

static void PollUiTest(void)
{
  uint8_t character;

  while (HAL_UART_Receive(&huart1, &character, 1U, 0U) == HAL_OK) {
    if (character == '\n') {
      ui_test_line[ui_test_length] = '\0';
      UiTest_HandleLine();
      ui_test_length = 0U;
    } else if (character != '\r') {
      if (ui_test_length < (UI_TEST_LINE_SIZE - 1U)) ui_test_line[ui_test_length++] = (char)character;
      else ui_test_length = 0U;
    }
  }
}

static void HandleUiEffect(UiEffect effect, uint32_t now_ms)
{
  char line[MENU_COMMAND_LINE_SIZE];
  size_t length = 0U;
  uint64_t epoch_ms;
  if (effect.kind != UI_EFFECT_SEND_COMMAND) return;
  epoch_ms = NetworkTime_EpochMilliseconds(&ui_clock, now_ms);
  if ((epoch_ms == 0ULL) || !MenuCommand_Begin(&command_context, (UiAction)effect.action,
                                                effect.value, epoch_ms, line,
                                                sizeof(line), &length)) {
    (void)UiState_CommandSendFailed(&ui_state, now_ms);
    return;
  }
  if (!UartTx_EnqueuePriority(&esp_tx_queue, line, (uint16_t)length)) {
    command_context.pending = 0U;
    (void)UiState_CommandSendFailed(&ui_state, now_ms);
    return;
  }
  if (!UiState_CommandDispatched(&ui_state, command_context.active_command_id)) {
    command_context.pending = 0U;
    (void)UiState_CommandSendFailed(&ui_state, now_ms);
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
  if (uart->Instance == USART2)
  {
    if (esp_rx_character == '\n')
    {
      if (esp_rx_discarding != 0U)
      {
        /* Oversized or queue-overflow line: drop through its terminator. */
        ++esp_rx_dropped_lines;
        esp_rx_discarding = 0U;
      }
      else if (esp_rx_length > 0U)
      {
        if (esp_rx_count < ESP_RX_QUEUE_CAPACITY)
        {
          esp_rx_lengths[esp_rx_tail] = esp_rx_length;
          esp_rx_tail = (uint8_t)((esp_rx_tail + 1U) % ESP_RX_QUEUE_CAPACITY);
          ++esp_rx_count;
        }
        else
          ++esp_rx_dropped_lines;
      }
      esp_rx_length = 0U;
    }
    else if (esp_rx_character != '\r')
    {
      if (esp_rx_discarding == 0U)
      {
        if (esp_rx_count >= ESP_RX_QUEUE_CAPACITY)
          esp_rx_discarding = 1U;
        else if (esp_rx_length < (ESP_RX_LINE_SIZE - 1U))
          esp_rx_lines[esp_rx_tail][esp_rx_length++] = (char)esp_rx_character;
        else
        {
          esp_rx_length = 0U;
          esp_rx_discarding = 1U;
        }
      }
    }
    (void)HAL_UART_Receive_IT(&huart2, &esp_rx_character, 1U);
  }
}

/* ORE/FE/NE leave the HAL reception disarmed with a half-built line.  Drop the
 * partial line and re-arm byte reception so the ESP link recovers without a
 * reboot.  USART1 is polled by PollUiTest() and must not be re-armed here. */
void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
  if ((uart == NULL) || (uart->Instance != USART2)) return;
  (void)HAL_UART_AbortReceive(uart);
  __disable_irq();
  esp_rx_length = 0U;
  esp_rx_discarding = 0U;
  __enable_irq();
  (void)HAL_UART_Receive_IT(&huart2, &esp_rx_character, 1U);
}

int main(void)
{
  uint32_t last_heartbeat = HAL_MAX_DELAY;
  uint32_t last_led = HAL_MAX_DELAY;
  uint32_t received_count = 0U;
  PeerReading peer = {0};

  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
  MX_USART1_UART_Init();
  MX_USART2_UART_Init();
  UiState_Init(&ui_state);
  (void)memset(&ui_snapshot, 0, sizeof(ui_snapshot));
  ScreenSnapshot_Init(&snapshot_context);
  NetworkTime_Init(&ui_clock);
  MenuCommand_Init(&command_context, NextBootId());
  UartTx_Init(&esp_tx_queue);
  UartTx_Init(&debug_tx_queue);
  if (HAL_UART_Receive_IT(&huart2, &esp_rx_character, 1U) != HAL_OK) Error_Handler();
  ST7735_Init();
  UiRenderer_Init();
  (void)UiRenderer_RenderFrame(&ui_state, &ui_snapshot, HAL_GetTick());
  MX_ADC1_Init();
  if (HAL_ADCEx_Calibration_Start(&hadc1) != HAL_OK) Error_Handler();
  Joystick_Init(&hadc1);
  NodeBSensorBank_Init(&sensor_bank, &hadc1);
  SensorTelemetry_Init(&telemetry_cursor, 1U);
  Tx_EnqueueLine("#NODE node-b boot\r\n", 19U);

  static uint32_t last_telemetry = HAL_MAX_DELAY;
  static uint32_t last_sensor_sample = HAL_MAX_DELAY;
  for (;;)
  {
    const uint32_t now = HAL_GetTick();
    UiInputEvent event;
    event = Joystick_Poll(now);
    if (event != UI_EVT_NONE) {
      const UiEffect effect = UiState_Handle(&ui_state, event, now);
      HandleUiEffect(effect, now);
    }
    /* Sample one bank item every 20 ms. Continuous ADC polling here used to
     * starve joystick input and display transfers. */
    if ((uint32_t)(now - last_sensor_sample) >= 20U) {
      NodeBSensorBank_Tick(&sensor_bank, now);
      last_sensor_sample = now;
    }
    PollUiTest();
    PollEsp(&received_count, &peer);
    /* Hand the queued diagnostic and heartbeat lines to the links under a byte
     * budget, so a busy or unplugged console cannot delay the input poll, the
     * snapshot parse or the render above. */
    Tx_DrainBoth(now);
    ScreenSnapshot_Tick(&snapshot_context, now, &ui_snapshot);
    if (LinkLease_Expired(now, last_gateway_online_ms, LINK_OFFLINE_TIMEOUT_MS)) {
      ui_snapshot.connectivity.gateway = (uint8_t)UI_LINK_OFFLINE;
    }
    if (LinkLease_Expired(now, last_mqtt_online_ms, LINK_OFFLINE_TIMEOUT_MS)) {
      ui_snapshot.connectivity.mqtt = (uint8_t)UI_LINK_OFFLINE;
      ui_snapshot.connectivity.iotda = (uint8_t)UI_LINK_OFFLINE;
    }
    if (LinkLease_Expired(now, last_node_a_online_ms, LINK_OFFLINE_TIMEOUT_MS)) {
      ui_snapshot.connectivity.node_a = (uint8_t)UI_LINK_OFFLINE;
    }
    ReportMqttStateTransition(now);
    NetworkTime_ToSnapshot(&ui_clock, now, &ui_snapshot.clock);
    UiState_SetControlAvailability(&ui_state, (uint8_t)(ui_snapshot.connectivity.mqtt == UI_LINK_ONLINE),
                                   ui_state.control.safety_locked);
    UiState_Tick(&ui_state, now);
    /* One diagnostic transfer per loop keeps input and ESP polling scheduled. */
    if (display_test_active) {
      St7735BusStats before;
      St7735BusStats after;
      St7735Bus_GetStats(&before);
      if (display_test_completed < DISPLAY_TEST_DIRTY_COUNT) {
        ST7735_FillRect(0, 32, LCD_WIDTH, 8,
                       (display_test_completed & 1U) ? LCD_BLUE : LCD_RED);
      } else {
        static const uint16_t colors[] = {LCD_BLUE, LCD_GREEN, LCD_RED};
        ST7735_Clear(colors[display_test_completed - DISPLAY_TEST_DIRTY_COUNT]);
      }
      St7735Bus_GetStats(&after);
      if (DisplayTest_RecordPrimitive(&before, &after)) {
        DisplayTest_Report();
        UiRenderer_Init();
        (void)UiRenderer_RenderFrame(&ui_state, &ui_snapshot, now);
      }
    }
    else {
      (void)UiRenderer_RenderFrame(&ui_state, &ui_snapshot, now);
    }
    if ((now - last_telemetry) >= TELEMETRY_INTERVAL_MS)
    {
      SendTelemetry();
      last_telemetry = now;
    }
    if ((now - last_heartbeat) >= ESP_HEARTBEAT_INTERVAL_MS)
    {
      SendHeartbeat();
      last_heartbeat = now;
    }
    if ((now - last_led) >= LED_INTERVAL_MS)
    {
      HAL_GPIO_TogglePin(LED_GPIO_Port, LED_Pin);
      last_led = now;
    }
  }
}

static void MX_ADC1_Init(void)
{
  hadc1.Instance = ADC1;
  hadc1.Init.ScanConvMode = ADC_SCAN_DISABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.NbrOfConversion = 1;
  if (HAL_ADC_Init(&hadc1) != HAL_OK) Error_Handler();
}

static void SendTelemetry(void)
{
  char buffer[768];
  uint16_t length = 0U;
  SensorTelemetryCursor next_cursor = telemetry_cursor;
  if (SensorTelemetry_FormatNext(NodeBSensorBank_Readings(&sensor_bank),
                                 NodeBSensorBank_Count(&sensor_bank),
                                 &next_cursor,
                                 buffer,
                                 sizeof(buffer),
                                 &length))
  {
    if (UartTx_Enqueue(&esp_tx_queue, buffer, length))
    {
      (void)UartTx_Enqueue(&debug_tx_queue, buffer, length);
      telemetry_cursor = next_cursor;
    }
  }
}

void SystemClock_Config(void)
{
  RCC_OscInitTypeDef oscillator = {0};
  RCC_ClkInitTypeDef clock = {0};
  RCC_PeriphCLKInitTypeDef peripheral_clock = {0};
  oscillator.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  oscillator.HSEState = RCC_HSE_ON;
  oscillator.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  oscillator.HSIState = RCC_HSI_ON;
  oscillator.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  oscillator.PLL.PLLState = RCC_PLL_ON;
  oscillator.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  oscillator.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&oscillator) != HAL_OK) Error_Handler();
  clock.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  clock.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  clock.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clock.APB1CLKDivider = RCC_HCLK_DIV2;
  clock.APB2CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_2) != HAL_OK) Error_Handler();
  peripheral_clock.PeriphClockSelection = RCC_PERIPHCLK_ADC;
  peripheral_clock.AdcClockSelection = RCC_ADCPCLK2_DIV6;
  if (HAL_RCCEx_PeriphCLKConfig(&peripheral_clock) != HAL_OK) Error_Handler();
}

static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef gpio = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin, GPIO_PIN_RESET);
  gpio.Pin = LED_Pin;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LED_GPIO_Port, &gpio);

  /* PA5/PA7 are configured by the SPI1 bus; PA6 remains unused. */
  gpio.Pin = TFT_RES_Pin | TFT_DC_Pin | TFT_CS_Pin | TFT_BLK_Pin;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(GPIOB, &gpio);
  HAL_GPIO_WritePin(GPIOB, gpio.Pin, GPIO_PIN_RESET);

  __HAL_RCC_GPIOC_CLK_ENABLE();
  gpio.Pin = GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_10 | GPIO_PIN_11;
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOC, &gpio);

  gpio.Pin = GPIO_PIN_8 | GPIO_PIN_9;
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOC, &gpio);
}

static void MX_USART1_UART_Init(void)
{
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 9600;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK) Error_Handler();
}

static void MX_USART2_UART_Init(void)
{
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 9600;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK) Error_Handler();
}

void Error_Handler(void)
{
  __disable_irq();
  while (1) { }
}
