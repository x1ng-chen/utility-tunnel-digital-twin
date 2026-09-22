#include <cstdio>

#include "network_client_config.h"

namespace {

int failures = 0;

#define CHECK_TRUE(expression)                                                     \
  do {                                                                             \
    if (!(expression)) {                                                           \
      std::fprintf(stderr, "%s:%d: CHECK_TRUE(%s) failed\n", __FILE__, __LINE__, \
                   #expression);                                                   \
      ++failures;                                                                  \
    }                                                                              \
  } while (0)

struct FakeClient {
  bool socket_connected = false;
  int no_delay_calls = 0;
  int keep_alive_calls = 0;
  bool no_delay_value = false;
  unsigned short keep_alive_idle = 0;
  unsigned short keep_alive_interval = 0;
  unsigned char keep_alive_count = 0;

  bool connected() const { return socket_connected; }

  void setNoDelay(bool value) {
    ++no_delay_calls;
    no_delay_value = value;
  }

  void keepAlive(unsigned short idle, unsigned short interval,
                 unsigned char count) {
    ++keep_alive_calls;
    keep_alive_idle = idle;
    keep_alive_interval = interval;
    keep_alive_count = count;
  }
};

void test_disconnected_client_is_never_dereferenced_for_socket_options() {
  FakeClient client{};

  const bool configured =
      network_client_config::ConfigureConnectedClient(client);

  CHECK_TRUE(!configured);
  CHECK_TRUE(client.no_delay_calls == 0);
  CHECK_TRUE(client.keep_alive_calls == 0);
}

void test_connected_client_receives_socket_options_once() {
  FakeClient client{};
  client.socket_connected = true;

  const bool configured =
      network_client_config::ConfigureConnectedClient(client);

  CHECK_TRUE(configured);
  CHECK_TRUE(client.no_delay_calls == 1);
  CHECK_TRUE(client.no_delay_value);
  CHECK_TRUE(client.keep_alive_calls == 1);
  CHECK_TRUE(client.keep_alive_idle == 10);
  CHECK_TRUE(client.keep_alive_interval == 5);
  CHECK_TRUE(client.keep_alive_count == 3);
}

}  // namespace

int main() {
  test_disconnected_client_is_never_dereferenced_for_socket_options();
  test_connected_client_receives_socket_options_once();
  if (failures == 0) std::puts("network_client_config tests passed");
  return failures == 0 ? 0 : 1;
}
