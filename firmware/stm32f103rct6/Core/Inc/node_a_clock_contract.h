#ifndef NODE_A_CLOCK_CONTRACT_H
#define NODE_A_CLOCK_CONTRACT_H

/* CTRL-01 (Node A) clock and peripheral contract.
 *
 * The clock-tree values below are derived from the selection macros that
 * SystemClock_Config() and the MX_*_Init() functions pass to the HAL, or from
 * HSE_VALUE in stm32f1xx_hal_conf.h, and the static assertions at the bottom of
 * this header fail the build if the retune drifts.  The peripheral periods, the
 * software-I2C delay budgets and the interrupt priorities are declared here as
 * literals because they are design choices rather than HAL encodings; the
 * persistent host test tests/node_a_clock_host_test.py derives those numbers
 * from the production sources and fails if they disagree with this header. */

#include "stm32f1xx_hal.h"

/* --- Oscillator and PLL ---------------------------------------------------
 * The board fits an 8 MHz crystal.  The PLL multiplies it by nine; the HAL
 * encodes "multiply by N" as N - 2 in RCC_CFGR.PLLMULL, so the multiplier is
 * recovered from the selected RCC_PLL_MUL9 macro rather than repeated. */
#define NODE_A_HSE_PREDIV                            1UL /* RCC_HSE_PREDIV_DIV1 */
#define NODE_A_PLL_MULTIPLIER \
  (((RCC_PLL_MUL9 >> RCC_CFGR_PLLMULL_Pos) + 2UL))
#define NODE_A_HSE_HZ                            (HSE_VALUE)
#define NODE_A_SYSCLK_HZ \
  ((NODE_A_HSE_HZ / NODE_A_HSE_PREDIV) * NODE_A_PLL_MULTIPLIER)

/* --- AHB / APB ------------------------------------------------------------
 * AHB = SYSCLK, APB1 = HCLK / 2, APB2 = HCLK.  The dividers are recovered
 * from the RCC_CFGR.PPRE encodings the HAL uses: the PPRE field holds the
 * APB prescaler code (0b0xx -> /1, 0b100 -> /2, 0b101 -> /4, ...). */
#define NODE_A_APB1_DIVIDER                          2UL
#define NODE_A_APB2_DIVIDER                          1UL
#define NODE_A_HCLK_HZ                       NODE_A_SYSCLK_HZ
#define NODE_A_PCLK1_HZ                 (NODE_A_HCLK_HZ / NODE_A_APB1_DIVIDER)
#define NODE_A_PCLK2_HZ                 (NODE_A_HCLK_HZ / NODE_A_APB2_DIVIDER)

/* APB1 timers run at 2 x PCLK1 whenever the APB1 prescaler is not one
 * (RM0008 timer clock rule). */
#define NODE_A_APB1_TIMER_HZ \
  ((NODE_A_PCLK1_HZ) * ((NODE_A_APB1_DIVIDER == 1UL) ? 1UL : 2UL))

/* --- FLASH ----------------------------------------------------------------
 * 48 MHz < 72 MHz <= 72 MHz requires two wait states on STM32F103.  The HAL
 * macro carries the LATENCY[2:0] register encoding (0b010), not the literal
 * wait-state count. */
#define NODE_A_FLASH_LATENCY                  FLASH_LATENCY_2
#define NODE_A_FLASH_WAIT_STATES                     2UL

/* --- SysTick / HAL tick ---------------------------------------------------
 * HAL_RCC_ClockConfig() updates SystemCoreClock and re-runs HAL_InitTick()
 * after the switch, so the HAL millisecond tick is derived from the new HCLK. */
#define NODE_A_HAL_TICK_HZ                        1000UL
#define NODE_A_SYSTICK_RELOAD \
  ((NODE_A_HCLK_HZ / NODE_A_HAL_TICK_HZ) - 1UL)

/* --- USART -----------------------------------------------------------------
 * Both USARTs stay at 9600 baud.  The HAL computes BRR for 16x oversampling as
 * USARTDIV x 100 = PCLK x 25 / (4 x baud), mantissa = /100, then the fractional
 * part rounded into sixteenths.  The macros mirror that derivation so the
 * expected BRR follows the selected PCLK instead of being repeated. */
#define NODE_A_UART_BAUD                            9600UL
#define NODE_A_UART_DIV_100(pclk) \
  (((pclk) * 25UL) / (4UL * NODE_A_UART_BAUD))
#define NODE_A_UART_BRR(pclk) \
  ((((NODE_A_UART_DIV_100(pclk)) / 100UL) << 4U) | \
   (((((NODE_A_UART_DIV_100(pclk)) % 100UL) * 16UL) + 50UL) / 100UL))

/* --- ADC -------------------------------------------------------------------
 * RCC_CFGR.ADCPRE encodes the ADC prescaler as (divider / 2) - 1, so the
 * divider is recovered from the selected RCC_ADCPCLK2_DIV6 macro. */
#define NODE_A_ADC_CLOCK_DIVIDER \
  (((RCC_ADCPCLK2_DIV6 >> RCC_CFGR_ADCPRE_Pos) + 1UL) * 2UL)
#define NODE_A_ADC_CLOCK_HZ \
  (NODE_A_PCLK2_HZ / NODE_A_ADC_CLOCK_DIVIDER)
#define NODE_A_ADC_MAX_CLOCK_HZ                  12000000UL
/* ADC_SAMPLETIME_239CYCLES_5 encodes SMP = 0b111 -> 239.5 sampling cycles; a
 * 12-bit conversion adds 12.5 cycles, giving 252.0 cycles per sample.  The
 * tenths are kept so the conversion time stays exact integer arithmetic. */
#define NODE_A_ADC_SAMPLE_TIME_CODE                  0x7UL
#define NODE_A_ADC_CONVERSION_CYCLES_X10            2520UL
#define NODE_A_ADC_CONVERSION_NS \
  ((NODE_A_ADC_CONVERSION_CYCLES_X10 * 1000000000ULL) / \
   (10ULL * NODE_A_ADC_CLOCK_HZ))
#define NODE_A_GAS_ADC_SAMPLE_COUNT                   64U
#define NODE_A_GAS_ADC_POLL_TIMEOUT_MS                10U

/* --- TIM4 fan PWM ----------------------------------------------------------
 * 72 MHz timer clock / 2880 = 25 kHz, the standard four-wire fan carrier. */
#define NODE_A_FAN_PWM_HZ                         25000UL
#define NODE_A_FAN_TIMER_PRESCALER                    0UL
#define NODE_A_FAN_TIMER_PERIOD                    2879UL
#define NODE_A_FAN_TIMER_CLOCK_HZ \
  (NODE_A_APB1_TIMER_HZ / (NODE_A_FAN_TIMER_PRESCALER + 1UL))
#define NODE_A_FAN_PWM_TIMER_HZ \
  (NODE_A_FAN_TIMER_CLOCK_HZ / (NODE_A_FAN_TIMER_PERIOD + 1UL))
#define NODE_A_FAN_PWM_RESOLUTION \
  (NODE_A_FAN_TIMER_PERIOD + 1UL)

/* --- SPI2 / WS2812 ---------------------------------------------------------
 * SPI2 is clocked from PCLK1 with BR = 0b010 -> PCLK1 / 8 = 4.5 MHz.  Each
 * WS2812 bit is six SPI bits: the leading HIGH bits carry the pulse width, the
 * trailing LOW bits the rest of the 1.33 us cell. */
#define NODE_A_WS2812_BITS_PER_DATA_BIT                 6UL
#define NODE_A_WS2812_BR_FIELD \
  ((SPI_CR1_BR_1 >> SPI_CR1_BR_Pos))
#define NODE_A_WS2812_SPI_DIVIDER \
  (1UL << (NODE_A_WS2812_BR_FIELD + 1UL))
#define NODE_A_WS2812_SPI_HZ \
  (NODE_A_PCLK1_HZ / NODE_A_WS2812_SPI_DIVIDER)
/* HIGH bits first: the top `high_bits` of the six transmitted bits are set. */
#define NODE_A_WS2812_PATTERN(high_bits) \
  ((0xFFU >> (8U - NODE_A_WS2812_BITS_PER_DATA_BIT)) & \
   (0xFFU << (NODE_A_WS2812_BITS_PER_DATA_BIT - (high_bits))))
#define NODE_A_WS2812_ZERO_HIGH_BITS                    1UL
#define NODE_A_WS2812_ONE_HIGH_BITS                     4UL
#define NODE_A_WS2812_ZERO_PATTERN \
  NODE_A_WS2812_PATTERN(NODE_A_WS2812_ZERO_HIGH_BITS)
#define NODE_A_WS2812_ONE_PATTERN \
  NODE_A_WS2812_PATTERN(NODE_A_WS2812_ONE_HIGH_BITS)
/* Multiply before dividing so the reported width keeps the sub-nanosecond
 * remainder instead of truncating each single-bit pulse first. */
#define NODE_A_WS2812_NS(bits) \
  (((bits) * 1000000000ULL) / NODE_A_WS2812_SPI_HZ)
#define NODE_A_WS2812_BIT_NS \
  NODE_A_WS2812_NS(1UL)
#define NODE_A_WS2812_CELL_NS \
  NODE_A_WS2812_NS(NODE_A_WS2812_BITS_PER_DATA_BIT)
#define NODE_A_WS2812_ZERO_HIGH_NS \
  NODE_A_WS2812_NS(NODE_A_WS2812_ZERO_HIGH_BITS)
#define NODE_A_WS2812_ONE_HIGH_NS \
  NODE_A_WS2812_NS(NODE_A_WS2812_ONE_HIGH_BITS)
#define NODE_A_WS2812_ZERO_LOW_NS \
  (NODE_A_WS2812_CELL_NS - NODE_A_WS2812_ZERO_HIGH_NS)
#define NODE_A_WS2812_ONE_LOW_NS \
  (NODE_A_WS2812_CELL_NS - NODE_A_WS2812_ONE_HIGH_NS)

/* --- Software I2C and sensor timing ---------------------------------------
 * I2c_Delay() is HAL_Delay(NODE_A_SOFT_I2C_DELAY_MS).  Every software-I2C
 * transfer is bounded twice over.  Structurally, each primitive is a fixed
 * count of bit slots and none of them waits on bus state, so a line held low by
 * a short or a stuck slave still completes after a known number of slots and
 * then fails its acknowledge or CRC check.  In time, every transaction carries
 * an absolute HAL tick deadline that is re-checked at each bit slot, each byte
 * boundary and after the stop, so the transaction is capped at the deadline
 * plus the longest uninterruptible delay on its path (the 20 ms conversion
 * delay, or the 40 ms INA226 sample settle) and the bus is always released
 * before returning.
 *
 * The deadline must stay above the slowest healthy transfer or it would cut
 * working bench reads, so the watchdogs below are strict upper bounds sized from
 * the fixed delay counts of the worst-case recovery paths rather than from the
 * nominal durations.  HAL_Delay(N) waits N + uwTickFreq ticks (the HAL adds one
 * to guarantee a minimum wait), which is why every modelled HAL_Delay carries
 * NODE_A_HAL_DELAY_OVERHEAD_TICKS on top of its argument. */
#define NODE_A_SOFT_I2C_DELAY_MS                      1UL
#define NODE_A_HAL_DELAY_OVERHEAD_TICKS               1UL
#define NODE_A_SHT30_MEASUREMENT_DELAY_MS            20UL
#define NODE_A_SHT30_FIXED_DELAY_COUNT              190UL
#define NODE_A_SHT30_WORST_CASE_MS \
  ((NODE_A_SHT30_MEASUREMENT_DELAY_MS + NODE_A_HAL_DELAY_OVERHEAD_TICKS) + \
   (NODE_A_SHT30_FIXED_DELAY_COUNT * \
    (NODE_A_SOFT_I2C_DELAY_MS + NODE_A_HAL_DELAY_OVERHEAD_TICKS)))
#define NODE_A_SHT30_TIMEOUT_MS                     500UL
/* INA226 worst case: the stuck-0x03ff recovery repeats the configure and sample
 * pass, so the budget counts two passes, each with six register reads (97 fixed
 * delays), three register writes (77 each) and twelve sample reads (97 each),
 * plus two I2c_Recover sequences (21 delays each) and the settles.  One pass
 * makes NODE_A_INA226_SETTLE_CALL_COUNT HAL_Delay calls: three in
 * Ina226_Configure (reset, configuration, calibration) and two in the sample
 * loop. */
#define NODE_A_INA226_SAMPLE_COUNT                    3UL
#define NODE_A_INA226_PASS_DELAY_COUNT             1977UL
#define NODE_A_INA226_I2C_RECOVER_DELAY_COUNT        21UL
#define NODE_A_INA226_FIXED_DELAY_COUNT \
  ((2UL * NODE_A_INA226_PASS_DELAY_COUNT) + \
   (2UL * NODE_A_INA226_I2C_RECOVER_DELAY_COUNT))
#define NODE_A_INA226_SETTLE_DELAY_MS                83UL
#define NODE_A_INA226_SETTLE_CALL_COUNT               5UL
#define NODE_A_INA226_SETTLE_BUDGET_MS \
  (2UL * (NODE_A_INA226_SETTLE_DELAY_MS + \
          ((NODE_A_INA226_SAMPLE_COUNT - 1UL) * 40UL) + \
          (NODE_A_INA226_SETTLE_CALL_COUNT * NODE_A_HAL_DELAY_OVERHEAD_TICKS)))
#define NODE_A_INA226_WORST_CASE_MS \
  ((NODE_A_INA226_FIXED_DELAY_COUNT * \
    (NODE_A_SOFT_I2C_DELAY_MS + NODE_A_HAL_DELAY_OVERHEAD_TICKS)) + \
   NODE_A_INA226_SETTLE_BUDGET_MS)
#define NODE_A_INA226_TIMEOUT_MS                  10000UL

/* --- SPI3 / secondary display ----------------------------------------------
 * The read-only status screen is the only SPI3 user.  SPI3 hangs off PCLK1 and
 * keeps its default (no-remap) pins PB3/PB5, so BR = 0b000 divides 36 MHz by
 * two: the same 18 MHz the primary screen reaches from PCLK2 / 4.  PB3 is
 * JTDO, released by the SWJ_NOJTAG setting HAL_MspInit() already applies while
 * keeping SWD on PA13/PA14. */
#define NODE_A_DISPLAY_BR_FIELD                       0UL
#define NODE_A_DISPLAY_SPI_DIVIDER \
  (1UL << (NODE_A_DISPLAY_BR_FIELD + 1UL))
#define NODE_A_DISPLAY_SPI_HZ \
  (NODE_A_PCLK1_HZ / NODE_A_DISPLAY_SPI_DIVIDER)
#define NODE_A_DISPLAY_SPI_MAX_HZ               18000000UL

/* --- Interrupt priorities --------------------------------------------------
 * USART2 (ESP-01 downlink) must be able to preempt the fan tach EXTI handler so
 * a command burst cannot lose a received byte.  The display DMA yields to both
 * - a late frame is a cosmetic cost, a lost tachometer edge is not - and the
 * HAL tick stays lowest. */
#define NODE_A_ESP_IRQ_PRIORITY                       1U
#define NODE_A_TACH_IRQ_PRIORITY                      2U
#define NODE_A_DISPLAY_IRQ_PRIORITY                   3U

_Static_assert(NODE_A_HSE_HZ == 8000000UL,
               "the CTRL-01 board fits an 8 MHz HSE");
_Static_assert((NODE_A_HSE_HZ * NODE_A_PLL_MULTIPLIER) == 72000000UL,
               "HSE x PLL must produce a 72 MHz SYSCLK");
_Static_assert(NODE_A_SYSCLK_HZ == 72000000UL,
               "Node A SYSCLK must be 72 MHz");
_Static_assert(NODE_A_HCLK_HZ == NODE_A_SYSCLK_HZ,
               "AHB must run at SYSCLK");
_Static_assert(RCC_SYSCLK_DIV1 == RCC_CFGR_HPRE_DIV1,
               "AHB prescaler selection must stay /1");
_Static_assert((RCC_HCLK_DIV2 >> RCC_CFGR_PPRE1_Pos) == 0x4UL,
               "APB1 prescaler encoding must stay /2");
_Static_assert((RCC_HCLK_DIV1 >> RCC_CFGR_PPRE2_Pos) == 0x0UL,
               "APB2 prescaler encoding must stay /1");
_Static_assert(NODE_A_PCLK1_HZ == 36000000UL,
               "Node A APB1 must be 36 MHz");
_Static_assert(NODE_A_PCLK2_HZ == 72000000UL,
               "Node A APB2 must be 72 MHz");
_Static_assert(NODE_A_APB1_TIMER_HZ == 72000000UL,
               "APB1 timers must keep the x2 boost at 72 MHz");
_Static_assert(RCC_HSE_PREDIV_DIV1 == 0x0UL,
               "HSE predivider /1 encoding changed");
_Static_assert(NODE_A_FLASH_LATENCY == NODE_A_FLASH_WAIT_STATES,
               "FLASH_LATENCY_2 must encode two wait states");
_Static_assert(NODE_A_FLASH_WAIT_STATES == 2UL,
               "72 MHz needs two FLASH wait states");
_Static_assert((1000UL / HAL_TICK_FREQ_DEFAULT) == NODE_A_HAL_TICK_HZ,
               "the HAL tick must stay 1 kHz");
_Static_assert(NODE_A_SYSTICK_RELOAD == 71999UL,
               "SysTick must reload from the 72 MHz HCLK");

_Static_assert(NODE_A_UART_BRR(NODE_A_PCLK2_HZ) == 7500UL,
               "USART1 BRR must stay 7500 at 72 MHz / 9600 baud");
_Static_assert(NODE_A_UART_BRR(NODE_A_PCLK1_HZ) == 3750UL,
               "USART2 BRR must stay 3750 at 36 MHz / 9600 baud");
_Static_assert((NODE_A_PCLK2_HZ % NODE_A_UART_BRR(NODE_A_PCLK2_HZ)) == 0UL,
               "USART1 must keep zero baud error");
_Static_assert((NODE_A_PCLK1_HZ % NODE_A_UART_BRR(NODE_A_PCLK1_HZ)) == 0UL,
               "USART2 must keep zero baud error");

_Static_assert(NODE_A_ADC_CLOCK_DIVIDER == 6UL,
               "ADC prescaler must stay PCLK2 / 6");
_Static_assert(NODE_A_ADC_CLOCK_HZ == 12000000UL,
               "Node A ADC clock must be 12 MHz");
_Static_assert(NODE_A_ADC_CLOCK_HZ <= NODE_A_ADC_MAX_CLOCK_HZ,
               "ADC clock must never exceed 12 MHz");
_Static_assert(ADC_SAMPLETIME_239CYCLES_5 == NODE_A_ADC_SAMPLE_TIME_CODE,
               "ADC sampling time encoding must stay 239.5 cycles");
_Static_assert(NODE_A_ADC_CONVERSION_NS == 21000ULL,
               "one 12-bit conversion must take 21 us at 12 MHz");
_Static_assert(NODE_A_GAS_ADC_POLL_TIMEOUT_MS >
               (NODE_A_ADC_CONVERSION_NS / 1000000ULL),
               "the ADC poll timeout must exceed one conversion");

_Static_assert(NODE_A_FAN_PWM_TIMER_HZ == NODE_A_FAN_PWM_HZ,
               "fan timer must produce exactly 25 kHz");
_Static_assert(NODE_A_FAN_PWM_HZ == 25000UL,
               "fan PWM must remain 25 kHz");
_Static_assert(NODE_A_FAN_TIMER_CLOCK_HZ == NODE_A_APB1_TIMER_HZ,
               "the fan timer must keep the 72 MHz APB1 timer clock");
_Static_assert(NODE_A_FAN_TIMER_PERIOD <= 0xFFFFUL,
               "the fan timer period must fit TIM4 ARR");
_Static_assert(NODE_A_FAN_PWM_RESOLUTION >= 100UL,
               "the fan PWM must resolve every commanded percent");

_Static_assert(NODE_A_WS2812_SPI_HZ == 4500000UL,
               "WS2812 SPI must stay at 4.5 MHz");
_Static_assert(NODE_A_WS2812_SPI_HZ >= 4000000UL &&
               NODE_A_WS2812_SPI_HZ <= 5000000UL,
               "WS2812 SPI clock must remain in the timing window");
_Static_assert(NODE_A_WS2812_ZERO_PATTERN == 0x20U,
               "WS2812 zero symbol must stay 100000");
_Static_assert(NODE_A_WS2812_ONE_PATTERN == 0x3CU,
               "WS2812 one symbol must stay 111100");
_Static_assert(NODE_A_WS2812_CELL_NS >= 650ULL &&
               NODE_A_WS2812_CELL_NS <= 1850ULL,
               "WS2812 cell must stay inside the 1.25 us +-600 ns window");
_Static_assert(NODE_A_WS2812_ZERO_HIGH_NS >= 200ULL,
               "WS2812 zero high pulse must clear the 0.35 us -150 ns minimum");
_Static_assert(NODE_A_WS2812_ONE_HIGH_NS >= 750ULL &&
               NODE_A_WS2812_ONE_HIGH_NS <= 1050ULL,
               "WS2812 one high pulse must stay in the 0.9 us +-150 ns window");
_Static_assert(NODE_A_WS2812_ONE_LOW_NS >= 250ULL &&
               NODE_A_WS2812_ONE_LOW_NS <= 550ULL,
               "WS2812 one low pulse must stay in the 0.35 us +-150 ns window");
_Static_assert(NODE_A_WS2812_ONE_HIGH_NS > NODE_A_WS2812_ZERO_HIGH_NS,
               "a one must be distinguishable from a zero by its high time");
_Static_assert(NODE_A_WS2812_ZERO_LOW_NS > NODE_A_WS2812_ONE_HIGH_NS,
               "a zero must remain longer low than a one is high");

_Static_assert(NODE_A_SHT30_WORST_CASE_MS == 401UL,
               "the SHT30 fixed-delay budget must stay 401 ms");
_Static_assert(NODE_A_SHT30_TIMEOUT_MS > NODE_A_SHT30_WORST_CASE_MS,
               "the SHT30 deadline must never cut a healthy read");
_Static_assert(NODE_A_SHT30_MEASUREMENT_DELAY_MS < NODE_A_SHT30_TIMEOUT_MS,
               "the conversion delay must fit inside the deadline");
_Static_assert(NODE_A_INA226_SAMPLE_COUNT == 3UL,
               "the median-of-three filter reads exactly three samples");
_Static_assert(NODE_A_INA226_SETTLE_BUDGET_MS == 336UL,
               "the INA226 settle budget must stay 336 ms");
_Static_assert(NODE_A_INA226_WORST_CASE_MS == 8328UL,
               "the INA226 worst case must stay 8328 ms");
_Static_assert(NODE_A_INA226_TIMEOUT_MS > NODE_A_INA226_WORST_CASE_MS,
               "the INA226 deadline must never cut a healthy transfer");
_Static_assert(NODE_A_SOFT_I2C_DELAY_MS > 0UL,
               "the software I2C delay must advance the deadline");

_Static_assert(NODE_A_DISPLAY_SPI_HZ == 18000000UL,
               "the secondary display must run at 18 MHz");
_Static_assert(NODE_A_DISPLAY_SPI_HZ <= NODE_A_DISPLAY_SPI_MAX_HZ,
               "SPI3 must never clock a 36 MHz PCLK1 faster than /2");
_Static_assert(NODE_A_DISPLAY_BR_FIELD == 0UL,
               "18 MHz from a 36 MHz PCLK1 needs BR = 0b000");

_Static_assert(NODE_A_ESP_IRQ_PRIORITY < NODE_A_TACH_IRQ_PRIORITY,
               "USART2 must preempt the tach EXTI handler");
_Static_assert(NODE_A_TACH_IRQ_PRIORITY < NODE_A_DISPLAY_IRQ_PRIORITY,
               "the fan tach handler must preempt the display DMA");
_Static_assert(NODE_A_DISPLAY_IRQ_PRIORITY < TICK_INT_PRIORITY,
               "the display DMA must preempt the HAL tick");

#endif
