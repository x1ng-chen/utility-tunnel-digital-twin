from pathlib import Path
import unittest


SOURCE = (Path(__file__).parents[1] / "src" / "main.cpp").read_text(encoding="utf-8")


def function_body(name: str) -> str:
    start = SOURCE.index(name)
    brace = SOURCE.index("{", start)
    depth = 0
    for index in range(brace, len(SOURCE)):
        if SOURCE[index] == "{":
            depth += 1
        elif SOURCE[index] == "}":
            depth -= 1
            if depth == 0:
                return SOURCE[brace:index + 1]
    raise AssertionError(f"unterminated function {name}")


class EspMainContractTest(unittest.TestCase):
    def test_diagnostics_share_the_framed_uart_queue(self):
        # A direct Serial.println can split MQTT|... JSON between UART chunks.
        self.assertNotIn("Serial.println(", SOURCE)
        self.assertNotIn("Serial.printf(", SOURCE)
        logger = function_body("class DiagnosticLogger")
        self.assertIn("EnqueueUartTxLine", logger)
        self.assertEqual(SOURCE.count("Serial.write("), 1)

    def test_mqtt_callback_never_writes_ctrl01_uart_synchronously(self):
        writer = function_body("bool writeUartCommand")
        self.assertNotIn("Serial.print(", writer)
        self.assertNotIn("Serial.write(", writer)
        self.assertIn("EnqueueUartTxLine", writer)

    def test_main_loop_drains_the_uart_queue(self):
        loop = function_body("void loop()")
        self.assertIn("pumpUartTxQueue();", loop)

    def test_ctrl01_boot_requests_clock_replay_before_json_filter(self):
        handler = function_body("void handleSerialLine")
        self.assertIn("IsCtrl01BootLine(line, length)", handler)
        self.assertLess(handler.index("IsCtrl01BootLine(line, length)"),
                        handler.index("if (line[0] != '{')"))
        self.assertIn("RequestTimeSync(&timeSyncSchedule)", handler)

    def test_clock_enqueue_failure_retries_instead_of_waiting_ten_minutes(self):
        handler = function_body("void handleNetworkTime")
        self.assertIn("UartTxEnqueueResult::Queued", handler)
        self.assertIn("UartTxEnqueueResult::Coalesced", handler)
        self.assertIn("RequestTimeSync(&timeSyncSchedule)", handler)

    def test_ack_classification_parses_the_protocol_instead_of_matching_bytes(self):
        handler = function_body("void handleSerialLine")
        self.assertIn("ParseCommandAck", handler)
        self.assertNotIn('strstr(line, "\\\"schema\\\":\\\"ut.command.ack.v1\\\"")', handler)

    def test_mqtt_callback_keeps_large_route_output_off_the_system_stack(self):
        callback = function_body("void onMqttMessage")
        self.assertNotIn("RouteOutput routed{}", callback)
        self.assertIn("&mqttRouteOutput", callback)
        self.assertIn("RouteOutput mqttRouteOutput{}", SOURCE)

    def test_serial_handler_keeps_large_route_output_off_the_system_stack(self):
        handler = function_body("void handleSerialLine")
        self.assertNotIn("RouteOutput routed{}", handler)
        self.assertIn("&mqttRouteOutput", handler)

    def test_wifi_reconnect_escalates_after_sustained_outage(self):
        handler = function_body("void connectWiFi()")
        self.assertIn("kWiFiHardRecoveryMs", SOURCE)
        self.assertIn("WiFi.disconnect(false);", handler)
        self.assertGreaterEqual(
            handler.count("WiFi.begin(WIFI_SSID, WIFI_PASSWORD);"), 2
        )
        self.assertIn("#WIFI hard_recovery", handler)


if __name__ == "__main__":
    unittest.main()
