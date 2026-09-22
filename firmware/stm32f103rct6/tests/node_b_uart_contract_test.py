from pathlib import Path


source = Path("Core/Src/node_b.c").read_text(encoding="utf-8")

# USART2 has one framed producer.  Heartbeats and menu commands must share the
# same FIFO; two independent byte drains can splice their JSON on the wire.
assert "UartTx_EnqueuePriority(&esp_tx_queue, line, (uint16_t)length)" in source
assert "UartTx_WriteByte(&huart2" not in source
assert "PollCommandTx();" not in source

# The screen and the command gate share one authoritative lease.  ESP-02 sends
# a heartbeat every two seconds, so tolerating up to seven missed frames keeps
# brief UART congestion from making the menu flap while still failing closed.
assert "#define LINK_OFFLINE_TIMEOUT_MS 15000U" in source
assert "UiState_SetControlAvailability(&ui_state, (uint8_t)(ui_snapshot.connectivity.mqtt == UI_LINK_ONLINE)" in source

# State-transition diagnostics must stay on the debug UART. Sending them back
# to ESP-02 would create diagnostic feedback traffic on the link under test.
assert '"#MQTTSTATE|%s|age=%lu|source=%u\\r\\n"' in source
assert 'UartTx_Enqueue(&debug_tx_queue, message, (uint16_t)length)' in source

print("Node B UART frame arbitration contract: PASS")
