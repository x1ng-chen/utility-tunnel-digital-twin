#include "menu.h"
#include "joystick.h"
#include "board_config.h"
#include "stm32f1xx_hal.h"
#include "../../common/interaction.h"
#include <stdio.h>
static UtMenu menu;
static uint8_t initialized;
static uint32_t gateway_session;
void Menu_Session(uint32_t session)
{
  if(!board_config.has_joystick || !session || session==gateway_session)return;
  if(!initialized){ut_menu_init(&menu);initialized=1U;}
  menu.pending=0U;menu.mode=0U;menu.result=UT_RESULT_UNKNOWN;gateway_session=session;
}
static uint32_t last_poll,view_at;
static uint16_t view[UT_VIEW_COUNT];
void Menu_Poll(uint32_t now)
{
  if(!board_config.has_joystick)return;
  if(!initialized){ut_menu_init(&menu);initialized=1U;}
  if((uint32_t)(now-last_poll)<20U)return;
  last_poll=now;uint16_t x,y;uint8_t pressed;
  Joystick_Read(&x,&y,&pressed);ut_menu_step(&menu,x,y,pressed,now);
  if(!gateway_session&&menu.pending){menu.pending=0U;menu.mode=0U;menu.result=UT_RESULT_UNKNOWN;}
}
uint8_t Menu_View(const uint16_t *registers,uint16_t count)
{
  if(count!=UT_VIEW_COUNT||!ut_snapshot_valid((uint8_t)registers[1],registers,count))return 0U;
  memcpy(view,registers,sizeof view);view_at=HAL_GetTick();return 1U;
}
void Menu_Ack(const uint16_t *registers)
{
  uint32_t nonce=((uint32_t)registers[0]<<16)|registers[1];
  if(registers[2]>=1U&&registers[2]<=UT_RESULT_UNKNOWN&&menu.pending&&nonce==menu.nonce) {
    menu.result=registers[2];menu.pending=0U;menu.mode=0U;
  }
}
void Menu_Registers(uint16_t *registers,uint32_t now)
{
  if(!initialized){ut_menu_init(&menu);initialized=1U;}
  registers[0]=(uint16_t)(menu.nonce>>16);registers[1]=(uint16_t)menu.nonce;
  registers[2]=menu.node;registers[3]=menu.code;registers[4]=menu.value;
  registers[5]=menu.pending&&!ut_due(now,menu.issued_at,10000U)?(uint16_t)(10000U-(uint32_t)(now-menu.issued_at)):0U;
  registers[6]=menu.node;registers[7]=menu.pending;
}
static void SensorTag(uint16_t id,char *text,unsigned size)
{
  if(id>=1U&&id<=20U) {
    static const char *names[4]={"MQ2","MQ4","CO","FLAME"};
    snprintf(text,size,"%s-%02u",names[(id-1U)%4U],(id-1U)/4U+1U);
  } else if(id<=24U&&id>=21U)snprintf(text,size,"SHT-%02u",id-20U);
  else if(id<=28U&&id>=25U)snprintf(text,size,"LEVEL-%02u",id-24U);
  else if(id<=31U&&id>=29U)snprintf(text,size,"O2-%02u",id-28U);
  else snprintf(text,size,"UNKNOWN");
}
void Menu_Line(uint8_t row,char *text,unsigned size,uint32_t now)
{
  const char *actions[]={"?","PWM","供电","蜂鸣","灯带","自动"};
  uint8_t fresh=view_at&&view[1]==menu.node&&(uint32_t)(now-view_at)<3500U;
  uint8_t slot=menu.slot;
  unsigned r=8U+slot*4U;
  uint32_t age=(fresh&&slot<view[3])?view[UT_SENSOR_AGE_BASE+slot]*10U+(uint32_t)(now-view_at):655350U;
  if(row==0U)snprintf(text,size,"主控%u %s",menu.node,fresh?"实时":"过期");
  else if(row>=1U&&row<=3U&&!fresh)snprintf(text,size,row==1U?"等待网关":(row==2U?"数据缺失":"当前视图过期"));
  else if(row>=1U&&row<=3U&&slot>=view[3]) {
    uint8_t fan=menu.node==4U?1U:2U;
    if(slot==view[3]) {
      if(row==1U)snprintf(text,size,"风机%u 转速",fan);
      else if(row==2U) {
        if(view[55]==1U||view[79]==65535U)snprintf(text,size,"转速缺失");
        else snprintf(text,size,"%lu RPM Q%u",(unsigned long)(((uint32_t)view[53]<<16)|view[54]),view[55]);
      } else snprintf(text,size,"PWM %u RELAY %u",view[63]&255U,(view[63]>>8)&1U);
    } else {
      uint32_t millivolts=((uint32_t)view[56]<<16)|view[57];
      int32_t microamps=(int32_t)(((uint32_t)view[58]<<16)|view[59]);
      uint32_t microwatts=((uint32_t)view[60]<<16)|view[61];
      if(row==1U)snprintf(text,size,"风机%u 功率",fan);
      else if((view[62]&255U)==1U)snprintf(text,size,"电流数据缺失");
      else if(row==2U)snprintf(text,size,"%lumV %ldmA",(unsigned long)millivolts,(long)(microamps/1000));
      else snprintf(text,size,"%lumW %s",(unsigned long)(microwatts/1000U),(view[62]&256U)?"已验证":"存疑");
    }
  } else if(row==1U)snprintf(text,size,"测点 %u/%u",slot+1U,view[3]);
  else if(row==2U) {
    if(r+3U>=UT_VIEW_COUNT||view[r]==65535U||view[r+3U]==1U)snprintf(text,size,"数据缺失");
    else if(age>5000U&&view[r+3U]!=3U)snprintf(text,size,"数据过期");
    else if(view[r]>=21U&&view[r]<=24U) {
      int t=(int16_t)view[r+1U],a=t<0?-t:t;
      snprintf(text,size,"SHT%u %s%d.%02dC",view[r]-20U,t<0?"-":"",a/100,a%100);
    } else {char tag[12];SensorTag(view[r],tag,sizeof tag);snprintf(text,size,"%s %u",tag,view[r+1U]);}
  } else if(row==3U) {
    if(view[r]>=21U&&view[r]<=24U)snprintf(text,size,"H%u.%02u%% Q%u",view[r+2U]/100U,view[r+2U]%100U,view[r+3U]);
    else if(view[r]>=29U)snprintf(text,size,"%umV 原始量",view[r+2U]);
    else if(view[r+3U]==3U)snprintf(text,size,"锁存 %lums",(unsigned long)age);
    else snprintf(text,size,"Q%u age%lums",view[r+3U],(unsigned long)age);
  } else if(row==4U)snprintf(text,size,"%s %s %u",menu.mode==2U?"确认":(menu.pending?"下发":"动作"),actions[menu.code<=5U?menu.code:0U],menu.value);
  else if(row==5U)snprintf(text,size,"%s",menu.mode==2U?"按确认 移动取消":(menu.mode==1U?"Y选类型 X数值":"X选节点Y选测点"));
  else if(!gateway_session)snprintf(text,size,"等待网关同步");
  else snprintf(text,size,"R%u %s",menu.result,menu.result==UT_RESULT_OK?"输出已应用":"未验证转动");
}
