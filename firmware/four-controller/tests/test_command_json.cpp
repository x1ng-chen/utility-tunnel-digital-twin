#include "test_support.h"
#include "../gateway/include/command_json.h"
#include "../gateway/include/command_ledger.h"
#ifndef UT_TEST_EMULATED
#include <stdio.h>
#endif
extern "C" { volatile UtTestResults ut_test_results; }
void test_entry(void) {
  memset((void *)&ut_test_results,0,sizeof ut_test_results);UtRequest request;
  GROUP(); /* canonical */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==true); }
  GROUP(); /* whitespace */
  { const char json[]="{\n  \"schema\": \"ut.command.v2\",\n  \"cmdId\": \"platform-case_01\",\n  \"controllerId\": \"CTRL-04\",\n  \"command\": \"fan\",\n  \"value\": 60,\n  \"issuedAtMs\": 1793000000000,\n  \"ttlMs\": 10000\n} \n";CHECK(ut_request_parse(json,sizeof json-1U,request)==true); }
  GROUP(); /* invalid_value_-1 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":-1,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_value_101 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":101,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_value_256 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":256,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_value_True */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":true,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_value_60 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":\"60\",\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_value_60.0 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60.0,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_ttlMs_99 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":99}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_ttlMs_60001 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":60001}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_ttlMs_65536 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":65536}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_ttlMs_False */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":false}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_schema_ut.command.v1 */
  { const char json[]="{\"schema\":\"ut.command.v1\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_controllerId_CTRL-01 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-01\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_controllerId_CTRL-00 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-00\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_controllerId_CTRL-05 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-05\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_command_pump */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"pump\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_cmdId_ */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_cmdId_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_cmdId_cmd<inject> */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"cmd<inject>\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_cmdId_abc\u0000tail */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"abc\\u0000tail\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_schema_ut.command.v2\u0000tail */
  { const char json[]="{\"schema\":\"ut.command.v2\\u0000tail\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_issuedAtMs_-1 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":-1,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_issuedAtMs_True */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":true,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_issuedAtMs_1793000000000 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":\"1793000000000\",\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* invalid_issuedAtMs_18446744073709551616 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":18446744073709551616,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* ttl_min */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":100}";CHECK(ut_request_parse(json,sizeof json-1U,request)==true); }
  GROUP(); /* ttl_max */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":60000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==true); }
  GROUP(); /* value_zero */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":0,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==true); }
  GROUP(); /* relay */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-02\",\"command\":\"relay\",\"value\":1,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==true); }
  GROUP(); /* relay_range */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-02\",\"command\":\"relay\",\"value\":2,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* buzzer */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-03\",\"command\":\"buzzer\",\"value\":1,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==true); }
  GROUP(); /* buzzer_range */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-03\",\"command\":\"buzzer\",\"value\":2,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* led */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-03\",\"command\":\"led\",\"value\":4,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==true); }
  GROUP(); /* led_range */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-03\",\"command\":\"led\",\"value\":5,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* auto */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"auto\",\"value\":0,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==true); }
  GROUP(); /* auto_range */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"auto\",\"value\":1,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* missing_schema */
  { const char json[]="{\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* missing_cmdId */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* missing_controllerId */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* missing_command */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* missing_value */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* missing_issuedAtMs */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* missing_ttlMs */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* truncated_brace */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* truncated_string */
  { const char json[]="{\"schema\":\"ut.command.v2";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* trailing_garbage */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}x";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* second_object */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}{}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* single_quote */
  { const char json[]="{'schema':'ut.command.v2','cmdId':'platform-case_01','controllerId':'CTRL-04','command':'fan','value':60,'issuedAtMs':1793000000000,'ttlMs':10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* unquoted_key */
  { const char json[]="{schema:\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* duplicate_key_8 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000,\"value\":50}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* duplicate_key_7 */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"value\":50}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* trailing_comma */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000,}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* array */
  { const char json[]="[{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}]";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* unknown_key */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000,\"extra\":0}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* nested_value */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":{\"a\":60},\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* exponent_integer */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":6e1,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* leading_zero */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":060,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==false); }
  GROUP(); /* escaped_command */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-case_01\",\"controllerId\":\"CTRL-04\",\"command\":\"\\u0066an\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}";CHECK(ut_request_parse(json,sizeof json-1U,request)==true); }
  GROUP(); /* decoded NUL key rejected */
  { const char json[]="{\"schema\\u0000tail\":\"ut.command.v2\",\"cmdId\":\"platform-nul\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}"; CHECK(!ut_request_parse(json,sizeof json-1U,request)); }
  GROUP(); /* decoded NUL key rejected */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\":\"platform-nul\",\"controllerId\":\"CTRL-04\",\"command\\u0000tail\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}"; CHECK(!ut_request_parse(json,sizeof json-1U,request)); }
  GROUP(); /* decoded NUL key rejected */
  { const char json[]="{\"schema\":\"ut.command.v2\",\"cmdId\\u0000tail\":\"platform-nul\",\"controllerId\":\"CTRL-04\",\"command\":\"fan\",\"value\":60,\"issuedAtMs\":1793000000000,\"ttlMs\":10000}"; CHECK(!ut_request_parse(json,sizeof json-1U,request)); }
  GROUP(); /* Durable command intent survives decoding and rejects corruption. */
  UtRequest durable={};
  strcpy(durable.cmdId,"durable-cmd-4");durable.board=4U;durable.code=1U;durable.value=60U;
  durable.ttl=10000U;durable.issuedAtMs=1793000000000ULL;durable.receivedAt=500U;
  UtLedgerRecord record=ut_ledger_make(durable,UT_RESULT_UNKNOWN),decoded;
  CHECK(ut_ledger_read(&record,sizeof record,decoded));
  CHECK(!strcmp(decoded.request.cmdId,durable.cmdId)&&decoded.result==UT_RESULT_UNKNOWN);
  CHECK(decoded.request.receivedAt==0U);
  CHECK(ut_ledger_read(&record,sizeof record,record));
  CHECK(!ut_ledger_read(&record,sizeof record-1U,decoded));
  for(size_t i=0;i<offsetof(UtLedgerRecord,checksum);i++) {
    UtLedgerRecord corrupt=record;((uint8_t *)&corrupt)[i]^=1U;
    CHECK(!ut_ledger_read(&corrupt,sizeof corrupt,decoded));
  }
  for(unsigned kind=0;kind<6U;kind++) {
    UtRequest invalid=durable;
    if(kind==0U)invalid.board=1U;
    if(kind==1U)invalid.value=101U;
    if(kind==2U)invalid.ttl=0U;
    if(kind==3U)invalid.issuedAtMs=0U;
    if(kind==4U)invalid.cmdId[0]=' ';
    if(kind==5U)memset(invalid.cmdId,'x',sizeof invalid.cmdId);
    UtLedgerRecord corrupt=ut_ledger_make(invalid,UT_RESULT_UNKNOWN);
    CHECK(!ut_ledger_read(&corrupt,sizeof corrupt,decoded));
  }
  ut_test_results.done=0x5554U;
}
#ifndef UT_TEST_EMULATED
int main() { test_entry();printf("{\"checks\":%u,\"failures\":%u,\"firstLine\":%u,\"groups\":%u}\n",(unsigned)ut_test_results.checks,(unsigned)ut_test_results.failures,(unsigned)ut_test_results.first_line,(unsigned)ut_test_results.groups);return ut_test_results.failures?1:0; }
#endif
