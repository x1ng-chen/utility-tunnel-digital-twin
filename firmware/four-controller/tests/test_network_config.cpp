#include "test_support.h"
#include "../gateway/include/network_config.h"
#ifndef UT_TEST_EMULATED
#include <stdio.h>
#endif
extern "C" {volatile UtTestResults ut_test_results;}
static const char canonical[]="{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"local-1\",\"action\":\"set\",\"ssid\":\"Local Lab\",\"wifiPassword\":\"example-only-123\",\"mqttHost\":\"192.168.1.2\",\"mqttPort\":1884,\"mqttUser\":\"\",\"mqttPassword\":\"\",\"ntpServer\":\"pool.ntp.org\"}";
void test_entry(void) {
  memset((void *)&ut_test_results,0,sizeof ut_test_results);UtConfigRequest r;
  GROUP();CHECK(ut_config_parse(canonical,sizeof canonical-1U,r));CHECK(r.action==UT_CONFIG_SET);CHECK(r.config.mqttPort==1884);
  for(size_t i=0;i<sizeof canonical-1U;++i)CHECK(!ut_config_parse(canonical,i,r));
  GROUP();
  const char *bad[]={
    "{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"a\",\"action\":\"status\",\"action\":\"status\"}",
    "{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"a\\u0000b\",\"action\":\"status\"}",
    "{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"a\",\"action\":\"clear\"}",
    "{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"a\",\"action\":\"clear\",\"confirm\":\"no\"}",
    "{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"a\",\"action\":\"status\"}true",
    "{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"a\",\"status\":\"status\"}",
    "{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"\",\"action\":\"status\"}"};
  for(const char *s:bad)CHECK(!ut_config_parse(s,strlen(s),r));
  const char status[]="{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"a\",\"action\":\"status\"}";
  CHECK(ut_config_parse(status,sizeof status-1U,r));CHECK(r.action==UT_CONFIG_STATUS);
  const char clear[]="{\"schema\":\"ut.gateway.config.v1\",\"requestId\":\"a\",\"action\":\"clear\",\"confirm\":\"ERASE_NETWORK_CONFIGURATION\"}";
  CHECK(ut_config_parse(clear,sizeof clear-1U,r));CHECK(r.action==UT_CONFIG_CLEAR);
  GROUP();CHECK(ut_config_parse(canonical,sizeof canonical-1U,r));UtNetworkConfig c=r.config,decoded{};
  auto record=ut_cfg_record(c);CHECK(ut_cfg_read(&record,sizeof record,decoded));CHECK(!memcmp(&c,&decoded,sizeof c));
  for(size_t i=0;i<sizeof record;++i) {
    auto copy=record;((uint8_t *)&copy)[i]^=1U;
    /* Struct trailing padding is not part of the checksum or persisted fields. */
    if(i<offsetof(UtConfigRecord,checksum)+sizeof(uint32_t))CHECK(!ut_cfg_read(&copy,sizeof copy,decoded));
  }
  CHECK(!ut_cfg_read(&record,sizeof record-1U,decoded));
  GROUP();
  c=r.config;memset(c.ssid,'x',sizeof c.ssid);CHECK(!ut_cfg_valid(c));
  c=r.config;strcpy(c.wifiPassword,"short");CHECK(!ut_cfg_valid(c));
  c=r.config;c.wifiPassword[0]=0;CHECK(ut_cfg_valid(c));
  c=r.config;c.mqttPort=0;CHECK(!ut_cfg_valid(c));
  c=r.config;strcpy(c.mqttHost,"http://broker/");CHECK(!ut_cfg_valid(c));
  c=r.config;strcpy(c.mqttUser,"user\n");CHECK(!ut_cfg_valid(c));
  c=r.config;memset(c.wifiPassword,'a',64U);c.wifiPassword[64]=0;CHECK(ut_cfg_valid(c));
  c.wifiPassword[0]='z';CHECK(!ut_cfg_valid(c));
  ut_test_results.done=0x5554U;
}
#ifndef UT_TEST_EMULATED
int main(){test_entry();printf("{\"checks\":%lu,\"failures\":%lu,\"firstLine\":%lu,\"groups\":%lu}\n",(unsigned long)ut_test_results.checks,(unsigned long)ut_test_results.failures,(unsigned long)ut_test_results.first_line,(unsigned long)ut_test_results.groups);return ut_test_results.failures?1:0;}
#endif
