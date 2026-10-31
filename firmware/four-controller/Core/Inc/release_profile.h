#ifndef UT_RELEASE_PROFILE_H
#define UT_RELEASE_PROFILE_H
#include "../../common/firmware_version.h"
#ifndef UT_WATCHDOG_ENABLED
#define UT_WATCHDOG_ENABLED 1
#endif
#ifndef FAN_PWM_INVERTED
#define FAN_PWM_INVERTED 1
#endif
#ifndef RELAY_ACTIVE_HIGH
#define RELAY_ACTIVE_HIGH 1
#endif
#ifndef FAN_PULSES_PER_REV
#define FAN_PULSES_PER_REV 2U
#endif
#ifndef FAN_TACH_VERIFIED
#define FAN_TACH_VERIFIED 0
#endif
#ifndef INA_SHUNT_MICROOHMS
#define INA_SHUNT_MICROOHMS 10000U
#endif
#ifndef INA_CURRENT_LSB_UA
#define INA_CURRENT_LSB_UA 100U
#endif
#ifndef INA_CALIBRATION_VERIFIED
#define INA_CALIBRATION_VERIFIED 0
#endif
#if defined(UT_RELEASE_BUILD) && UT_RELEASE_BUILD && (defined(ONLY_MODBUS) || defined(MINIMAL_485))
#error "Diagnostic-only flags are forbidden in business release images"
#endif
_Static_assert(FAN_PWM_INVERTED==0||FAN_PWM_INVERTED==1,"PWM polarity must be boolean");
_Static_assert(RELAY_ACTIVE_HIGH==0||RELAY_ACTIVE_HIGH==1,"Relay polarity must be boolean");
_Static_assert(UT_WATCHDOG_ENABLED==0||UT_WATCHDOG_ENABLED==1,"Watchdog flag must be boolean");
_Static_assert(FAN_TACH_VERIFIED==0||FAN_TACH_VERIFIED==1,"Tach verification flag must be boolean");
_Static_assert(INA_CALIBRATION_VERIFIED==0||INA_CALIBRATION_VERIFIED==1,"INA verification flag must be boolean");
#endif
