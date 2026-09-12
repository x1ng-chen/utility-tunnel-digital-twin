#include "st7735_bus.h"
#include "st7735.h"

static volatile uint8_t dma_active;
static volatile uint8_t dma_error;
static St7735BusStats counters;

static void ConfigureSpi(void)
{
    __HAL_RCC_SPI1_FORCE_RESET();
    __HAL_RCC_SPI1_RELEASE_RESET();
    /* Mode 0, MSB first, byte writes, PCLK2/4; transmit-only avoids RX overrun. */
    SPI1->CR1 = SPI_CR1_MSTR | SPI_CR1_BR_0 | SPI_CR1_SSM | SPI_CR1_SSI |
                SPI_CR1_BIDIMODE | SPI_CR1_BIDIOE;
    SPI1->CR2 = 0U;
    SPI1->CR1 |= SPI_CR1_SPE;
}

void St7735Bus_Init(void)
{
    GPIO_InitTypeDef gpio = {0};
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_SPI1_CLK_ENABLE();
    __HAL_RCC_DMA1_CLK_ENABLE();
    gpio.Pin = LCD_SCK_PIN | LCD_MOSI_PIN;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    gpio.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(LCD_SPI_PORT, &gpio); /* PA6 remains unused. */
    gpio.Pin = LCD_RES_PIN | LCD_DC_PIN | LCD_CS_PIN | LCD_BLK_PIN;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    HAL_GPIO_Init(LCD_CTRL_PORT, &gpio);
    LCD_CTRL_PORT->BSRR = LCD_CS_PIN | LCD_RES_PIN | LCD_BLK_PIN;
    ConfigureSpi();
    DMA1_Channel3->CCR = DMA_CCR_DIR | DMA_CCR_MINC | DMA_CCR_TCIE | DMA_CCR_TEIE;
    DMA1->IFCR = DMA_IFCR_CGIF3;
    dma_active = dma_error = 0U;
    counters = (St7735BusStats){0};
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    /* USART2 and ADC acquisition may preempt display completion. */
    HAL_NVIC_SetPriority(DMA1_Channel3_IRQn, 2U, 0U);
    HAL_NVIC_EnableIRQ(DMA1_Channel3_IRQn);
}

uint32_t St7735Bus_Cycles(void) { return DWT->CYCCNT; }

void St7735Bus_Recover(void)
{
    SPI1->CR2 &= ~SPI_CR2_TXDMAEN;
    DMA1_Channel3->CCR &= ~DMA_CCR_EN;
    DMA1->IFCR = DMA_IFCR_CGIF3;
    dma_active = dma_error = 0U;
    LCD_CTRL_PORT->BSRR = LCD_CS_PIN;
    ConfigureSpi();
}

uint8_t St7735Bus_IsBusy(void)
{
    return (dma_active || ((SPI1->SR & SPI_SR_BSY) != 0U)) ? 1U : 0U;
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
    while ((SPI1->SR & SPI_SR_TXE) == 0U) {
        if (((uint32_t)(HAL_GetTick() - tick) >= ST7735_BUS_TIMEOUT_MS) ||
            ((uint32_t)(St7735Bus_Cycles() - cycles) >=
             (SystemCoreClock / 1000U) * ST7735_BUS_TIMEOUT_MS)) {
            ++counters.dma_timeouts;
            St7735Bus_Recover();
            return 0U;
        }
    }
    *(__IO uint8_t *)&SPI1->DR = byte;
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
    DMA1_Channel3->CCR &= ~DMA_CCR_EN;
    DMA1->IFCR = DMA_IFCR_CGIF3;
    DMA1_Channel3->CPAR = (uint32_t)(uintptr_t)&SPI1->DR;
    DMA1_Channel3->CMAR = (uint32_t)(uintptr_t)bytes;
    DMA1_Channel3->CNDTR = length;
    dma_active = 1U;
    DMA1_Channel3->CCR |= DMA_CCR_EN;
    SPI1->CR2 |= SPI_CR2_TXDMAEN;
    return 1U;
}

void St7735Bus_DmaIrqHandler(void)
{
    const uint32_t flags = DMA1->ISR;
    if ((flags & (DMA_ISR_TCIF3 | DMA_ISR_TEIF3)) == 0U) return;
    SPI1->CR2 &= ~SPI_CR2_TXDMAEN;
    DMA1_Channel3->CCR &= ~DMA_CCR_EN;
    DMA1->IFCR = DMA_IFCR_CGIF3; /* Never clear ADC Channel1 flags. */
    if (flags & DMA_ISR_TEIF3) dma_error = 1U;
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
    stats->spi_hz = HAL_RCC_GetPCLK2Freq() / (2U << ((SPI1->CR1 & SPI_CR1_BR) >> 3U));
}
