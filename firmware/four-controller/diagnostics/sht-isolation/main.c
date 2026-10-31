/* CTRL-02 SHT-only A/B diagnostic. No INA, ADC, display, RTU or fan commands.
 * Same PB10/PB11 and power wiring in both phases; no sensor reset command.
 * Thirty 2-second cycles of production software I2C, then thirty hardware I2C2.
 * Wrong-address discovery failures are shown separately, not measurement data. */
#include "stm32f1xx_hal.h"
#include <stdio.h>
#include <string.h>
#if !defined(UT_SHT_DIAGNOSTIC) || BOARD_ID != 2
#error "CTRL-02 diagnostic target only"
#endif

static UART_HandleTypeDef uart;
static I2C_HandleTypeDef bus;
static const char identity[]="UT-DIAGNOSTIC:SHT:CTRL-02:" DIAG_BUILD_ID;
void DiagSoft_Init(void);
uint8_t DiagSoft_Read(uint8_t address,uint8_t raw[6],uint32_t *error);
void SysTick_Handler(void){HAL_IncTick();}
void Error_Handler(void){__disable_irq();for(;;){}}
void NMI_Handler(void){Error_Handler();}
void HardFault_Handler(void){Error_Handler();}
void MemManage_Handler(void){Error_Handler();}
void BusFault_Handler(void){Error_Handler();}
void UsageFault_Handler(void){Error_Handler();}

static void Clock_Init(void)
{
  RCC_OscInitTypeDef osc={0};RCC_ClkInitTypeDef clk={0};
  osc.OscillatorType=RCC_OSCILLATORTYPE_HSI;osc.HSIState=RCC_HSI_ON;
  osc.HSICalibrationValue=RCC_HSICALIBRATION_DEFAULT;osc.PLL.PLLState=RCC_PLL_NONE;
  if(HAL_RCC_OscConfig(&osc)!=HAL_OK)Error_Handler();
  clk.ClockType=RCC_CLOCKTYPE_SYSCLK|RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  clk.SYSCLKSource=RCC_SYSCLKSOURCE_HSI;clk.AHBCLKDivider=RCC_SYSCLK_DIV1;
  clk.APB1CLKDivider=RCC_HCLK_DIV1;clk.APB2CLKDivider=RCC_HCLK_DIV1;
  if(HAL_RCC_ClockConfig(&clk,FLASH_LATENCY_0)!=HAL_OK)Error_Handler();
}

static void Uart_Init(void)
{
  __HAL_RCC_GPIOA_CLK_ENABLE();__HAL_RCC_GPIOB_CLK_ENABLE();__HAL_RCC_USART1_CLK_ENABLE();
  GPIO_InitTypeDef g={0};
  /* High-active relay remains off, including during this temporary test. */
  HAL_GPIO_WritePin(GPIOA,GPIO_PIN_1,GPIO_PIN_RESET);
  g.Pin=GPIO_PIN_1;g.Mode=GPIO_MODE_OUTPUT_PP;g.Speed=GPIO_SPEED_FREQ_LOW;HAL_GPIO_Init(GPIOA,&g);
  g.Pin=GPIO_PIN_9;g.Mode=GPIO_MODE_AF_PP;g.Speed=GPIO_SPEED_FREQ_HIGH;HAL_GPIO_Init(GPIOA,&g);
  g.Pin=GPIO_PIN_10;g.Mode=GPIO_MODE_INPUT;g.Pull=GPIO_PULLUP;HAL_GPIO_Init(GPIOA,&g);
  uart.Instance=USART1;uart.Init.BaudRate=115200U;uart.Init.WordLength=UART_WORDLENGTH_8B;
  uart.Init.StopBits=UART_STOPBITS_1;uart.Init.Parity=UART_PARITY_NONE;
  uart.Init.Mode=UART_MODE_TX_RX;uart.Init.HwFlowCtl=UART_HWCONTROL_NONE;uart.Init.OverSampling=UART_OVERSAMPLING_16;
  if(HAL_UART_Init(&uart)!=HAL_OK)Error_Handler();
}

static void Watchdog_Init(void)
{
  IWDG->KR=0xCCCCU;IWDG->KR=0x5555U;IWDG->PR=4U;IWDG->RLR=2499U;
  uint32_t at=HAL_GetTick();
  while(IWDG->SR){if((uint32_t)(HAL_GetTick()-at)>100U)Error_Handler();}
  IWDG->KR=0xAAAAU;
}

static uint8_t Crc(const uint8_t *p)
{
  uint8_t c=0xffU;
  for(unsigned n=0;n<2U;n++){c^=p[n];for(unsigned b=0;b<8U;b++)c=(c&0x80U)?(uint8_t)((c<<1U)^0x31U):(uint8_t)(c<<1U);}
  return c;
}

static uint8_t Hard_Init(void)
{
  __HAL_RCC_I2C2_CLK_ENABLE();__HAL_RCC_I2C2_FORCE_RESET();__HAL_RCC_I2C2_RELEASE_RESET();
  GPIO_InitTypeDef g={0};g.Pin=GPIO_PIN_10|GPIO_PIN_11;g.Mode=GPIO_MODE_AF_OD;g.Speed=GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_WritePin(GPIOB,g.Pin,GPIO_PIN_SET);HAL_GPIO_Init(GPIOB,&g);
  memset(&bus,0,sizeof bus);bus.Instance=I2C2;bus.Init.ClockSpeed=100000U;bus.Init.DutyCycle=I2C_DUTYCYCLE_2;
  bus.Init.AddressingMode=I2C_ADDRESSINGMODE_7BIT;bus.Init.DualAddressMode=I2C_DUALADDRESS_DISABLE;
  bus.Init.GeneralCallMode=I2C_GENERALCALL_DISABLE;bus.Init.NoStretchMode=I2C_NOSTRETCH_DISABLE;
  return HAL_I2C_Init(&bus)==HAL_OK;
}

static uint8_t Hard_Read(uint8_t addr,uint8_t raw[6],uint32_t *error)
{
  uint8_t cmd[2]={0x24U,0};
  if(HAL_I2C_Master_Transmit(&bus,(uint16_t)(addr<<1U),cmd,2U,100U)!=HAL_OK){*error=HAL_I2C_GetError(&bus);return 0;}
  HAL_Delay(50U);
  if(HAL_I2C_Master_Receive(&bus,(uint16_t)(addr<<1U),raw,6U,100U)!=HAL_OK){*error=0x10000U|HAL_I2C_GetError(&bus);return 0;}
  if(Crc(raw)!=raw[2] || Crc(raw+3)!=raw[5]){*error=0x20000U;return 0;}
  *error=0;return 1;
}

int main(void)
{
  HAL_Init();Clock_Init();Uart_Init();Watchdog_Init();
  (void)HAL_UART_Transmit(&uart,(uint8_t *)identity,sizeof identity-1U,100U);
  const char header[]="\r\nSHT_ONLY CTRL-02 PB10=SCL PB11=SDA SOFT=production HARD=I2C2 100kHz; NO_BUSINESS_TELEMETRY\r\n";
  (void)HAL_UART_Transmit(&uart,(uint8_t *)header,sizeof header-1U,100U);
  uint8_t mode=0,active_address=0;uint32_t cycle=0,good=0,failed=0,phase=0;
  for(;;){
    if(!cycle){
      if(mode){if(!Hard_Init())Error_Handler();}
      else{if(bus.Instance){(void)HAL_I2C_DeInit(&bus);bus.Instance=NULL;}DiagSoft_Init();}
      active_address=0;good=0;failed=0;++phase;HAL_Delay(100U);
    }
    uint32_t started=HAL_GetTick(),errors[2]={0,0};uint8_t raw[6]={0},ok=0,used=active_address;
    for(unsigned n=0;n<(active_address?1U:2U);n++){
      used=active_address?active_address:(n?0x45U:0x44U);memset(raw,0,sizeof raw);
      ok=mode?Hard_Read(used,raw,&errors[n]):DiagSoft_Read(used,raw,&errors[n]);
      if(ok){active_address=used;break;}
    }
    if(ok)++good;else ++failed;
    ++cycle;
    char line[320];int count;
    if(ok){
      int32_t t=(int32_t)(17500L*((uint32_t)raw[0]*256U+raw[1])/65535U)-4500L;
      uint32_t h=10000UL*((uint32_t)raw[3]*256U+raw[4])/65535U;
      count=snprintf(line,sizeof line,"SHT_ONLY mode=%s phase=%lu cycle=%lu at=%lu addr=%02x valid=1 temp_centi=%ld rh_centi=%lu good=%lu fail=%lu raw=%02x%02x%02x%02x%02x%02x\r\n",mode?"HARD":"SOFT",(unsigned long)phase,(unsigned long)cycle,(unsigned long)HAL_GetTick(),used,(long)t,(unsigned long)h,(unsigned long)good,(unsigned long)failed,raw[0],raw[1],raw[2],raw[3],raw[4],raw[5]);
    }else{
      count=snprintf(line,sizeof line,"SHT_ONLY mode=%s phase=%lu cycle=%lu at=%lu addr=%02x valid=0 err0=%08lx err1=%08lx good=%lu fail=%lu idle=%u%u\r\n",mode?"HARD":"SOFT",(unsigned long)phase,(unsigned long)cycle,(unsigned long)HAL_GetTick(),used,(unsigned long)errors[0],(unsigned long)errors[1],(unsigned long)good,(unsigned long)failed,HAL_GPIO_ReadPin(GPIOB,GPIO_PIN_10)==GPIO_PIN_SET,HAL_GPIO_ReadPin(GPIOB,GPIO_PIN_11)==GPIO_PIN_SET);
    }
    if(count>0&&(size_t)count<sizeof line)(void)HAL_UART_Transmit(&uart,(uint8_t *)line,(uint16_t)count,100U);
    while((uint32_t)(HAL_GetTick()-started)<2000U)HAL_Delay(1U);
    IWDG->KR=0xAAAAU;
    if(cycle>=30U){cycle=0;mode^=1U;}
  }
}
