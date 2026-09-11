#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

struct BrokerEndpoint {
  uint8_t address[4];
  uint16_t port;
};

#pragma pack(push, 1)
struct StoredBrokerEndpoint {
  uint32_t magic;
  uint8_t version;
  uint8_t address[4];
  uint16_t port;
  uint32_t crc;
};
#pragma pack(pop)

namespace mqtt_discovery_detail {
constexpr uint32_t kStorageMagic = 0x55544d51UL;  // "UTMQ"
constexpr uint8_t kStorageVersion = 1;
constexpr char kPacketPrefix[] = "UT-MQTT-DISCOVERY/1|utility-tunnel|";

inline uint32_t crc32(const uint8_t* bytes, size_t length) {
  uint32_t crc = 0xffffffffUL;
  for (size_t i = 0; i < length; ++i) {
    crc ^= bytes[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc >> 1) ^ (0xedb88320UL & (0U - (crc & 1U)));
    }
  }
  return ~crc;
}
}  // namespace mqtt_discovery_detail

inline bool endpointEquals(const BrokerEndpoint& left, const BrokerEndpoint& right) {
  return left.port == right.port && std::memcmp(left.address, right.address, sizeof(left.address)) == 0;
}

inline bool parseDiscoveryPacket(const char* data, size_t length, const uint8_t sender[4],
                                 BrokerEndpoint* endpoint) {
  if (data == nullptr || sender == nullptr || endpoint == nullptr) return false;
  constexpr size_t prefixLength = sizeof(mqtt_discovery_detail::kPacketPrefix) - 1;
  if (length <= prefixLength ||
      std::memcmp(data, mqtt_discovery_detail::kPacketPrefix, prefixLength) != 0) {
    return false;
  }

  uint32_t port = 0;
  for (size_t i = prefixLength; i < length; ++i) {
    if (data[i] < '0' || data[i] > '9') return false;
    port = port * 10U + static_cast<uint32_t>(data[i] - '0');
    if (port > 65535U) return false;
  }
  if (port == 0) return false;

  std::memcpy(endpoint->address, sender, sizeof(endpoint->address));
  endpoint->port = static_cast<uint16_t>(port);
  return true;
}

inline StoredBrokerEndpoint makeStoredEndpoint(const BrokerEndpoint& endpoint) {
  StoredBrokerEndpoint stored{};
  stored.magic = mqtt_discovery_detail::kStorageMagic;
  stored.version = mqtt_discovery_detail::kStorageVersion;
  std::memcpy(stored.address, endpoint.address, sizeof(stored.address));
  stored.port = endpoint.port;
  stored.crc = mqtt_discovery_detail::crc32(reinterpret_cast<const uint8_t*>(&stored),
                                             offsetof(StoredBrokerEndpoint, crc));
  return stored;
}

inline bool loadStoredEndpoint(const StoredBrokerEndpoint& stored, BrokerEndpoint* endpoint) {
  if (endpoint == nullptr || stored.magic != mqtt_discovery_detail::kStorageMagic ||
      stored.version != mqtt_discovery_detail::kStorageVersion || stored.port == 0) {
    return false;
  }
  const uint32_t expected = mqtt_discovery_detail::crc32(
      reinterpret_cast<const uint8_t*>(&stored), offsetof(StoredBrokerEndpoint, crc));
  if (stored.crc != expected) return false;
  std::memcpy(endpoint->address, stored.address, sizeof(endpoint->address));
  endpoint->port = stored.port;
  return true;
}
