#ifndef UT_INTERACTION_H
#define UT_INTERACTION_H
#include "protocol.h"
#include "snapshot.h"
typedef struct {
  uint8_t node,slot,mode,axis_ready,button_history,button_down,pending;
  uint16_t code,value,result;
  uint32_t nonce,issued_at;
} UtMenu;
static inline void ut_menu_init(UtMenu *s)
{ memset(s,0,sizeof *s);s->node=2U;s->code=1U;s->value=50U;s->axis_ready=1U; }
static inline void ut_menu_step(UtMenu *s,uint16_t x,uint16_t y,uint8_t pressed,uint32_t now)
{
  s->button_history=(uint8_t)(((s->button_history<<1)|(pressed!=0U))&7U);
  uint8_t click=(s->button_history==7U&&!s->button_down);
  if(s->button_history==7U)s->button_down=1U;
  if(s->button_history==0U)s->button_down=0U;
  int axis=0;
  if(x>1600U&&x<2500U&&y>1600U&&y<2500U)s->axis_ready=1U;
  if(s->axis_ready) {
    if(x<1200U)axis=-1;else if(x>2900U)axis=1;
    else if(y<1200U)axis=-2;else if(y>2900U)axis=2;
    if(axis)s->axis_ready=0U;
  }
  if(s->pending&&ut_due(now,s->issued_at,10000U)) {
    s->pending=0U;s->result=UT_RESULT_UNKNOWN;s->mode=0U;
  }
  if(s->pending)return;
  if(s->mode==0U) {
    if(axis==1||axis==-1){s->node=(uint8_t)((s->node+3U+(axis==1?1U:3U))%4U+1U);s->slot=0U;}
    uint8_t pages=(uint8_t)(ut_sensor_count(s->node)+((s->node==2U||s->node==4U)?2U:0U));
    if(axis==2)s->slot=(uint8_t)((s->slot+1U)%pages);
    if(axis==-2)s->slot=(uint8_t)((s->slot+pages-1U)%pages);
    if(click&&s->node==1U){s->result=UT_RESULT_UNSUPPORTED;return;}
    if(click){s->mode=1U;s->code=(s->node==2U||s->node==4U)?1U:(s->node==3U?3U:5U);s->value=s->code==1U?50U:0U;}
  } else if(s->mode==1U) {
    if(axis==2||axis==-2) {
      for(unsigned i=0;i<5U;i++) {
        s->code=axis==2?((s->code%5U)+1U):(((s->code+3U)%5U)+1U);
        if(ut_capable(s->node,s->code))break;
      }
      s->value=s->code==1U?50U:0U;
    }
    if(axis==1||axis==-1) {
      int step=s->code==1U?25:1,max=s->code==1U?100:(s->code==4U?4:(s->code==5U?0:1));
      int value=(int)s->value+(axis==1?step:-step);
      s->value=(uint16_t)(value<0?0:(value>max?max:value));
    }
    if(click)s->mode=2U;
  } else if(s->mode==2U) {
    if(axis){s->mode=0U;return;} /* Any direction cancels; no command exists yet. */
    if(click){if(++s->nonce==0U)++s->nonce;s->issued_at=now;s->pending=1U;s->mode=3U;s->result=0U;}
  }
}
#endif
