#include "test_support.h"
#include "../gateway/include/telemetry_encode.h"
#ifndef UT_TEST_EMULATED
#include <stdio.h>
#endif
extern "C" {
  volatile UtTestResults ut_test_results;
  char ut_fixture_json[4][4096];
}
static void fixture(uint8_t board,uint16_t *r)
{
  memset(r,0,UT_INPUT_COUNT*sizeof *r);
  r[0]=0x5554U;r[1]=board;r[2]=UT_VERSION;r[3]=ut_sensor_count(board);r[5]=2U;r[6]=17U;
  unsigned slot=0U;
  for(unsigned id=1U;id<=31U;id++) {
    if(ut_sensor_owner((uint16_t)id)!=board)continue;
    unsigned at=8U+4U*slot;r[at]=(uint16_t)id;
    if(id<=20U){unsigned type=(id-1U)%4U;r[at+1U]=(type==0U||type==3U)?0U:321U;}
    else if(id<=24U){r[at+1U]=(uint16_t)(int16_t)-425;r[at+2U]=5231U;}
    else if(id<=28U)r[at+1U]=0U;
    else {r[at+1U]=14U;r[at+2U]=11U;r[at+3U]=2U;}
    r[UT_SENSOR_AGE_BASE+slot]=id>=21U&&id<=24U?200U:10U;
    ++slot;
  }
  r[54]=1200U;r[55]=0U;r[57]=12100U;
  uint32_t current=(uint32_t)(int32_t)-250;
  r[58]=(uint16_t)(current>>16);r[59]=(uint16_t)current;r[61]=20000U;
  r[62]=256U;r[63]=316U;r[79]=10U;r[86]=10U;
}
static void clobber()
{volatile char data[1024];for(unsigned i=0;i<sizeof data;i++)data[i]=(char)i;}
void test_entry(void)
{
  memset((void *)&ut_test_results,0,sizeof ut_test_results);
  StaticJsonDocument<6144> doc;
  uint16_t r[UT_INPUT_COUNT];
  unsigned total=0U;
  for(unsigned board=1;board<=4U;board++) {
    GROUP();fixture((uint8_t)board,r);
    CHECK(ut_telemetry(doc,(uint8_t)board,r,"fixture-boot",1U,110U,"2026-10-27T00:00:00.000Z"));
    clobber();serializeJson(doc,ut_fixture_json[board-1U],4096U);
    CHECK(!doc.overflowed());CHECK(strlen(ut_fixture_json[board-1U])<4032U);
    JsonArray rows=doc["readings"];
    unsigned expected=board==1U?14U:(board==3U?8U:16U);
    CHECK(rows.size()==expected);total+=(unsigned)rows.size();
    char controller[12];snprintf(controller,sizeof controller,"CTRL-%02u",board);
    CHECK(!strcmp(doc["controllerId"],controller));
    CHECK(!strcmp(rows[rows.size()-1U]["assetCode"],controller));
    for(JsonObject item:rows) {
      const char *metric=item["metric"];
      CHECK(strcmp(metric,"oxygen.concentration")!=0);
      if(!strcmp(metric,"temperature")){CHECK(item["value"].as<double>()==-4.25);CHECK(item["sampleAgeMs"].as<unsigned>()==2110U);}
      if(!strcmp(metric,"motor.current"))CHECK(item["value"].as<double>()==-.25);
      if(!strcmp(metric,"oxygen.raw"))CHECK(!strcmp(item["quality"],"suspect"));
    }
    CHECK(ut_telemetry(doc,(uint8_t)board,r,"fixture-boot",1U,110U,nullptr));
    CHECK(!doc.containsKey("ts"));
    for(JsonObject item:doc["readings"].as<JsonArray>())CHECK(!strcmp(item["quality"],"suspect"));
  }
  CHECK(total==54U);
  GROUP();fixture(1U,r);r[9]=1U;r[11]=3U;r[UT_SENSOR_AGE_BASE]=200U;
  CHECK(ut_telemetry(doc,1U,r,"fixture-boot",0U,110U,"2026-10-27T00:00:00.000Z"));
  CHECK(doc["readings"][0]["eventLatched"]==true);
  CHECK(!strcmp(doc["readings"][0]["quality"],"good"));
  r[UT_SENSOR_AGE_BASE]=600U;
  CHECK(ut_telemetry(doc,1U,r,"fixture-boot",0U,110U,"2026-10-27T00:00:00.000Z"));
  CHECK(!strcmp(doc["readings"][0]["quality"],"bad"));
  r[UT_SENSOR_AGE_BASE]=65535U;r[11]=1U;
  CHECK(ut_telemetry(doc,1U,r,"fixture-boot",0U,110U,"2026-10-27T00:00:00.000Z"));
  CHECK(!strcmp(doc["readings"][0]["quality"],"missing"));
  fixture(1U,r);r[8]=1U;CHECK(!ut_telemetry(doc,1U,r,"fixture-boot",0U,0U,nullptr));
  fixture(1U,r);r[15]=3U;CHECK(!ut_telemetry(doc,1U,r,"fixture-boot",0U,0U,nullptr));
  fixture(1U,r);CHECK(!ut_telemetry(doc,1U,r,"fixture-boot",0U,301U,nullptr));
  ut_test_results.done=0x5554U;
}
#ifndef UT_TEST_EMULATED
int main() {
  test_entry();
  printf("{\"checks\":%u,\"failures\":%u,\"firstLine\":%u,\"groups\":%u}\n",
    (unsigned)ut_test_results.checks,(unsigned)ut_test_results.failures,(unsigned)ut_test_results.first_line,(unsigned)ut_test_results.groups);
  FILE *out=fopen(".agent-eval/firmware-fix/gateway-fixtures.json","wb");
  if(!out)return 2;
  fputs("[",out);for(unsigned i=0;i<4U;i++){if(i)fputs(",",out);fputs(ut_fixture_json[i],out);}fputs("]\n",out);fclose(out);
  return ut_test_results.failures?1:0;
}
#endif
