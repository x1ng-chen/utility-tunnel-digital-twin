#include "test_support.h"
#include "../common/protocol.h"
#include "../common/interaction.h"
#include "../common/digital.h"
#include "../common/measurements.h"
#ifndef UT_TEST_EMULATED
#include <stdio.h>
#endif
volatile UtTestResults ut_test_results;
static void crc_append(uint8_t *p,unsigned n)
{uint16_t c=ut_crc(p,n);p[n]=(uint8_t)c;p[n+1U]=(uint8_t)(c>>8);}
static void query(uint8_t *p,uint8_t board)
{p[0]=board;p[1]=4;p[2]=p[3]=p[4]=0;p[5]=96;crc_append(p,6);}
static unsigned feed(UtRtu *s,uint8_t board,const uint8_t *p,unsigned n,uint32_t *time)
{
  uint8_t out[260];unsigned found=0;
  for(unsigned i=0;i<n;i++) {
    ut_push(s,p[i],(*time)++);
    while(ut_next(s,board,out))++found;
  }
  return found;
}
static void test_rtu(void)
{
  GROUP();uint8_t out[260],q[8],peer[197];uint32_t t=20;UtRtu s={0};
  CHECK(ut_crc((const uint8_t *)"123456789",9)==0x4b37U);
  query(q,3);CHECK(feed(&s,3,q,7,&t)==0);CHECK(feed(&s,3,q+7,1,&t)==1);
  for(unsigned board=1;board<=4;board++) {
    for(unsigned length=109;length<=197;length+=88U) {
      memset(&s,0,sizeof s);t=20;query(q,(uint8_t)board);
      unsigned other=board==4U?1U:4U;
      peer[0]=(uint8_t)other;peer[1]=4;peer[2]=(uint8_t)(length-5U);
      memset(peer+3,0x55,length-5U);
      /* A complete valid request inside a peer payload must never execute. */
      memcpy(peer+20,q,sizeof q);crc_append(peer,length-2U);
      uint8_t request_other[8];query(request_other,(uint8_t)other);
      CHECK(feed(&s,(uint8_t)board,request_other,8,&t)==0);
      t+=5U;CHECK(feed(&s,(uint8_t)board,peer,length,&t)==0);
      t+=5U;CHECK(feed(&s,(uint8_t)board,q,8,&t)==1);
    }
  }
  for(unsigned b=0;b<=255U;b++) {
    memset(&s,0,sizeof s);t=20;query(q,3);uint8_t noise=(uint8_t)b;
    unsigned found=feed(&s,3,&noise,1,&t)+feed(&s,3,q,8,&t);
    if(found==0U)found+=ut_finish(&s,3,out)!=0U;
    CHECK(found==1U);
  }
  memset(&s,0,sizeof s);t=20;query(q,3);q[7]^=1U;
  CHECK(feed(&s,3,q,8,&t)==0);CHECK(ut_finish(&s,3,out)==0);
  q[7]^=1U;t+=5U;CHECK(feed(&s,3,q,8,&t)==1);
  /* A deceptive long response header is abandoned at the quiet boundary. */
  memset(&s,0,sizeof s);t=20;uint8_t misleading[]={2,4,192};
  CHECK(feed(&s,3,misleading,3,&t)==0);CHECK(feed(&s,3,q,8,&t)==0);
  CHECK(ut_finish(&s,3,out)==8U);CHECK(!memcmp(out,q,8));
  /* Partial frames do not combine across an RTU gap, including tick wrap. */
  memset(&s,0,sizeof s);t=UINT32_MAX-3U;
  CHECK(feed(&s,3,q,4,&t)==0);t+=5U;CHECK(feed(&s,3,q+4,4,&t)==0);
  t+=5U;CHECK(feed(&s,3,q,8,&t)==1);
  /* Complete atomic write, no truncated/oversized write can execute. */
  uint8_t write[25]={3,16,0,0,0,8,16};crc_append(write,23);
  memset(&s,0,sizeof s);t=20;
  CHECK(feed(&s,3,write,24,&t)==0);CHECK(feed(&s,3,write+24,1,&t)==1);
  write[5]=97;write[6]=194;crc_append(write,23);
  memset(&s,0,sizeof s);t=20;CHECK(feed(&s,3,write,25,&t)==0);
  CHECK(ut_finish(&s,3,out)==0);
  /* Startup handshake at holding window 516 has a different request length. */
  uint8_t bind[13]={3U,16U,2U,4U,0U,2U,4U,0x12U,0x34U,0x56U,0x78U,0U,0U};
  crc_append(bind,11U);memset(&s,0,sizeof s);t=20U;
  CHECK(feed(&s,3U,bind,12U,&t)==0U);CHECK(feed(&s,3U,bind+12U,1U,&t)==1U);
  /* Bounded overflow is counted, and a subsequent clean frame recovers. */
  memset(&s,0,sizeof s);for(unsigned i=0;i<600U;i++)ut_push(&s,0x55U,i);
  CHECK(s.used<=sizeof s.bytes);CHECK(s.overflow==2U);
  t=610U;CHECK(feed(&s,3,q,8,&t)==1);
  /* Long deterministic noise streams cannot grow the parser or invent frames. */
  memset(&s,0,sizeof s);uint32_t random=0x425958U;t=20;unsigned frames=0;
  for(unsigned i=0;i<8192U;i++) {
    random=random*1664525U+1013904223U;uint8_t b=(uint8_t)(random>>24);
    frames+=feed(&s,3,&b,1,&t);
  }
  CHECK(s.used<=sizeof s.bytes);CHECK(frames==0U);
  t+=5U;CHECK(feed(&s,3,q,8,&t)==1);
}
static UtCommand command(uint16_t code,uint16_t value,uint32_t nonce)
{UtCommand c={code,value,10000U,0x12345678U,nonce};return c;}
static void test_control(void)
{
  GROUP();UtControl s={0};s.board=4;
  CHECK(ut_apply(&s,command(1,60,1),100)==UT_RESULT_OK);
  ut_outputs(&s,2100);CHECK(s.output[0]==60U);CHECK(s.output[1]==0U);
  CHECK(ut_apply(&s,command(2,1,2),300)==UT_RESULT_OK);
  CHECK(ut_apply(&s,command(1,60,1),1000)==UT_RESULT_OK);
  CHECK(s.at[0]==100U);ut_outputs(&s,10100);CHECK(s.output[0]==0U&&s.output[1]==1U);
  CHECK(ut_apply(&s,command(1,60,1),10100)==UT_RESULT_EXPIRED);
  UtCommand c=command(1,61,1);CHECK(ut_apply(&s,c,1000)==UT_RESULT_CONFLICT);
  c=command(1,101,3);CHECK(ut_apply(&s,c,1000)==UT_RESULT_INVALID);
  c.value=65535U;CHECK(ut_apply(&s,c,1000)==UT_RESULT_INVALID);
  c.value=256U;CHECK(ut_apply(&s,c,1000)==UT_RESULT_INVALID);
  c=command(2,2,3);CHECK(ut_apply(&s,c,1000)==UT_RESULT_INVALID);
  c=command(1,50,3);c.ttl=99;CHECK(ut_apply(&s,c,1000)==UT_RESULT_INVALID);
  c.ttl=60001U;CHECK(ut_apply(&s,c,1000)==UT_RESULT_INVALID);
  c.ttl=100;c.session=0;CHECK(ut_apply(&s,c,1000)==UT_RESULT_INVALID);
  c.session=1;c.nonce=0;CHECK(ut_apply(&s,c,1000)==UT_RESULT_INVALID);
  s.board=1;CHECK(ut_apply(&s,command(1,60,3),1000)==UT_RESULT_UNSUPPORTED);
  CHECK(!ut_capable(1,5));CHECK(!ut_capable(0,5));CHECK(!ut_capable(5,5));
  s.board=3;CHECK(ut_apply(&s,command(1,60,3),1000)==UT_RESULT_UNSUPPORTED);
  CHECK(ut_apply(&s,command(3,1,3),1000)==UT_RESULT_OK);
  c=command(4,5,4);CHECK(ut_apply(&s,c,1000)==UT_RESULT_INVALID);
  c.value=4;CHECK(ut_apply(&s,c,1000)==UT_RESULT_OK);
  ut_outputs(&s,1100);CHECK(s.output[2]==1U&&s.output[3]==4U);
  s.alarm=1;ut_outputs(&s,1101);CHECK(s.output[2]==1U&&s.output[3]==1U);
  CHECK(ut_apply(&s,command(3,0,5),1200)==UT_RESULT_PROTECTED);
  s.alarm=0;ut_outputs(&s,1300);CHECK(s.output[2]==1U&&s.output[3]==4U);
  s.alarm=1;CHECK(ut_apply(&s,command(5,0,6),1400)==UT_RESULT_OK);
  ut_outputs(&s,1400);CHECK(s.output[2]==1U&&s.output[3]==1U);
  s.alarm=0;ut_outputs(&s,1500);CHECK(s.output[2]==0U&&s.output[3]==0U);
  /* Cache eviction cannot make an old nonce in the current stream execute again. */
  memset(&s,0,sizeof s);s.board=4;
  for(unsigned i=1;i<=12;i++)CHECK(ut_apply(&s,command(1,40,i),i)==UT_RESULT_OK);
  CHECK(ut_apply(&s,command(1,40,1),100)==UT_RESULT_EXPIRED);
  c=command(1,75,13);c.ttl=1000;
  CHECK(ut_apply(&s,c,UINT32_MAX-500U)==UT_RESULT_OK);
  ut_outputs(&s,200U);CHECK(s.output[0]==75U);
  ut_outputs(&s,500U);CHECK(s.output[0]==0U);
  s.alarm=1;ut_outputs(&s,700U);CHECK(s.output[0]==100U&&s.output[1]==1U);
}
static void release_button(UtMenu *m,uint32_t *t)
{for(unsigned i=0;i<3;i++){*t+=20U;ut_menu_step(m,2048,2048,0,*t);}}
static void click(UtMenu *m,uint32_t *t)
{release_button(m,t);for(unsigned i=0;i<3;i++){*t+=20U;ut_menu_step(m,2048,2048,1,*t);}}
static void axis(UtMenu *m,uint16_t x,uint16_t y,uint32_t *t)
{*t+=20U;ut_menu_step(m,2048,2048,0,*t);*t+=20U;ut_menu_step(m,x,y,0,*t);}
static void test_menu(void)
{
  GROUP();UtMenu m;ut_menu_init(&m);uint32_t t=0;
  CHECK(m.node==2U&&m.mode==0U&&!m.pending);
  ut_menu_step(&m,1500,2600,0,20);CHECK(m.node==2U&&m.slot==0U);
  axis(&m,3500,2048,&t);CHECK(m.node==3U);
  for(unsigned i=0;i<20;i++)ut_menu_step(&m,3500,2048,0,t+i*20);
  CHECK(m.node==3U); /* Holding an axis is one edge until re-centred. */
  axis(&m,500,2048,&t);CHECK(m.node==2U);
  for(unsigned i=0;i<2;i++)ut_menu_step(&m,2048,2048,1,t+=20);
  CHECK(m.mode==0U);ut_menu_step(&m,2048,2048,0,t+=20);CHECK(m.mode==0U);
  click(&m,&t);CHECK(m.mode==1U&&!m.pending&&m.code==1U);
  axis(&m,3500,2048,&t);CHECK(m.value==75U&&!m.pending);
  axis(&m,3500,2048,&t);axis(&m,3500,2048,&t);CHECK(m.value==100U);
  click(&m,&t);CHECK(m.mode==2U&&!m.pending);
  axis(&m,500,2048,&t);CHECK(m.mode==0U&&!m.pending&&m.nonce==0U);
  click(&m,&t);click(&m,&t);CHECK(m.mode==2U&&!m.pending);
  click(&m,&t);CHECK(m.mode==3U&&m.pending&&m.nonce==1U);
  uint8_t selected=m.node;axis(&m,3500,2048,&t);CHECK(m.node==selected&&m.nonce==1U);
  ut_menu_step(&m,2048,2048,0,m.issued_at+10000U);
  CHECK(!m.pending&&m.mode==0U&&m.result==UT_RESULT_UNKNOWN);
  ut_menu_init(&m);m.node=1;t=0;click(&m,&t);
  CHECK(m.mode==0U&&!m.pending&&m.result==UT_RESULT_UNSUPPORTED);
  ut_menu_init(&m);m.node=3;t=0;click(&m,&t);CHECK(m.code==3U);
  for(unsigned i=0;i<10;i++){axis(&m,2048,3500,&t);CHECK(ut_capable(m.node,m.code));}
  ut_menu_init(&m);m.node=4;t=0;axis(&m,3500,2048,&t);CHECK(m.node==1U);
  axis(&m,500,2048,&t);CHECK(m.node==4U);
}
static void test_digital(void)
{
  GROUP();UtDigital d={0};
  CHECK(!d.valid&&!ut_digital_latched(&d,0));
  ut_digital_observe(&d,1,1);ut_digital_observe(&d,1,2);
  CHECK(!d.valid&&d.events==0U);
  ut_digital_observe(&d,0,3);ut_digital_observe(&d,0,4);ut_digital_observe(&d,0,5);
  CHECK(d.valid&&!d.level&&d.events==0U&&!ut_digital_latched(&d,5));
  for(unsigned i=6;i<=8;i++)ut_digital_observe(&d,1,i);
  CHECK(d.level&&d.events==1U&&d.last_active==8U);
  for(unsigned i=9;i<=11;i++)ut_digital_observe(&d,0,i);
  CHECK(!d.level&&d.events==1U&&ut_digital_latched(&d,1000));
  CHECK(ut_digital_latched(&d,10007U));CHECK(!ut_digital_latched(&d,10008U));
  /* A pulse occurring between old 2-second polls is still observed by ISR ticks. */
  memset(&d,0,sizeof d);
  for(unsigned i=0;i<2001;i++)ut_digital_observe(&d,i>=500U&&i<550U,i);
  CHECK(d.events==1U&&d.seen&&!d.level&&ut_digital_latched(&d,2000U));
  CHECK(d.last_active>=500U&&d.last_active<550U);
  /* No invented event when no samples saw a pulse. */
  memset(&d,0,sizeof d);for(unsigned i=0;i<8;i++)ut_digital_observe(&d,0,i);
  CHECK(!ut_digital_latched(&d,5000U)&&d.events==0U);
  memset(&d,0,sizeof d);
  for(unsigned i=0;i<3;i++)ut_digital_observe(&d,1,UINT32_MAX-3U+i);
  for(unsigned i=0;i<3;i++)ut_digital_observe(&d,0,i);
  CHECK(ut_digital_latched(&d,200U));CHECK(!ut_digital_latched(&d,11000U));
}
static void test_measurements(void)
{
  GROUP();CHECK(ut_rpm(100,1000,2)==3000U);CHECK(ut_rpm(50,1000,2)==1500U);
  CHECK(ut_rpm(0,1000,2)==0U);CHECK(ut_rpm(1,0,2)==0U);CHECK(ut_rpm(1,1000,0)==0U);
  CHECK(ut_rpm(UINT32_MAX,1,1)==UINT32_MAX);
  CHECK(ut_ina_current(100,10)==1000);CHECK(ut_ina_current(65535U,10)==-10);
  CHECK(ut_ina_current(32768U,10)==-327680);
  CHECK(ut_ina_power(4000,10)==1000000U);
  CHECK(ut_ina_power(65535,UINT32_MAX)==INT32_MAX);
  uint8_t encoded[5]={0},*p=encoded,pending=0,bits=0;
  ut_ws_encode_byte(0xa5U,&p,&pending,&bits);
  CHECK(p-encoded==5&&bits==0U);
  uint64_t packed=0;for(unsigned i=0;i<5;i++)packed=(packed<<8)|encoded[i];
  for(unsigned i=0;i<8;i++) {
    unsigned symbol=(unsigned)((packed>>(35U-i*5U))&31U);
    CHECK(symbol==((0xa5U&(0x80U>>i))?0x1cU:0x18U));
  }
}
static void test_ack(void)
{
  GROUP();uint8_t p[8]={4,16,0,0,0,8};crc_append(p,6);
  CHECK(ut_ack_matches(p,8,4,16,0,8));CHECK(!ut_ack_matches(p,8,3,16,0,8));
  CHECK(!ut_ack_matches(p,8,4,6,0,8));CHECK(!ut_ack_matches(p,8,4,16,1,8));
  CHECK(!ut_ack_matches(p,8,4,16,0,7));CHECK(!ut_ack_matches(p,7,4,16,0,8));
  p[7]^=1U;CHECK(!ut_ack_matches(p,8,4,16,0,8));
}
void test_entry(void)
{
  memset((void *)&ut_test_results,0,sizeof ut_test_results);
  test_rtu();test_control();test_menu();test_digital();test_measurements();test_ack();
  ut_test_results.done=0x5554U;
}
#ifndef UT_TEST_EMULATED
int main(void)
{
  test_entry();printf("{\"checks\":%u,\"failures\":%u,\"firstLine\":%u,\"groups\":%u}\n",
    (unsigned)ut_test_results.checks,(unsigned)ut_test_results.failures,(unsigned)ut_test_results.first_line,(unsigned)ut_test_results.groups);
  return ut_test_results.failures?1:0;
}
#endif
