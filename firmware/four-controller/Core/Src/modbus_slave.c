#include "modbus_slave.h"
#include "actuators.h"
#include "stm32f1xx_hal.h"
#include <string.h>

void Error_Handler(void);

#define MODBUS_SIGNATURE 0x5554U
#define MODBUS_VERSION   0x0100U

static UART_HandleTypeDef huart2;
static uint8_t rx_byte;
static volatile uint8_t ring[256];
static volatile uint16_t producer, consumer;
static volatile uint32_t rx_tick;
static uint8_t slave_address = 1U;
static uint16_t input_regs[MODBUS_REGISTER_COUNT];
static uint16_t holding_regs[MODBUS_HOLDING_COUNT];

/* 调试计数：用 SWD 直接读取，判断 USART2 是否收到字节/帧。 */
volatile uint32_t modbus_rx_bytes;
volatile uint32_t modbus_rx_frames;
volatile uint32_t modbus_tx_frames;
volatile uint32_t modbus_bad_len;
volatile uint32_t modbus_bad_addr;
volatile uint32_t modbus_bad_crc;
volatile uint32_t modbus_bad_func;

/* ---------- CRC16（Modbus 多项式 0xA001，初值 0xFFFF） ---------- */

static uint16_t Modbus_Crc(const uint8_t *bytes, uint16_t count)
{
  uint16_t crc = 0xFFFFU;
  uint16_t i;
  uint8_t bit;
  for (i = 0U; i < count; ++i)
  {
    crc ^= bytes[i];
    for (bit = 0U; bit < 8U; ++bit)
      crc = (crc & 1U) ? (uint16_t)((crc >> 1U) ^ 0xA001U) : (uint16_t)(crc >> 1U);
  }
  return crc;
}

static uint16_t ReadU16(const uint8_t *p)
{
  return (uint16_t)(((uint16_t)p[0] << 8U) | p[1]);
}

/* ---------- UART 中断接收 ---------- */

void USART2_IRQHandler(void)
{
  HAL_UART_IRQHandler(&huart2);
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
  uint16_t next;
  if (uart != &huart2) return;
  next = (uint16_t)((producer + 1U) & 0xFFU);
  if (next != consumer)
  {
    ring[producer] = rx_byte;
    producer = next;
  }
  ++modbus_rx_bytes;
  rx_tick = HAL_GetTick();
  (void)HAL_UART_Receive_IT(&huart2, &rx_byte, 1U);
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
  if (uart != &huart2) return;
  (void)HAL_UART_Receive_IT(&huart2, &rx_byte, 1U);
}

/* ---------- 初始化 ---------- */

void Modbus_Init(uint8_t address)
{
  GPIO_InitTypeDef gpio = {0};
  uint8_t i;

  slave_address = (address >= 1U && address <= 4U) ? address : 1U;
  memset(input_regs, 0, sizeof input_regs);
  input_regs[0] = MODBUS_SIGNATURE;
  input_regs[1] = slave_address;
  input_regs[2] = MODBUS_VERSION;
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

/* ---------- 寄存器填充 ---------- */

void Modbus_SetSamples(const SensorSample *samples, uint8_t count,
                       uint32_t uptime_s, uint16_t sequence)
{
  uint8_t i;
  if (count > MODBUS_SLOT_COUNT) count = MODBUS_SLOT_COUNT;

  input_regs[3] = count;
  input_regs[4] = (uint16_t)(uptime_s >> 16U);
  input_regs[5] = (uint16_t)uptime_s;
  input_regs[6] = sequence;
  /* 执行器状态：低字节风机百分比，bit8 继电器。 */
  input_regs[7] = (uint16_t)(Actuators_FanPercent() & 0xFFU) |
                  (Actuators_RelayOn() ? 0x0100U : 0U);
  for (i = 0U; i < count; ++i)
  {
    uint16_t base = (uint16_t)(8U + i * 4U);
    input_regs[base + 0U] = BoardIo_SensorId(i);
    input_regs[base + 1U] = samples[i].value;
    input_regs[base + 2U] = samples[i].aux;
    input_regs[base + 3U] = samples[i].status;
  }
  for (; i < MODBUS_SLOT_COUNT; ++i)
  {
    uint16_t base = (uint16_t)(8U + i * 4U);
    input_regs[base + 0U] = 0xFFFFU;
    input_regs[base + 1U] = 0U;
    input_regs[base + 2U] = 0U;
    input_regs[base + 3U] = SENSOR_STATUS_MISSING;
  }
}

/* ---------- 帧处理 ---------- */

static void Execute_Command(void)
{
  uint16_t command = holding_regs[0];
  uint16_t parameter = holding_regs[1];

  holding_regs[3] = 0U;
  switch (command)
  {
    case 1U:
      Actuators_SetFanPercent((uint8_t)parameter);
      holding_regs[3] = 1U;
      break;
    case 2U:
      Actuators_SetRelay(parameter ? 1U : 0U);
      holding_regs[3] = 1U;
      break;
    case 3U:
      Actuators_SetBuzzer(parameter ? 1U : 0U);
      holding_regs[3] = 1U;
      break;
    case 4U:
    {
      uint8_t red = 0U, green = 0U, blue = 0U;
      switch (parameter)
      {
        case 1U: red = 255U; break;                    /* 红 */
        case 2U: red = 255U; green = 180U; break;      /* 黄 */
        case 3U: green = 255U; break;                  /* 绿 */
        case 4U: blue = 255U; break;                   /* 蓝 */
        default: break;                                /* 0 = 关 */
      }
      Actuators_SetLedColor(red, green, blue);
      holding_regs[3] = 1U;
      break;
    }
    default:
      holding_regs[3] = 2U;                            /* 本板不支持 */
      break;
  }
  holding_regs[2] = 0U;
}

static void Respond(const uint8_t *request, uint16_t length)
{
  uint8_t reply[8U + MODBUS_REGISTER_COUNT * 2U + 2U];
  const uint16_t *table;
  uint16_t table_count;
  uint16_t start;
  uint16_t count;
  uint16_t i;
  uint16_t crc;

  if (length != 8U) { ++modbus_bad_len; return; }
  if (request[0] != slave_address) { ++modbus_bad_addr; return; }
  if (Modbus_Crc(request, length) != 0U) { ++modbus_bad_crc; return; }

  /* 功能码 06：写单个保持寄存器，寄存器 2 写 1 触发执行。 */
  if (request[1] == 0x06U)
  {
    uint16_t reg = ReadU16(request + 2U);
    uint16_t value = ReadU16(request + 4U);
    if (reg >= MODBUS_HOLDING_COUNT) return;
    holding_regs[reg] = value;
    if ((reg == 2U) && (value == 1U)) Execute_Command();
    memcpy(reply, request, 8U);
    (void)HAL_UART_Transmit(&huart2, reply, 8U, 100U);
    return;
  }

  if (request[1] == 0x03U)
  {
    table = holding_regs;
    table_count = MODBUS_HOLDING_COUNT;
  }
  else if (request[1] == 0x04U)
  {
    table = input_regs;
    table_count = MODBUS_REGISTER_COUNT;
  }
  else
  {
    ++modbus_bad_func;
    return;
  }

  start = ReadU16(request + 2U);
  count = ReadU16(request + 4U);
  if (start >= table_count) return;
  if (count == 0U) return;
  if ((uint32_t)start + count > table_count) return;

  reply[0] = slave_address;
  reply[1] = request[1];
  reply[2] = (uint8_t)(count * 2U);
  for (i = 0U; i < count; ++i)
  {
    reply[3U + i * 2U] = (uint8_t)(table[start + i] >> 8U);
    reply[4U + i * 2U] = (uint8_t)table[start + i];
  }
  crc = Modbus_Crc(reply, (uint16_t)(3U + count * 2U));
  reply[3U + count * 2U] = (uint8_t)crc;
  reply[4U + count * 2U] = (uint8_t)(crc >> 8U);
  ++modbus_tx_frames;
  (void)HAL_UART_Transmit(&huart2, reply, (uint16_t)(5U + count * 2U), 100U);
}

void Modbus_DebugPing(void)
{
  const uint8_t ping[] = "PING\r\n";
  ++modbus_tx_frames;
  (void)HAL_UART_Transmit(&huart2, (uint8_t *)ping, sizeof ping - 1U, 100U);
}

void Modbus_Poll(void)
{
  uint8_t frame[8];
  uint16_t i;

  /* 请求帧固定 8 字节。采样可能阻塞约 100 ms，期间总线上会堆积多帧，
   * 因此按 8 字节切帧，而不是把整段缓冲当成一帧。 */
  while ((uint16_t)((producer - consumer) & 0xFFU) >= 8U)
  {
    for (i = 0U; i < 8U; ++i)
    {
      frame[i] = ring[consumer];
      consumer = (uint16_t)((consumer + 1U) & 0xFFU);
    }
    ++modbus_rx_frames;
    Respond(frame, 8U);
  }
}
