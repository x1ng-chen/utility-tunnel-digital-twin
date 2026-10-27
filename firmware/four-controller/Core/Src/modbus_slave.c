#include "modbus_slave.h"
#include "actuators.h"
#include "board_config.h"
#include "menu.h"
#include "stm32f1xx_hal.h"
#include <string.h>
void Error_Handler(void);
#define MODBUS_SIGNATURE 0x5554U
static UART_HandleTypeDef huart2;
static uint8_t rx_byte,slave_address=1U;
typedef struct { uint8_t data;uint32_t at; } RxCell;
/* ISR is sole producer, main sole consumer. No parsing or output in ISR. */
static volatile RxCell ring[512];
static volatile uint16_t producer,consumer;
static volatile uint8_t rx_reset;
static UtRtu parser;
static UtControl control;
static uint32_t boot_session;
static uint16_t input_regs[UT_INPUT_COUNT],holding_regs[UT_COMMAND_REGS];
volatile uint32_t modbus_rx_bytes,modbus_rx_frames,modbus_tx_frames;
volatile uint32_t modbus_bad_crc,modbus_overflow,modbus_uart_errors,modbus_tx_errors;
void USART2_IRQHandler(void) { HAL_UART_IRQHandler(&huart2); }
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
  if(uart!=&huart2)return;
  uint16_t next=(producer+1U)&511U;
  if(next!=consumer) {ring[producer].data=rx_byte;ring[producer].at=HAL_GetTick();producer=next;}
  else {++modbus_overflow;rx_reset=1U;}
  ++modbus_rx_bytes;
  if(HAL_UART_Receive_IT(&huart2,&rx_byte,1U)!=HAL_OK)rx_reset=1U;
}
void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
  if(uart!=&huart2)return;
  ++modbus_uart_errors;rx_reset=1U;
  (void)HAL_UART_Receive_IT(&huart2,&rx_byte,1U);
}
void Modbus_Init(uint8_t address)
{
  GPIO_InitTypeDef gpio = {0};
  uint8_t i;

  slave_address = (address >= 1U && address <= 4U) ? address : 1U;
  memset(input_regs, 0, sizeof input_regs);
  control.board=slave_address;
  input_regs[0] = MODBUS_SIGNATURE;
  input_regs[1] = slave_address;
  input_regs[2] = UT_VERSION;
  for (i = 0U; i < MODBUS_SLOT_COUNT; ++i)
    input_regs[8U + i * 4U] = 0xFFFFU;

  __HAL_RCC_AFIO_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_USART2_CLK_ENABLE();

  /* 先让自动收发模块的 TXD 处于空闲高电平，再切到复用。 */
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_2, GPIO_PIN_SET);
  gpio.Pin = GPIO_PIN_2;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(GPIOA, &gpio);
  gpio.Pin = GPIO_PIN_3;
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOA, &gpio);

  huart2.Instance = USART2;
  huart2.Init.BaudRate = 19200U;
  /* STM32F1 的 9 位字长 + 偶校验 = 8 位数据 + 1 位校验。 */
  huart2.Init.WordLength = UART_WORDLENGTH_9B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_EVEN;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK) Error_Handler();

  HAL_NVIC_SetPriority(USART2_IRQn, 2U, 0U);
  HAL_NVIC_EnableIRQ(USART2_IRQn);
  if (HAL_UART_Receive_IT(&huart2, &rx_byte, 1U) != HAL_OK) Error_Handler();
}


static void Put32(unsigned at,uint32_t value)
{ input_regs[at]=(uint16_t)(value>>16);input_regs[at+1U]=(uint16_t)value; }
static uint16_t Age(uint32_t now,uint32_t at,uint8_t missing)
{ uint32_t age=(uint32_t)(now-at)/10U;return missing?65535U:(uint16_t)(age>65534U?65534U:age); }
static void ApplyOutputs(uint32_t now)
{
  static uint16_t previous[4]={65535U,65535U,65535U,65535U};
  control.alarm=BoardIo_AlarmActive();ut_outputs(&control,now);
  for(unsigned i=0;i<4;i++) {
    if(previous[i]==control.output[i])continue;
    previous[i]=control.output[i];uint16_t v=control.output[i];
    if(i==0U)Actuators_SetFanPercent((uint8_t)v);
    else if(i==1U)Actuators_SetRelay((uint8_t)v);
    else if(i==2U)Actuators_SetBuzzer((uint8_t)v);
    else Actuators_SetLedColor(v==1U||v==2U?255U:0U,v==2U?180U:(v==3U?255U:0U),v==4U?255U:0U);
  }
}
void Modbus_SetSamples(const SensorSample *samples,uint8_t count,uint32_t uptime_s,uint16_t sequence)
{
  uint32_t now=HAL_GetTick();if(count>11U)count=11U;
  input_regs[3]=count;Put32(4U,uptime_s);input_regs[6]=sequence;
  input_regs[7]=(uint16_t)Actuators_FanPercent()|(Actuators_RelayOn()?0x100U:0U);
  input_regs[52]=BoardIo_AlarmActive();input_regs[65]=0U;
  for(unsigned i=0;i<11U;i++) {
    unsigned r=8U+4U*i;
    input_regs[r]=i<count?BoardIo_SensorId((uint8_t)i):65535U;
    input_regs[r+1U]=i<count?samples[i].value:0U;
    input_regs[r+2U]=i<count?samples[i].aux:0U;
    input_regs[r+3U]=i<count?samples[i].status:SENSOR_STATUS_MISSING;
    input_regs[UT_SENSOR_AGE_BASE+i]=i<count?Age(now,samples[i].sampled_at,samples[i].status==SENSOR_STATUS_MISSING):65535U;
    if(i<count&&samples[i].status==SENSOR_STATUS_LATCHED)input_regs[65]|=(uint16_t)(1U<<i);
  }
  const ActuatorFeedback *f=Actuators_Feedback();
  Put32(53U,f->rpm);input_regs[55]=f->rpm_quality;
  Put32(56U,f->ina.bus_millivolts);Put32(58U,(uint32_t)f->ina.current_microamps);
  Put32(60U,(uint32_t)f->ina.power_microwatts);
  input_regs[62]=f->ina_quality|(f->ina.calibrated?0x100U:0U);
  input_regs[63]=input_regs[7];input_regs[64]=0U;
  for(unsigned i=0;i<4U;i++)if(control.ttl[i]&&!ut_due(now,control.at[i],control.ttl[i]))input_regs[64]|=(uint16_t)(1U<<i);
  input_regs[66]=(uint16_t)parser.bad;input_regs[67]=(uint16_t)modbus_overflow;
  input_regs[79]=Age(now,f->rpm_at,!f->rpm_at);Put32(80U,control.session);
  Put32(82U,control.nonce);input_regs[84]=control.result;input_regs[85]=control.alarm;
  input_regs[86]=Age(now,f->ina_at,!f->ina_at);Menu_Registers(input_regs+87U,now);
  input_regs[95]=f->output_fault|(boot_session?2U:0U);
}
static void Send(uint8_t *p,uint16_t n)
{
  uint16_t crc=ut_crc(p,n);p[n]=(uint8_t)crc;p[n+1U]=(uint8_t)(crc>>8);
  if(HAL_UART_Transmit(&huart2,p,n+2U,160U)==HAL_OK)++modbus_tx_frames;
  else ++modbus_tx_errors;
}
static void Exception(uint8_t function,uint8_t code)
{ uint8_t p[5]={slave_address,(uint8_t)(function|0x80U),code,0,0};Send(p,3U); }
static void Respond(const uint8_t *p,uint16_t length)
{
  uint8_t out[UT_INPUT_COUNT*2U+5U];uint16_t start=ut_u16(p+2),count=ut_u16(p+4);
  if(p[1]==16U) {
    if(length!=9U+2U*count||p[6]!=2U*count){Exception(p[1],3U);return;}
    uint16_t data[UT_INPUT_COUNT];for(unsigned i=0;i<count;i++)data[i]=ut_u16(p+7U+i*2U);
    if(start==UT_BOOT_SESSION_BASE&&count==2U) {
      uint32_t token=((uint32_t)data[0]<<16)|data[1];
      if(!token){Exception(p[1],3U);return;}
      boot_session=token;Menu_Session(token);
    } else if(start==0U&&count==UT_COMMAND_REGS&&data[7]==0U) {
      if(!boot_session){Exception(p[1],6U);return;}
      UtCommand c={data[0],data[1],data[2],((uint32_t)data[3]<<16)|data[4],((uint32_t)data[5]<<16)|data[6]};
      control.alarm=BoardIo_AlarmActive();(void)ut_apply(&control,c,HAL_GetTick());
      memcpy(holding_regs,data,sizeof holding_regs);ApplyOutputs(HAL_GetTick());
      if(control.result==UT_RESULT_OK&&Actuators_Feedback()->output_fault) {
        control.result=UT_RESULT_UNKNOWN;
        for(unsigned i=0;i<8;i++)if(control.cache[i].used&&control.cache[i].command.session==c.session&&control.cache[i].command.nonce==c.nonce)control.cache[i].result=UT_RESULT_UNKNOWN;
      }
    } else if(board_config.has_joystick&&start==UT_VIEW_BASE&&count==UT_VIEW_COUNT&&data[0]==MODBUS_SIGNATURE&&data[1]>=1U&&data[1]<=4U&&data[2]==UT_VERSION) {if(!Menu_View(data,count)){Exception(p[1],3U);return;}}
    else if(board_config.has_joystick&&start==UT_MENU_ACK_BASE&&count==3U)Menu_Ack(data);
    else {Exception(p[1],2U);return;}
    memcpy(out,p,6U);Send(out,6U);return;
  }
  if(p[1]!=3U&&p[1]!=4U){Exception(p[1],1U);return;}
  unsigned total=p[1]==4U?UT_INPUT_COUNT:UT_COMMAND_REGS;
  if(!count||count>UT_INPUT_COUNT||(uint32_t)start+count>total){Exception(p[1],2U);return;}
  Modbus_SetSamples(BoardIo_Samples(),BoardIo_SampleCount(),HAL_GetTick()/1000U,BoardIo_Sequence());
  const uint16_t *table=p[1]==4U?input_regs:holding_regs;
  out[0]=slave_address;out[1]=p[1];out[2]=(uint8_t)(count*2U);
  for(unsigned i=0;i<count;i++)ut_put(out+3U+i*2U,table[start+i]);
  Send(out,(uint16_t)(3U+count*2U));
}
void Modbus_DebugPing(void) { /* No unsolicited traffic on a shared RTU bus. */ }
void Modbus_Poll(void)
{
  ApplyOutputs(HAL_GetTick());
  if(rx_reset) {
    uint32_t mask=__get_PRIMASK();__disable_irq();consumer=producer;rx_reset=0U;__set_PRIMASK(mask);parser.used=0U;
  }
  uint8_t frame[260];
  while(consumer!=producer) {
    uint8_t b=ring[consumer].data;uint32_t at=ring[consumer].at;
    consumer=(consumer+1U)&511U;
    if(parser.used&&ut_due(at,parser.last,4U)) {
      uint16_t finished;
      while((finished=ut_finish(&parser,slave_address,frame))!=0U){++modbus_rx_frames;Respond(frame,finished);}
      parser.used=0U;
    }
    ut_push(&parser,b,at);
    uint16_t n;while((n=ut_next(&parser,slave_address,frame))!=0U){++modbus_rx_frames;Respond(frame,n);}
  }
  if(parser.used&&ut_due(HAL_GetTick(),parser.last,4U)) {
    uint16_t n;while((n=ut_finish(&parser,slave_address,frame))!=0U){++modbus_rx_frames;Respond(frame,n);}
  }
  modbus_bad_crc=parser.bad;
}
