#ifndef UT_SNAPSHOT_H
#define UT_SNAPSHOT_H
#include "protocol.h"
static inline uint8_t ut_sensor_owner(uint16_t id)
{
  if(id>=1U&&id<=4U)return 4U;
  if(id<=8U&&id>=5U)return 3U;
  if((id>=9U&&id<=12U)||(id>=17U&&id<=20U))return 1U;
  if(id>=13U&&id<=16U)return 2U;
  if(id>=21U&&id<=28U) {
    static const uint8_t extra[4]={4U,3U,1U,2U};
    return extra[(id-21U)%4U];
  }
  return id==29U?4U:(id==30U?1U:(id==31U?2U:0U));
}
static inline uint8_t ut_sensor_count(uint8_t board)
{
  static const uint8_t counts[4]={11U,7U,6U,7U};
  return board>=1U&&board<=4U?counts[board-1U]:0U;
}
/* Shared wire-level identity/range check, independent of HAL and model labels.
 * A complete node snapshot has no repeated or reassigned physical modules. */
static inline uint8_t ut_snapshot_valid(uint8_t board,const uint16_t *r,size_t count)
{
  if(!r||count<UT_VIEW_COUNT||board<1U||board>4U||r[0]!=0x5554U||
      r[1]!=board||r[2]!=UT_VERSION||r[3]!=ut_sensor_count(board))return 0U;
  uint32_t seen=0;
  for(unsigned i=0;i<r[3];i++) {
    unsigned at=8U+i*4U;uint16_t id=r[at],value=r[at+1U],aux=r[at+2U];
    if(!id||id>31U||ut_sensor_owner(id)!=board||(seen&(1UL<<(id-1U)))||r[at+3U]>3U)return 0U;
    if(r[at+3U]==3U&&!(id<=20U&&((id-1U)%4U==0U||(id-1U)%4U==3U))&&!(id>=25U&&id<=28U))return 0U;
    if(r[at+3U]==3U&&value!=1U)return 0U;
    seen|=1UL<<(id-1U);
    if(id<=20U) {
      unsigned type=(id-1U)%4U;
      if((type==0U||type==3U)?value>1U:value>4095U)return 0U;
    } else if(id<=24U) {
      if((int16_t)value < -4500 || (int16_t)value>13000 || aux>10000U)return 0U;
    } else if(id<=28U) {if(value>1U)return 0U;}
    else if(value>4095U||aux>3300U)return 0U;
  }
  return 1U;
}
#endif
