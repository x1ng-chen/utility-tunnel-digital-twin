#include "stm32f1xx_hal.h"
#include "bench_protocol.h"
#include <stdio.h>
#include <string.h>

static UART_HandleTypeDef bus, debug;
static uint8_t rx_byte;
static volatile uint8_t ring[256];
static volatile uint16_t producer, consumer;
static volatile uint32_t uart_errors, ring_overruns, rx_tick;
static uint32_t accepted, bad_crc;
#define BENCH_TEXT_INNER(x) #x
#define BENCH_TEXT(x) BENCH_TEXT_INNER(x)

static void stop(void) { __disable_irq(); for (;;) {} }
void SysTick_Handler(void) { HAL_IncTick(); }
void USART2_IRQHandler(void) { HAL_UART_IRQHandler(&bus); }
void NMI_Handler(void) { stop(); }
void HardFault_Handler(void) { stop(); }
void MemManage_Handler(void) { stop(); }
void BusFault_Handler(void) { stop(); }
void UsageFault_Handler(void) { stop(); }

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart) {
    if (uart != &bus) return;
    uint16_t next = (producer + 1u) & 255u;
    if (next == consumer) ++ring_overruns;
    else { ring[producer] = rx_byte; producer = next; }
    rx_tick = HAL_GetTick();
    (void)HAL_UART_Receive_IT(&bus, &rx_byte, 1u);
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart) {
    if (uart != &bus) return;
    ++uart_errors;
    (void)HAL_UART_Receive_IT(&bus, &rx_byte, 1u);
}

static void uart_setup(void) {
    __HAL_RCC_AFIO_CLK_ENABLE();
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_USART1_CLK_ENABLE();
    __HAL_RCC_USART2_CLK_ENABLE();
    GPIO_InitTypeDef pin = {0};
    /* Establish the auto-direction module TX idle before enabling its AF. */
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_2 | GPIO_PIN_9, GPIO_PIN_SET);
    pin.Pin = GPIO_PIN_2 | GPIO_PIN_9;
    pin.Mode = GPIO_MODE_AF_PP; pin.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOA, &pin);
    pin.Pin = GPIO_PIN_3 | GPIO_PIN_10;
    pin.Mode = GPIO_MODE_INPUT; pin.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOA, &pin);
    debug.Instance = USART1;
    debug.Init.BaudRate = 115200;
    debug.Init.WordLength = UART_WORDLENGTH_8B;
    debug.Init.StopBits = UART_STOPBITS_1;
    debug.Init.Parity = UART_PARITY_NONE;
    debug.Init.Mode = UART_MODE_TX_RX;
    debug.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    debug.Init.OverSampling = UART_OVERSAMPLING_16;
    if (HAL_UART_Init(&debug) != HAL_OK) stop();
    bus.Instance = USART2;
    bus.Init.BaudRate = 19200;
    /* STM32F1 9-bit word WITH parity means 8 payload bits plus parity. */
    bus.Init.WordLength = UART_WORDLENGTH_9B;
    bus.Init.StopBits = UART_STOPBITS_1;
    bus.Init.Parity = UART_PARITY_EVEN;
    bus.Init.Mode = UART_MODE_TX_RX;
    bus.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    bus.Init.OverSampling = UART_OVERSAMPLING_16;
    if (HAL_UART_Init(&bus) != HAL_OK) stop();
    HAL_NVIC_SetPriority(USART2_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(USART2_IRQn);
    if (HAL_UART_Receive_IT(&bus, &rx_byte, 1u) != HAL_OK) stop();
}

static void log_status(void) {
    char line[160];
    int size = snprintf(line, sizeof line,
        "CTRL0%u_BENCH selftest=PASS uptime_ms=%lu requests=%lu crc_errors=%lu uart_errors=%lu overruns=%lu\r\n",
        (unsigned)BENCH_ADDRESS,
        (unsigned long)HAL_GetTick(), (unsigned long)accepted,
        (unsigned long)bad_crc, (unsigned long)uart_errors, (unsigned long)ring_overruns);
    if (size > 0 && (size_t)size < sizeof line)
        (void)HAL_UART_Transmit(&debug, (uint8_t *)line, (uint16_t)size, 30u);
}

static void respond(const uint8_t *request, size_t size) {
    if (size == 8u && request[0] == BENCH_ADDRESS && !bench_valid_crc(request, size)) ++bad_crc;
    if (!bench_is_request(request, size)) return;
    ++accepted;
    uint32_t seconds = HAL_GetTick() / 1000u;
    uint16_t regs[BENCH_REGISTER_COUNT] = {BENCH_SIGNATURE, BENCH_ADDRESS, BENCH_VERSION,
        (uint16_t)(seconds >> 16), (uint16_t)seconds,
        (uint16_t)(accepted >> 16), (uint16_t)accepted, (uint16_t)bad_crc};
    uint8_t reply[21] = {BENCH_ADDRESS, 3, 16};
    for (unsigned i = 0; i < BENCH_REGISTER_COUNT; ++i) {
        reply[3u + i * 2u] = (uint8_t)(regs[i] >> 8);
        reply[4u + i * 2u] = (uint8_t)regs[i];
    }
    bench_add_crc(reply, 19u);
    /* Received a complete frame after >=4 ms silence; only then own the bus. */
    if (HAL_UART_Transmit(&bus, reply, sizeof reply, 100u) != HAL_OK) ++uart_errors;
}

int main(void) {
    /* Also support entry from the ROM bootloader's GO command. */
    __disable_irq();
    SysTick->CTRL = 0u;
    SCB->VTOR = FLASH_BASE;
    __DSB(); __ISB();
    HAL_Init();
    __enable_irq();
    /* HSI avoids depending on the board's external oscillator variant. */
    RCC_OscInitTypeDef osc = {0};
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    osc.HSIState = RCC_HSI_ON; osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    osc.PLL.PLLState = RCC_PLL_NONE;
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) stop();
    RCC_ClkInitTypeDef clk = {0};
    clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV1; clk.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_0) != HAL_OK) stop();
    uart_setup();
    if (bench_self_test() != 0) {
        const char error[] = "PROTOCOL_SELFTEST FAIL\r\n";
        (void)HAL_UART_Transmit(&debug, (uint8_t *)error, sizeof error - 1u, 100u);
        stop();
    }
    const char banner[] = "RS485_BENCH_V1 CTRL-0" BENCH_TEXT(BENCH_ADDRESS)
        " SLAVE=" BENCH_TEXT(BENCH_ADDRESS) " BUS=PA2/PA3 19200-8E1 DIAGNOSTIC_ONLY\r\n";
    (void)HAL_UART_Transmit(&debug, (uint8_t *)banner, sizeof banner - 1u, 100u);
    uint8_t frame[64]; size_t length = 0; uint8_t overflow = 0;
    uint32_t last_log = HAL_GetTick();
    for (;;) {
        while (consumer != producer) {
            uint8_t byte = ring[consumer]; consumer = (consumer + 1u) & 255u;
            if (length < sizeof frame) frame[length++] = byte;
            else overflow = 1;
        }
        if (length && (uint32_t)(HAL_GetTick() - rx_tick) >= 4u) {
            if (!overflow) respond(frame, length);
            length = 0; overflow = 0;
        }
        if ((uint32_t)(HAL_GetTick() - last_log) >= 5000u) {
            log_status(); last_log = HAL_GetTick();
        }
    }
}
