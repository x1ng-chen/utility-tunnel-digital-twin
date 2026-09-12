/* Exercise the actual SPI bus against mapped CMSIS peripheral registers.
 * This validates software state, register contracts and failure paths, not
 * electrical SPI timing or the hardware DMA engine. */
#include <assert.h>
#include <stdio.h>
#include <sys/mman.h>
#include "st7735.h"
#include "st7735_bus.h"

uint32_t SystemCoreClock = 72000000U;
static uint32_t tick, gpio_a_pins, gpio_b_pins;
static int frozen_tick;
uint32_t HAL_GetTick(void) {
    DWT->CYCCNT += 72000U;
    return frozen_tick ? tick : tick++;
}
uint32_t HAL_RCC_GetPCLK2Freq(void) { return 72000000U; }
void HAL_GPIO_Init(GPIO_TypeDef *gpio, GPIO_InitTypeDef *init) {
    if (gpio == GPIOA) { gpio_a_pins |= init->Pin; assert(init->Mode == GPIO_MODE_AF_PP); }
    if (gpio == GPIOB) { gpio_b_pins |= init->Pin; assert(init->Mode == GPIO_MODE_OUTPUT_PP); }
}
void HAL_NVIC_SetPriority(IRQn_Type irq, uint32_t priority, uint32_t sub) {
    assert(irq == DMA1_Channel3_IRQn && priority == 2 && sub == 0);
}
void HAL_NVIC_EnableIRQ(IRQn_Type irq) { assert(irq == DMA1_Channel3_IRQn); }
static void flags(uint32_t value) { *(volatile uint32_t *)&DMA1->ISR = value; }
int main(void) {
    assert(mmap((void *)0x40000000, 0x30000, PROT_READ|PROT_WRITE,
                MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED, -1, 0) != MAP_FAILED);
    assert(mmap((void *)0xE0000000, 0x100000, PROT_READ|PROT_WRITE,
                MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED, -1, 0) != MAP_FAILED);
    DMA1_Channel1->CCR = 0x55AA;
    St7735Bus_Init();
    assert(gpio_a_pins == (GPIO_PIN_5 | GPIO_PIN_7));
    assert(gpio_b_pins == (GPIO_PIN_6 | GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9));
    assert(DMA1_Channel1->CCR == 0x55AA);
    assert(DMA1_Channel3->CCR == (DMA_CCR_DIR|DMA_CCR_MINC|DMA_CCR_TCIE|DMA_CCR_TEIE));
    assert((SPI1->CR1 & (SPI_CR1_CPOL|SPI_CR1_CPHA|SPI_CR1_DFF|SPI_CR1_LSBFIRST)) == 0);
    St7735BusStats stats;
    St7735Bus_GetStats(&stats);
    assert(stats.spi_hz == 18000000 && !stats.dma_timeouts);
    uint8_t bytes[256] = {0};
    assert(!St7735Bus_WriteAsync(NULL, 1));
    assert(!St7735Bus_WriteAsync(bytes, 0));
    assert(!St7735Bus_WriteAsync(bytes, 257));
    assert(!St7735Bus_IsBusy());
    assert(St7735Bus_BeginData());
    assert(St7735Bus_WriteAsync(bytes, 256));
    assert(DMA1_Channel3->CNDTR == 256 && DMA1_Channel3->CPAR == (uint32_t)(uintptr_t)&SPI1->DR);
    assert(St7735Bus_IsBusy() && !St7735Bus_WriteAsync(bytes, 2));
    flags(DMA_ISR_TCIF1); St7735Bus_DmaIrqHandler();
    assert(St7735Bus_IsBusy());
    SPI1->SR = SPI_SR_BSY;
    flags(DMA_ISR_TCIF1|DMA_ISR_TCIF3); St7735Bus_DmaIrqHandler();
    assert(St7735Bus_IsBusy()); /* TC must not permit DC changes before last bit. */
    assert(DMA1->IFCR == DMA_IFCR_CGIF3);
    SPI1->SR = SPI_SR_TXE;
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
    assert(!St7735Bus_IsBusy() && !(DMA1_Channel3->CCR & DMA_CCR_EN));
    assert(!(SPI1->CR2 & SPI_CR2_TXDMAEN));
    assert(GPIOB->BSRR == GPIO_PIN_8);
    St7735Bus_GetStats(&stats); assert(stats.dma_timeouts == 1);

    /* Error IRQ aborts immediately; the next transaction remains usable. */
    assert(St7735Bus_WriteAsync(bytes, 2));
    flags(DMA_ISR_TEIF3); St7735Bus_DmaIrqHandler();
    assert(!St7735Bus_Wait());
    St7735Bus_GetStats(&stats); assert(stats.dma_errors == 1);
    flags(0);
    assert(St7735Bus_WriteAsync(bytes, 2));
    flags(DMA_ISR_TCIF3); St7735Bus_DmaIrqHandler();
    assert(St7735Bus_Wait());

    /* Stuck SPI or TXE, including frozen SysTick, must be bounded by DWT. */
    frozen_tick = 1; SPI1->SR = SPI_SR_BSY;
    assert(!St7735Bus_Wait());
    SPI1->SR = 0;
    assert(!St7735Bus_WriteByte(0x2C, 0));
    St7735Bus_GetStats(&stats); assert(stats.dma_timeouts == 3);
    assert(DMA1_Channel1->CCR == 0x55AA);
    SPI1->SR = SPI_SR_TXE;
    assert(St7735Bus_WriteByte(0x2C, 0));
    assert((uint8_t)SPI1->DR == 0x2C);
    St7735Bus_ResetStats();
    St7735Bus_GetStats(&stats);
    assert(stats.dma_frames == 0 && stats.dma_timeouts == 0 && stats.dma_errors == 0);
    assert(stats.worst_frame_us == 0 && stats.spi_hz == 18000000);
    puts("Display bus test: PASS");
    return 0;
}
