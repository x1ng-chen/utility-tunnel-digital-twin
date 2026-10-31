#ifndef UT_NETWORK_CONFIG_H
#define UT_NETWORK_CONFIG_H
#include "command_json.h"
#include <stddef.h>

/* Provisioned through local UART only. Never received over MQTT. */
struct UtNetworkConfig {
  char ssid[33],wifiPassword[65],mqttHost[128],mqttUser[65],mqttPassword[129],ntpServer[128];
  uint16_t mqttPort;
};
struct UtConfigRequest {char requestId[33];uint8_t action;UtNetworkConfig config;};
struct UtConfigRecord {uint32_t magic;UtNetworkConfig config;uint32_t checksum;};
enum {UT_CONFIG_SET=1,UT_CONFIG_STATUS=2,UT_CONFIG_CLEAR=3};

static inline bool ut_cfg_string(const char *p,size_t capacity,bool required=false)
{
  const char *end=(const char *)memchr(p,0,capacity);
  if(!end||(required&&end==p))return false;
  for(const char *c=p;c!=end;++c)if((unsigned char)*c<32U||*c==127)return false;
  return true;
}
static inline bool ut_cfg_host(const char *s,size_t capacity)
{
  if(!ut_cfg_string(s,capacity,true))return false;
  for(;*s;++s)if(!((*s>='a'&&*s<='z')||(*s>='A'&&*s<='Z')||(*s>='0'&&*s<='9')||strchr(".-_:",*s)))return false;
  return true;
}
static inline bool ut_cfg_valid(const UtNetworkConfig &c)
{
  if(!ut_cfg_string(c.ssid,sizeof c.ssid,true)||!ut_cfg_string(c.wifiPassword,sizeof c.wifiPassword)||
      !ut_cfg_host(c.mqttHost,sizeof c.mqttHost)||!ut_cfg_host(c.ntpServer,sizeof c.ntpServer)||
      !ut_cfg_string(c.mqttUser,sizeof c.mqttUser)||!ut_cfg_string(c.mqttPassword,sizeof c.mqttPassword)||!c.mqttPort)return false;
  size_t n=strlen(c.wifiPassword);
  if(n&&n<8U)return false;
  if(n==64U)for(const char *p=c.wifiPassword;*p;++p)if(!strchr("0123456789abcdefABCDEF",*p))return false;
  return true;
}
static inline bool ut_cfg_copy(JsonVariantConst value,char *out,size_t capacity)
{
  if(!ut_json_text(value)||value.as<JsonString>().size()>=capacity)return false;
  strcpy(out,value.as<const char *>());return true;
}
static inline bool ut_config_parse(const char *p,size_t n,UtConfigRequest &request)
{
  memset(&request,0,sizeof request);
  if(n>1024U)return false;
  StaticJsonDocument<2048> doc;
  if(deserializeJson(doc,p,n,DeserializationOption::NestingLimit(2))||!doc.is<JsonObject>()||
      !ut_json_text(doc["schema"])||strcmp(doc["schema"],"ut.gateway.config.v1")||
      !ut_cfg_copy(doc["requestId"],request.requestId,sizeof request.requestId)||!request.requestId[0]||!ut_json_text(doc["action"]))return false;
  for(const char *s=request.requestId;*s;++s)if(!((*s>='a'&&*s<='z')||(*s>='A'&&*s<='Z')||(*s>='0'&&*s<='9')||strchr("._:-",*s)))return false;
  const char *action=doc["action"];
  request.action=!strcmp(action,"set")?UT_CONFIG_SET:!strcmp(action,"status")?UT_CONFIG_STATUS:!strcmp(action,"clear")?UT_CONFIG_CLEAR:0;
  unsigned count=request.action==UT_CONFIG_SET?10U:request.action==UT_CONFIG_CLEAR?4U:3U;
  if(!request.action||doc.size()!=count||!ut_json_shape(p,n,count))return false;
  const char *keys[]={"schema","requestId","action","ssid","wifiPassword","mqttHost","mqttPort","mqttUser","mqttPassword","ntpServer","confirm"};
  for(JsonPairConst kv:doc.as<JsonObjectConst>()) {
    bool allowed=false;
    for(unsigned i=0;i<11U;++i)if(!strcmp(keys[i],kv.key().c_str())&&
        (i<3U||(request.action==UT_CONFIG_SET&&i<10U)||(request.action==UT_CONFIG_CLEAR&&i==10U)))allowed=true;
    if(!allowed)return false;
  }
  if(request.action==UT_CONFIG_CLEAR)return ut_json_text(doc["confirm"])&&!strcmp(doc["confirm"],"ERASE_NETWORK_CONFIGURATION");
  if(request.action==UT_CONFIG_STATUS)return true;
  auto &c=request.config;
  if(!doc["mqttPort"].is<uint16_t>())return false;
  c.mqttPort=doc["mqttPort"];
  return ut_cfg_copy(doc["ssid"],c.ssid,sizeof c.ssid)&&ut_cfg_copy(doc["wifiPassword"],c.wifiPassword,sizeof c.wifiPassword)&&
    ut_cfg_copy(doc["mqttHost"],c.mqttHost,sizeof c.mqttHost)&&ut_cfg_copy(doc["mqttUser"],c.mqttUser,sizeof c.mqttUser)&&
    ut_cfg_copy(doc["mqttPassword"],c.mqttPassword,sizeof c.mqttPassword)&&ut_cfg_copy(doc["ntpServer"],c.ntpServer,sizeof c.ntpServer)&&ut_cfg_valid(c);
}
static inline uint32_t ut_cfg_checksum(const void *p,size_t n)
{
  const uint8_t *bytes=(const uint8_t *)p;uint32_t h=2166136261U;
  for(size_t i=0;i<n;++i)h=(h^bytes[i])*16777619U;
  return h; /* Corruption detection only, not cryptographic authentication. */
}
static inline UtConfigRecord ut_cfg_record(const UtNetworkConfig &c)
{
  UtConfigRecord r;memset(&r,0,sizeof r);r.magic=0x554e4331U;r.config=c;
  r.checksum=ut_cfg_checksum(&r,offsetof(UtConfigRecord,checksum));return r;
}
static inline bool ut_cfg_read(const void *p,size_t n,UtNetworkConfig &c)
{
  if(n!=sizeof(UtConfigRecord))return false;
  UtConfigRecord r;memcpy(&r,p,sizeof r);
  if(r.magic!=0x554e4331U||r.checksum!=ut_cfg_checksum(&r,offsetof(UtConfigRecord,checksum))||!ut_cfg_valid(r.config))return false;
  c=r.config;return true;
}
#endif
