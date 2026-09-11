#include "joystick.h"

#include "main.h"

#define JOYSTICK_CALIBRATION_SAMPLES 16U
#define JOYSTICK_CENTER_DEFAULT 2048U
#define JOYSTICK_DEAD_ZONE 500
#define JOYSTICK_HYSTERESIS 100
#define JOYSTICK_SAMPLE_PERIOD_MS 5U
#define JOYSTICK_SWITCH_DEBOUNCE_MS 25U
#define JOYSTICK_LONG_PRESS_MS 1000U
#define JOYSTICK_REPEAT_DELAY_MS 350U
#define JOYSTICK_REPEAT_PERIOD_MS 100U
#define JOYSTICK_CALIBRATION_TIMEOUT_MS (JOYSTICK_SAMPLE_PERIOD_MS * 2U)

typedef struct {
  uint16_t center_x;
  uint16_t center_y;
  UiInputEvent active_direction;
  uint32_t direction_started_ms;
  uint32_t direction_event_ms;
  uint8_t stable_released;
  uint8_t candidate_released;
  uint32_t switch_changed_ms;
  uint32_t press_started_ms;
  uint8_t long_press_sent;
} JoystickDecoder;

static ADC_HandleTypeDef joystick_adc;
static TIM_HandleTypeDef joystick_timer;
static JoystickDecoder joystick_decoder;
static JoystickDecoder joystick_test_decoder;
static volatile uint16_t joystick_dma_samples[4];
static volatile uint8_t joystick_dma_sample_index;
static volatile uint8_t joystick_dma_sample_ready;
static uint8_t joystick_calibrated;
static uint32_t joystick_last_sample_ms;

static uint32_t JoystickTimerClockHz(void)
{
  uint32_t timer_clock = HAL_RCC_GetPCLK1Freq();

  if ((RCC->CFGR & RCC_CFGR_PPRE1) != 0U) timer_clock *= 2U;
  return timer_clock;
}

static int32_t Absolute(int32_t value)
{
  return (value < 0) ? -value : value;
}

static uint8_t Elapsed(uint32_t now_ms, uint32_t then_ms, uint32_t duration_ms)
{
  return ((uint32_t)(now_ms - then_ms) >= duration_ms) ? 1U : 0U;
}

static void DecoderReset(JoystickDecoder *decoder, uint16_t center_x, uint16_t center_y)
{
  decoder->center_x = center_x;
  decoder->center_y = center_y;
  decoder->active_direction = UI_EVT_NONE;
  decoder->direction_started_ms = 0U;
  decoder->direction_event_ms = 0U;
  decoder->stable_released = 1U;
  decoder->candidate_released = 1U;
  decoder->switch_changed_ms = 0U;
  decoder->press_started_ms = 0U;
  decoder->long_press_sent = 0U;
}

static UiInputEvent DirectionForSample(const JoystickDecoder *decoder, uint16_t x, uint16_t y)
{
  const int32_t delta_x = (int32_t)x - (int32_t)decoder->center_x;
  const int32_t delta_y = (int32_t)y - (int32_t)decoder->center_y;
  const int32_t absolute_x = Absolute(delta_x);
  const int32_t absolute_y = Absolute(delta_y);

  if ((absolute_x <= JOYSTICK_DEAD_ZONE) && (absolute_y <= JOYSTICK_DEAD_ZONE)) return UI_EVT_NONE;
  if (absolute_x >= absolute_y) return (delta_x > 0) ? UI_EVT_RIGHT : UI_EVT_LEFT;
  return (delta_y < 0) ? UI_EVT_UP : UI_EVT_DOWN;
}

static uint8_t DirectionStillEngaged(const JoystickDecoder *decoder, uint16_t x, uint16_t y)
{
  const int32_t release_threshold = JOYSTICK_DEAD_ZONE - JOYSTICK_HYSTERESIS;
  const int32_t delta_x = (int32_t)x - (int32_t)decoder->center_x;
  const int32_t delta_y = (int32_t)y - (int32_t)decoder->center_y;

  switch (decoder->active_direction) {
    case UI_EVT_RIGHT: return (delta_x >= release_threshold) ? 1U : 0U;
    case UI_EVT_LEFT: return (delta_x <= -release_threshold) ? 1U : 0U;
    case UI_EVT_UP: return (delta_y <= -release_threshold) ? 1U : 0U;
    case UI_EVT_DOWN: return (delta_y >= release_threshold) ? 1U : 0U;
    default: return 0U;
  }
}

static UiInputEvent DecodeSample(JoystickDecoder *decoder, uint16_t x, uint16_t y,
                                 uint8_t switch_released, uint32_t now_ms)
{
  UiInputEvent direction;

  switch_released = switch_released ? 1U : 0U;
  if (switch_released != decoder->candidate_released) {
    decoder->candidate_released = switch_released;
    decoder->switch_changed_ms = now_ms;
  }

  if ((decoder->stable_released != decoder->candidate_released) &&
      Elapsed(now_ms, decoder->switch_changed_ms, JOYSTICK_SWITCH_DEBOUNCE_MS)) {
    decoder->stable_released = decoder->candidate_released;
    if (decoder->stable_released == 0U) {
      decoder->press_started_ms = now_ms;
      decoder->long_press_sent = 0U;
    } else if (decoder->long_press_sent == 0U) {
      return UI_EVT_PRESS;
    }
    decoder->long_press_sent = 0U;
  }

  if ((decoder->stable_released == 0U) && (decoder->long_press_sent == 0U) &&
      Elapsed(now_ms, decoder->press_started_ms, JOYSTICK_LONG_PRESS_MS)) {
    decoder->long_press_sent = 1U;
    return UI_EVT_LONG_PRESS;
  }

  direction = DirectionStillEngaged(decoder, x, y) ? decoder->active_direction :
              DirectionForSample(decoder, x, y);
  if (direction != decoder->active_direction) {
    decoder->active_direction = direction;
    decoder->direction_started_ms = now_ms;
    decoder->direction_event_ms = now_ms;
    return direction;
  }

  if (((direction == UI_EVT_UP) || (direction == UI_EVT_DOWN)) &&
      Elapsed(now_ms, decoder->direction_started_ms, JOYSTICK_REPEAT_DELAY_MS) &&
      Elapsed(now_ms, decoder->direction_event_ms, JOYSTICK_REPEAT_PERIOD_MS)) {
    decoder->direction_event_ms = now_ms;
    return direction;
  }

  return UI_EVT_NONE;
}

void Joystick_Init(void)
{
  ADC_ChannelConfTypeDef configuration = {0};
  GPIO_InitTypeDef gpio = {0};
  RCC_PeriphCLKInitTypeDef peripheral_clock = {0};
  const uint32_t timer_clock = JoystickTimerClockHz();

  /* The joystick module's pin marked "+5V" is wired to 3.3 V only; its
   * potentiometer outputs must never exceed the ADC reference. */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1;
  gpio.Mode = GPIO_MODE_ANALOG;
  HAL_GPIO_Init(GPIOC, &gpio);
  gpio.Pin = GPIO_PIN_4;
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOC, &gpio);

  peripheral_clock.PeriphClockSelection = RCC_PERIPHCLK_ADC;
  peripheral_clock.AdcClockSelection = RCC_ADCPCLK2_DIV6;
  if (HAL_RCCEx_PeriphCLKConfig(&peripheral_clock) != HAL_OK) {
    joystick_calibrated = 0U;
    return;
  }

  if (timer_clock < 10000U) {
    joystick_calibrated = 0U;
    return;
  }
  __HAL_RCC_TIM3_CLK_ENABLE();
  joystick_timer.Instance = TIM3;
  joystick_timer.Init.Prescaler = (timer_clock / 10000U) - 1U;
  joystick_timer.Init.CounterMode = TIM_COUNTERMODE_UP;
  joystick_timer.Init.Period = 49U;
  joystick_timer.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  joystick_timer.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&joystick_timer) != HAL_OK) {
    joystick_calibrated = 0U;
    return;
  }
  joystick_timer.Instance->CR2 = (joystick_timer.Instance->CR2 & ~TIM_CR2_MMS) | TIM_TRGO_UPDATE;

  joystick_adc.Instance = ADC1;
  joystick_adc.Init.ScanConvMode = ADC_SCAN_ENABLE;
  joystick_adc.Init.ContinuousConvMode = DISABLE;
  joystick_adc.Init.DiscontinuousConvMode = DISABLE;
  joystick_adc.Init.ExternalTrigConv = ADC_EXTERNALTRIGCONV_T3_TRGO;
  joystick_adc.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  joystick_adc.Init.NbrOfConversion = 2U;
  if (HAL_ADC_Init(&joystick_adc) != HAL_OK) {
    joystick_calibrated = 0U;
    return;
  }
  configuration.Channel = ADC_CHANNEL_10;
  configuration.Rank = ADC_REGULAR_RANK_1;
  configuration.SamplingTime = ADC_SAMPLETIME_239CYCLES_5;
  if (HAL_ADC_ConfigChannel(&joystick_adc, &configuration) != HAL_OK) {
    joystick_calibrated = 0U;
    return;
  }
  configuration.Channel = ADC_CHANNEL_11;
  configuration.Rank = ADC_REGULAR_RANK_2;
  if ((HAL_ADC_ConfigChannel(&joystick_adc, &configuration) != HAL_OK) ||
      (HAL_ADCEx_Calibration_Start(&joystick_adc) != HAL_OK) ||
      (HAL_ADC_Start_DMA(&joystick_adc, (uint32_t *)joystick_dma_samples,
                         sizeof(joystick_dma_samples) / sizeof(joystick_dma_samples[0])) != HAL_OK)) {
    joystick_calibrated = 0U;
    return;
  }
  if (HAL_TIM_Base_Start(&joystick_timer) != HAL_OK) {
    (void)HAL_ADC_Stop_DMA(&joystick_adc);
    joystick_calibrated = 0U;
    return;
  }

  DecoderReset(&joystick_decoder, JOYSTICK_CENTER_DEFAULT, JOYSTICK_CENTER_DEFAULT);
  Joystick_Calibrate();
}

void Joystick_Calibrate(void)
{
  uint32_t sum_x = 0U;
  uint32_t sum_y = 0U;
  uint8_t sample_index;
  uint32_t deadline;
  uint8_t sample;

  joystick_calibrated = 0U;
  for (sample = 0U; sample < JOYSTICK_CALIBRATION_SAMPLES; ++sample) {
    deadline = HAL_GetTick();
    while ((joystick_dma_sample_ready == 0U) &&
           (Elapsed(HAL_GetTick(), deadline, JOYSTICK_CALIBRATION_TIMEOUT_MS) == 0U)) { }
    if (joystick_dma_sample_ready == 0U) return;
    joystick_dma_sample_ready = 0U;
    sample_index = joystick_dma_sample_index;
    sum_x += joystick_dma_samples[sample_index];
    sum_y += joystick_dma_samples[sample_index + 1U];
  }
  DecoderReset(&joystick_decoder, (uint16_t)(sum_x / JOYSTICK_CALIBRATION_SAMPLES),
               (uint16_t)(sum_y / JOYSTICK_CALIBRATION_SAMPLES));
  joystick_last_sample_ms = HAL_GetTick();
  joystick_calibrated = 1U;
}

UiInputEvent Joystick_ProcessSample(uint16_t x, uint16_t y, uint8_t switch_released,
                                    uint32_t now_ms)
{
  return DecodeSample(&joystick_decoder, x, y, switch_released, now_ms);
}

void Joystick_TestReset(uint16_t center_x, uint16_t center_y)
{
  DecoderReset(&joystick_test_decoder, center_x, center_y);
}

UiInputEvent Joystick_TestProcessSample(uint16_t x, uint16_t y, uint8_t switch_released,
                                        uint32_t now_ms)
{
  return DecodeSample(&joystick_test_decoder, x, y, switch_released, now_ms);
}

UiInputEvent Joystick_Poll(uint32_t now_ms)
{
  uint8_t sample_index;
  const uint8_t switch_released =
      (HAL_GPIO_ReadPin(GPIOC, GPIO_PIN_4) == GPIO_PIN_SET) ? 1U : 0U;

  if ((joystick_calibrated == 0U) ||
      (Elapsed(now_ms, joystick_last_sample_ms, JOYSTICK_SAMPLE_PERIOD_MS) == 0U)) return UI_EVT_NONE;
  joystick_last_sample_ms = now_ms;
  if (joystick_dma_sample_ready == 0U) return UI_EVT_NONE;
  joystick_dma_sample_ready = 0U;
  sample_index = joystick_dma_sample_index;
  return Joystick_ProcessSample(joystick_dma_samples[sample_index],
                                joystick_dma_samples[sample_index + 1U], switch_released, now_ms);
}

void Joystick_DmaIrqHandler(void)
{
  HAL_DMA_IRQHandler(joystick_adc.DMA_Handle);
}

void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc->Instance != ADC1) return;
  joystick_dma_sample_index = 0U;
  joystick_dma_sample_ready = 1U;
}

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc->Instance != ADC1) return;
  joystick_dma_sample_index = 2U;
  joystick_dma_sample_ready = 1U;
}
