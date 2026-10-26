#ifndef ACTUATORS_H
#define ACTUATORS_H

#include <stdint.h>

typedef struct
{
  uint8_t online;
  uint8_t plausible;
  uint16_t bus_raw;
  int16_t current_raw;
  uint16_t power_raw;
  uint32_t bus_millivolts;
  int32_t current_microamps;
  int32_t power_microwatts;
} InaReading;

void Actuators_Init(void);
void Actuators_Poll(uint32_t now);

/* 仅 2/4 号板有风机与继电器；其他板调用保持为空操作。 */
void Actuators_SetFanPercent(uint8_t percent);
uint8_t Actuators_FanPercent(void);
uint32_t Actuators_FanRpm(void);
void Actuators_SetRelay(uint8_t on);
uint8_t Actuators_RelayOn(void);
uint8_t Actuators_ReadIna(InaReading *out);

/* 仅 3 号板有蜂鸣器与灯带。 */
void Actuators_SetBuzzer(uint8_t on);
void Actuators_SetLedColor(uint8_t red, uint8_t green, uint8_t blue);

#endif
