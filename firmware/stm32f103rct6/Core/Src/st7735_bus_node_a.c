/**
 * @file    st7735_bus_node_a.c
 * @brief   CTRL-01 board adapter for the shared ST7735 display transport:
 *          SPI3 (PB3=SCK, PB5=MOSI) with DMA2 Channel 2, control lines on
 *          PC4=RES, PC5=DC, PC6=CS, PC7=BLK.
 *
 * Node A could not reuse Node B's SPI1 mapping: PB6/PB7 carry the SHT30
 * software I2C, PA7 carries fan 2's tachometer and PB8/PB9 carry the TIM4 fan
 * PWM outputs.  SPI3 sits on PCLK1, so BR = 0b000 divides 36 MHz by two and
 * yields the same 18 MHz the primary screen uses.  The default SPI3 pins need
 * no AFIO remap, and PB3 (JTDO) is already released by the SWJ_NOJTAG setting
 * that HAL_MspInit() applies while keeping SWD on PA13/PA14.
 *
 * The transport contract itself - async write, bounded wait, recovery and the
 * statistics counters - is the shared one from st7735_bus.h, so the renderer
 * in st7735.c is identical on both boards. */
#include "st7735_bus.h"
#include "st7735.h"
/* The 18 MHz bit rate and the interrupt ordering are asserted once, in the
 * contract header, so this adapter only has to use them. */
#include "node_a_clock_contract.h"

static volatile uint8_t dma_active;
static volatile uint8_t dma_error;
static St7735BusStats counters;

static void ConfigureSpi(void)
{
    __HAL_RCC_SPI3_FORCE_RESET();
    __HAL_RCC_SPI3_RELEASE_RESET();
    /* Mode 0, MSB first, byte writes, PCLK1/2 = 18 MHz (BR = 0b000);
     * transmit-only avoids RX overrun. */
    SPI3->CR1 = SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI |
                SPI_CR1_BIDIMODE | SPI_CR1_BIDIOE | SPI_CR1_SPE;
    SPI3->CR2 = 0U;
}

void St7735Bus_Init(void)
{
    GPIO_InitTypeDef gpio = {0};
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_SPI3_CLK_ENABLE();
    __HAL_RCC_DMA2_CLK_ENABLE();
    gpio.Pin = LCD_SCK_PIN | LCD_MOSI_PIN;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    gpio.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(LCD_SPI_PORT, &gpio);
    /* PB8/PB9 keep driving the TIM4 fan PWM; only the control lines move. */
    gpio.Pin = LCD_RES_PIN | LCD_DC_PIN | LCD_CS_PIN | LCD_BLK_PIN;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    HAL_GPIO_Init(LCD_CTRL_PORT, &gpio);
    LCD_CTRL_PORT->BSRR = LCD_CS_PIN | LCD_RES_PIN | LCD_BLK_PIN;
    ConfigureSpi();
    DMA2_Channel2->CCR = DMA_CCR_DIR | DMA_CCR_MINC | DMA_CCR_TCIE | DMA_CCR_TEIE;
    DMA2->IFCR = DMA_IFCR_CGIF2; /* Never clear the ADC or WS2812 DMA1 flags. */
    dma_active = dma_error = 0U;
    counters = (St7735BusStats){0};
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    /* USART2, the gas ADC and the fan tachometer may preempt display
     * completion; only the HAL tick stays below the display. */
    HAL_NVIC_SetPriority(DMA2_Channel2_IRQn, NODE_A_DISPLAY_IRQ_PRIORITY, 0U);
    HAL_NVIC_EnableIRQ(DMA2_Channel2_IRQn);
}

uint32_t St7735Bus_Cycles(void) { return DWT->CYCCNT; }

void St7735Bus_Recover(void)
{
    SPI3->CR2 &= ~SPI_CR2_TXDMAEN;
    DMA2_Channel2->CCR &= ~DMA_CCR_EN;
    DMA2->IFCR = DMA_IFCR_CGIF2;
    dma_active = dma_error = 0U;
    LCD_CTRL_PORT->BSRR = LCD_CS_PIN;
    ConfigureSpi();
}

uint8_t St7735Bus_IsBusy(void)
{
    return (dma_active || ((SPI3->SR & SPI_SR_BSY) != 0U)) ? 1U : 0U;
}

uint8_t St7735Bus_Wait(void)
{
    const uint32_t tick = HAL_GetTick();
    const uint32_t cycles = St7735Bus_Cycles();
    /* DWT bounds the wait even if SysTick cannot advance. Interrupts stay on. */
    while (St7735Bus_IsBusy() && !dma_error) {
        if (((uint32_t)(HAL_GetTick() - tick) >= ST7735_BUS_TIMEOUT_MS) ||
            ((uint32_t)(St7735Bus_Cycles() - cycles) >=
             (SystemCoreClock / 1000U) * ST7735_BUS_TIMEOUT_MS)) {
            ++counters.dma_timeouts;
            St7735Bus_Recover();
            return 0U;
        }
    }
    if (dma_error) {
        ++counters.dma_errors;
        St7735Bus_Recover();
        return 0U;
    }
    return 1U;
}

uint8_t St7735Bus_WriteByte(uint8_t byte, uint8_t data)
{
    uint32_t tick, cycles;
    if (!St7735Bus_Wait()) return 0U;
    LCD_CTRL_PORT->BSRR = ((uint32_t)LCD_CS_PIN << 16U) |
        (data ? LCD_DC_PIN : ((uint32_t)LCD_DC_PIN << 16U));
    tick = HAL_GetTick();
    cycles = St7735Bus_Cycles();
    while ((SPI3->SR & SPI_SR_TXE) == 0U) {
        if (((uint32_t)(HAL_GetTick() - tick) >= ST7735_BUS_TIMEOUT_MS) ||
            ((uint32_t)(St7735Bus_Cycles() - cycles) >=
             (SystemCoreClock / 1000U) * ST7735_BUS_TIMEOUT_MS)) {
            ++counters.dma_timeouts;
            St7735Bus_Recover();
            return 0U;
        }
    }
    *(__IO uint8_t *)&SPI3->DR = byte;
    return St7735Bus_Wait();
}

uint8_t St7735Bus_BeginData(void)
{
    if (!St7735Bus_Wait()) return 0U;
    LCD_CTRL_PORT->BSRR = ((uint32_t)LCD_CS_PIN << 16U) | LCD_DC_PIN;
    return 1U;
}

uint8_t St7735Bus_WriteAsync(const uint8_t *bytes, uint16_t length)
{
    if (!bytes || !length || length > ST7735_BUS_BUFFER_BYTES ||
        St7735Bus_IsBusy() || dma_error) return 0U;
    DMA2_Channel2->CCR &= ~DMA_CCR_EN;
    DMA2->IFCR = DMA_IFCR_CGIF2;
    DMA2_Channel2->CPAR = (uint32_t)(uintptr_t)&SPI3->DR;
    DMA2_Channel2->CMAR = (uint32_t)(uintptr_t)bytes;
    DMA2_Channel2->CNDTR = length;
    dma_active = 1U;
    DMA2_Channel2->CCR |= DMA_CCR_EN;
    SPI3->CR2 |= SPI_CR2_TXDMAEN;
    return 1U;
}

void St7735Bus_DmaIrqHandler(void)
{
    const uint32_t flags = DMA2->ISR;
    if ((flags & (DMA_ISR_TCIF2 | DMA_ISR_TEIF2)) == 0U) return;
    SPI3->CR2 &= ~SPI_CR2_TXDMAEN;
    DMA2_Channel2->CCR &= ~DMA_CCR_EN;
    DMA2->IFCR = DMA_IFCR_CGIF2; /* Never clear DMA1 Channel1/Channel5 flags. */
    if (flags & DMA_ISR_TEIF2) dma_error = 1U;
    dma_active = 0U; /* SPI may still be shifting its last byte. */
}

void St7735Bus_RecordFrame(uint32_t started_cycles)
{
    const uint32_t elapsed = (uint32_t)(St7735Bus_Cycles() - started_cycles);
    const uint32_t us = elapsed / (SystemCoreClock / 1000000U);
    ++counters.dma_frames;
    if (us > counters.worst_frame_us) counters.worst_frame_us = us;
}

void St7735Bus_GetStats(St7735BusStats *stats)
{
    if (!stats) return;
    *stats = counters;
    stats->spi_hz = HAL_RCC_GetPCLK1Freq() / (2U << ((SPI3->CR1 & SPI_CR1_BR) >> 3U));
}

void St7735Bus_ResetStats(void)
{
    /* Only foreground code mutates counters; the DMA IRQ publishes bus state. */
    counters = (St7735BusStats){0};
}
