#ifndef UT_RUNTIME_CONFIG_H
#define UT_RUNTIME_CONFIG_H
#ifdef UT_RUNTIME_CONFIG_TEST
#include "test_runtime_hal.h"
#else
#include <Arduino.h>
#include <Preferences.h>
#endif
#include "network_config.h"
#include "../../common/firmware_version.h"

class UtRuntimeConfig {
  Preferences storage;
  UtNetworkConfig active{};
  char line[1025]{};
  size_t used=0;
  uint32_t last_byte=0,restart_at=0;
  bool ready=false,configured_=false,discard=false,restart_=false;
  const char *source="unconfigured";
  void reply(const char *id,const char *result,bool restart=false) {
    char out[384];
#ifdef UT_RUNTIME_CONFIG_TEST
    unsigned long stack_free=0; /* Host stub has no FreeRTOS stack measurement. */
#else
    /* ESP-IDF's Xtensa port reports this watermark in bytes, not words. */
    unsigned long stack_free=(unsigned long)uxTaskGetStackHighWaterMark(nullptr);
#endif
    int n=snprintf(out,sizeof out,"{\"schema\":\"ut.gateway.config-ack.v1\",\"requestId\":\"%s\",\"result\":\"%s\",\"configured\":%s,\"restart\":%s,\"source\":\"%s\",\"firmware\":\"%s\",\"loopStackMinFreeBytes\":%lu}\n",
      id,result,configured_?"true":"false",restart?"true":"false",source,UT_FIRMWARE_VERSION,stack_free);
    if(n>0&&(size_t)n<sizeof out&&Serial.availableForWrite()>=n)Serial.write((const uint8_t *)out,(size_t)n);
  }
  bool persist(const UtConfigRecord &record) {
    if(!ready||storage.putBytes("config",&record,sizeof record)!=sizeof record)return false;
    UtConfigRecord check{};
    return storage.getBytes("config",&check,sizeof check)==sizeof check&&!memcmp(&record,&check,sizeof check);
  }
  void handle() {
    UtConfigRequest request;
    if(!ut_config_parse(line,used,request)){reply("","invalid_request");return;}
    if(request.action==UT_CONFIG_STATUS){reply(request.requestId,ready?"status":"storage_unavailable");return;}
    if(restart_){reply(request.requestId,"restarting",true);return;}
    if(!ready){reply(request.requestId,"storage_unavailable");return;}
    if(request.action==UT_CONFIG_SET&&configured_&&!memcmp(&active,&request.config,sizeof active)) {
      reply(request.requestId,"unchanged");return;
    }
    UtConfigRecord record=ut_cfg_record(request.config);
    if(request.action==UT_CONFIG_CLEAR) {
      memset(&record,0,sizeof record);record.magic=0x554e4330U;
      record.checksum=ut_cfg_checksum(&record,offsetof(UtConfigRecord,checksum));
    }
    bool success=persist(record);
    memset(&request.config,0,sizeof request.config);memset(&record,0,sizeof record);
    if(!success){reply(request.requestId,"storage_unavailable");return;}
    /* Keep active credentials immutable while the network task can read them.
     * New settings take effect after a short, acknowledged restart. */
    restart_=true;restart_at=millis();reply(request.requestId,"saved",true);
  }
public:
  void begin(const UtNetworkConfig *compiled=nullptr) {
    ready=storage.begin("ut-net-v1",false);
    if(!ready){source="storage_unavailable";return;}
    if(storage.isKey("config")) {
      UtConfigRecord record{};
      if(storage.getBytesLength("config")!=sizeof record||storage.getBytes("config",&record,sizeof record)!=sizeof record){source="invalid_storage";return;}
      if(record.magic==0x554e4330U&&record.checksum==ut_cfg_checksum(&record,offsetof(UtConfigRecord,checksum))){source="cleared";return;}
      configured_=ut_cfg_read(&record,sizeof record,active);source=configured_?"nvs":"invalid_storage";
      memset(&record,0,sizeof record);return;
    }
    if(compiled&&ut_cfg_valid(*compiled)){active=*compiled;configured_=true;source="compiled_private";}
  }
  bool configured() const {return configured_;}
  bool restarting() const {return restart_;}
  const UtNetworkConfig &value() const {return active;}
  void poll() {
    uint32_t now=millis();
    if(restart_&&ut_due(now,restart_at,200U)){ESP.restart();return;}
    if(used&&ut_due(now,last_byte,2000U)){used=0;discard=true;}
    for(unsigned budget=0;budget<64U&&Serial.available();++budget) {
      int c=Serial.read();if(c<0)break;last_byte=now;
      if(c=='\n') {
        if(!discard&&used){if(line[used-1U]=='\r')--used;line[used]=0;if(used)handle();}
        memset(line,0,sizeof line);used=0;discard=false;
      } else if(!discard) {
        if(used<sizeof line-1U)line[used++]=(char)c;
        else{memset(line,0,sizeof line);used=0;discard=true;}
      }
    }
  }
};
#endif
