/* Exercise the Node A SPI3/DMA2 display bus against mapped CMSIS registers.
 * This validates the register contract, the preserved Node A peripherals and
 * the failure paths, not electrical SPI timing or the hardware DMA engine. */
#include <assert.h>
#include <stdio.h>
#include <sys/mman.h>
#include "node_a_clock_contract.h"
#include "st7735.h"
#include "st7735_bus.h"

uint32_t SystemCoreClock = 72000000U;
static uint32_t tick, gpio_b_pins, gpio_c_pins, gpio_b_modes, gpio_c_modes;
static uint32_t tick_calls;
static int frozen_tick;
uint32_t HAL_GetTick(void) {
    ++tick_calls;
    DWT->CYCCNT += 72000U;
    return frozen_tick ? tick : tick++;
}
uint32_t HAL_RCC_GetPCLK1Freq(void) { return 36000000U; }
uint32_t HAL_RCC_GetPCLK2Freq(void) { return 72000000U; }
void HAL_GPIO_Init(GPIO_TypeDef *gpio, GPIO_InitTypeDef *init) {
    if (gpio == GPIOB) {
        /* PB8/PB9 are the TIM4 fan PWM outputs and must stay untouched. */
        assert((init->Pin & (GPIO_PIN_8 | GPIO_PIN_9)) == 0U);
        gpio_b_pins |= init->Pin;
        gpio_b_modes = init->Mode;
    }
    if (gpio == GPIOC) { gpio_c_pins |= init->Pin; gpio_c_modes = init->Mode; }
    assert(gpio == GPIOB || gpio == GPIOC);
}
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t priority, uint32_t sub) {
    assert(irq == DMA2_Channel2_IRQn && sub == 0U);
    assert(priority == NODE_A_DISPLAY_IRQ_PRIORITY);
}
void HAL_NVIC_EnableIRQ(IRQn_Type irq) { assert(irq == DMA2_Channel2_IRQn); }
static void flags(uint32_t value) { *(volatile uint32_t *)&DMA2->ISR = value; }
int main(void) {
    assert(mmap((void *)0x40000000, 0x30000, PROT_READ|PROT_WRITE,
                MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED, -1, 0) != MAP_FAILED);
    assert(mmap((void *)0xE0000000, 0x100000, PROT_READ|PROT_WRITE,
                MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED, -1, 0) != MAP_FAILED);
    /* Poison every neighbouring peripheral the display must leave alone. */
    DMA2_Channel1->CCR = 0x55AA;
    DMA1_Channel5->CCR = 0x1234;
    TIM4->CCR3 = 0x0BAD;
    TIM4->CCR4 = 0x0BEE;
    TIM4->ARR = 2879U;
    St7735Bus_Init();
    assert(gpio_b_pins == (LCD_SCK_PIN | LCD_MOSI_PIN));
    assert(gpio_b_modes == GPIO_MODE_AF_PP);
    assert(gpio_c_pins == (LCD_RES_PIN | LCD_DC_PIN | LCD_CS_PIN | LCD_BLK_PIN));
    assert(gpio_c_modes == GPIO_MODE_OUTPUT_PP);
    assert(LCD_SCK_PIN == GPIO_PIN_3 && LCD_MOSI_PIN == GPIO_PIN_5);
    assert(LCD_RES_PIN == GPIO_PIN_4 && LCD_DC_PIN == GPIO_PIN_5);
    assert(LCD_CS_PIN == GPIO_PIN_6 && LCD_BLK_PIN == GPIO_PIN_7);
    assert((RCC->APB1ENR & RCC_APB1ENR_SPI3EN) != 0U);
    assert((RCC->AHBENR & RCC_AHBENR_DMA2EN) != 0U);
    assert((RCC->APB2ENR & RCC_APB2ENR_IOPBEN) != 0U);
    assert((RCC->APB2ENR & RCC_APB2ENR_IOPCEN) != 0U);
    /* SPI3 mode 0, 8-bit, MSB first, software NSS, PCLK1/2 = 18 MHz. */
    assert(SPI3->CR1 == (SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI |
                         SPI_CR1_BIDIMODE | SPI_CR1_BIDIOE | SPI_CR1_SPE));
    assert((SPI3->CR1 & (SPI_CR1_BR | SPI_CR1_CPOL | SPI_CR1_CPHA |
                         SPI_CR1_DFF | SPI_CR1_LSBFIRST)) == 0U);
    assert(SPI3->CR2 == 0U);
    assert(DMA2_Channel2->CCR == (DMA_CCR_DIR|DMA_CCR_MINC|DMA_CCR_TCIE|DMA_CCR_TEIE));
    assert(DMA2->IFCR == DMA_IFCR_CGIF2);
    assert(DMA2_Channel1->CCR == 0x55AA);
    assert(DMA1_Channel5->CCR == 0x1234);
    assert(TIM4->CCR3 == 0x0BAD && TIM4->CCR4 == 0x0BEE && TIM4->ARR == 2879U);
    St7735BusStats stats;
    St7735Bus_GetStats(&stats);
    assert(stats.spi_hz == 18000000U && !stats.dma_timeouts && !stats.dma_errors);
    uint8_t bytes[256] = {0};
    assert(!St7735Bus_WriteAsync(NULL, 1));
    assert(!St7735Bus_WriteAsync(bytes, 0));
    assert(!St7735Bus_WriteAsync(bytes, 257));
    assert(!St7735Bus_IsBusy());
    assert(St7735Bus_BeginData());
    assert(St7735Bus_WriteAsync(bytes, 256));
    assert(DMA2_Channel2->CNDTR == 256);
    assert(DMA2_Channel2->CPAR == (uint32_t)(uintptr_t)&SPI3->DR);
    assert(DMA2_Channel2->CMAR == (uint32_t)(uintptr_t)bytes);
    assert((SPI3->CR2 & SPI_CR2_TXDMAEN) != 0U);
    assert(St7735Bus_IsBusy() && !St7735Bus_WriteAsync(bytes, 2));
    flags(DMA_ISR_TCIF1); St7735Bus_DmaIrqHandler();
    assert(St7735Bus_IsBusy()); /* another channel's flag must be ignored */
    SPI3->SR = SPI_SR_BSY;
    flags(DMA_ISR_TCIF1|DMA_ISR_TCIF2); St7735Bus_DmaIrqHandler();
    assert(St7735Bus_IsBusy()); /* TC must not permit DC changes before last bit */
    assert(DMA2->IFCR == DMA_IFCR_CGIF2);
    assert(DMA2_Channel1->CCR == 0x55AA);
    SPI3->SR = SPI_SR_TXE;
    assert(St7735Bus_Wait());
    const uint32_t start = DWT->CYCCNT;
    DWT->CYCCNT += 72000;
    St7735Bus_RecordFrame(start);
    St7735Bus_GetStats(&stats);
    assert(stats.dma_frames == 1 && stats.worst_frame_us == 1000);

    /* Missing IRQ: unsigned tick/cycle wrap must still terminate and recover. */
    tick = UINT32_MAX; DWT->CYCCNT = UINT32_MAX - 72000;
    assert(St7735Bus_WriteAsync(bytes, 2));
    assert(!St7735Bus_Wait());
    assert(!St7735Bus_IsBusy() && !(DMA2_Channel2->CCR & DMA_CCR_EN));
    assert(!(SPI3->CR2 & SPI_CR2_TXDMAEN));
    assert(GPIOC->BSRR == LCD_CS_PIN);
    assert((SPI3->CR1 & SPI_CR1_SPE) != 0U);
    St7735Bus_GetStats(&stats); assert(stats.dma_timeouts == 1);

    /* Error IRQ aborts immediately; the next transaction remains usable. */
    assert(St7735Bus_WriteAsync(bytes, 2));
    flags(DMA_ISR_TEIF2); St7735Bus_DmaIrqHandler();
    assert(!St7735Bus_Wait());
    St7735Bus_GetStats(&stats); assert(stats.dma_errors == 1);
    flags(0);
    assert(St7735Bus_WriteAsync(bytes, 2));
    flags(DMA_ISR_TCIF2); St7735Bus_DmaIrqHandler();
    assert(St7735Bus_Wait());

    /* Stuck SPI or TXE, including frozen SysTick, must be bounded by DWT, and
     * the budget must actually be spent: one 1 ms tick per poll means a 2 ms
     * budget can only be reached after more than one poll.  A wait that gives
     * up on the first poll would tear frames instead of riding out a burst. */
    frozen_tick = 1; SPI3->SR = SPI_SR_BSY;
    tick_calls = 0U;
    assert(!St7735Bus_Wait());
    assert(tick_calls >= 3U);
    SPI3->SR = 0;
    assert(!St7735Bus_WriteByte(0x2C, 0));
    St7735Bus_GetStats(&stats); assert(stats.dma_timeouts == 3);
    assert(DMA2_Channel1->CCR == 0x55AA && DMA1_Channel5->CCR == 0x1234);
    SPI3->SR = SPI_SR_TXE;
    assert(St7735Bus_WriteByte(0x2C, 0));
    assert((uint8_t)SPI3->DR == 0x2C);
    assert(GPIOC->BSRR == (((uint32_t)LCD_CS_PIN << 16U) |
                           ((uint32_t)LCD_DC_PIN << 16U)));
    assert(St7735Bus_BeginData());
    assert(GPIOC->BSRR == (((uint32_t)LCD_CS_PIN << 16U) | LCD_DC_PIN));
    St7735Bus_ResetStats();
    St7735Bus_GetStats(&stats);
    assert(stats.dma_frames == 0 && stats.dma_timeouts == 0 && stats.dma_errors == 0);
    assert(stats.worst_frame_us == 0 && stats.spi_hz == 18000000U);
    puts("Node A display bus test: PASS");
    return 0;
}
