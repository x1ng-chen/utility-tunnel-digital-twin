#include "screen.h"
#include "board_config.h"
#include "st7735.h"
#include "menu.h"
#include <stdio.h>
#include <string.h>
void Screen_Init(void) { ST7735_Init(); }
void Screen_Update(uint8_t board,uint16_t sequence,uint32_t uptime_s,uint8_t alarm,const SensorSample *samples,uint8_t count)
{
  /* Exactly one 128x8 font row per call, padded to erase shorter previous text.
   * Seven calls form a full page. UART is serviced between rows. */
  static uint8_t row,page,previous_alarm;
  static uint32_t page_at;
  static char previous[7][17];
  char line[40]={0},padded[17];
  if(!samples||count>board_config.sensor_count){samples=BoardIo_Samples();count=BoardIo_SampleCount();}
  unsigned pages=(count+4U)/5U;if(!pages)pages=1U;
  if(page>=pages)page=0U;
  if(alarm!=previous_alarm){memset(previous,0,sizeof previous);previous_alarm=alarm;}
  if(board_config.has_joystick)Menu_Line(row,line,sizeof line,HAL_GetTick());
  else if(row==0U)snprintf(line,sizeof line,"CTRL-%u %s",board,alarm?"ALARM":"READY");
  else if(row==6U) {
    snprintf(line,sizeof line,"SEQ%u %lus",sequence,(unsigned long)uptime_s);
    if((uint32_t)(HAL_GetTick()-page_at)>=3000U){page=(uint8_t)((page+1U)%pages);page_at=HAL_GetTick();}
  }
  else {
    unsigned i=(unsigned)page*5U+row-1U;
    if(i<count) {
      const SensorDef *d=&board_config.sensors[i];
      if(samples[i].status==SENSOR_STATUS_MISSING)snprintf(line,sizeof line,"%s -- MISSING",d->tag);
      else if(d->type==SENSOR_SHT) {
        int t=(int16_t)samples[i].value,a=t<0?-t:t;
        snprintf(line,sizeof line,"T%s%d.%d H%u",t<0?"-":"",a/100,(a%100)/10,samples[i].aux/100U);
      } else snprintf(line,sizeof line,"%s %u Q%u",d->tag,samples[i].value,samples[i].status);
    }
  }
  memset(padded,' ',16U);padded[16]='\0';
  size_t length=strlen(line);if(length>16U)length=16U;memcpy(padded,line,length);
  if(memcmp(previous[row],padded,17U)!=0) {
    ST7735_DrawString(0,row*18,padded,alarm?LCD_RED:LCD_WHITE,LCD_BLACK);
    memcpy(previous[row],padded,17U);
  }
  row=(row+1U)%7U;
}
