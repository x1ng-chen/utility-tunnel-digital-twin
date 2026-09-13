#ifndef NODE_A_CLOCK_CONTRACT_H
#define NODE_A_CLOCK_CONTRACT_H

/* CTRL-01 clock/peripheral contract. The board's 8 MHz HSE is multiplied by
 * nine; APB1 is divided by two while its timer clocks retain the x2 boost. */
#define NODE_A_HSE_HZ                         8000000UL
#define NODE_A_PLL_MULTIPLIER                       9UL
#define NODE_A_SYSCLK_HZ                     72000000UL
#define NODE_A_HCLK_HZ                       NODE_A_SYSCLK_HZ
#define NODE_A_PCLK1_HZ                      36000000UL
#define NODE_A_PCLK2_HZ                      72000000UL
#define NODE_A_APB1_TIMER_HZ                 72000000UL

#define NODE_A_ADC_CLOCK_DIVIDER                    6UL
#define NODE_A_ADC_CLOCK_HZ             (NODE_A_PCLK2_HZ / NODE_A_ADC_CLOCK_DIVIDER)

#define NODE_A_FAN_PWM_HZ                         25000UL
#define NODE_A_FAN_TIMER_PRESCALER                    0UL
#define NODE_A_FAN_TIMER_PERIOD                    2879UL

#define NODE_A_UART_BAUD                           9600UL

/* SHT30 high-repeatability conversion and its bounded read timeout. */
#define NODE_A_SHT30_MEASUREMENT_DELAY_MS             20UL
#define NODE_A_SHT30_TIMEOUT_MS                     100UL
#define NODE_A_SOFT_I2C_DELAY_MS                      1UL

/* PCLK1 / 8 = 4.5 MHz; six SPI bits form a 1.333 us WS2812 cell. */
#define NODE_A_WS2812_SPI_DIVIDER                    8UL
#define NODE_A_WS2812_SPI_HZ             (NODE_A_PCLK1_HZ / NODE_A_WS2812_SPI_DIVIDER)
#define NODE_A_WS2812_BITS_PER_DATA_BIT               6UL
#define NODE_A_WS2812_ZERO_PATTERN                 0x20U /* 100000 */
#define NODE_A_WS2812_ONE_PATTERN                  0x3CU /* 111100 */
#define NODE_A_WS2812_CELL_NS \
  ((NODE_A_WS2812_BITS_PER_DATA_BIT * 1000000000ULL) / NODE_A_WS2812_SPI_HZ)

_Static_assert((NODE_A_HSE_HZ * NODE_A_PLL_MULTIPLIER) == NODE_A_SYSCLK_HZ,
               "PLL/HSE must produce a 72 MHz SYSCLK");
_Static_assert(NODE_A_HCLK_HZ == NODE_A_SYSCLK_HZ,
               "AHB must run at SYSCLK");
_Static_assert(NODE_A_PCLK1_HZ == (NODE_A_HCLK_HZ / 2UL),
               "APB1 must be divided by two");
_Static_assert(NODE_A_PCLK2_HZ == NODE_A_HCLK_HZ,
               "APB2 must run at HCLK");
_Static_assert(NODE_A_ADC_CLOCK_HZ <= 12000000UL,
               "ADC clock must not exceed 12 MHz");
_Static_assert(((NODE_A_APB1_TIMER_HZ /
                 (NODE_A_FAN_TIMER_PRESCALER + 1UL)) /
                (NODE_A_FAN_TIMER_PERIOD + 1UL)) == NODE_A_FAN_PWM_HZ,
               "fan timer must produce 25 kHz PWM");
_Static_assert(NODE_A_WS2812_SPI_HZ >= 4000000UL &&
               NODE_A_WS2812_SPI_HZ <= 5000000UL,
               "WS2812 SPI clock must remain in the timing window");
_Static_assert(NODE_A_WS2812_CELL_NS >= 1200UL &&
               NODE_A_WS2812_CELL_NS <= 1400UL,
               "WS2812 encoded cell must remain in the timing window");

#endif
