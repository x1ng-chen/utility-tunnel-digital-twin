from pathlib import Path


source = Path("Core/Src/node_a.c").read_text(encoding="utf-8")

# Blocking sensor waits must service command RX and both UART TX queues.  A
# missing INA226 can otherwise hold the foreground loop for seconds and make a
# valid five-second menu command time out before Node A sees it.
assert "static void Communication_Service(void)" in source
service = source.split("static void Communication_Service(void)", 2)[2]
service = service.split("}", 1)[0]
assert "Command_Poll();" in service
assert "UartTx_DrainBoth(HAL_GetTick());" in service

assert "static void DelayWithCommunication(uint32_t delay_ms)" in source
assert "I2c_Stop(bus); DelayWithCommunication(NODE_A_SHT30_MEASUREMENT_DELAY_MS);" in source
assert source.count("DelayWithCommunication(INA226_SAMPLE_SETTLE_MS);") >= 3

print("Node A communication service contract: PASS")
