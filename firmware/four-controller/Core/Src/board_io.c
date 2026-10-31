#include "board_io.h"
#include "board_config.h"
#include "../../common/digital.h"
#include <string.h>

void Error_Handler(void);

#define ADC_SAMPLE_COUNT      8U
#define ADC_REFERENCE_MV      3300UL

typedef struct
{
  GPIO_TypeDef *port;
  uint16_t scl_pin;
  uint16_t sda_pin;
} SoftI2cBus;

static ADC_HandleTypeDef hadc1;
static SoftI2cBus i2c_bus;
static SensorSample samples[11];
static volatile uint8_t sample_count;
static uint16_t sample_sequence;
static uint32_t attempted[11];
static volatile UtDigital digital[11];
static uint8_t cursor, sht_phase, sht_index, sht_address;
static uint32_t sht_started;
static uint32_t sht_good, sht_failed, sht_last_good, sht_raw_read;
static uint8_t i2c_clock_fault;
static uint32_t i2c_clock_timeouts;


volatile uint8_t BoardIo_I2cScanResult;
volatile uint8_t BoardIo_ShtDebug;
volatile uint8_t BoardIo_ShtRaw[6];
volatile uint8_t BoardIo_I2cIdleSda;
volatile uint8_t BoardIo_I2cIdleScl;
volatile uint8_t BoardIo_ShtFoundAddr;

/* ---------- Bounded software I2C, nominal <=100 kHz ---------- */

/* I2C timing changed deliberately: bench verification is still required. */
static void I2c_Delay(void)
{
  /* 5 us nominal half-cycle. DWT failure has a bounded fallback, never a hang. */
  uint32_t cycles=SystemCoreClock/200000U, start=DWT->CYCCNT;
  for(uint32_t guard=0;guard<cycles*8U && (uint32_t)(DWT->CYCCNT-start)<cycles;guard++) { __NOP(); }
}

/* 与旧台架代码一致：两根线都用开漏输出，依赖模块外部上拉。 */
static void I2c_Sda(GPIO_PinState state)
{
  HAL_GPIO_WritePin(i2c_bus.port, i2c_bus.sda_pin, state);
}

static void I2c_Scl(GPIO_PinState state)
{
  HAL_GPIO_WritePin(i2c_bus.port, i2c_bus.scl_pin, state);
  if(state!=GPIO_PIN_SET || i2c_clock_fault)return;
  /* Open drain SET only releases SCL. Sample the actual line, with a fixed
   * upper bound even when the tick/cycle counter or a slave stops working. */
  for(uint8_t guard=0U;guard<64U;guard++) {
    if(HAL_GPIO_ReadPin(i2c_bus.port,i2c_bus.scl_pin)==GPIO_PIN_SET)return;
    I2c_Delay();
  }
  i2c_clock_fault=1U;++i2c_clock_timeouts;
}

static void I2c_Start(void)
{
  i2c_clock_fault=0U;
  I2c_Sda(GPIO_PIN_SET); I2c_Scl(GPIO_PIN_SET); I2c_Delay();
  if(i2c_clock_fault)return;
  I2c_Sda(GPIO_PIN_RESET); I2c_Delay(); I2c_Scl(GPIO_PIN_RESET);
}

static void I2c_Stop(void)
{
  I2c_Sda(GPIO_PIN_RESET); I2c_Delay(); I2c_Scl(GPIO_PIN_SET);
  I2c_Delay(); I2c_Sda(GPIO_PIN_SET); I2c_Delay();
}

static uint8_t I2c_WriteByte(uint8_t value)
{
  uint8_t bit;
  uint8_t nack;
  if(i2c_clock_fault)return 0U;
  for (bit = 0U; bit < 8U; ++bit)
  {
    I2c_Sda((value & 0x80U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    I2c_Delay(); I2c_Scl(GPIO_PIN_SET);
    if(i2c_clock_fault)return 0U;
    I2c_Delay(); I2c_Scl(GPIO_PIN_RESET);
    value <<= 1U;
  }
  I2c_Sda(GPIO_PIN_SET); I2c_Delay(); I2c_Scl(GPIO_PIN_SET); I2c_Delay();
  if(i2c_clock_fault)return 0U;
  /* 与旧台架代码一致：SDA 被从机拉低表示 ACK，返回 1；调用处用 ! 判失败。 */
  nack = (HAL_GPIO_ReadPin(i2c_bus.port, i2c_bus.sda_pin) == GPIO_PIN_RESET) ? 1U : 0U;
  I2c_Scl(GPIO_PIN_RESET);
  return nack;   /* 1 = ACK */
}

static uint8_t I2c_ReadByte(uint8_t acknowledge)
{
  uint8_t bit;
  uint8_t value = 0U;
  if(i2c_clock_fault)return 0U;
  I2c_Sda(GPIO_PIN_SET);
  for (bit = 0U; bit < 8U; ++bit)
  {
    value <<= 1U;
    I2c_Delay(); I2c_Scl(GPIO_PIN_SET); I2c_Delay();
    if(i2c_clock_fault)return 0U;
    if (HAL_GPIO_ReadPin(i2c_bus.port, i2c_bus.sda_pin) == GPIO_PIN_SET) value |= 1U;
    I2c_Scl(GPIO_PIN_RESET);
  }
  I2c_Sda(acknowledge ? GPIO_PIN_RESET : GPIO_PIN_SET);
  I2c_Delay(); I2c_Scl(GPIO_PIN_SET); I2c_Delay(); I2c_Scl(GPIO_PIN_RESET);
  I2c_Sda(GPIO_PIN_SET);
  return value;
}

uint8_t BoardIo_I2cRead16(uint8_t address, uint8_t reg, uint16_t *value)
{
  uint8_t high;
  uint8_t low;
  if (value == NULL) return 0U;
  I2c_Start();
  if (!I2c_WriteByte((uint8_t)(address << 1U)) || !I2c_WriteByte(reg))
  {
    I2c_Stop();
    return 0U;
  }
  I2c_Start();
  if (!I2c_WriteByte((uint8_t)((address << 1U) | 1U)))
  {
    I2c_Stop();
    return 0U;
  }
  high = I2c_ReadByte(1U);
  low = I2c_ReadByte(0U);
  I2c_Stop();
  if(i2c_clock_fault)return 0U;
  *value = (uint16_t)(((uint16_t)high << 8U) | low);
  return 1U;
}

uint8_t BoardIo_I2cWrite16(uint8_t address, uint8_t reg, uint16_t value)
{
  I2c_Start();
  if (!I2c_WriteByte((uint8_t)(address << 1U)) || !I2c_WriteByte(reg) ||
      !I2c_WriteByte((uint8_t)(value >> 8U)) || !I2c_WriteByte((uint8_t)value))
  {
    I2c_Stop();
    return 0U;
  }
  I2c_Stop();
  return i2c_clock_fault?0U:1U;
}

static uint8_t __attribute__((unused)) Sht30_Crc(const uint8_t *data, uint8_t length)
{
  uint8_t crc = 0xFFU;
  uint8_t i;
  while (length-- > 0U)
  {
    crc ^= *data++;
    for (i = 0U; i < 8U; ++i)
      crc = (crc & 0x80U) ? (uint8_t)((crc << 1U) ^ 0x31U) : (uint8_t)(crc << 1U);
  }
  return crc;
}

static uint8_t Sht30_Begin(uint8_t address)
{
  uint8_t stage=1U;
  I2c_Start();
  if (!I2c_WriteByte((uint8_t)(address<<1U))) goto done;
  stage=2U;
  if (!I2c_WriteByte(0x24U)) goto done;
  stage=3U;
  if (!I2c_WriteByte(0U)) goto done;
  stage=0U;
done:
  I2c_Stop();
  BoardIo_ShtDebug=i2c_clock_fault?7U:stage;
  return BoardIo_ShtDebug==0U;
}
static uint8_t Sht30_Finish(uint8_t address, SensorSample *out)
{
  uint8_t response[6],i;
  uint16_t raw_temperature,raw_humidity;
  out->status=SENSOR_STATUS_MISSING;
  I2c_Start();
  if (!I2c_WriteByte((uint8_t)((address << 1U) | 1U)))
  {
    I2c_Stop();
    BoardIo_ShtDebug = i2c_clock_fault?7U:4U;
    return 0U;
  }
  for (i = 0U; i < sizeof(response); ++i)
  {
    response[i] = I2c_ReadByte((i < (sizeof(response) - 1U)) ? 1U : 0U);
    BoardIo_ShtRaw[i] = response[i];
  }
  I2c_Stop();
  if(i2c_clock_fault) {BoardIo_ShtDebug=7U;return 0U;}
  sht_raw_read=HAL_GetTick();
  if (Sht30_Crc(response, 2U) != response[2]) { BoardIo_ShtDebug = 5U; return 0U; }
  if (Sht30_Crc(&response[3], 2U) != response[5]) { BoardIo_ShtDebug = 6U; return 0U; }
  BoardIo_ShtDebug = 0U;

  raw_temperature = (uint16_t)(((uint16_t)response[0] << 8U) | response[1]);
  raw_humidity = (uint16_t)(((uint16_t)response[3] << 8U) | response[4]);
  out->value = (uint16_t)(int16_t)(((int32_t)17500 * raw_temperature) / 65535 - 4500);
  out->aux = (uint16_t)(((uint32_t)10000 * raw_humidity) / 65535U);
  out->status = SENSOR_STATUS_OK;
  return 1U;
}

uint8_t BoardIo_GetI2cDiagnostics(BoardIoI2cDiagnostics *out)
{
  static const uint8_t addresses[3]={0x40U,0x44U,0x45U};
  if(out==NULL || sht_phase)return 0U;
  memset(out,0,sizeof(*out));
  out->good=sht_good;out->failed=sht_failed;out->last_good_ms=sht_last_good;
  out->raw_read_ms=sht_raw_read;out->address=sht_address;out->stage=BoardIo_ShtDebug;
  out->clock_timeouts=i2c_clock_timeouts;
  out->idle_sda=HAL_GPIO_ReadPin(i2c_bus.port,i2c_bus.sda_pin)==GPIO_PIN_SET;
  out->idle_scl=HAL_GPIO_ReadPin(i2c_bus.port,i2c_bus.scl_pin)==GPIO_PIN_SET;
  for(uint8_t i=0;i<6U;i++)out->raw[i]=BoardIo_ShtRaw[i];
  /* Do not force clocks or send a general-call reset on a bus held low. */
  if(!out->idle_sda || !out->idle_scl)return 1U;
  for(uint8_t i=0;i<3U;i++) {
    I2c_Start();
    if(I2c_WriteByte((uint8_t)(addresses[i]<<1U)))out->ack_mask|=(uint8_t)(1U<<i);
    I2c_Stop();
  }
  out->probes_run=1U;
  return 1U;
}

/* ---------- ADC ---------- */

static uint8_t Adc_ReadRaw(uint32_t channel, uint16_t *raw)
{
  ADC_ChannelConfTypeDef config = {0};
  uint32_t sum = 0UL;
  uint16_t valid = 0U;
  uint16_t i;

  if (raw == NULL) return 0U;
  config.Channel = channel;
  config.Rank = ADC_REGULAR_RANK_1;
  config.SamplingTime = ADC_SAMPLETIME_239CYCLES_5;
  if (HAL_ADC_ConfigChannel(&hadc1, &config) != HAL_OK) return 0U;

  for (i = 0U; i < ADC_SAMPLE_COUNT; ++i)
  {
    if (HAL_ADC_Start(&hadc1) != HAL_OK) return 0U;
    if (HAL_ADC_PollForConversion(&hadc1, 1U) == HAL_OK)
    {
      sum += HAL_ADC_GetValue(&hadc1);
      ++valid;
    }
    (void)HAL_ADC_Stop(&hadc1);
    if (valid != i+1U) return 0U;
  }
  if (valid == 0U)
  {
    *raw = 0U;
    return 0U;
  }
  *raw = (uint16_t)((sum + (valid / 2U)) / valid);
  return 1U;
}

static uint16_t Adc_ToMillivolts(uint16_t raw)
{
  return (uint16_t)(((uint32_t)raw * ADC_REFERENCE_MV + 2047UL) / 4095UL);
}

uint8_t BoardIo_AdcRead(uint32_t channel, uint16_t *raw)
{
  return Adc_ReadRaw(channel, raw);
}

void BoardIo_ReinitI2c(void)
{
  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = i2c_bus.scl_pin | i2c_bus.sda_pin;
  gpio.Mode = GPIO_MODE_OUTPUT_OD;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(i2c_bus.port, &gpio);
  HAL_GPIO_WritePin(i2c_bus.port, i2c_bus.scl_pin | i2c_bus.sda_pin, GPIO_PIN_SET);
}

static uint8_t __attribute__((unused)) BoardIo_I2cScan(void)
{
  uint8_t address;

  /* 空闲时 SCL/SDA 都应被上拉到高；任一为低说明总线被拉死。 */
  HAL_GPIO_WritePin(i2c_bus.port, i2c_bus.scl_pin | i2c_bus.sda_pin, GPIO_PIN_SET);
  for (volatile uint32_t wait = 0U; wait < 2000U; ++wait) { __NOP(); }
  if ((HAL_GPIO_ReadPin(i2c_bus.port, i2c_bus.sda_pin) == GPIO_PIN_RESET) ||
      (HAL_GPIO_ReadPin(i2c_bus.port, i2c_bus.scl_pin) == GPIO_PIN_RESET))
    return 0xFEU;

  for (address = 0x08U; address < 0x78U; ++address)
  {
    I2c_Start();
    if (I2c_WriteByte((uint8_t)(address << 1U)) == 1U)
    {
      I2c_Stop();
      return address;
    }
    I2c_Stop();
  }
  return 0U;
}

uint16_t BoardIo_AdcToMillivolts(uint16_t raw)
{
  return Adc_ToMillivolts(raw);
}

/* ---------- 数字量 ---------- */

/* SysTick producer, main-loop consumer. Three consecutive 1-ms observations
 * debounce the input; observed events are held 10 s and explicitly tagged.
 * Pulses below 4 ms are not guaranteed; verify IRQ jitter on the bench. */
void BoardIo_FastTick(uint32_t now)
{
  for(uint8_t i=0;i<sample_count;i++) {
    const SensorDef *d=&board_config.sensors[i];
    if(d->type!=SENSOR_MQ2 && d->type!=SENSOR_FLAME && d->type!=SENSOR_LEVEL)continue;
    ut_digital_observe(&digital[i],HAL_GPIO_ReadPin(d->port,d->pin)==GPIO_PIN_RESET,now);
  }
}

/* ---------- 初始化 ---------- */

void BoardIo_Init(void)
{
  GPIO_InitTypeDef gpio = {0};
  uint8_t i;

  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_ADC1_CLK_ENABLE();

  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  sample_count = 0U;
  sht_good=0U;sht_failed=0U;sht_last_good=0U;sht_raw_read=0U;
  i2c_clock_fault=0U;i2c_clock_timeouts=0U;
  memset(samples, 0, sizeof samples);

  for (i = 0U; i < board_config.sensor_count; ++i)
  {
    samples[i].status=SENSOR_STATUS_MISSING;
    attempted[i]=HAL_GetTick()-2000U;
    const SensorDef *s = &board_config.sensors[i];
    if (s->port == NULL) continue;

    if (s->type == SENSOR_MQ4 || s->type == SENSOR_CO || s->type == SENSOR_O2)
    {
      gpio.Pin = s->pin;
      gpio.Mode = GPIO_MODE_ANALOG;
      gpio.Speed = GPIO_SPEED_FREQ_LOW;
      HAL_GPIO_Init(s->port, &gpio);
    }
    else if (s->type == SENSOR_MQ2 || s->type == SENSOR_FLAME || s->type == SENSOR_LEVEL)
    {
      gpio.Pin = s->pin;
      gpio.Mode = GPIO_MODE_INPUT;
      gpio.Pull = GPIO_PULLUP;
      HAL_GPIO_Init(s->port, &gpio);
    }
  }

  /* 本地软件 I2C：开漏，空闲为高。 */
  i2c_bus.port = board_config.i2c_port;
  i2c_bus.scl_pin = board_config.i2c_scl;
  i2c_bus.sda_pin = board_config.i2c_sda;
  /* 与旧台架一致：SCL/SDA 都是开漏输出，空闲写 1 由模块上拉拉高。 */
  gpio.Pin = i2c_bus.scl_pin | i2c_bus.sda_pin;
  gpio.Mode = GPIO_MODE_OUTPUT_OD;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;   /* 与旧台架一致 */
  HAL_GPIO_Init(i2c_bus.port, &gpio);
  HAL_GPIO_WritePin(i2c_bus.port, i2c_bus.scl_pin | i2c_bus.sda_pin, GPIO_PIN_SET);

  hadc1.Instance = ADC1;
  hadc1.Init.ScanConvMode = ADC_SCAN_DISABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.NbrOfConversion = 1;
  if (HAL_ADC_Init(&hadc1) != HAL_OK) Error_Handler();
  if (HAL_ADCEx_Calibration_Start(&hadc1) != HAL_OK) Error_Handler();

  sample_count=board_config.sensor_count;
  HAL_Delay(50U);
  BoardIo_I2cIdleSda = (HAL_GPIO_ReadPin(i2c_bus.port, i2c_bus.sda_pin) == GPIO_PIN_SET) ? 1U : 0U;
  BoardIo_I2cIdleScl = (HAL_GPIO_ReadPin(i2c_bus.port, i2c_bus.scl_pin) == GPIO_PIN_SET) ? 1U : 0U;
  BoardIo_I2cScanResult = 0U;
}

/* ---------- 采集 ---------- */

void BoardIo_Poll(uint32_t now)
{
  /* Fast ISR snapshots are copied in a short critical section; I2C/ADC never
   * run with interrupts disabled. Each call performs at most one slow transfer. */
  for(uint8_t i=0;i<sample_count;i++) {
    const SensorDef *d=&board_config.sensors[i];SensorSample *v=&samples[i];
    if(d->type!=SENSOR_MQ2&&d->type!=SENSOR_FLAME&&d->type!=SENSOR_LEVEL)continue;
    uint32_t mask=__get_PRIMASK();__disable_irq();
    UtDigital snapshot=digital[i];
    __set_PRIMASK(mask);
    uint8_t latched=ut_digital_latched(&snapshot,now);
    uint16_t value=(snapshot.level||latched)?1U:0U;
    uint8_t status=!snapshot.valid?SENSOR_STATUS_MISSING:(latched?SENSOR_STATUS_LATCHED:SENSOR_STATUS_OK);
    if(v->value!=value||v->status!=status)++sample_sequence;
    v->value=value;v->aux=0;v->status=status;v->sampled_at=latched?snapshot.last_active:snapshot.observed_at;
  }
  if(sht_phase) {
    if((uint32_t)(now-sht_started)<20U)return;
    SensorSample *v=&samples[sht_index];
    if(Sht30_Finish(sht_address,v)) {
      BoardIo_ShtFoundAddr=sht_address;++sht_good;sht_last_good=now;
    } else {v->status=SENSOR_STATUS_MISSING;BoardIo_ShtFoundAddr=0U;++sht_failed;}
    v->sampled_at=now;++sample_sequence;sht_phase=0;return;
  }
  for(uint8_t n=0;n<sample_count;n++) {
    uint8_t i=cursor++%sample_count;const SensorDef *d=&board_config.sensors[i];
    if((uint32_t)(now-attempted[i])<2000U)continue;
    if(d->type==SENSOR_MQ2||d->type==SENSOR_FLAME||d->type==SENSOR_LEVEL)continue;
    attempted[i]=now;SensorSample *v=&samples[i];
    if(d->type==SENSOR_SHT) {
      /* Alternate addresses on the next cycle, not another blocking retry. */
      sht_address=BoardIo_ShtFoundAddr?BoardIo_ShtFoundAddr:
        ((BoardIo_ShtDebug && sht_address==d->i2c_address)?(d->i2c_address==0x44U?0x45U:0x44U):d->i2c_address);
      sht_index=i;
      /* now may precede a blocking RTU response or the command transfer. The
       * conversion wait starts only after the command has actually completed. */
      if(Sht30_Begin(sht_address)){sht_phase=1;sht_started=HAL_GetTick();}
      else {BoardIo_ShtFoundAddr=0U;v->status=SENSOR_STATUS_MISSING;v->sampled_at=now;++sample_sequence;++sht_failed;}
    } else {
      uint16_t raw;
      if(Adc_ReadRaw(d->adc_channel,&raw)) {
        v->value=raw;v->aux=d->type==SENSOR_O2?Adc_ToMillivolts(raw):0U;
        v->status=d->type==SENSOR_O2?SENSOR_STATUS_SUSPECT:SENSOR_STATUS_OK;
      } else v->status=SENSOR_STATUS_MISSING;
      v->sampled_at=now;++sample_sequence;
    }
    return;
  }
}
/* Compatibility entry point is nonblocking; call Poll repeatedly in main. */
void BoardIo_SampleAll(void) { BoardIo_Poll(HAL_GetTick()); }
uint16_t BoardIo_Sequence(void) { return sample_sequence; }

const SensorSample *BoardIo_Samples(void) { return samples; }
uint8_t BoardIo_SampleCount(void) { return sample_count; }

uint16_t BoardIo_SensorId(uint8_t index)
{
  if (index >= sample_count) return 0xFFFFU;
  return board_config.sensors[index].id;
}

uint8_t BoardIo_AlarmActive(void)
{
  uint8_t i;
  for (i = 0U; i < sample_count; ++i)
  {
    const SensorDef *s = &board_config.sensors[i];
    if (((s->type == SENSOR_MQ2) || (s->type == SENSOR_FLAME)) &&
        (samples[i].value != 0U))
      return 1U;
  }
  return 0U;
}
