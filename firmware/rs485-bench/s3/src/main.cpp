#include <Arduino.h>
#include "bench_protocol.h"

static HardwareSerial bus(1);
#ifndef BENCH_POLL_MASK
#define BENCH_POLL_MASK 8
#endif
#if BENCH_POLL_MASK < 1 || BENCH_POLL_MASK > 15
#error "BENCH_POLL_MASK selects slave numbers 1 through 4"
#endif
struct NodeCounts { uint32_t polls, successes, timeouts, malformed; };
static NodeCounts nodes[5];
static uint32_t polls;
static uint32_t last_poll;
static const uint8_t scan_order[] = {4, 3, 2, 1};
static uint8_t scan_index;

static uint8_t next_address() {
    for (;;) {
        uint8_t address = scan_order[scan_index];
        scan_index = (scan_index + 1u) % 4u;
        if (BENCH_POLL_MASK & (1u << (address - 1u))) return address;
    }
}

static void poll_slave(uint8_t address) {
    NodeCounts &counts = nodes[address];
    uint8_t request[8] = {address, 3, 0, 0, 0, BENCH_REGISTER_COUNT};
    bench_add_crc(request, 6);
    while (bus.available()) (void)bus.read();
    ++polls;
    ++counts.polls;
    bus.write(request, sizeof request);
    bus.flush();  // Wait for the final byte; automatic-direction hardware owns DE.
    uint8_t incoming[128]; size_t used = 0; bool overflow = false;
    uint32_t start = millis(), last_byte = start;
    while ((uint32_t)(millis() - start) < 300u) {
        while (bus.available()) {
            int value = bus.read();
            if (used < sizeof incoming) incoming[used++] = (uint8_t)value;
            else overflow = true;
            last_byte = millis();
        }
        if (used >= 21u && (uint32_t)(millis() - last_byte) >= 10u) break;
        delay(1);
    }
    /* Scan past an optional exact request echo; require CRC, signature and ID. */
    if (!overflow) for (size_t offset = 0; offset + 21u <= used; ++offset) {
        const uint8_t *reply = incoming + offset;
        if (!bench_is_response_for(reply, 21u, address)) continue;
        ++counts.successes;
        uint32_t seconds = ((uint32_t)bench_u16(reply + 9) << 16) | bench_u16(reply + 11);
        uint32_t requests = ((uint32_t)bench_u16(reply + 13) << 16) | bench_u16(reply + 15);
        Serial.printf("RS485_OK poll=%lu slave=%u uptime_s=%lu requests=%lu slave_crc_errors=%u ok=%lu node_poll=%lu\r\n",
            (unsigned long)polls, (unsigned)address, (unsigned long)seconds, (unsigned long)requests,
            bench_u16(reply + 17), (unsigned long)counts.successes, (unsigned long)counts.polls);
        return;
    }
    if (!used) ++counts.timeouts; else ++counts.malformed;
    Serial.printf("RS485_FAIL poll=%lu slave=%u rx_bytes=%u timeout=%lu malformed=%lu overflow=%u node_poll=%lu\r\n",
        (unsigned long)polls, (unsigned)address, (unsigned)used, (unsigned long)counts.timeouts,
        (unsigned long)counts.malformed, (unsigned)overflow, (unsigned long)counts.polls);
    if (used) {
        Serial.print("RX_HEX ");
        for (size_t i = 0; i < used; ++i) Serial.printf("%02X ", incoming[i]);
        Serial.println();
    }
}

void setup() {
    Serial.begin(115200);
    int self_test = bench_self_test();
    if (self_test) {
        for (;;) { Serial.printf("PROTOCOL_SELFTEST FAIL case=%d\r\n", self_test); delay(1000); }
    }
    // No Wi-Fi, PSRAM, output drivers, sensors or voice functionality in this image.
    bus.setRxBufferSize(256);
    bus.begin(19200, SERIAL_8E1, 18, 17);
    delay(500);
    Serial.printf("RS485_BENCH_V1 S3_MASTER TX=17 RX=18 19200-8E1 MASK=%u DIAGNOSTIC_ONLY\r\n", (unsigned)BENCH_POLL_MASK);
    Serial.println("PROTOCOL_SELFTEST PASS cases=9");
    last_poll = millis() - 1000u;
}

void loop() {
    const uint32_t interval = BENCH_POLL_MASK == 8 ? 1000u : 500u;
    if ((uint32_t)(millis() - last_poll) >= interval) {
        last_poll = millis(); poll_slave(next_address());
    }
    delay(1);
}
