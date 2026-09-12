"""Compile exact clock/UART/ADC MSP bodies with HAL capture; no target execution.

Extract just those functions to avoid replacing unrelated application IRQ/ASM.
The joystick module itself is compiled whole to check its timer configuration.
Run on Linux/WSL with GCC from the firmware directory.
"""
import argparse
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument(
    '--node-b-revision',
    help='load Node B and MSP sources from a git revision (used to demonstrate RED)',
)
args = parser.parse_args()

def source_text(relative_path):
    if not args.node_b_revision:
        return (root / relative_path).read_text(encoding='utf-8')
    worktree = root.parents[1]
    pointer = (worktree / '.git').read_text(encoding='utf-8').strip()
    assert pointer.startswith('gitdir: '), pointer
    git_directory = pointer.removeprefix('gitdir: ')
    if re.match(r'^[A-Za-z]:/', git_directory):
        git_directory = pathlib.Path('/mnt') / git_directory[0].lower() / git_directory[3:]
    repository_relative = (root / relative_path).relative_to(worktree).as_posix()
    return subprocess.run(
        ['git', f'--git-dir={git_directory}', f'--work-tree={worktree}',
         'show', f'{args.node_b_revision}:{repository_relative}'],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout

node_b_source = source_text('Core/Src/node_b.c')
msp_source = source_text('Core/Src/stm32f1xx_hal_msp.c')

def function(source, name):
    match = re.search(r'(?:static )?void ' + name + r'\([^)]*\)\s*\{', source)
    assert match, name
    depth, end = 1, match.end()
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]

harness = r'''
#include <assert.h>
#include <stdio.h>
#include <sys/mman.h>
#include "main.h"
#include "joystick.h"
UART_HandleTypeDef huart1, huart2;
DMA_HandleTypeDef hdma_adc1;
static RCC_OscInitTypeDef osc;
static RCC_ClkInitTypeDef clock_tree;
static uint32_t latency, adc_div, tick;
static uint32_t sysclk, pclk1, pclk2, period, prescaler;
static ADC_ChannelConfTypeDef adc_channels[2];
static uint32_t adc_channel_count, adc_dma_count;
static uint32_t adc_irq_priority, adc_irq_enabled;
void Error_Handler(void) { assert(0); }
HAL_StatusTypeDef HAL_RCC_OscConfig(RCC_OscInitTypeDef *v) { osc = *v; return HAL_OK; }
HAL_StatusTypeDef HAL_RCC_ClockConfig(RCC_ClkInitTypeDef *v, uint32_t l) {
  clock_tree = *v; latency = l; return HAL_OK;
}
HAL_StatusTypeDef HAL_RCCEx_PeriphCLKConfig(RCC_PeriphCLKInitTypeDef *v) {
  assert(v->PeriphClockSelection == RCC_PERIPHCLK_ADC);
  adc_div = v->AdcClockSelection; return HAL_OK;
}
HAL_StatusTypeDef HAL_UART_Init(UART_HandleTypeDef *v) {
  assert(v->Instance == USART1 || v->Instance == USART2);
  assert(v->Init.BaudRate == 9600);
  assert(v->Init.WordLength == UART_WORDLENGTH_8B && v->Init.StopBits == UART_STOPBITS_1);
  assert(v->Init.Parity == UART_PARITY_NONE && v->Init.OverSampling == UART_OVERSAMPLING_16);
  assert(v->Init.Mode == UART_MODE_TX_RX && v->Init.HwFlowCtl == UART_HWCONTROL_NONE);
  uint32_t freq = v->Instance == USART1 ? pclk2 : pclk1;
  uint32_t brr = UART_BRR_SAMPLING16(freq, v->Init.BaudRate);
  assert(freq / brr == 9600);
  assert(brr == (v->Instance == USART1 ? 7500 : 3750));
  return HAL_OK;
}
uint32_t HAL_RCC_GetPCLK1Freq(void) { return pclk1; }
uint32_t HAL_GetTick(void) { return tick++; }
void HAL_GPIO_Init(GPIO_TypeDef *port, GPIO_InitTypeDef *gpio) { (void)port; (void)gpio; }
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t priority, uint32_t subpriority) {
  assert(irq == DMA1_Channel1_IRQn && subpriority == 0);
  adc_irq_priority = priority;
}
void HAL_NVIC_EnableIRQ(IRQn_Type irq) {
  assert(irq == DMA1_Channel1_IRQn); adc_irq_enabled = 1;
}
HAL_StatusTypeDef HAL_TIM_Base_Init(TIM_HandleTypeDef *timer) {
  assert(timer->Instance == TIM3);
  assert(timer->Init.CounterMode == TIM_COUNTERMODE_UP);
  assert(timer->Init.ClockDivision == TIM_CLOCKDIVISION_DIV1);
  assert(timer->Init.AutoReloadPreload == TIM_AUTORELOAD_PRELOAD_DISABLE);
  prescaler = timer->Init.Prescaler; period = timer->Init.Period;
  return HAL_OK;
}
HAL_StatusTypeDef HAL_TIM_Base_Start(TIM_HandleTypeDef *timer) {
  assert((timer->Instance->CR2 & TIM_CR2_MMS) == TIM_TRGO_UPDATE); return HAL_OK;
}
HAL_StatusTypeDef HAL_ADC_Init(ADC_HandleTypeDef *adc) {
  assert(adc->Instance == ADC1);
  assert(adc->Init.ExternalTrigConv == ADC_EXTERNALTRIGCONV_T3_TRGO);
  assert(adc->Init.NbrOfConversion == 2 && adc->Init.ScanConvMode == ADC_SCAN_ENABLE);
  assert(adc->Init.ContinuousConvMode == DISABLE && adc->Init.DiscontinuousConvMode == DISABLE);
  assert(adc->Init.DataAlign == ADC_DATAALIGN_RIGHT);
  return HAL_OK;
}
HAL_StatusTypeDef HAL_ADC_ConfigChannel(ADC_HandleTypeDef *adc, ADC_ChannelConfTypeDef *c) {
  assert(adc->Instance == ADC1 && adc_channel_count < 2);
  adc_channels[adc_channel_count++] = *c; return HAL_OK;
}
HAL_StatusTypeDef HAL_ADCEx_Calibration_Start(ADC_HandleTypeDef *adc) { (void)adc; return HAL_OK; }
HAL_StatusTypeDef HAL_ADC_Start_DMA(ADC_HandleTypeDef *adc, uint32_t *data, uint32_t n) {
  assert(adc->Instance == ADC1 && data != NULL); adc_dma_count = n; return HAL_OK;
}
HAL_StatusTypeDef HAL_ADC_Stop_DMA(ADC_HandleTypeDef *adc) { (void)adc; return HAL_OK; }
HAL_StatusTypeDef HAL_DMA_Init(DMA_HandleTypeDef *dma) {
  assert(dma == &hdma_adc1); return HAL_OK;
}
'''
harness += '\n'.join(function(node_b_source, name) for name in (
    'SystemClock_Config', 'MX_USART1_UART_Init', 'MX_USART2_UART_Init'))
harness += function(msp_source, 'HAL_ADC_MspInit')
harness += r'''
int main(void) {
  assert(mmap((void *)0x40000000, 0x30000, PROT_READ|PROT_WRITE,
    MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED, -1, 0) != MAP_FAILED);
  SystemClock_Config();
  assert(osc.OscillatorType == RCC_OSCILLATORTYPE_HSE && osc.HSEState == RCC_HSE_ON);
  assert(osc.HSEPredivValue == RCC_HSE_PREDIV_DIV1 && osc.PLL.PLLSource == RCC_PLLSOURCE_HSE);
  assert(osc.PLL.PLLState == RCC_PLL_ON && osc.PLL.PLLMUL == RCC_PLL_MUL9);
  assert(clock_tree.SYSCLKSource == RCC_SYSCLKSOURCE_PLLCLK);
  sysclk = HSE_VALUE * ((osc.PLL.PLLMUL >> 18) + 2);
  assert(sysclk == 72000000 && latency == FLASH_LATENCY_2);
  assert(clock_tree.AHBCLKDivider == RCC_SYSCLK_DIV1);
  assert(clock_tree.APB1CLKDivider == RCC_HCLK_DIV2);
  assert(clock_tree.APB2CLKDivider == RCC_HCLK_DIV1);
  pclk1 = sysclk / 2; pclk2 = sysclk;
  RCC->CFGR = clock_tree.APB1CLKDivider;
  MX_USART1_UART_Init(); MX_USART2_UART_Init();
  Joystick_Init();
  assert(adc_div == RCC_ADCPCLK2_DIV6 && pclk2 / 6 == 12000000);
  assert(prescaler == 7199 && period == 49);
  assert((pclk1 * 2) / (prescaler + 1) / (period + 1) == 200);
  assert(adc_dma_count == 4 && adc_channel_count == 2);
  assert(adc_channels[0].Channel == ADC_CHANNEL_10);
  assert(adc_channels[0].Rank == ADC_REGULAR_RANK_1);
  assert(adc_channels[0].SamplingTime == ADC_SAMPLETIME_239CYCLES_5);
  assert(adc_channels[1].Channel == ADC_CHANNEL_11);
  assert(adc_channels[1].Rank == ADC_REGULAR_RANK_2);
  assert(adc_channels[1].SamplingTime == ADC_SAMPLETIME_239CYCLES_5);

  ADC_HandleTypeDef msp_adc = {0};
  msp_adc.Instance = ADC1;
  HAL_ADC_MspInit(&msp_adc);
  assert(hdma_adc1.Instance == DMA1_Channel1);
  assert(hdma_adc1.Init.Direction == DMA_PERIPH_TO_MEMORY);
  assert(hdma_adc1.Init.PeriphInc == DMA_PINC_DISABLE);
  assert(hdma_adc1.Init.MemInc == DMA_MINC_ENABLE);
  assert(hdma_adc1.Init.PeriphDataAlignment == DMA_PDATAALIGN_HALFWORD);
  assert(hdma_adc1.Init.MemDataAlignment == DMA_MDATAALIGN_HALFWORD);
  assert(hdma_adc1.Init.Mode == DMA_CIRCULAR && hdma_adc1.Init.Priority == DMA_PRIORITY_LOW);
  assert(msp_adc.DMA_Handle == &hdma_adc1 && hdma_adc1.Parent == &msp_adc);
  assert(adc_irq_priority == 1 && adc_irq_enabled == 1);
  puts("Display clock/UART/joystick contract test: PASS");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    binary = str(pathlib.Path(tmp) / 'clock_test')
    command = ['gcc', '-std=c11', '-D_GNU_SOURCE', '-DNODE_B_FIRMWARE', '-DSTM32F103xE',
               '-DUSE_HAL_DRIVER', '-O2', '-ffunction-sections', '-fdata-sections',
               '-Wno-int-to-pointer-cast', '-ICore/Inc', '-IDrivers/STM32F1xx_HAL_Driver/Inc',
               '-IDrivers/CMSIS/Device/ST/STM32F1xx/Include', '-IDrivers/CMSIS/Include',
               '-x', 'c', '-', 'Core/Src/joystick.c', '-Wl,--gc-sections', '-o', binary]
    subprocess.run(command, input=harness, text=True, cwd=root, check=True)
    subprocess.run([binary], check=True)
