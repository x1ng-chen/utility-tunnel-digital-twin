#include <cstring>

#include <unity.h>

#include "mqtt_discovery.h"

void test_accepts_valid_packet_and_uses_sender_address() {
  const char packet[] = "UT-MQTT-DISCOVERY/2|utility-tunnel|1884|0ecd20b0b1069e60760f442846cbdfd028600e21a6f442b385c9de05636671ff";
  const uint8_t sender[] = {10, 249, 215, 113};
  BrokerEndpoint endpoint{};

  const char key[] = "bench-discovery-key";
  TEST_ASSERT_TRUE(parseDiscoveryPacket(packet, std::strlen(packet), sender,
                                        key, std::strlen(key), &endpoint));
  TEST_ASSERT_EQUAL_UINT8_ARRAY(sender, endpoint.address, 4);
  TEST_ASSERT_EQUAL_UINT16(1884, endpoint.port);
}

void test_rejects_wrong_service_version_and_invalid_port() {
  const uint8_t sender[] = {10, 0, 0, 2};
  BrokerEndpoint endpoint{};
  const char wrongService[] = "UT-MQTT-DISCOVERY/2|other-service|1884|0ecd20b0b1069e60760f442846cbdfd028600e21a6f442b385c9de05636671ff";
  const char wrongVersion[] = "UT-MQTT-DISCOVERY/1|utility-tunnel|1884";
  const char invalidPort[] = "UT-MQTT-DISCOVERY/2|utility-tunnel|70000|0ecd20b0b1069e60760f442846cbdfd028600e21a6f442b385c9de05636671ff";
  const char key[] = "bench-discovery-key";

  TEST_ASSERT_FALSE(parseDiscoveryPacket(wrongService, std::strlen(wrongService), sender, key, std::strlen(key), &endpoint));
  TEST_ASSERT_FALSE(parseDiscoveryPacket(wrongVersion, std::strlen(wrongVersion), sender, key, std::strlen(key), &endpoint));
  TEST_ASSERT_FALSE(parseDiscoveryPacket(invalidPort, std::strlen(invalidPort), sender, key, std::strlen(key), &endpoint));
  TEST_ASSERT_FALSE(parseDiscoveryPacket(wrongService, std::strlen(wrongService), sender, "", 0U, &endpoint));
}

void test_validates_persisted_endpoint_with_crc() {
  const BrokerEndpoint endpoint{{192, 168, 10, 25}, 1884};
  StoredBrokerEndpoint stored = makeStoredEndpoint(endpoint);
  BrokerEndpoint restored{};

  TEST_ASSERT_TRUE(loadStoredEndpoint(stored, &restored));
  TEST_ASSERT_TRUE(endpointEquals(endpoint, restored));

  stored.address[3] ^= 1;
  TEST_ASSERT_FALSE(loadStoredEndpoint(stored, &restored));
}

void test_rejects_erased_or_outdated_persisted_data() {
  StoredBrokerEndpoint erased{};
  std::memset(&erased, 0xff, sizeof(erased));
  BrokerEndpoint endpoint{};
  TEST_ASSERT_FALSE(loadStoredEndpoint(erased, &endpoint));

  const BrokerEndpoint original{{192, 168, 1, 9}, 1884};
  StoredBrokerEndpoint outdated = makeStoredEndpoint(original);
  outdated.version++;
  TEST_ASSERT_FALSE(loadStoredEndpoint(outdated, &endpoint));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_accepts_valid_packet_and_uses_sender_address);
  RUN_TEST(test_rejects_wrong_service_version_and_invalid_port);
  RUN_TEST(test_validates_persisted_endpoint_with_crc);
  RUN_TEST(test_rejects_erased_or_outdated_persisted_data);
  return UNITY_END();
}
