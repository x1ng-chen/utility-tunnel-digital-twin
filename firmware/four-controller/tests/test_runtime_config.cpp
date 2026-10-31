#define UT_RUNTIME_CONFIG_TEST 1
#include "test_support.h"
#include "../gateway/include/runtime_config.h"
extern "C" {volatile UtTestResults ut_test_results;}
static void send(UtRuntimeConfig &c,const char *s){Serial.clear();Serial.feed(s);for(unsigned i=0;i<70U&&Serial.available();++i)c.poll();}
static const char set_config[]="{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"test-1\",\"action\":\"set\",\"ssid\":\"Local Lab\",\"wifiPassword\":\"example-only-123\",\"mqttHost\":\"192.168.1.2\",\"mqttPort\":1884,\"mqttUser\":\"user\",\"mqttPassword\":\"local-mqtt-test\",\"ntpServer\":\"pool.ntp.org\"}\n";
static const char status[]="{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"status-1\",\"action\":\"status\"}\n";
void test_entry() {
  memset((void *)&ut_test_results,0,sizeof ut_test_results);
  GROUP();UtRuntimeConfig a;a.begin();CHECK(!a.configured());send(a,status);CHECK(strstr(Serial.output,"\"configured\":false"));CHECK(nvs.writes==0U);
  GROUP();send(a,set_config);CHECK(nvs.writes==1U);CHECK(a.restarting());CHECK(!a.configured());CHECK(strstr(Serial.output,"\"result\":\"saved\""));
  CHECK(!strstr(Serial.output,"example-only-123"));CHECK(!strstr(Serial.output,"local-mqtt-test"));
  send(a,set_config);CHECK(nvs.writes==1U);CHECK(strstr(Serial.output,"restarting"));fake_time=201;a.poll();CHECK(ESP.restarts==1U);
  GROUP();UtRuntimeConfig b;b.begin();CHECK(b.configured());CHECK(b.value().mqttPort==1884U);send(b,set_config);CHECK(nvs.writes==1U);CHECK(!b.restarting());CHECK(strstr(Serial.output,"unchanged"));
  GROUP();nvs.data[12]^=1U;UtRuntimeConfig broken;broken.begin();CHECK(!broken.configured());send(broken,status);CHECK(strstr(Serial.output,"invalid_storage"));nvs.data[12]^=1U;
  GROUP();nvs.writable=false;send(broken,set_config);CHECK(!broken.restarting());CHECK(strstr(Serial.output,"storage_unavailable"));nvs.writable=true;
  GROUP();char oversized[1300];memset(oversized,'x',sizeof oversized-2U);oversized[sizeof oversized-2U]='\n';oversized[sizeof oversized-1U]=0;
  send(b,oversized);CHECK(Serial.written==0U);send(b,status);CHECK(strstr(Serial.output,"status-1"));
  GROUP();send(b,"{\"schema\":");fake_time+=2100U;b.poll();send(b,"\"ut.gateway.config.v1\"}\n");CHECK(Serial.written==0U);send(b,status);CHECK(strstr(Serial.output,"status-1"));
  GROUP();send(b,"{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"bad\r-id\",\"action\":\"status\"}\n");CHECK(strstr(Serial.output,"invalid_request"));
  send(b,"{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"crlf\",\"action\":\"status\"}\r\n");CHECK(strstr(Serial.output,"crlf"));
  GROUP();send(b,"{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"clear-1\",\"action\":\"clear\",\"confirm\":\"ERASE_NETWORK_CONFIGURATION\"}\n");
  CHECK(b.restarting());UtRuntimeConfig cleared;cleared.begin();CHECK(!cleared.configured());send(cleared,status);CHECK(strstr(Serial.output,"cleared"));
  ut_test_results.done=0x5554U;
}
#ifndef UT_TEST_EMULATED
int main(){test_entry();printf("{\"checks\":%lu,\"failures\":%lu,\"firstLine\":%lu,\"groups\":%lu}\n",(unsigned long)ut_test_results.checks,(unsigned long)ut_test_results.failures,(unsigned long)ut_test_results.first_line,(unsigned long)ut_test_results.groups);return ut_test_results.failures?1:0;}
#endif
