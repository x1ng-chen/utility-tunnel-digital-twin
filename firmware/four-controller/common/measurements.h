#ifndef UT_MEASUREMENTS_H
#define UT_MEASUREMENTS_H
#include <stdint.h>
#include <limits.h>
static inline uint32_t ut_rpm(uint32_t pulses,uint32_t elapsed,uint32_t ppr)
{
  if(!elapsed||!ppr)return 0U;
  uint64_t value=(uint64_t)pulses*60000ULL/((uint64_t)ppr*elapsed);
  return value>UINT32_MAX?UINT32_MAX:(uint32_t)value;
}
static inline int32_t ut_ina_current(uint16_t raw,uint32_t lsb_microamps)
{
  int64_t value=(int64_t)(int16_t)raw*lsb_microamps;
  return value>INT32_MAX?INT32_MAX:(value<INT32_MIN?INT32_MIN:(int32_t)value);
}
static inline uint32_t ut_ina_power(uint16_t raw,uint32_t lsb_microamps)
{
  uint64_t value=(uint64_t)raw*25U*lsb_microamps;
  return value>INT32_MAX?INT32_MAX:(uint32_t)value;
}
/* APB1 8 MHz, SPI2 /2 = 4 MHz: five SPI bits per 1.25-us WS2812B bit.
 * 11000 gives T0H=0.50us; 11100 gives T1H=0.75us. Bench-check actual strip. */
static inline void ut_ws_encode_byte(uint8_t value,uint8_t **cursor,uint8_t *pending,uint8_t *bits)
{
  for(uint8_t source=0x80U;source;source>>=1U) {
    uint8_t symbol=(value&source)?0x1cU:0x18U;
    for(uint8_t mask=0x10U;mask;mask>>=1U) {
      *pending=(uint8_t)((*pending<<1U)|((symbol&mask)!=0U));
      if(++*bits==8U){*(*cursor)++=*pending;*pending=0U;*bits=0U;}
    }
  }
}
#endif
