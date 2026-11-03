#include "stm32f1xx_hal.h"
#include <stdio.h>
#include <string.h>
#if !defined(UT_SHT_DIAGNOSTIC) || BOARD_ID != 2
#error "CTRL-02 diagnostic target only"
#endif

static UART_HandleTypeDef uart;
static I2C_HandleTypeDef bus;
static const char identity[]="UT-DIAGNOSTIC:I2C-SHARED:CTRL-02:" DIAG_BUILD_ID;
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


uint8_t BoardIo_I2cRead16(uint8_t address, uint8_t reg, uint16_t *value);

static uint32_t ReadIna(uint8_t hard, uint8_t reg, uint16_t *value)
{
  if (!hard) return BoardIo_I2cRead16(0x40U, reg, value) ? 0U : 0x80000000U;
  uint8_t raw[2];
  if (HAL_I2C_Mem_Read(&bus, 0x40U << 1, reg, I2C_MEMADD_SIZE_8BIT,
                       raw, sizeof raw, 100U) != HAL_OK)
    return 0x100U | HAL_I2C_GetError(&bus);
  *value = (uint16_t)(((uint16_t)raw[0] << 8) | raw[1]);
  return 0U;
}

static unsigned Idle(void)
{
  return (HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_10) == GPIO_PIN_SET ? 2U : 0U) |
         (HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_11) == GPIO_PIN_SET ? 1U : 0U);
}

typedef struct {
  uint32_t err44, err45;
  unsigned address;
} ShtResult;

static ShtResult ReadSht(uint8_t hard)
{
  ShtResult result = {0xffffffffU, 0xffffffffU, 0U};
  uint8_t raw[6];
  for (uint8_t addr = 0x44U; addr <= 0x45U; ++addr) {
    uint32_t *err = addr == 0x44U ? &result.err44 : &result.err45;
    if (hard ? Hard_Read(addr, raw, err) : DiagSoft_Read(addr, raw, err)) {
      result.address = addr;
      break;
    }
  }
  return result;
}

int main(void)
{
  HAL_Init(); Clock_Init(); Uart_Init(); Watchdog_Init();
  (void)HAL_UART_Transmit(&uart, (uint8_t *)identity, sizeof identity - 1U, 100U);
  const char header[] = "\r\nI2C_SHARED PB10=SCL PB11=SDA idle bits: 2=SCL 1=SDA; INA READ ONLY\r\n";
  (void)HAL_UART_Transmit(&uart, (uint8_t *)header, sizeof header - 1U, 100U);
  DiagSoft_Init();
  HAL_Delay(100U);

  const char *labels[] = {"SOFT_SHT_ONLY", "SOFT_SHARED", "HARD_SHARED"};
  for (unsigned phase = 0U;; phase = (phase + 1U) % 3U) {
    uint8_t hard = phase == 2U;
    if (hard) {
      if (!Hard_Init()) Error_Handler();
    } else if (bus.Instance) {
      (void)HAL_I2C_DeInit(&bus);
      bus.Instance = NULL;
      DiagSoft_Init();
    }

    for (unsigned round = 1U; round <= 5U; ++round) {
      const unsigned idle = Idle();
      unsigned idleAfterIna = idle;
      ShtResult before = {0xffffffffU, 0xffffffffU, 0U}, after = before;
      uint32_t inaIdErr = 0xffffffffU, inaDieErr = 0xffffffffU;
      uint16_t manufacturer = 0U, die = 0U;
      if (idle == 3U) before = ReadSht(hard);
      if (phase != 0U && Idle() == 3U) {
        inaIdErr = ReadIna(hard, 0xfeU, &manufacturer);
        if (inaIdErr == 0U && Idle() == 3U)
          inaDieErr = ReadIna(hard, 0xffU, &die);
        idleAfterIna = Idle();
        if (idleAfterIna == 3U) after = ReadSht(hard);
      }

      char line[320];
      int n = snprintf(line, sizeof line,
        "%s n=%u idle=%u pre=%02x pre44=%08lx pre45=%08lx "
        "ina_id=%04x ina_die=%04x id_err=%08lx die_err=%08lx "
        "after_ina=%u post=%02x post44=%08lx post45=%08lx end=%u\r\n",
        labels[phase], round, idle, before.address, (unsigned long)before.err44,
        (unsigned long)before.err45, (unsigned)manufacturer, (unsigned)die,
        (unsigned long)inaIdErr, (unsigned long)inaDieErr, idleAfterIna,
        after.address, (unsigned long)after.err44, (unsigned long)after.err45, Idle());
      if (n > 0 && (size_t)n < sizeof line)
        (void)HAL_UART_Transmit(&uart, (uint8_t *)line, (uint16_t)n, 100U);
      IWDG->KR = 0xAAAAU;
      HAL_Delay(500U);
    }
  }
}
