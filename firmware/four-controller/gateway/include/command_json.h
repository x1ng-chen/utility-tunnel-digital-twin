#ifndef UT_COMMAND_JSON_H
#define UT_COMMAND_JSON_H
#include <ArduinoJson.h>
#include "../../common/protocol.h"
struct UtRequest {
  char cmdId[81];
  uint8_t board;
  uint16_t code,value,ttl;
  uint64_t issuedAtMs;
  uint32_t receivedAt;
};
static inline bool ut_space(char c){return c==' '||c=='\r'||c=='\n'||c=='\t';}
static inline bool ut_json_string(const char *p,size_t n,size_t &i)
{
  if(i>=n||p[i++]!='"')return false;
  while(i<n) {
    unsigned char c=p[i++];
    if(c=='"')return true;
    if(c<32U)return false;
    if(c!='\\')continue;
    if(i==n)return false;
    char e=p[i++];
    if(e=='u') {
      unsigned code=0U;
      for(unsigned k=0;k<4U;k++) {
        if(i==n)return false;
        char h=p[i++];
        if(!((h>='0'&&h<='9')||(h>='a'&&h<='f')||(h>='A'&&h<='F')))return false;
        code=(code<<4U)+(unsigned)(h<='9'?h-'0':(h<='F'?h-'A'+10:h-'a'+10));
      }
      if(code==0U)return false; /* Never allow a decoded NUL in an object key/value. */
    } else if(!strchr("\"\\/bfnrt",e))return false;
  }
  return false;
}
/* Our command schema is flat and contains strings and integers only. Enforce
 * JSON quoting, separators, full consumption, and exactly seven keys before
 * the library decodes types/escapes. Duplicate keys reduce JsonObject::size. */
static inline bool ut_json_shape(const char *p,size_t n,unsigned expected_keys=7U)
{
  size_t i=0;unsigned keys=0;
  while(i<n&&ut_space(p[i]))++i;
  if(i==n||p[i++]!='{')return false;
  for(;;) {
    while(i<n&&ut_space(p[i]))++i;
    if(!ut_json_string(p,n,i))return false;
    while(i<n&&ut_space(p[i]))++i;
    if(i==n||p[i++]!=':')return false;
    while(i<n&&ut_space(p[i]))++i;
    if(i==n)return false;
    if(p[i]=='"'){if(!ut_json_string(p,n,i))return false;}
    else {
      if(p[i]=='-')++i;
      if(i==n||p[i]<'0'||p[i]>'9')return false;
      if(p[i]=='0')++i;else while(i<n&&p[i]>='0'&&p[i]<='9')++i;
    }
    ++keys;while(i<n&&ut_space(p[i]))++i;
    if(i==n)return false;
    if(p[i]=='}'){++i;break;}
    if(p[i++]!=','||keys>=expected_keys)return false;
  }
  while(i<n&&ut_space(p[i]))++i;
  return keys==expected_keys&&i==n;
}
static inline bool ut_json_text(JsonVariantConst v)
{ return v.is<const char *>() && v.as<JsonString>().size()==strlen(v.as<const char *>()); }
static inline bool ut_request_parse(const char *p,size_t n,UtRequest &r)
{
  memset(&r,0,sizeof r);
  if(n>512U||!ut_json_shape(p,n))return false;
  StaticJsonDocument<1024> doc;
  if(deserializeJson(doc,p,n,DeserializationOption::NestingLimit(2))||doc.size()!=7U)return false;
  const char *keys[]={"schema","cmdId","controllerId","command","value","issuedAtMs","ttlMs"};
  for(JsonPairConst kv:doc.as<JsonObjectConst>()) {
    bool known=false;for(const char *key:keys)if(strcmp(kv.key().c_str(),key)==0)known=true;
    if(!known)return false;
  }
  if(!ut_json_text(doc["schema"])||strcmp(doc["schema"],"ut.command.v2")||
      !ut_json_text(doc["cmdId"])||!ut_json_text(doc["controllerId"])||!ut_json_text(doc["command"])||
      !doc["value"].is<uint16_t>()||!doc["ttlMs"].is<uint16_t>()||!doc["issuedAtMs"].is<uint64_t>())return false;
  const char *id=doc["cmdId"],*board=doc["controllerId"],*command=doc["command"];
  size_t len=strlen(id);if(!len||len>80U)return false;
  for(size_t i=0;i<len;i++)if(!((id[i]>='a'&&id[i]<='z')||(id[i]>='A'&&id[i]<='Z')||
      (id[i]>='0'&&id[i]<='9')||strchr("._:-",id[i])))return false;
  if(strlen(board)!=7U||strncmp(board,"CTRL-0",6U)||board[6]<'1'||board[6]>'4')return false;
  r.board=(uint8_t)(board[6]-'0');
  if(!strcmp(command,"fan"))r.code=1U;else if(!strcmp(command,"relay"))r.code=2U;
  else if(!strcmp(command,"buzzer"))r.code=3U;else if(!strcmp(command,"led"))r.code=4U;
  else if(!strcmp(command,"auto"))r.code=5U;else return false;
  r.value=doc["value"];r.ttl=doc["ttlMs"];r.issuedAtMs=doc["issuedAtMs"];
  if(!ut_capable(r.board,r.code)||r.ttl<100U||r.ttl>UT_MAX_TTL_MS||
      (r.code==1U&&r.value>100U)||((r.code==2U||r.code==3U)&&r.value>1U)||
      (r.code==4U&&r.value>4U)||(r.code==5U&&r.value))return false;
  memcpy(r.cmdId,id,len+1U);
  return true;
}
#endif
