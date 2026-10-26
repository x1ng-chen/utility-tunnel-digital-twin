#ifndef UT_TELEMETRY_ENCODE_H
#define UT_TELEMETRY_ENCODE_H
#include <ArduinoJson.h>
#include <stdio.h>
#include "../../common/snapshot.h"
#include "device_map.h"
static inline uint32_t ut_reg32(const uint16_t *r,unsigned at)
{ return ((uint32_t)r[at]<<16)|r[at+1U]; }
static inline const char *ut_quality(uint16_t status,uint32_t age,bool clocked)
{
  if(status==1U||age>=655350U)return "missing";
  if(age>5000U)return "bad";
  if(status==2U||!clocked)return "suspect";
  return "good";
}
static inline JsonObject ut_reading(JsonArray list,const char *asset,const char *metric,double value,
                                    const char *unit,const char *q,uint32_t age)
{
  JsonObject row=list.createNestedObject();row["assetCode"]=JsonString(asset,JsonString::Copied);row["metric"]=metric;
  row["value"]=value;row["unit"]=unit;row["quality"]=q;row["sampleAgeMs"]=age;
  return row;
}
/* Actual gateway encoder, shared with executable tests. Epoch/boot/timestamp
 * are gateway observations; no uptime field is ever formatted as wall time. */
static inline bool ut_telemetry(JsonDocument &doc,uint8_t board,const uint16_t *r,
                                const char *boot,uint32_t epoch,uint32_t transit,const char *utc)
{
  doc.clear();
  if(!ut_snapshot_valid(board,r,UT_INPUT_COUNT)||!boot||strlen(boot)>23U||transit>300U)return false;
  for(unsigned i=0;i<r[3];i++)if(UT_DEVICES[r[8U+i*4U]].board!=board)return false;
  bool clocked=utc&&*utc;
  doc["schema"]="ut.telemetry.v1";doc["seq"]=r[6];doc["rawOnly"]=true;
  doc["source"]="four-controller-rtu-v2";doc["layoutVersion"]="four-controller-20261026.1";
  char controller[12];snprintf(controller,sizeof controller,"CTRL-%02u",board);doc["controllerId"]=controller;
  char frame[80];snprintf(frame,sizeof frame,"%s:%u:%lu:%lu:%u",boot,board,(unsigned long)epoch,(unsigned long)ut_reg32(r,4U),r[6]);
  doc["frameId"]=frame;doc["clockSource"]=clocked?"gateway-ntp":"receiver-estimated";
  if(clocked)doc["ts"]=JsonString(utc,JsonString::Copied);
  JsonArray list=doc.createNestedArray("readings");
  for(unsigned i=0;i<r[3];i++) {
    unsigned at=8U+i*4U,id=r[at];const UtDevice &d=UT_DEVICES[id];
    uint32_t age=r[UT_SENSOR_AGE_BASE+i]*10U+transit;
    const char *q=ut_quality(r[at+3U],age,clocked);
    if(id>=29U&&strcmp(q,"good")==0)q="suspect"; /* bare AO-02 always raw */
    double value=(id>=21U&&id<=24U)?(int16_t)r[at+1U]/100.0:r[at+1U];
    JsonObject row=ut_reading(list,d.asset,d.metric,value,d.unit,q,age);
    if(r[at+3U]==3U)row["eventLatched"]=true;
    if(id>=21U&&id<=24U)ut_reading(list,d.asset,"humidity",r[at+2U]/100.0,"%RH",q,age);
    if(id>=29U)ut_reading(list,d.asset,"oxygen.voltage",r[at+2U],"mV",q,age);
  }
  if(board==2U||board==4U) {
    const char *fan=board==4U?"FAN-01":"FAN-02";
    uint32_t rpm_age=r[79]*10U+transit,ina_age=r[86]*10U+transit;
    ut_reading(list,fan,"rotational.speed",ut_reg32(r,53U),"rpm",ut_quality(r[55],rpm_age,clocked),rpm_age);
    ut_reading(list,fan,"supply.voltage",ut_reg32(r,56U)/1000.0,"V",ut_quality(r[62]&255U,ina_age,clocked),ina_age);
    const char *current_quality=ut_quality((r[62]&0x100U)?(r[62]&255U):((r[62]&255U)==1U?1U:2U),ina_age,clocked);
    ut_reading(list,fan,"motor.current",(int32_t)ut_reg32(r,58U)/1000.0,"mA",current_quality,ina_age);
    ut_reading(list,fan,"power",(int32_t)ut_reg32(r,60U)/1000000.0,"W",current_quality,ina_age);
    ut_reading(list,fan,"pwm.duty",r[63]&255U,"%",ut_quality(0U,transit,clocked),transit);
    ut_reading(list,fan,"relay.commanded",(r[63]&0x100U)?1:0,"bool",ut_quality(0U,transit,clocked),transit);
  }
  ut_reading(list,controller,"heartbeat",1,"bool",ut_quality(0U,transit,clocked),transit);
  return !doc.overflowed()&&measureJson(doc)<4032U;
}
#endif
