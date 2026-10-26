#ifndef BENCH_PROTOCOL_H
#define BENCH_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>

/* Isolated diagnostic holding registers, not the production sensor contract. */
#ifndef BENCH_ADDRESS
#define BENCH_ADDRESS 4u
#endif
#if BENCH_ADDRESS < 1 || BENCH_ADDRESS > 4
#error "Diagnostic slave address must match a physical board number from 1 to 4"
#endif
#define BENCH_REGISTER_COUNT 8u
#define BENCH_SIGNATURE 0x4853u
#define BENCH_VERSION 0x0100u

static inline uint16_t bench_crc(const uint8_t *bytes, size_t count) {
    uint16_t crc = 0xffffu;
    for (size_t i = 0; i < count; ++i) {
        crc ^= bytes[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc & 1u) ? (uint16_t)((crc >> 1) ^ 0xa001u) : (uint16_t)(crc >> 1);
    }
    return crc;
}

static inline void bench_add_crc(uint8_t *frame, size_t size_without_crc) {
    uint16_t crc = bench_crc(frame, size_without_crc);
    frame[size_without_crc] = (uint8_t)crc;
    frame[size_without_crc + 1u] = (uint8_t)(crc >> 8);
}

static inline int bench_valid_crc(const uint8_t *frame, size_t count) {
    return count >= 4u && bench_crc(frame, count) == 0u;
}

static inline uint16_t bench_u16(const uint8_t *bytes) {
    return (uint16_t)(((uint16_t)bytes[0] << 8) | bytes[1]);
}

/* Only one read-only query is supported. No writes, exceptions or broadcasts. */
static inline int bench_is_request_for(const uint8_t *frame, size_t count, uint8_t address) {
    return count == 8u && bench_valid_crc(frame, count) &&
        address >= 1u && address <= 4u && frame[0] == address && frame[1] == 3u &&
        bench_u16(frame + 2) == 0u && bench_u16(frame + 4) == BENCH_REGISTER_COUNT;
}

static inline int bench_is_response_for(const uint8_t *frame, size_t count, uint8_t address) {
    return count == 21u && bench_valid_crc(frame, count) &&
        address >= 1u && address <= 4u && frame[0] == address && frame[1] == 3u && frame[2] == 16u &&
        bench_u16(frame + 3) == BENCH_SIGNATURE &&
        bench_u16(frame + 5) == address && bench_u16(frame + 7) == BENCH_VERSION;
}

static inline int bench_is_request(const uint8_t *frame, size_t count) {
    return bench_is_request_for(frame, count, BENCH_ADDRESS);
}

static inline int bench_is_response(const uint8_t *frame, size_t count) {
    return bench_is_response_for(frame, count, BENCH_ADDRESS);
}

/* Known CRC vectors and access-policy checks, executed on each MCU at boot. */
static inline int bench_self_test(void) {
    static const uint8_t digits[] = "123456789";
    uint8_t known[] = {1, 3, 0, 0, 0, 10, 0xc5, 0xcd};
    if (bench_crc(digits, 9u) != 0x4b37u) return 1;
    if (!bench_valid_crc(known, sizeof known)) return 2;
    known[2] ^= 1u;
    if (bench_valid_crc(known, sizeof known)) return 3;
    uint8_t query[] = {BENCH_ADDRESS, 3, 0, 0, 0, BENCH_REGISTER_COUNT, 0, 0};
    bench_add_crc(query, 6u);
    if (!bench_is_request(query, sizeof query)) return 4;
    query[0] = (BENCH_ADDRESS % 4u) + 1u; bench_add_crc(query, 6u);
    if (bench_is_request(query, sizeof query)) return 5;
    query[0] = BENCH_ADDRESS; query[1] = 6u; bench_add_crc(query, 6u);
    if (bench_is_request(query, sizeof query)) return 6;
    uint8_t response[21] = {BENCH_ADDRESS, 3, 16, 0x48, 0x53, 0, BENCH_ADDRESS, 1, 0};
    bench_add_crc(response, 19u);
    if (!bench_is_response_for(response, sizeof response, BENCH_ADDRESS)) return 7;
    uint8_t other_address = (BENCH_ADDRESS % 4u) + 1u;
    if (bench_is_response_for(response, sizeof response, other_address)) return 8;
    response[6] = other_address; bench_add_crc(response, 19u);
    if (bench_is_response_for(response, sizeof response, BENCH_ADDRESS)) return 9;
    return 0;
}
#endif
