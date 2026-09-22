#pragma once

namespace network_client_config {

template <typename Client>
bool ConfigureConnectedClient(Client& client) {
  if (!client.connected()) return false;
  client.setNoDelay(true);
  client.keepAlive(10, 5, 3);
  return true;
}

}  // namespace network_client_config
