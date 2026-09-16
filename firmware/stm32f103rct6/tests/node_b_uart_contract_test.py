from pathlib import Path


source = Path("Core/Src/node_b.c").read_text(encoding="utf-8")

# USART2 has one framed producer.  Heartbeats and menu commands must share the
# same FIFO; two independent byte drains can splice their JSON on the wire.
assert "UartTx_EnqueuePriority(&esp_tx_queue, line, (uint16_t)length)" in source
assert "UartTx_WriteByte(&huart2" not in source
assert "PollCommandTx();" not in source

print("Node B UART frame arbitration contract: PASS")
