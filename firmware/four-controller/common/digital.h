#ifndef UT_DIGITAL_H
#define UT_DIGITAL_H
#include <stdint.h>
#define UT_DIGITAL_HOLD_MS 10000U
typedef struct {
  uint8_t history,level,samples,valid,seen;
  uint32_t observed_at,last_active,events;
} UtDigital;
/* SysTick is the only writer. Main copies a snapshot with IRQ state preserved.
 * Three observed samples reject glitches; this cannot recover an unseen pulse. */
static inline void ut_digital_observe(volatile UtDigital *s,uint8_t active,uint32_t now)
{
  s->history=(uint8_t)(((s->history<<1U)|(active!=0U))&7U);
  if(s->samples<3U)++s->samples;
  s->observed_at=now;
  if(s->samples<3U)return;
  if(s->history==7U) {
    if(!s->level)++s->events;
    s->valid=1U;s->seen=1U;s->level=1U;s->last_active=now;
  } else if(s->history==0U){s->valid=1U;s->level=0U;}
}
static inline uint8_t ut_digital_latched(const UtDigital *s,uint32_t now)
{ return s->valid&&!s->level&&s->seen&&(uint32_t)(now-s->last_active)<UT_DIGITAL_HOLD_MS; }
#endif
