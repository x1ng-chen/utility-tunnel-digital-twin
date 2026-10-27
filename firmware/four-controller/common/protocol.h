#ifndef UT_BUSINESS_PROTOCOL_H
#define UT_BUSINESS_PROTOCOL_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define UT_VERSION 0x0200U
#define UT_INPUT_COUNT 96U
#define UT_COMMAND_REGS 8U
#define UT_VIEW_BASE 256U
#define UT_VIEW_COUNT 80U
#define UT_MENU_ACK_BASE 512U
#define UT_BOOT_SESSION_BASE 516U
#define UT_MAX_TTL_MS 60000U
#define UT_SENSOR_AGE_BASE 68U
#define UT_RESULT_OK 1U
#define UT_RESULT_UNSUPPORTED 2U
#define UT_RESULT_INVALID 3U
#define UT_RESULT_EXPIRED 4U
#define UT_RESULT_PROTECTED 5U
#define UT_RESULT_CONFLICT 6U
#define UT_RESULT_UNKNOWN 7U

static inline uint16_t ut_crc(const uint8_t *p, size_t n)
{
  uint16_t c=0xffffU;
  while(n--) { c^=*p++; for(uint8_t i=0;i<8;i++) c=(c&1U)?(uint16_t)((c>>1)^0xa001U):(uint16_t)(c>>1); }
  return c;
}
static inline uint16_t ut_u16(const uint8_t *p) { return (uint16_t)(((uint16_t)p[0]<<8)|p[1]); }
static inline void ut_put(uint8_t *p,uint16_t v) { p[0]=(uint8_t)(v>>8);p[1]=(uint8_t)v; }
static inline int ut_due(uint32_t now,uint32_t then,uint32_t span) { return (uint32_t)(now-then)>=span; }

/* One receiver sees requests AND every other slave's replies. Consume a CRC-valid
 * peer frame as a whole; CRC errors slide one byte, and an RTU gap drops partials.
 * Caller drains next() after each push. No HAL, allocation, or global state. */
typedef struct { uint8_t bytes[260]; uint16_t used; uint32_t last, bad, overflow; } UtRtu;
static inline void ut_drop(UtRtu *p,uint16_t n)
{ if(n>p->used)n=p->used; p->used=(uint16_t)(p->used-n);memmove(p->bytes,p->bytes+n,p->used); }
static inline void ut_push(UtRtu *p,uint8_t b,uint32_t at)
{
  if(p->used && ut_due(at,p->last,4U))p->used=0;
  p->last=at;
  if(p->used==sizeof p->bytes){p->used=0;++p->overflow;}
  p->bytes[p->used++]=b;
}
/* Returns length of a complete request for this node, 0 when more input needed.
 * Only supported, bounded requests are passed to the device dispatcher. */
static inline uint16_t ut_next_frame(UtRtu *p,uint8_t address,uint8_t out[260],int final)
{
  while(p->used>=3U) {
    uint8_t f=p->bytes[1]; uint16_t n=0; int request=0;
    if(p->bytes[0]<1U||p->bytes[0]>4U){ut_drop(p,1);continue;}
    if(f==3U||f==4U) {
      request=(p->bytes[2]==0U);n=request?8U:(uint16_t)(5U+p->bytes[2]);
      if(!request&&(p->bytes[2]&1U)){ut_drop(p,1);continue;}
    } else if(f==6U){n=8U;request=1;}
    else if(f==16U) {
      if(p->used<7U)return 0;
      uint16_t count=ut_u16(p->bytes+4);
      request=(count>0U&&count<=UT_INPUT_COUNT&&p->bytes[6]==count*2U);
      n=request?(uint16_t)(9U+p->bytes[6]):8U;
    } else {ut_drop(p,1);continue;}
    if(n>sizeof p->bytes||n<5U){ut_drop(p,1);continue;}
    if(p->used<n){if(final){ut_drop(p,1U);continue;}return 0;}
    if(ut_crc(p->bytes,n)!=0U){++p->bad;ut_drop(p,1);continue;}
    int mine=request&&p->bytes[0]==address;
    if(mine)memcpy(out,p->bytes,n);
    ut_drop(p,n);
    if(mine)return n;
  }
  return 0;
}

static inline uint16_t ut_next(UtRtu *p,uint8_t address,uint8_t out[260])
{ return ut_next_frame(p,address,out,0); }
static inline uint16_t ut_finish(UtRtu *p,uint8_t address,uint8_t out[260])
{ return ut_next_frame(p,address,out,1); }

typedef struct { uint16_t code,value,ttl;uint32_t session,nonce; } UtCommand;
typedef struct { UtCommand command;uint32_t at;uint16_t result;uint8_t used; } UtCached;
typedef struct {
  uint8_t board,alarm;uint16_t desired[4],output[4];uint32_t at[4],ttl[4];
  UtCached cache[8];uint8_t cursor;uint32_t session,nonce,stream_session,stream_nonce;uint16_t result;
} UtControl;
static inline int ut_capable(uint8_t board,uint16_t code)
{ return (code==5U && board>=2U && board<=4U) || ((code==1U||code==2U)&&(board==2U||board==4U)) || ((code==3U||code==4U)&&board==3U); }
static inline uint16_t ut_apply(UtControl *s,UtCommand c,uint32_t now)
{
  uint16_t result=UT_RESULT_OK;
  s->session=c.session;s->nonce=c.nonce;
  if(!ut_capable(s->board,c.code))return s->result=UT_RESULT_UNSUPPORTED;
  if(!c.session||!c.nonce||c.ttl<100U||c.ttl>UT_MAX_TTL_MS||
      (c.code==1U&&c.value>100U)||((c.code==2U||c.code==3U)&&c.value>1U)||
      (c.code==4U&&c.value>4U)||(c.code==5U&&c.value))return s->result=UT_RESULT_INVALID;
  for(unsigned i=0;i<8;i++) {
    UtCached *e=&s->cache[i];
    if(!e->used||e->command.session!=c.session||e->command.nonce!=c.nonce)continue;
    if(e->command.code!=c.code||e->command.value!=c.value||e->command.ttl!=c.ttl)
      return s->result=UT_RESULT_CONFLICT;
    return s->result=ut_due(now,e->at,c.ttl)?UT_RESULT_EXPIRED:e->result;
  }
  if(c.session==s->stream_session&&c.nonce<=s->stream_nonce)return s->result=UT_RESULT_EXPIRED;
  s->stream_session=c.session;s->stream_nonce=c.nonce;
  if(s->alarm&&c.code!=5U)result=UT_RESULT_PROTECTED;
  if(result==UT_RESULT_OK) {
    if(c.code==5U)memset(s->ttl,0,sizeof s->ttl);
    else {unsigned i=c.code-1U;s->desired[i]=c.value;s->at[i]=now;s->ttl[i]=c.ttl;}
  }
  UtCached *e=&s->cache[s->cursor++%8U];e->command=c;e->at=now;e->result=result;e->used=1;
  return s->result=result;
}
static inline void ut_outputs(UtControl *s,uint32_t now)
{
  for(unsigned i=0;i<4;i++)s->output[i]=(s->ttl[i]&&!ut_due(now,s->at[i],s->ttl[i]))?s->desired[i]:0U;
  if(s->alarm) {
    if(s->board==2U||s->board==4U){s->output[0]=100U;s->output[1]=1U;}
    if(s->board==3U){s->output[2]=1U;s->output[3]=1U;}
  }
}
static inline int ut_ack_matches(const uint8_t *p,size_t n,uint8_t board,uint8_t function,uint16_t start,uint16_t value)
{ return n==8U&&ut_crc(p,n)==0U&&p[0]==board&&p[1]==function&&ut_u16(p+2)==start&&ut_u16(p+4)==value; }
#endif
