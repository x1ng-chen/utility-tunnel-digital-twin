#include "bench_protocol.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    assert(bench_self_test() == 0);
    uint8_t frame[8] = {BENCH_ADDRESS, 3, 0, 0, 0, 8};
    bench_add_crc(frame, 6);
    assert(bench_is_request(frame, sizeof frame));
    for (size_t size = 0; size < sizeof frame; ++size)
        assert(!bench_is_request(frame, size));
    frame[5] = 9; bench_add_crc(frame, 6);
    assert(!bench_is_request(frame, sizeof frame));
    frame[5] = 8; frame[3] = 1; bench_add_crc(frame, 6);
    assert(!bench_is_request(frame, sizeof frame));
    frame[3] = 0; frame[0] = 0; bench_add_crc(frame, 6);
    assert(!bench_is_request(frame, sizeof frame));
    for (uint8_t address = 1; address <= 4; ++address) {
        uint8_t reply[21] = {address, 3, 16, 0x48, 0x53, 0, address, 1, 0};
        bench_add_crc(reply, 19);
        for (uint8_t target = 1; target <= 4; ++target)
            assert(bench_is_response_for(reply, sizeof reply, target) == (address == target));
        assert(!bench_is_response_for(reply, sizeof reply, 0));
        assert(!bench_is_response_for(reply, sizeof reply, 5));
        assert(!bench_is_response_for(reply, 20, address));
        reply[6] = (address % 4) + 1; bench_add_crc(reply, 19);
        assert(!bench_is_response_for(reply, sizeof reply, address));
    }
    printf("Protocol checks passed for local address %u\n", (unsigned)BENCH_ADDRESS);
    return 0;
}
