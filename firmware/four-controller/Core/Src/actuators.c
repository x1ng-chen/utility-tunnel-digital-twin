#include "actuators.h"
#include "board_config.h"
#include "board_io.h"
#include "release_profile.h"
#include "../../common/measurements.h"
#include "stm32f1xx_hal.h"
#include <string.h>

void Error_Handler(void);

/* 2/4 号：风机 PWM 与继电器。
 * 2 号的 PB8 让给屏幕 CS，风机 2 改用 PB1 / TIM3_CH4；
 * 4 号仍用 PB8 / TIM4_CH3。 */
#if BOARD_ID == 2
#define FAN_PWM_PIN          GPIO_PIN_1
#define FAN_PWM_PORT         GPIOB
#define FAN_TIMER            TIM3
#define FAN_TIMER_CLK()      __HAL_RCC_TIM3_CLK_ENABLE()
#define FAN_CCR              TIM3->CCR4
#define FAN_CCMR2_OC_MODE    (TIM_CCMR2_OC4M_1 | TIM_CCMR2_OC4M_2 | TIM_CCMR2_OC4PE)
#define FAN_CCER_ENABLE      TIM_CCER_CC4E
#else
#define FAN_PWM_PIN          GPIO_PIN_8
#define FAN_PWM_PORT         GPIOB
#define FAN_TIMER            TIM4
#define FAN_TIMER_CLK()      __HAL_RCC_TIM4_CLK_ENABLE()
#define FAN_CCR              TIM4->CCR3
#define FAN_CCMR2_OC_MODE    (TIM_CCMR2_OC3M_1 | TIM_CCMR2_OC3M_2 | TIM_CCMR2_OC3PE)
#define FAN_CCER_ENABLE      TIM_CCER_CC3E
#endif
#define FAN_TACH_PIN         GPIO_PIN_7
#define FAN_TACH_PORT        GPIOA
#define RELAY_PIN            GPIO_PIN_1
#define RELAY_PORT           GPIOA
#define FAN_PWM_TIMER_PERIOD 319U      /* 8 MHz / 320 = 25 kHz */
#ifndef FAN_PULSES_PER_REV
#define FAN_PULSES_PER_REV 2U
#endif
#ifndef FAN_TACH_VERIFIED
#define FAN_TACH_VERIFIED 0
#endif
#ifndef INA_SHUNT_MICROOHMS
#define INA_SHUNT_MICROOHMS 100000U
#endif
#ifndef INA_CURRENT_LSB_UA
#define INA_CURRENT_LSB_UA 10U
#endif
#ifndef INA_CALIBRATION_VERIFIED
#define INA_CALIBRATION_VERIFIED 0
#endif
_Static_assert(FAN_PULSES_PER_REV>0,"Fan PPR must be positive");
_Static_assert(INA_SHUNT_MICROOHMS>0 && INA_CURRENT_LSB_UA>0,"INA calibration must be positive");

/* 3 号：蜂鸣器与灯带 */
#define BUZZER_PIN           GPIO_PIN_0
#define BUZZER_PORT          GPIOB
#define LED_PIN              GPIO_PIN_15
#define LED_PORT             GPIOB
#define LED_COUNT            18U

/* INA226（2/4 号） */
#define INA_ADDRESS          0x40U
#define INA_REG_CONFIG       0x00U
#define INA_REG_SHUNT        0x01U
#define INA_REG_BUS          0x02U
#define INA_REG_POWER        0x03U
#define INA_REG_CURRENT      0x04U
#define INA_REG_CALIBRATION  0x05U
#define INA_REG_MANUFACTURER 0xFEU
#define INA_REG_DIE          0xFFU
#define INA_MANUFACTURER_ID  0x5449U
#define INA_DIE_ID           0x2260U
#define INA_CONFIG           0x4527U
#define INA_CALIBRATION ((uint16_t)(5120000000ULL / ((uint64_t)INA_CURRENT_LSB_UA * INA_SHUNT_MICROOHMS)))
_Static_assert(5120000000ULL/((uint64_t)INA_CURRENT_LSB_UA*INA_SHUNT_MICROOHMS)>0U &&
  5120000000ULL/((uint64_t)INA_CURRENT_LSB_UA*INA_SHUNT_MICROOHMS)<=65535U,"INA CAL outside register range");
_Static_assert(INA_CURRENT_LSB_UA<=1000U,"INA current/power scaling exceeds int32 range");

static ActuatorFeedback feedback;
static uint32_t feedback_at;
static uint8_t fan_percent;
static uint8_t relay_on;
static volatile uint32_t tach_pulses;
static uint32_t tach_last_pulses;
static uint32_t tach_last_at;
static uint8_t led_encoded[LED_COUNT * 15U];

void EXTI9_5_IRQHandler(void)
{
  HAL_GPIO_EXTI_IRQHandler(FAN_TACH_PIN);
}

void HAL_GPIO_EXTI_Callback(uint16_t gpio_pin)
{
  if (gpio_pin == FAN_TACH_PIN) ++tach_pulses;
}

static void Ws2812_Send(uint8_t red, uint8_t green, uint8_t blue)
{
  uint8_t *cursor = led_encoded;
  uint8_t pending = 0U;
  uint8_t pending_bits = 0U;
  uint8_t pixel;

  if (!board_config.has_led) return;
  for (pixel = 0U; pixel < LED_COUNT; ++pixel)
  {
    ut_ws_encode_byte(green, &cursor, &pending, &pending_bits);
    ut_ws_encode_byte(red, &cursor, &pending, &pending_bits);
    ut_ws_encode_byte(blue, &cursor, &pending, &pending_bits);
  }
  if (pending_bits != 0U) { *cursor++ = pending; }

  uint32_t deadline=HAL_GetTick();
  while ((SPI2->SR & SPI_SR_TXE) == 0U) { if((uint32_t)(HAL_GetTick()-deadline)>2U)goto fail; }
  *(__IO uint8_t *)&SPI2->DR = 0U;
  while ((SPI2->SR & SPI_SR_BSY) != 0U) { if((uint32_t)(HAL_GetTick()-deadline)>5U)goto fail; }
  (void)SPI2->DR;

  DMA1_Channel5->CCR = 0U;
  DMA1_Channel5->CNDTR = (uint32_t)(cursor - led_encoded);
  DMA1_Channel5->CPAR = (uint32_t)&SPI2->DR;
  DMA1_Channel5->CMAR = (uint32_t)led_encoded;
  DMA1_Channel5->CCR = DMA_CCR_DIR | DMA_CCR_MINC | DMA_CCR_PL_1;
  SPI2->CR2 |= SPI_CR2_TXDMAEN;
  DMA1_Channel5->CCR |= DMA_CCR_EN;
  while (DMA1_Channel5->CNDTR != 0U) { if((uint32_t)(HAL_GetTick()-deadline)>5U)goto fail; }
  while ((SPI2->SR & SPI_SR_BSY) != 0U) { if((uint32_t)(HAL_GetTick()-deadline)>5U)goto fail; }
  DMA1_Channel5->CCR = 0U;
  SPI2->CR2 &= ~SPI_CR2_TXDMAEN;
  (void)SPI2->DR;
  HAL_Delay(1U); /* Reset low >50 us; IRQs remain enabled. */
  feedback.output_fault=0U;
  return;
fail:
  DMA1_Channel5->CCR=0U;SPI2->CR2 &= ~SPI_CR2_TXDMAEN;
  feedback.output_fault=1U;
}

static void FanPwm_Set(uint8_t percent)
{
  uint32_t counts;
  if (percent > 100U) percent = 100U;
  fan_percent = percent;
  /* 经外部 NPN 驱动，MCU 波形反相：晶体管截止=风机端高电平=运行。 */
  counts = ((uint32_t)(FAN_PWM_INVERTED?100U-percent:percent) * (FAN_PWM_TIMER_PERIOD + 1U) + 50U) / 100U;
  FAN_CCR = counts;
}

void Actuators_Init(void)
{
  GPIO_InitTypeDef gpio = {0};
  feedback.rpm_quality=1U;feedback.ina_quality=1U;

  if (board_config.has_fan)
  {
    __HAL_RCC_AFIO_CLK_ENABLE();
    FAN_TIMER_CLK();
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();

    gpio.Pin = FAN_PWM_PIN;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(FAN_PWM_PORT, &gpio);

    FAN_TIMER->CR1 = 0U;
    FAN_TIMER->PSC = 0U;
    FAN_TIMER->ARR = FAN_PWM_TIMER_PERIOD;
    FAN_TIMER->CCMR2 = FAN_CCMR2_OC_MODE;
    FAN_TIMER->CCER = FAN_CCER_ENABLE;
    FanPwm_Set(0U);
    FAN_TIMER->EGR = TIM_EGR_UG;
    FAN_TIMER->CR1 = TIM_CR1_ARPE | TIM_CR1_CEN;

    gpio.Pin = FAN_TACH_PIN;
    gpio.Mode = GPIO_MODE_IT_RISING;
    gpio.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(FAN_TACH_PORT, &gpio);
    HAL_NVIC_SetPriority(EXTI9_5_IRQn, 3U, 0U);
    HAL_NVIC_EnableIRQ(EXTI9_5_IRQn);

    gpio.Pin = RELAY_PIN;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    /* Set the inactive latch before enabling the output driver. */
    HAL_GPIO_WritePin(RELAY_PORT,RELAY_PIN,RELAY_ACTIVE_HIGH?GPIO_PIN_RESET:GPIO_PIN_SET);
    HAL_GPIO_Init(RELAY_PORT, &gpio);
    relay_on = 0U;
    tach_last_at = HAL_GetTick();
  }

  if (board_config.has_buzzer)
  {
    __HAL_RCC_GPIOB_CLK_ENABLE();
    gpio.Pin = BUZZER_PIN;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(BUZZER_PORT, &gpio);
    HAL_GPIO_WritePin(BUZZER_PORT, BUZZER_PIN, GPIO_PIN_RESET);
  }

  if (board_config.has_led)
  {
    __HAL_RCC_DMA1_CLK_ENABLE();
    __HAL_RCC_SPI2_CLK_ENABLE();
    gpio.Pin = LED_PIN;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(LED_PORT, &gpio);
    SPI2->CR1 = SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI;
    SPI2->CR2 = 0U;
    SPI2->CR1 |= SPI_CR1_SPE;
    Ws2812_Send(0U, 0U, 0U);
  }

  if (board_config.has_fan)
  {
    uint16_t id = 0U;
    uint16_t die = 0U;
    /* 有 INA226 的板先尝试写配置，失败不影响启动。 */
    (void)BoardIo_I2cRead16(INA_ADDRESS, INA_REG_MANUFACTURER, &id);
    (void)BoardIo_I2cRead16(INA_ADDRESS, INA_REG_DIE, &die);
    if (id == INA_MANUFACTURER_ID)
    {
      (void)BoardIo_I2cWrite16(INA_ADDRESS, INA_REG_CONFIG, INA_CONFIG);
      (void)BoardIo_I2cWrite16(INA_ADDRESS, INA_REG_CALIBRATION, INA_CALIBRATION);
    }
  }
}

static uint32_t CalculateRpm(void);
void Actuators_Poll(uint32_t now)
{
  if(!board_config.has_fan || (uint32_t)(now-feedback_at)<1000U)return;
  feedback_at=now;
  feedback.rpm=CalculateRpm();feedback.rpm_at=now;
  feedback.rpm_quality=FAN_TACH_VERIFIED?0U:2U;
  if(feedback.rpm>200000U)feedback.rpm_quality=1U;
  InaReading reading;
  if(Actuators_ReadIna(&reading)) {
    feedback.ina=reading;feedback.ina_quality=reading.plausible?0U:2U;
  } else feedback.ina_quality=1U;
  feedback.ina_at=now;
}
const ActuatorFeedback *Actuators_Feedback(void) { return &feedback; }
uint32_t Actuators_FanRpm(void) { return feedback.rpm; }

void Actuators_SetFanPercent(uint8_t percent)
{
  if (board_config.has_fan) FanPwm_Set(percent);
}

uint8_t Actuators_FanPercent(void)
{
  return fan_percent;
}

static uint32_t CalculateRpm(void)
{
  uint32_t pulses;
  uint32_t elapsed;
  uint32_t delta;

  if (!board_config.has_fan) return 0U;
  uint32_t mask=__get_PRIMASK();__disable_irq();
  pulses = tach_pulses;
  uint32_t now=HAL_GetTick();
  __set_PRIMASK(mask);
  elapsed = now - tach_last_at;
  delta = pulses - tach_last_pulses;
  tach_last_pulses = pulses;
  tach_last_at = now;
  if (elapsed == 0U) return feedback.rpm;
  return ut_rpm(delta,elapsed,FAN_PULSES_PER_REV);
}

void Actuators_SetRelay(uint8_t on)
{
  if (!board_config.has_fan) return;
  relay_on = on ? 1U : 0U;
  HAL_GPIO_WritePin(RELAY_PORT, RELAY_PIN, (relay_on==RELAY_ACTIVE_HIGH)?GPIO_PIN_SET:GPIO_PIN_RESET);
}

uint8_t Actuators_RelayOn(void)
{
  return relay_on;
}

uint8_t Actuators_ReadIna(InaReading *out)
{
  uint16_t manufacturer;
  uint16_t die;
  uint16_t bus;
  uint16_t current;
  uint16_t power;
  uint16_t shunt,calibration;

  if ((out == NULL) || (!board_config.has_fan)) return 0U;
  memset(out, 0, sizeof(*out));
  if (!BoardIo_I2cRead16(INA_ADDRESS, INA_REG_MANUFACTURER, &manufacturer) ||
      (manufacturer != INA_MANUFACTURER_ID))
    return 0U;
  if (!BoardIo_I2cRead16(INA_ADDRESS, INA_REG_DIE, &die) ||
      ((die & 0xFFF0U) != INA_DIE_ID))
    return 0U;
  if (!BoardIo_I2cRead16(INA_ADDRESS, INA_REG_BUS, &bus) ||
      !BoardIo_I2cRead16(INA_ADDRESS, INA_REG_SHUNT, &shunt) ||
      !BoardIo_I2cRead16(INA_ADDRESS, INA_REG_CURRENT, &current) ||
      !BoardIo_I2cRead16(INA_ADDRESS, INA_REG_POWER, &power) ||
      !BoardIo_I2cRead16(INA_ADDRESS, INA_REG_CALIBRATION, &calibration))
    return 0U;

  out->bus_raw = bus;
  out->current_raw = (int16_t)current;
  out->power_raw = power;
  out->bus_millivolts = (uint32_t)bus * 1250UL / 1000UL;
  /* Do not zero measured current/power when the relay is commanded off. */
  out->current_microamps=ut_ina_current(current,INA_CURRENT_LSB_UA);
  out->power_microwatts=(int32_t)ut_ina_power(power,INA_CURRENT_LSB_UA);
  out->calibrated=(INA_CALIBRATION_VERIFIED && calibration==INA_CALIBRATION)?1U:0U;
  out->online = 1U;
  out->plausible = (out->bus_millivolts <= 18000UL) ? 1U : 0U;
  return 1U;
}

void Actuators_SetBuzzer(uint8_t on)
{
  if (!board_config.has_buzzer) return;
  HAL_GPIO_WritePin(BUZZER_PORT, BUZZER_PIN, on ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

void Actuators_SetLedColor(uint8_t red, uint8_t green, uint8_t blue)
{
  if (!board_config.has_led) return;
  Ws2812_Send(red, green, blue);
}
