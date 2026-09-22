from pathlib import Path


source = Path("Core/Src/node_a.c").read_text(encoding="utf-8")

# Slow software-I2C waits must continue servicing the 200 ms gas safety loop.
service_start = source.index("static void Communication_Service(void)\n{")
service_end = source.index("\n}", service_start)
service_body = source[service_start:service_end]
assert "GasSafety_Service(now);" in service_body

# Blocking sensor waits must service command RX and both UART TX queues.  A
# missing INA226 can otherwise hold the foreground loop for seconds and make a
# valid five-second menu command time out before Node A sees it.
assert "static void Communication_Service(void)" in source
service = source.split("static void Communication_Service(void)", 2)[2]
service = service.split("}", 1)[0]
assert "Command_Poll();" in service
# The drain is timestamped once per service pass via the local `now`; requiring
# the literal HAL_GetTick() argument would be testing a spelling, not the
# contract.  `now` must still be derived from HAL_GetTick() inside this
# function so blocking waits service queues with a coherent timestamp.
assert "const uint32_t now = HAL_GetTick();" in service
assert "UartTx_DrainBoth(now);" in service

assert "static void DelayWithCommunication(uint32_t delay_ms)" in source
assert "I2c_Stop(bus); DelayWithCommunication(NODE_A_SHT30_MEASUREMENT_DELAY_MS);" in source
assert source.count("DelayWithCommunication(INA226_SAMPLE_SETTLE_MS);") >= 3

print("Node A communication service contract: PASS")
