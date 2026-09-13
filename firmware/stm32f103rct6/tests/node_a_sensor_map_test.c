#include "node_a_clock_contract.h"
#include "stm32f1xx_hal.h"
#include "node_a_ina226.h"
#include "node_a_sensor_map.h"

_Static_assert(NODE_A_SYSCLK_HZ == 72000000UL,
               "Node A SYSCLK must be 72 MHz");
_Static_assert(NODE_A_HCLK_HZ == 72000000UL,
               "Node A HCLK must be 72 MHz");
_Static_assert(NODE_A_PCLK1_HZ == 36000000UL,
               "Node A APB1 must be 36 MHz");
_Static_assert(NODE_A_PCLK2_HZ == 72000000UL,
               "Node A APB2 must be 72 MHz");
_Static_assert(NODE_A_ADC_CLOCK_HZ <= 12000000UL,
               "Node A ADC clock must not exceed 12 MHz");
_Static_assert(NODE_A_FAN_PWM_HZ == 25000UL,
               "fan PWM must remain 25 kHz");
_Static_assert(NODE_A_FAN_TIMER_PERIOD == 2879U,
               "TIM4 period must match 72 MHz timer clock");
_Static_assert(NODE_A_UART_BAUD == 9600UL,
               "Node A UARTs must remain 9600 baud");
_Static_assert(NODE_A_SHT30_MEASUREMENT_DELAY_MS == 20U,
               "SHT30 conversion timing must remain valid");
_Static_assert(NODE_A_SHT30_TIMEOUT_MS == 100U,
               "SHT30 timeout must remain bounded");
_Static_assert(NODE_A_WS2812_SPI_HZ >= 4000000UL &&
               NODE_A_WS2812_SPI_HZ <= 5000000UL,
               "WS2812 SPI clock must remain in the timing window");
_Static_assert(NODE_A_WS2812_BITS_PER_DATA_BIT == 6U,
               "WS2812 encoding must use six SPI bits per data bit");
_Static_assert(NODE_A_WS2812_ZERO_PATTERN == 0x20U &&
               NODE_A_WS2812_ONE_PATTERN == 0x3CU,
               "WS2812 waveform patterns must preserve pulse widths");

_Static_assert(NODE_A_CO_ADC_CHANNEL == ADC_CHANNEL_11,
               "CO analog input must remain on PC1 / ADC1_IN11");
_Static_assert(NODE_A_METHANE_ADC_CHANNEL == ADC_CHANNEL_12,
               "methane analog input must remain on PC2 / ADC1_IN12");
_Static_assert(NODE_A_OXYGEN_ADC_CHANNEL == ADC_CHANNEL_13,
               "oxygen analog input must remain on PC3 / ADC1_IN13");
_Static_assert(NODE_A_ADC_RAW_TO_UV(1518U) == 1223297UL,
               "ADC conversion must not overflow above raw code 1301");
_Static_assert(NODE_A_MEDIAN3(100U, 900U, 110U) == 110U,
               "median filter must reject a single high spike");
_Static_assert(NODE_A_EMA_QUARTER(100U, 200U) == 125U,
               "EMA must move one quarter toward the new sample");
_Static_assert(NODE_A_HIGH_ALARM_STATE(0U, 1800U, 1800U, 1700U) == 1U,
               "high alarm must enter at the on threshold");
_Static_assert(NODE_A_HIGH_ALARM_STATE(1U, 1750U, 1800U, 1700U) == 1U,
               "high alarm must remain latched inside hysteresis");
_Static_assert(NODE_A_HIGH_ALARM_STATE(1U, 1700U, 1800U, 1700U) == 0U,
               "high alarm must clear at the off threshold");
_Static_assert(NODE_A_LOW_ALARM_STATE(0U, 36U, 36U, 40U) == 1U,
               "low alarm must enter at the on threshold");
_Static_assert(NODE_A_LOW_ALARM_STATE(1U, 38U, 36U, 40U) == 1U,
               "low alarm must remain latched inside hysteresis");
_Static_assert(NODE_A_LOW_ALARM_STATE(1U, 40U, 36U, 40U) == 0U,
               "low alarm must clear at the off threshold");
_Static_assert(NODE_A_OPERATIONAL_GAS_ALARM(1U, 0U, 1U) == 0U,
               "uncalibrated oxygen and CO channels must not drive actuators");
_Static_assert(NODE_A_OPERATIONAL_GAS_ALARM(0U, 1U, 0U) == 1U,
               "the bench-verified methane channel must still drive the alarm");
_Static_assert(NODE_A_GAS_VENTILATION_HOLD_MS == 30000U,
               "gas ventilation must continue for 30 seconds after clear");
_Static_assert(NODE_A_GAS_VENTILATION_SHOULD_RUN(1U, 0U, 0U) == 1U,
               "an active gas alarm must force ventilation on");
_Static_assert(NODE_A_GAS_VENTILATION_SHOULD_RUN(0U, 1U, 29999U) == 1U,
               "ventilation must remain on during the post-alarm hold");
_Static_assert(NODE_A_GAS_VENTILATION_SHOULD_RUN(0U, 1U, 30000U) == 0U,
               "ventilation may stop when the post-alarm hold expires");
_Static_assert(NODE_A_INA226_BUS_RAW_TO_UV(9520U) == 11900000UL,
               "INA226 bus voltage conversion must preserve a measured 11.9 V rail");
_Static_assert(NODE_A_INA226_SHUNT_RAW_TO_UA(400) == 10000L,
               "R100 shunt conversion must map 1 mV to 10 mA");
_Static_assert(NODE_A_INA226_POWER_UW(11900000UL, 10000L) == 119000L,
               "power must be derived from measured bus voltage and shunt current");
_Static_assert(NODE_A_INA226_SAMPLE_STUCK_03FF(1023U, 1023, 1023, 1023U) == 1U,
               "identical 0x03ff measurement registers must be rejected");
_Static_assert(NODE_A_INA226_SAMPLE_STUCK_03FF(1023U, 1023, 0, 0U) == 1U,
               "bus and shunt 0x03ff must be rejected even without calibration");
_Static_assert(NODE_A_INA226_SAMPLE_STUCK_03FF(9520U, 400, 1000, 476U) == 0U,
               "a plausible loaded-fan sample must not be rejected");

int main(void)
{
  return 0;
}
