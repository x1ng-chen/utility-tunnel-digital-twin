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
/* Version 2: endpoints learned while discovery was unsigned (protocol /1) are
 * invalidated so every persisted broker has been authenticated at least once. */
constexpr uint8_t kStorageVersion = 2;
/* Protocol /2 wire layout, all ASCII:
 *   "UT-MQTT-DISCOVERY/2|<service>|<port>|<64 lowercase hex chars>"
 * The HMAC-SHA256 signature covers every byte up to and including the '|'
 * before the hex tail, keyed with the deployment-shared DISCOVERY_HMAC_KEY.
 * Packets without a valid signature (including all /1 packets) are rejected. */
constexpr char kPacketPrefix[] = "UT-MQTT-DISCOVERY/2|utility-tunnel|";
constexpr size_t kSignatureHexLength = 64U;

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

/* --- SHA-256 (FIPS 180-4) and HMAC-SHA256 (FIPS 198-1) ---------------------
 * Implemented here rather than via an SDK library so the exact code the ESP
 * runs is also what the host unit test exercises. */
inline uint32_t sha256Rotr(uint32_t value, uint32_t count) {
  return (value >> count) | (value << (32U - count));
}

struct Sha256Context {
  uint32_t h[8];
  uint64_t length;
  uint8_t buffer[64];
  size_t buffered;
};

inline void sha256Init(Sha256Context* context) {
  context->h[0] = 0x6a09e667UL; context->h[1] = 0xbb67ae85UL;
  context->h[2] = 0x3c6ef372UL; context->h[3] = 0xa54ff53aUL;
  context->h[4] = 0x510e527fUL; context->h[5] = 0x9b05688cUL;
  context->h[6] = 0x1f83d9abUL; context->h[7] = 0x5be0cd19UL;
  context->length = 0ULL;
  context->buffered = 0U;
}

inline void sha256Block(Sha256Context* context, const uint8_t* block) {
  static const uint32_t k[64] = {
      0x428a2f98UL, 0x71374491UL, 0xb5c0fbcfUL, 0xe9b5dba5UL,
      0x3956c25bUL, 0x59f111f1UL, 0x923f82a4UL, 0xab1c5ed5UL,
      0xd807aa98UL, 0x12835b01UL, 0x243185beUL, 0x550c7dc3UL,
      0x72be5d74UL, 0x80deb1feUL, 0x9bdc06a7UL, 0xc19bf174UL,
      0xe49b69c1UL, 0xefbe4786UL, 0x0fc19dc6UL, 0x240ca1ccUL,
      0x2de92c6fUL, 0x4a7484aaUL, 0x5cb0a9dcUL, 0x76f988daUL,
      0x983e5152UL, 0xa831c66dUL, 0xb00327c8UL, 0xbf597fc7UL,
      0xc6e00bf3UL, 0xd5a79147UL, 0x06ca6351UL, 0x14292967UL,
      0x27b70a85UL, 0x2e1b2138UL, 0x4d2c6dfcUL, 0x53380d13UL,
      0x650a7354UL, 0x766a0abbUL, 0x81c2c92eUL, 0x92722c85UL,
      0xa2bfe8a1UL, 0xa81a664bUL, 0xc24b8b70UL, 0xc76c51a3UL,
      0xd192e819UL, 0xd6990624UL, 0xf40e3585UL, 0x106aa070UL,
      0x19a4c116UL, 0x1e376c08UL, 0x2748774cUL, 0x34b0bcb5UL,
      0x391c0cb3UL, 0x4ed8aa4aUL, 0x5b9cca4fUL, 0x682e6ff3UL,
      0x748f82eeUL, 0x78a5636fUL, 0x84c87814UL, 0x8cc70208UL,
      0x90befffaUL, 0xa4506cebUL, 0xbef9a3f7UL, 0xc67178f2UL,
  };
  uint32_t w[64];
  for (size_t i = 0U; i < 16U; ++i) {
    w[i] = (static_cast<uint32_t>(block[i * 4U]) << 24) |
           (static_cast<uint32_t>(block[i * 4U + 1U]) << 16) |
           (static_cast<uint32_t>(block[i * 4U + 2U]) << 8) |
           static_cast<uint32_t>(block[i * 4U + 3U]);
  }
  for (size_t i = 16U; i < 64U; ++i) {
    const uint32_t s0 = sha256Rotr(w[i - 15U], 7U) ^ sha256Rotr(w[i - 15U], 18U) ^
                        (w[i - 15U] >> 3);
    const uint32_t s1 = sha256Rotr(w[i - 2U], 17U) ^ sha256Rotr(w[i - 2U], 19U) ^
                        (w[i - 2U] >> 10);
    w[i] = w[i - 16U] + s0 + w[i - 7U] + s1;
  }
  uint32_t a = context->h[0], b = context->h[1], c = context->h[2], d = context->h[3];
  uint32_t e = context->h[4], f = context->h[5], g = context->h[6], h = context->h[7];
  for (size_t i = 0U; i < 64U; ++i) {
    const uint32_t sum1 = sha256Rotr(e, 6U) ^ sha256Rotr(e, 11U) ^ sha256Rotr(e, 25U);
    const uint32_t choice = (e & f) ^ (~e & g);
    const uint32_t temp1 = h + sum1 + choice + k[i] + w[i];
    const uint32_t sum0 = sha256Rotr(a, 2U) ^ sha256Rotr(a, 13U) ^ sha256Rotr(a, 22U);
    const uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
    const uint32_t temp2 = sum0 + majority;
    h = g; g = f; f = e; e = d + temp1;
    d = c; c = b; b = a; a = temp1 + temp2;
  }
  context->h[0] += a; context->h[1] += b; context->h[2] += c; context->h[3] += d;
  context->h[4] += e; context->h[5] += f; context->h[6] += g; context->h[7] += h;
}

inline void sha256Update(Sha256Context* context, const uint8_t* data, size_t length) {
  context->length += length;
  while (length > 0U) {
    const size_t room = 64U - context->buffered;
    const size_t take = (room < length) ? room : length;
    for (size_t i = 0U; i < take; ++i) {
      context->buffer[context->buffered + i] = data[i];
    }
    context->buffered += take;
    data += take;
    length -= take;
    if (context->buffered == 64U) {
      sha256Block(context, context->buffer);
      context->buffered = 0U;
    }
  }
}

inline void sha256Final(Sha256Context* context, uint8_t out[32]) {
  const uint64_t bitLength = context->length * 8ULL;
  const uint8_t one = 0x80U;
  const uint8_t zero = 0x00U;
  sha256Update(context, &one, 1U);
  while (context->buffered != 56U) sha256Update(context, &zero, 1U);
  uint8_t lengthBytes[8];
  for (size_t i = 0U; i < 8U; ++i) {
    lengthBytes[i] = static_cast<uint8_t>(bitLength >> (56U - i * 8U));
  }
  sha256Update(context, lengthBytes, 8U);
  for (size_t i = 0U; i < 8U; ++i) {
    out[i * 4U] = static_cast<uint8_t>(context->h[i] >> 24);
    out[i * 4U + 1U] = static_cast<uint8_t>(context->h[i] >> 16);
    out[i * 4U + 2U] = static_cast<uint8_t>(context->h[i] >> 8);
    out[i * 4U + 3U] = static_cast<uint8_t>(context->h[i]);
  }
}

inline void hmacSha256(const uint8_t* key, size_t keyLength,
                       const uint8_t* message, size_t messageLength, uint8_t out[32]) {
  uint8_t keyBlock[64] = {};
  uint8_t pad[64];
  uint8_t inner[32];
  Sha256Context context;

  /* Keys longer than the block size are hashed first (FIPS 198-1). */
  if (keyLength > sizeof(keyBlock)) {
    sha256Init(&context);
    sha256Update(&context, key, keyLength);
    sha256Final(&context, keyBlock);
  } else {
    for (size_t i = 0U; i < keyLength; ++i) keyBlock[i] = key[i];
  }
  for (size_t i = 0U; i < 64U; ++i) pad[i] = static_cast<uint8_t>(keyBlock[i] ^ 0x36U);
  sha256Init(&context);
  sha256Update(&context, pad, 64U);
  sha256Update(&context, message, messageLength);
  sha256Final(&context, inner);
  for (size_t i = 0U; i < 64U; ++i) pad[i] = static_cast<uint8_t>(keyBlock[i] ^ 0x5cU);
  sha256Init(&context);
  sha256Update(&context, pad, 64U);
  sha256Update(&context, inner, 32U);
  sha256Final(&context, out);
}

inline int hexValue(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}
}  // namespace mqtt_discovery_detail

inline bool endpointEquals(const BrokerEndpoint& left, const BrokerEndpoint& right) {
  return right.port == left.port && std::memcmp(left.address, right.address, sizeof(left.address)) == 0;
}

inline bool parseDiscoveryPacket(const char* data, size_t length, const uint8_t sender[4],
                                 const char* key, size_t keyLength, BrokerEndpoint* endpoint) {
  if (data == nullptr || sender == nullptr || endpoint == nullptr) return false;
  /* No key configured means discovery is disabled, not downgraded to unsigned. */
  if (key == nullptr || keyLength == 0U) return false;
  constexpr size_t prefixLength = sizeof(mqtt_discovery_detail::kPacketPrefix) - 1U;
  if (length <= prefixLength ||
      std::memcmp(data, mqtt_discovery_detail::kPacketPrefix, prefixLength) != 0) {
    return false;
  }

  size_t separator = prefixLength;
  while (separator < length && data[separator] >= '0' && data[separator] <= '9') {
    ++separator;
  }
  if (separator == prefixLength) return false;
  if (data[separator] != '|') return false;
  if ((length - separator - 1U) != mqtt_discovery_detail::kSignatureHexLength) return false;

  uint32_t port = 0U;
  for (size_t i = prefixLength; i < separator; ++i) {
    port = port * 10U + static_cast<uint32_t>(data[i] - '0');
    if (port > 65535U) return false;
  }
  if (port == 0U) return false;

  uint8_t expected[32];
  mqtt_discovery_detail::hmacSha256(
      reinterpret_cast<const uint8_t*>(key), keyLength,
      reinterpret_cast<const uint8_t*>(data), separator + 1U, expected);
  /* Compare without an early exit so the answer does not leak how many bytes
   * matched. */
  uint8_t difference = 0U;
  for (size_t i = 0U; i < 32U; ++i) {
    const int high = mqtt_discovery_detail::hexValue(data[separator + 1U + i * 2U]);
    const int low = mqtt_discovery_detail::hexValue(data[separator + 1U + i * 2U + 1U]);
    if ((high < 0) || (low < 0)) return false;
    difference |= static_cast<uint8_t>(((high << 4) | low) ^ expected[i]);
  }
  if (difference != 0U) return false;

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
