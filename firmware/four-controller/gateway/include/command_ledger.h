#ifndef UT_COMMAND_LEDGER_H
#define UT_COMMAND_LEDGER_H
#include "command_json.h"
#include <stddef.h>
/* Bump the storage format if fields change. Unreadable records fail closed;
 * never silently erase an unknown in-flight command after a firmware update. */
#define UT_LEDGER_MAGIC 0x55540201UL
struct UtLedgerRecord {
  uint32_t magic;
  UtRequest request;
  uint16_t result,checksum;
};
static inline UtLedgerRecord ut_ledger_make(const UtRequest &r,uint16_t result)
{
  UtLedgerRecord record;
  memset(&record,0,sizeof record);
  record.magic=UT_LEDGER_MAGIC;record.request=r;record.request.receivedAt=0U;
  record.result=result;
  record.checksum=ut_crc((const uint8_t *)&record,offsetof(UtLedgerRecord,checksum));
  return record;
}
static inline bool ut_ledger_read(const void *data,size_t size,UtLedgerRecord &out)
{
  if(size!=sizeof out)return false;
  if(data!=&out)memcpy(&out,data,sizeof out);
  if(out.magic!=UT_LEDGER_MAGIC||out.request.cmdId[80]!='\0'||
      out.checksum!=ut_crc((const uint8_t *)&out,offsetof(UtLedgerRecord,checksum)))return false;
  if(!out.request.cmdId[0]||out.request.board<1U||out.request.board>4U||
      !ut_capable(out.request.board,out.request.code)||out.result<1U||out.result>UT_RESULT_UNKNOWN)return false;
  const UtRequest &r=out.request;
  if(r.ttl<100U||r.ttl>UT_MAX_TTL_MS||!r.issuedAtMs||
      (r.code==1U&&r.value>100U)||((r.code==2U||r.code==3U)&&r.value>1U)||
      (r.code==4U&&r.value>4U)||(r.code==5U&&r.value))return false;
  for(size_t i=0;r.cmdId[i];i++)if(!((r.cmdId[i]>='a'&&r.cmdId[i]<='z')||
      (r.cmdId[i]>='A'&&r.cmdId[i]<='Z')||(r.cmdId[i]>='0'&&r.cmdId[i]<='9')||strchr("._:-",r.cmdId[i])))return false;
  return true;
}
#endif
