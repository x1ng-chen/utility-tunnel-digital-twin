#ifndef NODE_A_INA226_H
#define NODE_A_INA226_H

#include <stdint.h>

/* INA226 conversion constants for the installed R100 (100 mOhm) modules. */
#define NODE_A_INA226_BUS_RAW_TO_UV(raw) \
  ((uint32_t)(raw) * 1250UL)

#define NODE_A_INA226_SHUNT_RAW_TO_UA(raw) \
  ((int32_t)(raw) * 25L)

#define NODE_A_INA226_POWER_UW(bus_uv, current_ua) \
  ((int32_t)(((int64_t)(bus_uv) * (int64_t)(current_ua)) / 1000000LL))

/* 0x03ff simultaneously appearing in every independent conversion register
 * is the field failure signature observed on both modules.  It must never be
 * promoted to apparently valid engineering values. */
#define NODE_A_INA226_SAMPLE_STUCK_03FF(bus, shunt, current, power) \
  (((uint16_t)(bus) == 0x03FFU) && ((uint16_t)(shunt) == 0x03FFU))

#endif
