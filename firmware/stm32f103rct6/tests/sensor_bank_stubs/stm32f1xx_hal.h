#ifndef SENSOR_BANK_TEST_HAL_H
#define SENSOR_BANK_TEST_HAL_H
#include <stdint.h>
typedef struct {uint32_t unused;} GPIO_TypeDef;
extern GPIO_TypeDef bank_gpio_a, bank_gpio_b, bank_gpio_c;
#define GPIOA (&bank_gpio_a)
#define GPIOB (&bank_gpio_b)
#define GPIOC (&bank_gpio_c)
#define GPIO_PIN_0 1U
#define GPIO_PIN_1 2U
#define GPIO_PIN_2 4U
#define GPIO_PIN_3 8U
#define GPIO_PIN_4 16U
#define GPIO_PIN_5 32U
#define GPIO_PIN_6 64U
#define GPIO_PIN_7 128U
#define GPIO_PIN_8 256U
#define GPIO_PIN_9 512U
#define GPIO_PIN_10 1024U
#define GPIO_PIN_11 2048U
#define GPIO_PIN_12 4096U
#define GPIO_PIN_13 8192U
#define GPIO_PIN_14 16384U
#define ADC_CHANNEL_0 0U
#define ADC_CHANNEL_1 1U
#define ADC_CHANNEL_4 4U
#define ADC_CHANNEL_5 5U
#define ADC_CHANNEL_6 6U
#define ADC_CHANNEL_8 8U
#define ADC_CHANNEL_9 9U
#define ADC_CHANNEL_11 11U
#define ADC_CHANNEL_12 12U
#define ADC_CHANNEL_13 13U
#define ADC_REGULAR_RANK_1 1U
#define ADC_SAMPLETIME_239CYCLES_5 239U
#define HAL_OK 0
typedef enum {GPIO_PIN_RESET=0,GPIO_PIN_SET=1} GPIO_PinState;
typedef struct {void *Instance;} ADC_HandleTypeDef;
typedef struct {uint32_t Channel,Rank,SamplingTime;} ADC_ChannelConfTypeDef;
static inline int HAL_ADC_ConfigChannel(ADC_HandleTypeDef *a,ADC_ChannelConfTypeDef *c){(void)a;(void)c;return 1;}
static inline int HAL_ADC_Start(ADC_HandleTypeDef *a){(void)a;return 1;}
static inline int HAL_ADC_PollForConversion(ADC_HandleTypeDef *a,uint32_t t){(void)a;(void)t;return 1;}
static inline uint32_t HAL_ADC_GetValue(ADC_HandleTypeDef *a){(void)a;return 0;}
static inline int HAL_ADC_Stop(ADC_HandleTypeDef *a){(void)a;return 0;}
static inline GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *p,uint16_t n){(void)p;(void)n;return GPIO_PIN_SET;}
#endif
