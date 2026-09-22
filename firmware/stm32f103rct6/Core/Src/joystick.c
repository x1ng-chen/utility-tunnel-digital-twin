#include "joystick.h"
#include "main.h"

#define JOYSTICK_CALIBRATION_SAMPLES 16U
#define JOYSTICK_CENTER_DEFAULT 2048U
#define JOYSTICK_DEAD_ZONE 500
#define JOYSTICK_HYSTERESIS 100
#define JOYSTICK_SAMPLE_PERIOD_MS 10U
#define JOYSTICK_SWITCH_DEBOUNCE_MS 25U
#define JOYSTICK_LONG_PRESS_MS 1000U
#define JOYSTICK_REPEAT_DELAY_MS 350U
#define JOYSTICK_REPEAT_PERIOD_MS 100U

typedef struct { uint16_t center_x, center_y; UiInputEvent active_direction; uint32_t direction_started_ms, direction_event_ms; uint8_t stable_released, candidate_released; uint32_t switch_changed_ms, press_started_ms; uint8_t long_press_sent; } JoystickDecoder;
static ADC_HandleTypeDef *joystick_adc;
static JoystickDecoder joystick_decoder, joystick_test_decoder;
static uint8_t joystick_calibrated;
static uint32_t joystick_last_sample_ms;

static int32_t Absolute(int32_t v) { return v < 0 ? -v : v; }
static uint8_t Elapsed(uint32_t now, uint32_t then, uint32_t duration) { return (uint32_t)(now - then) >= duration; }
static void DecoderReset(JoystickDecoder *d, uint16_t x, uint16_t y) { d->center_x=x; d->center_y=y; d->active_direction=UI_EVT_NONE; d->direction_started_ms=0; d->direction_event_ms=0; d->stable_released=1; d->candidate_released=1; d->switch_changed_ms=0; d->press_started_ms=0; d->long_press_sent=0; }
static UiInputEvent DirectionForSample(const JoystickDecoder *d, uint16_t x, uint16_t y) { int32_t dx=(int32_t)x-d->center_x, dy=(int32_t)y-d->center_y, ax=Absolute(dx), ay=Absolute(dy); if (ax<=JOYSTICK_DEAD_ZONE && ay<=JOYSTICK_DEAD_ZONE) return UI_EVT_NONE; if (ax>=ay) return dx>0?UI_EVT_RIGHT:UI_EVT_LEFT; return dy<0?UI_EVT_UP:UI_EVT_DOWN; }
static uint8_t DirectionStillEngaged(const JoystickDecoder *d, uint16_t x, uint16_t y) { int32_t t=JOYSTICK_DEAD_ZONE-JOYSTICK_HYSTERESIS, dx=(int32_t)x-d->center_x, dy=(int32_t)y-d->center_y; switch(d->active_direction){case UI_EVT_RIGHT:return dx>=t;case UI_EVT_LEFT:return dx<=-t;case UI_EVT_UP:return dy<=-t;case UI_EVT_DOWN:return dy>=t;default:return 0;} }
static UiInputEvent DecodeSample(JoystickDecoder *d, uint16_t x, uint16_t y, uint8_t released, uint32_t now) {
  UiInputEvent direction; released=released?1:0;
  if(released!=d->candidate_released){d->candidate_released=released;d->switch_changed_ms=now;}
  if(d->stable_released!=d->candidate_released && Elapsed(now,d->switch_changed_ms,JOYSTICK_SWITCH_DEBOUNCE_MS)){d->stable_released=d->candidate_released;if(!d->stable_released){d->press_started_ms=now;d->long_press_sent=0;}else if(!d->long_press_sent)return UI_EVT_PRESS;d->long_press_sent=0;}
  if(!d->stable_released&&!d->long_press_sent&&Elapsed(now,d->press_started_ms,JOYSTICK_LONG_PRESS_MS)){d->long_press_sent=1;return UI_EVT_LONG_PRESS;}
  direction=DirectionStillEngaged(d,x,y)?d->active_direction:DirectionForSample(d,x,y);
  if(direction!=d->active_direction){d->active_direction=direction;d->direction_started_ms=now;d->direction_event_ms=now;return direction;}
  if((direction==UI_EVT_UP||direction==UI_EVT_DOWN)&&Elapsed(now,d->direction_started_ms,JOYSTICK_REPEAT_DELAY_MS)&&Elapsed(now,d->direction_event_ms,JOYSTICK_REPEAT_PERIOD_MS)){d->direction_event_ms=now;return direction;}
  return UI_EVT_NONE;
}
static uint8_t ReadAxis(uint32_t channel,uint16_t *value){ADC_ChannelConfTypeDef c={0};if(!joystick_adc||!value)return 0;c.Channel=channel;c.Rank=ADC_REGULAR_RANK_1;c.SamplingTime=ADC_SAMPLETIME_239CYCLES_5;if(HAL_ADC_ConfigChannel(joystick_adc,&c)!=HAL_OK||HAL_ADC_Start(joystick_adc)!=HAL_OK)return 0;if(HAL_ADC_PollForConversion(joystick_adc,1)!=HAL_OK){(void)HAL_ADC_Stop(joystick_adc);return 0;}*value=(uint16_t)HAL_ADC_GetValue(joystick_adc);(void)HAL_ADC_Stop(joystick_adc);return 1;}
static uint8_t ReadAxes(uint16_t *x,uint16_t *y){return ReadAxis(ADC_CHANNEL_10,x)&&ReadAxis(ADC_CHANNEL_11,y);}

void Joystick_Init(ADC_HandleTypeDef *hadc){GPIO_InitTypeDef g={0};joystick_adc=hadc;__HAL_RCC_GPIOC_CLK_ENABLE();g.Pin=GPIO_PIN_0|GPIO_PIN_1;g.Mode=GPIO_MODE_ANALOG;HAL_GPIO_Init(GPIOC,&g);g.Pin=GPIO_PIN_4;g.Mode=GPIO_MODE_INPUT;g.Pull=GPIO_PULLUP;HAL_GPIO_Init(GPIOC,&g);DecoderReset(&joystick_decoder,JOYSTICK_CENTER_DEFAULT,JOYSTICK_CENTER_DEFAULT);Joystick_Calibrate();}
void Joystick_Calibrate(void){uint32_t sx=0,sy=0;uint16_t x,y;uint8_t i;joystick_calibrated=0;for(i=0;i<JOYSTICK_CALIBRATION_SAMPLES;i++){if(!ReadAxes(&x,&y))return;sx+=x;sy+=y;HAL_Delay(2);}DecoderReset(&joystick_decoder,(uint16_t)(sx/JOYSTICK_CALIBRATION_SAMPLES),(uint16_t)(sy/JOYSTICK_CALIBRATION_SAMPLES));joystick_last_sample_ms=HAL_GetTick();joystick_calibrated=1;}
UiInputEvent Joystick_ProcessSample(uint16_t x,uint16_t y,uint8_t released,uint32_t now){return DecodeSample(&joystick_decoder,x,y,released,now);}
void Joystick_TestReset(uint16_t x,uint16_t y){DecoderReset(&joystick_test_decoder,x,y);}
UiInputEvent Joystick_TestProcessSample(uint16_t x,uint16_t y,uint8_t released,uint32_t now){return DecodeSample(&joystick_test_decoder,x,y,released,now);}
UiInputEvent Joystick_Poll(uint32_t now){uint16_t x,y;uint8_t released;if(!joystick_calibrated||!Elapsed(now,joystick_last_sample_ms,JOYSTICK_SAMPLE_PERIOD_MS))return UI_EVT_NONE;joystick_last_sample_ms=now;if(!ReadAxes(&x,&y))return UI_EVT_NONE;released=HAL_GPIO_ReadPin(GPIOC,GPIO_PIN_4)==GPIO_PIN_SET;return Joystick_ProcessSample(x,y,released,now);}
