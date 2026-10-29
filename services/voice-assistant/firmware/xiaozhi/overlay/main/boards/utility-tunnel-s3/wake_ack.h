#ifndef UTILITY_TUNNEL_WAKE_ACK_H
#define UTILITY_TUNNEL_WAKE_ACK_H

#include "config.h"
#include <string_view>

namespace UtilityTunnelVoice {
extern const char wake_ack_start[] asm("_binary_ut_wake_ack_ogg_start");
extern const char wake_ack_end[] asm("_binary_ut_wake_ack_ogg_end");

inline std::string_view WakeAcknowledgement() {
    return {wake_ack_start, static_cast<size_t>(wake_ack_end - wake_ack_start)};
}
extern const char stop_ack_start[] asm("_binary_ut_stop_ack_ogg_start");
extern const char stop_ack_end[] asm("_binary_ut_stop_ack_ogg_end");
inline std::string_view StopAcknowledgement() {
    return {stop_ack_start, static_cast<size_t>(stop_ack_end - stop_ack_start)};
}
}  // namespace UtilityTunnelVoice
#endif
