#include "node_a_sensor_bank.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
GPIO_TypeDef bank_gpio_a,bank_gpio_b,bank_gpio_c;
static unsigned calls[4];
static unsigned fail_fourth;
static uint8_t read_sht(const NodeI2CSensorPin *cfg,int16_t *t,uint16_t *h)
{
  unsigned i=(unsigned)(cfg->asset_code[5]-'1');
  assert(i<4);
  assert(cfg->scl_port==GPIOB && cfg->sda_port==GPIOB);
  assert(cfg->scl_pin==(i<2?GPIO_PIN_6:GPIO_PIN_10));
  assert(cfg->sda_pin==(i<2?GPIO_PIN_7:GPIO_PIN_11));
  assert(cfg->i2c_address==(i%2?0x45:0x44));
  calls[i]++;
  if(i==3 && fail_fourth)return 0;
  *t=(int16_t)(2100+i*100); *h=(uint16_t)(5000+i*100);
  return 1;
}
int main(void)
{
  NodeASensorBank b;
  NodeASensorBank_Init(&b,NULL,NULL,NULL);
  b.sht30_reader=read_sht;
  for(unsigned i=0;i<4;i++)assert(b.readings[i].enabled);
  for(unsigned i=0;i<NODE_A_SENSOR_COUNT;i++)NodeASensorBank_Tick(&b,i);
  for(unsigned i=0;i<4;i++){
    assert(calls[i]==1);
    assert(b.readings[i].online && b.readings[i].quality==SENSOR_QUALITY_GOOD);
    assert(b.readings[i].temperature_centi_c==2100+(int)i*100);
  }
  fail_fourth=1;
  for(unsigned i=0;i<NODE_A_SENSOR_COUNT;i++)NodeASensorBank_Tick(&b,100+i);
  assert(!b.readings[3].online && b.readings[3].quality==SENSOR_QUALITY_MISSING);
  assert(b.readings[0].online && b.readings[1].online && b.readings[2].online);
  fail_fourth=0;
  for(unsigned i=0;i<NODE_A_SENSOR_COUNT;i++)NodeASensorBank_Tick(&b,200+i);
  assert(b.readings[3].online);
  NodeASensorBank_SetEnabled(&b,1,0);
  unsigned before=calls[1];
  for(unsigned i=0;i<NODE_A_SENSOR_COUNT;i++)NodeASensorBank_Tick(&b,300+i);
  assert(calls[1]==before && b.readings[1].quality==SENSOR_QUALITY_MISSING);
  puts("sht4 acquisition: four bus/address mappings, disconnect, reconnect, disable PASS");
}
