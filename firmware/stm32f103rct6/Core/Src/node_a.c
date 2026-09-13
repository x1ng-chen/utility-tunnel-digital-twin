#include "main.h"
#include "node_a_command.h"
#include "node_a_ina226.h"
#include "node_a_sensor_map.h"

#include <stdio.h>
#include <string.h>

#define NODE_ID                         "node-a"
#define TELEMETRY_INTERVAL_MS           2000U
#define LED_INTERVAL_MS                  500U
#define LED_ANIM_INTERVAL_MS              50U
#define BUZZER_TEST_DURATION_MS         1000U
#define SHT30_COMMAND_HIGH_REPEATABLE    0x2400U
#define SHT30_ADDRESS_44                 0x44U
#define SHT30_ADDRESS_45                 0x45U
#define INA226_ADDRESS                   0x40U
#define INA226_REG_SHUNT_VOLTAGE         0x01U
#define INA226_REG_BUS_VOLTAGE           0x02U
#define INA226_REG_POWER                 0x03U
#define INA226_REG_CURRENT               0x04U
#define INA226_REG_CALIBRATION           0x05U
#define INA226_REG_CONFIG                0x00U
#define INA226_REG_MANUFACTURER_ID       0xFEU
#define INA226_REG_DIE_ID                0xFFU
#define INA226_MANUFACTURER_ID         0x5449U
#define INA226_DIE_ID_MASK             0xFFF0U
#define INA226_DIE_ID                  0x2260U
#define INA226_CALIBRATION_VALUE          5120U
#define INA226_CONFIG_AVG16_CONTINUOUS   0x4527U
#define INA226_CONFIG_RESET              0x8000U
#define INA226_SAMPLE_COUNT                   3U
#define INA226_SAMPLE_SETTLE_MS              40U
#define INA226_MAX_BUS_MICROVOLTS       18000000UL
#define INA226_FAULT_NONE                       0U
#define INA226_FAULT_COMMUNICATION              1U
#define INA226_FAULT_IDENTITY                   2U
#define INA226_FAULT_CONFIGURATION              3U
#define INA226_FAULT_STUCK_03FF                 4U
#define ESP_RX_LINE_SIZE                  384U
#define ESP_RX_QUEUE_CAPACITY             4U
#define NODE_TEST_LINE_SIZE               384U
#define BUZZER_Pin                         GPIO_PIN_0
#define BUZZER_GPIO_Port                   GPIOB
#define RELAY_Pin                          GPIO_PIN_1
#define RELAY_GPIO_Port                    GPIOA
#define SMOKE_Pin                          GPIO_PIN_12
#define SMOKE_GPIO_Port                    GPIOB
#define FLAME_Pin                          GPIO_PIN_14
#define FLAME_GPIO_Port                    GPIOB
#define LEVEL_Pin                          GPIO_PIN_0
#define LEVEL_GPIO_Port                    GPIOC
#define WS2812_Pin                         GPIO_PIN_15
#define WS2812_GPIO_Port                   GPIOB
#define FAN1_TACH_Pin                      GPIO_PIN_6
#define FAN1_TACH_GPIO_Port                GPIOA
#define FAN_TACH_PULSES_PER_REVOLUTION            2U
#define FAN1_PWM_Pin                       GPIO_PIN_8
#define FAN1_PWM_GPIO_Port                 GPIOB
#define FAN2_TACH_Pin                      GPIO_PIN_7
#define FAN2_TACH_GPIO_Port                GPIOA
#define FAN2_PWM_Pin                       GPIO_PIN_9
#define FAN2_PWM_GPIO_Port                 GPIOB
#define FAN_PWM_TIMER_PERIOD                    319U
#define WS2812_PIXEL_COUNT                 9U
#define WS2812_TEST_BRIGHTNESS             32U
#define SMOKE_SAMPLE_INTERVAL_MS            50U
#define SMOKE_STABLE_SAMPLE_COUNT            4U
#define FLAME_SAMPLE_INTERVAL_MS            50U
#define FLAME_ALARM_HOLD_MS               12000U
#define LEVEL_SAMPLE_INTERVAL_MS            50U
#define LEVEL_STABLE_SAMPLE_COUNT            4U
#define GAS_ADC_SAMPLE_COUNT                 64U

typedef struct
{
  GPIO_TypeDef *port;
  uint16_t scl_pin;
  uint16_t sda_pin;
} SoftI2cBus;

typedef struct
{
  uint8_t configured;
} Ina226State;

typedef struct
{
  uint8_t online;
  int16_t temperature_centi_c;
  uint16_t humidity_centi_rh;
} Sht30Reading;

typedef struct
{
  uint8_t online;
  uint8_t plausible;
  uint8_t fault;
  uint16_t manufacturer_id;
  uint16_t die_id;
  uint16_t config_raw;
  uint16_t bus_raw;
  int16_t shunt_raw;
  int16_t current_raw;
  uint16_t power_raw;
  uint16_t calibration_raw;
  uint32_t bus_microvolts;
  int32_t current_microamps;
  int32_t power_microwatts;
} Ina226Reading;

typedef struct
{
  uint16_t samples[3];
  uint16_t filtered;
  uint8_t count;
  uint8_t next;
} GasAdcFilter;

static const SoftI2cBus i2c1_bus = {GPIOB, GPIO_PIN_6, GPIO_PIN_7};
static const SoftI2cBus i2c2_bus = {GPIOB, GPIO_PIN_10, GPIO_PIN_11};
static Ina226State ina226_fan1_state;
static Ina226State ina226_fan2_state;
UART_HandleTypeDef huart2;
UART_HandleTypeDef huart1;
ADC_HandleTypeDef hadc1;
static uint8_t esp_rx_character;
static volatile char esp_rx_lines[ESP_RX_QUEUE_CAPACITY][ESP_RX_LINE_SIZE];
static volatile uint16_t esp_rx_length;
static volatile uint8_t esp_rx_discarding;
static volatile uint16_t esp_rx_lengths[ESP_RX_QUEUE_CAPACITY];
static volatile uint32_t esp_rx_received_at[ESP_RX_QUEUE_CAPACITY];
static volatile uint8_t esp_rx_head;
static volatile uint8_t esp_rx_tail;
static volatile uint8_t esp_rx_count;
static volatile uint32_t esp_rx_bytes;
static volatile uint32_t esp_rx_completed_lines;
static volatile uint32_t esp_rx_dropped_lines;
static NodeACommandDedup command_dedup;
static NodeAActuatorState g_actuator = { 100U, 100U, 0U, 0U, 0U,
                                         NODE_A_LED_OFF, 100U };
static uint32_t relay_started_at;
static uint32_t relay_duration_ms;
static uint32_t buzzer_started_at;
static uint32_t buzzer_duration_ms;
static volatile uint32_t fan1_tach_pulses;
static uint32_t fan1_tach_last_pulses;
static uint32_t fan1_tach_last_sample_at;
static volatile uint32_t fan2_tach_pulses;
static uint32_t fan2_tach_last_pulses;
static uint32_t fan2_tach_last_sample_at;
static uint8_t smoke_alarm;
static uint8_t smoke_active_samples;
static uint32_t smoke_last_sample_at;
static uint8_t flame_alarm;
static uint8_t flame_raw_level;
static uint32_t flame_last_sample_at;
static uint32_t flame_last_detected_at;
static uint8_t level_detected;
static uint8_t level_candidate;
static uint8_t level_candidate_samples;
static uint32_t level_last_sample_at;
static uint8_t co_warning;
static uint8_t co_alarm;
static uint8_t methane_warning;
static uint8_t methane_alarm;
static uint8_t oxygen_warning;
static uint8_t oxygen_alarm;
static uint8_t gas_warning;
static uint8_t gas_alarm;
static uint8_t gas_ventilation_active;
static uint8_t gas_ventilation_cooling;
static uint32_t gas_ventilation_clear_started_at;
static uint8_t ws2812_encoded[WS2812_PIXEL_COUNT * 15U];
static char node_test_line[NODE_TEST_LINE_SIZE];
static uint16_t node_test_length;
static uint8_t test_safety_smoke;
static uint8_t test_safety_flame;
static uint8_t test_safety_gas;
static uint8_t test_safety_vent;
static volatile uint8_t test_force_telemetry;

void SystemClock_Config(void);
void Error_Handler(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_ADC1_Init(void);
static uint8_t GasAdc_ReadRaw(uint32_t channel, uint16_t *raw);
static uint16_t GasAdcFilter_Update(GasAdcFilter *filter, uint16_t sample);
static void GasAlarm_Update(uint16_t oxygen_raw, uint8_t oxygen_online,
                            uint16_t methane_raw, uint8_t methane_online,
                            uint16_t co_raw, uint8_t co_online);
static void GasVentilation_Update(uint32_t now);
static uint8_t Sht30_Read(const SoftI2cBus *bus, uint8_t address, Sht30Reading *reading);
static uint8_t Ina226_Read(const SoftI2cBus *bus, Ina226State *state,
                           Ina226Reading *reading);
static void SendTelemetry(const Sht30Reading readings[3], uint8_t smoke_detected,
                          uint8_t flame_detected,
                          uint8_t level_is_detected, uint16_t oxygen_raw,
                          uint32_t oxygen_microvolts, uint8_t oxygen_online,
                          uint16_t methane_raw, uint32_t methane_microvolts,
                          uint8_t methane_online, uint16_t co_raw,
                          uint32_t co_microvolts, uint8_t co_online,
                          const Ina226Reading *fan1_power,
                          uint32_t fan1_rpm, const Ina226Reading *fan2_power,
                          uint32_t fan2_rpm);
static void Command_Poll(void);
static void Command_ProcessPayload(const char *payload, uint32_t received_at);
static void Command_SendAck(const char *command_id, const char *status,
                            const char *reason, uint32_t applied_value);
static void NodeTest_Poll(void);
static void Safety_Snapshot(NodeASafetyState *safety);
static void CommitActuators(const NodeACommand *command, uint32_t now,
                            const NodeAActuatorState *before);
static void Led_Render(uint32_t now);
static void Buzzer_Silence(void);
static void Buzzer_Start(uint32_t duration_ms);
static void Relay_Disable(void);
static void Relay_Enable(uint32_t duration_ms);
static void Smoke_Poll(uint32_t now);
static void Flame_Poll(uint32_t now);
static void Level_Poll(uint32_t now);
static void MX_WS2812_SPI_Init(void);
static void Ws2812_Show(uint8_t red, uint8_t green, uint8_t blue);
static uint32_t Fan1Tach_ReadRpm(uint32_t now);
static uint32_t Fan2Tach_ReadRpm(uint32_t now);
static void MX_FAN1_PWM_Init(void);
static void Fan1Pwm_SetPercent(uint8_t percent);
static void Fan2Pwm_SetPercent(uint8_t percent);

void HAL_GPIO_EXTI_Callback(uint16_t gpio_pin)
{
  if (gpio_pin == FAN1_TACH_Pin) ++fan1_tach_pulses;
  else if (gpio_pin == FAN2_TACH_Pin) ++fan2_tach_pulses;
}

static uint32_t Fan1Tach_ReadRpm(uint32_t now)
{
  uint32_t pulses;
  uint32_t elapsed_ms = now - fan1_tach_last_sample_at;
  uint32_t delta;

  __disable_irq();
  pulses = fan1_tach_pulses;
  __enable_irq();
  delta = pulses - fan1_tach_last_pulses;
  fan1_tach_last_pulses = pulses;
  fan1_tach_last_sample_at = now;
  if ((elapsed_ms == 0U) || (g_actuator.relay_on == 0U)) return 0U;
  return (uint32_t)(((uint64_t)delta * 60000ULL) /
                    ((uint64_t)FAN_TACH_PULSES_PER_REVOLUTION * elapsed_ms));
}

static uint32_t Fan2Tach_ReadRpm(uint32_t now)
{
  uint32_t pulses;
  uint32_t elapsed_ms = now - fan2_tach_last_sample_at;
  uint32_t delta;

  __disable_irq();
  pulses = fan2_tach_pulses;
  __enable_irq();
  delta = pulses - fan2_tach_last_pulses;
  fan2_tach_last_pulses = pulses;
  fan2_tach_last_sample_at = now;
  if ((elapsed_ms == 0U) || (g_actuator.relay_on == 0U)) return 0U;
  return (uint32_t)(((uint64_t)delta * 60000ULL) /
                    ((uint64_t)FAN_TACH_PULSES_PER_REVOLUTION * elapsed_ms));
}

/* A standard four-wire fan expects an approximately 25 kHz open-collector
 * PWM signal. PB8/TIM4_CH3 drives an external NPN transistor, so the MCU
 * waveform is inverted relative to the fan input: transistor off is HIGH at
 * the fan and therefore represents commanded run time. */
static void Fan1Pwm_SetPercent(uint8_t percent)
{
  uint32_t transistor_on_counts;
  if (percent > 100U) percent = 100U;
  g_actuator.fan1_pwm_percent = percent;
  transistor_on_counts = ((uint32_t)(100U - percent) *
                          (FAN_PWM_TIMER_PERIOD + 1U) + 50U) / 100U;
  TIM4->CCR3 = transistor_on_counts;
}

static void Fan2Pwm_SetPercent(uint8_t percent)
{
  uint32_t transistor_on_counts;
  if (percent > 100U) percent = 100U;
  g_actuator.fan2_pwm_percent = percent;
  transistor_on_counts = ((uint32_t)(100U - percent) *
                          (FAN_PWM_TIMER_PERIOD + 1U) + 50U) / 100U;
  TIM4->CCR4 = transistor_on_counts;
}

static void MX_FAN1_PWM_Init(void)
{
  GPIO_InitTypeDef gpio = {0};
  __HAL_RCC_TIM4_CLK_ENABLE();
  gpio.Pin = FAN1_PWM_Pin | FAN2_PWM_Pin;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(FAN1_PWM_GPIO_Port, &gpio);

  TIM4->CR1 = 0U;
  TIM4->PSC = 0U;
  TIM4->ARR = FAN_PWM_TIMER_PERIOD; /* 8 MHz / 320 = 25 kHz. */
  TIM4->CCMR2 = TIM_CCMR2_OC3M_1 | TIM_CCMR2_OC3M_2 | TIM_CCMR2_OC3PE |
                TIM_CCMR2_OC4M_1 | TIM_CCMR2_OC4M_2 | TIM_CCMR2_OC4PE;
  TIM4->CCER = TIM_CCER_CC3E | TIM_CCER_CC4E;
  Fan1Pwm_SetPercent(100U);
  Fan2Pwm_SetPercent(100U);
  TIM4->EGR = TIM_EGR_UG;
  TIM4->CR1 = TIM_CR1_ARPE | TIM_CR1_CEN;
}

/* The existing Cube package omitted HAL I2C. These deliberately slow,
 * open-drain routines are sufficient for initial SHT30 bring-up at 500 Hz. */
static void I2c_Delay(void) { HAL_Delay(1U); }
static void I2c_Sda(const SoftI2cBus *bus, GPIO_PinState state)
{
  HAL_GPIO_WritePin(bus->port, bus->sda_pin, state);
}
static void I2c_Scl(const SoftI2cBus *bus, GPIO_PinState state)
{
  HAL_GPIO_WritePin(bus->port, bus->scl_pin, state);
}
static void I2c_Start(const SoftI2cBus *bus)
{
  I2c_Sda(bus, GPIO_PIN_SET); I2c_Scl(bus, GPIO_PIN_SET); I2c_Delay();
  I2c_Sda(bus, GPIO_PIN_RESET); I2c_Delay(); I2c_Scl(bus, GPIO_PIN_RESET);
}
static void I2c_Stop(const SoftI2cBus *bus)
{
  I2c_Sda(bus, GPIO_PIN_RESET); I2c_Delay(); I2c_Scl(bus, GPIO_PIN_SET);
  I2c_Delay(); I2c_Sda(bus, GPIO_PIN_SET); I2c_Delay();
}
static void I2c_Recover(const SoftI2cBus *bus)
{
  uint8_t pulse;
  I2c_Sda(bus, GPIO_PIN_SET);
  for (pulse = 0U; pulse < 9U; ++pulse)
  {
    I2c_Scl(bus, GPIO_PIN_RESET); I2c_Delay();
    I2c_Scl(bus, GPIO_PIN_SET); I2c_Delay();
  }
  I2c_Stop(bus);
}
static uint8_t I2c_WriteByte(const SoftI2cBus *bus, uint8_t value)
{
  uint8_t bit;
  for (bit = 0U; bit < 8U; ++bit)
  {
    I2c_Sda(bus, (value & 0x80U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    I2c_Delay(); I2c_Scl(bus, GPIO_PIN_SET); I2c_Delay(); I2c_Scl(bus, GPIO_PIN_RESET);
    value <<= 1U;
  }
  I2c_Sda(bus, GPIO_PIN_SET); I2c_Delay(); I2c_Scl(bus, GPIO_PIN_SET); I2c_Delay();
  bit = (HAL_GPIO_ReadPin(bus->port, bus->sda_pin) == GPIO_PIN_RESET) ? 1U : 0U;
  I2c_Scl(bus, GPIO_PIN_RESET);
  return bit;
}
static uint8_t I2c_ReadByte(const SoftI2cBus *bus, uint8_t acknowledge)
{
  uint8_t bit;
  uint8_t value = 0U;
  I2c_Sda(bus, GPIO_PIN_SET);
  for (bit = 0U; bit < 8U; ++bit)
  {
    value <<= 1U;
    I2c_Delay(); I2c_Scl(bus, GPIO_PIN_SET); I2c_Delay();
    if (HAL_GPIO_ReadPin(bus->port, bus->sda_pin) == GPIO_PIN_SET) value |= 1U;
    I2c_Scl(bus, GPIO_PIN_RESET);
  }
  I2c_Sda(bus, acknowledge ? GPIO_PIN_RESET : GPIO_PIN_SET);
  I2c_Delay(); I2c_Scl(bus, GPIO_PIN_SET); I2c_Delay(); I2c_Scl(bus, GPIO_PIN_RESET);
  I2c_Sda(bus, GPIO_PIN_SET);
  return value;
}
static uint8_t I2c_ReadRegister16(const SoftI2cBus *bus, uint8_t address,
                                  uint8_t reg, uint16_t *value)
{
  uint8_t high;
  uint8_t low;
  if (value == NULL) return 0U;
  I2c_Start(bus);
  if (!I2c_WriteByte(bus, (uint8_t)(address << 1U)) || !I2c_WriteByte(bus, reg))
  {
    I2c_Stop(bus);
    return 0U;
  }
  I2c_Start(bus);
  if (!I2c_WriteByte(bus, (uint8_t)((address << 1U) | 1U)))
  {
    I2c_Stop(bus);
    return 0U;
  }
  high = I2c_ReadByte(bus, 1U);
  low = I2c_ReadByte(bus, 0U);
  I2c_Stop(bus);
  *value = (uint16_t)(((uint16_t)high << 8U) | low);
  return 1U;
}
static uint8_t I2c_WriteRegister16(const SoftI2cBus *bus, uint8_t address,
                                   uint8_t reg, uint16_t value)
{
  I2c_Start(bus);
  if (!I2c_WriteByte(bus, (uint8_t)(address << 1U)) ||
      !I2c_WriteByte(bus, reg) ||
      !I2c_WriteByte(bus, (uint8_t)(value >> 8U)) ||
      !I2c_WriteByte(bus, (uint8_t)value))
  {
    I2c_Stop(bus);
    return 0U;
  }
  I2c_Stop(bus);
  return 1U;
}
static uint16_t Median3U16(uint16_t a, uint16_t b, uint16_t c)
{
  if (a > b) { uint16_t t = a; a = b; b = t; }
  if (b > c) { uint16_t t = b; b = c; c = t; }
  if (a > b) { uint16_t t = a; a = b; b = t; }
  return b;
}
static int16_t Median3S16(int16_t a, int16_t b, int16_t c)
{
  if (a > b) { int16_t t = a; a = b; b = t; }
  if (b > c) { int16_t t = b; b = c; c = t; }
  if (a > b) { int16_t t = a; a = b; b = t; }
  return b;
}
static uint8_t Sht30_Crc(const uint8_t *data, uint8_t length)
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
static uint8_t Sht30_Read(const SoftI2cBus *bus, uint8_t address, Sht30Reading *reading)
{
  uint8_t response[6];
  uint8_t i;
  uint16_t raw_temperature;
  uint16_t raw_humidity;

  reading->online = 0U;
  I2c_Start(bus);
  if (!I2c_WriteByte(bus, (uint8_t)(address << 1U)) ||
      !I2c_WriteByte(bus, (uint8_t)(SHT30_COMMAND_HIGH_REPEATABLE >> 8U)) ||
      !I2c_WriteByte(bus, (uint8_t)SHT30_COMMAND_HIGH_REPEATABLE))
  {
    I2c_Stop(bus); return 0U;
  }
  I2c_Stop(bus); HAL_Delay(20U); I2c_Start(bus);
  if (!I2c_WriteByte(bus, (uint8_t)((address << 1U) | 1U)))
  {
    I2c_Stop(bus); return 0U;
  }
  for (i = 0U; i < sizeof(response); ++i)
    response[i] = I2c_ReadByte(bus, i < (sizeof(response) - 1U));
  I2c_Stop(bus);
  if (Sht30_Crc(response, 2U) != response[2] || Sht30_Crc(&response[3], 2U) != response[5]) return 0U;
  raw_temperature = (uint16_t)((response[0] << 8U) | response[1]);
  raw_humidity = (uint16_t)((response[3] << 8U) | response[4]);
  reading->temperature_centi_c = (int16_t)(((int32_t)17500 * raw_temperature) / 65535 - 4500);
  reading->humidity_centi_rh = (uint16_t)(((uint32_t)10000 * raw_humidity) / 65535U);
  reading->online = 1U;
  return 1U;
}
static uint8_t Ina226_Configure(const SoftI2cBus *bus, Ina226State *state,
                                Ina226Reading *reading, uint8_t reset_first)
{
  uint16_t config;
  uint16_t calibration;
  if (!I2c_ReadRegister16(bus, INA226_ADDRESS, INA226_REG_MANUFACTURER_ID,
                          &reading->manufacturer_id) ||
      !I2c_ReadRegister16(bus, INA226_ADDRESS, INA226_REG_DIE_ID,
                          &reading->die_id))
  {
    reading->fault = INA226_FAULT_COMMUNICATION;
    return 0U;
  }
  if ((reading->manufacturer_id != INA226_MANUFACTURER_ID) ||
      ((reading->die_id & INA226_DIE_ID_MASK) != INA226_DIE_ID))
  {
    reading->fault = INA226_FAULT_IDENTITY;
    return 0U;
  }
  reading->online = 1U;
  if (reset_first != 0U)
  {
    if (!I2c_WriteRegister16(bus, INA226_ADDRESS, INA226_REG_CONFIG,
                            INA226_CONFIG_RESET))
    {
      reading->fault = INA226_FAULT_COMMUNICATION;
      return 0U;
    }
    HAL_Delay(3U);
    state->configured = 0U;
  }
  if (!I2c_ReadRegister16(bus, INA226_ADDRESS, INA226_REG_CONFIG, &config))
  {
    reading->fault = INA226_FAULT_COMMUNICATION;
    return 0U;
  }
  if ((state->configured == 0U) || (config != INA226_CONFIG_AVG16_CONTINUOUS))
  {
    if (!I2c_WriteRegister16(bus, INA226_ADDRESS, INA226_REG_CONFIG,
                            INA226_CONFIG_AVG16_CONTINUOUS))
    {
      reading->fault = INA226_FAULT_CONFIGURATION;
      return 0U;
    }
    HAL_Delay(INA226_SAMPLE_SETTLE_MS);
  }
  if (!I2c_ReadRegister16(bus, INA226_ADDRESS, INA226_REG_CONFIG,
                          &reading->config_raw) ||
      (reading->config_raw != INA226_CONFIG_AVG16_CONTINUOUS))
  {
    reading->fault = INA226_FAULT_CONFIGURATION;
    state->configured = 0U;
    return 0U;
  }
  if (!I2c_ReadRegister16(bus, INA226_ADDRESS, INA226_REG_CALIBRATION,
                          &calibration))
  {
    reading->fault = INA226_FAULT_COMMUNICATION;
    return 0U;
  }
  reading->calibration_raw = calibration;
  if (calibration != INA226_CALIBRATION_VALUE)
  {
    /* CURRENT and POWER depend on calibration, but BUS and SHUNT do not.
     * Try to restore the calibrated datapath for diagnostics; a module that
     * refuses this write is still usable through the physical R100 shunt. */
    if (I2c_WriteRegister16(bus, INA226_ADDRESS, INA226_REG_CALIBRATION,
                           INA226_CALIBRATION_VALUE))
    {
      HAL_Delay(INA226_SAMPLE_SETTLE_MS);
      if (I2c_ReadRegister16(bus, INA226_ADDRESS, INA226_REG_CALIBRATION,
                            &calibration))
        reading->calibration_raw = calibration;
    }
  }
  state->configured = 1U;
  return 1U;
}

static uint8_t Ina226_ReadSamples(const SoftI2cBus *bus,
                                  Ina226Reading *reading)
{
  uint16_t bus_samples[INA226_SAMPLE_COUNT];
  int16_t shunt_samples[INA226_SAMPLE_COUNT];
  int16_t current_samples[INA226_SAMPLE_COUNT];
  uint16_t power_samples[INA226_SAMPLE_COUNT];
  uint8_t sample;
  for (sample = 0U; sample < INA226_SAMPLE_COUNT; ++sample)
  {
    uint16_t shunt_word;
    uint16_t current_word;
    if (!I2c_ReadRegister16(bus, INA226_ADDRESS, INA226_REG_BUS_VOLTAGE,
                           &bus_samples[sample]) ||
        !I2c_ReadRegister16(bus, INA226_ADDRESS, INA226_REG_SHUNT_VOLTAGE,
                           &shunt_word) ||
        !I2c_ReadRegister16(bus, INA226_ADDRESS, INA226_REG_CURRENT,
                           &current_word) ||
        !I2c_ReadRegister16(bus, INA226_ADDRESS, INA226_REG_POWER,
                           &power_samples[sample]))
    {
      reading->fault = INA226_FAULT_COMMUNICATION;
      return 0U;
    }
    shunt_samples[sample] = (int16_t)shunt_word;
    current_samples[sample] = (int16_t)current_word;
    if ((sample + 1U) < INA226_SAMPLE_COUNT)
      HAL_Delay(INA226_SAMPLE_SETTLE_MS);
  }
  reading->bus_raw = Median3U16(bus_samples[0], bus_samples[1], bus_samples[2]);
  reading->shunt_raw = Median3S16(shunt_samples[0], shunt_samples[1],
                                  shunt_samples[2]);
  reading->current_raw = Median3S16(current_samples[0], current_samples[1],
                                    current_samples[2]);
  reading->power_raw = Median3U16(power_samples[0], power_samples[1],
                                  power_samples[2]);
  return 1U;
}

static uint8_t Ina226_Read(const SoftI2cBus *bus, Ina226State *state,
                           Ina226Reading *reading)
{
  if ((bus == NULL) || (state == NULL) || (reading == NULL)) return 0U;
  memset(reading, 0, sizeof(*reading));
  reading->fault = INA226_FAULT_COMMUNICATION;
  if (state->configured == 0U) I2c_Recover(bus);
  if (!Ina226_Configure(bus, state, reading, 0U) ||
      !Ina226_ReadSamples(bus, reading))
  {
    state->configured = 0U;
    return 0U;
  }

  if (NODE_A_INA226_SAMPLE_STUCK_03FF(reading->bus_raw, reading->shunt_raw,
                                      reading->current_raw, reading->power_raw))
  {
    /* Recover once from the exact converter-lock signature seen in the field.
     * If reset does not clear it, retain the raw diagnostics but never publish
     * those words as trustworthy voltage/current/power values. */
    state->configured = 0U;
    I2c_Recover(bus);
    if (!Ina226_Configure(bus, state, reading, 1U) ||
        !Ina226_ReadSamples(bus, reading))
      return 0U;
    if (NODE_A_INA226_SAMPLE_STUCK_03FF(reading->bus_raw, reading->shunt_raw,
                                        reading->current_raw, reading->power_raw))
    {
      reading->fault = INA226_FAULT_STUCK_03FF;
      reading->plausible = 0U;
      return 0U;
    }
  }

  reading->bus_microvolts = NODE_A_INA226_BUS_RAW_TO_UV(reading->bus_raw);
  if (g_actuator.relay_on != 0U)
  {
    reading->current_microamps =
        NODE_A_INA226_SHUNT_RAW_TO_UA(reading->shunt_raw);
    reading->power_microwatts =
        NODE_A_INA226_POWER_UW(reading->bus_microvolts,
                               reading->current_microamps);
  }
  reading->fault = INA226_FAULT_NONE;
  reading->plausible =
      (reading->bus_microvolts <= INA226_MAX_BUS_MICROVOLTS) ? 1U : 0U;
  return reading->plausible;
}

static void SendTelemetry(const Sht30Reading readings[3], uint8_t smoke_detected,
                          uint8_t flame_detected, uint8_t level_is_detected,
                          uint16_t oxygen_raw,
                          uint32_t oxygen_microvolts, uint8_t oxygen_online,
                          uint16_t methane_raw, uint32_t methane_microvolts,
                          uint8_t methane_online, uint16_t co_raw,
                          uint32_t co_microvolts, uint8_t co_online,
                          const Ina226Reading *fan1_power,
                          uint32_t fan1_rpm, const Ina226Reading *fan2_power,
                          uint32_t fan2_rpm)
{
  char message[896];
  char methane_message[640];
  char gas_status_message[768];
  char fan_message[1280];
  char fan2_message[1088];
  char actuator_message[512];
  static uint32_t sequence = 0U;
  int32_t temperature_abs;
  const char *temperature_sign;
  const char *quality;
  const char *oxygen_quality;
  const char *methane_quality;
  const char *co_quality;
  const char *fan_quality;
  const char *current_sign;
  const char *power_sign;
  int32_t current_abs;
  int32_t power_abs;
  int length;

  /* Slot 1 is the physically installed environmental sensor.  Report only
   * that truthful source in the platform contract; Slots 2/3 are reserved
   * buses and must not create fabricated zero-value readings. */
  sequence++;
  temperature_abs = readings[0].temperature_centi_c;
  temperature_sign = "";
  if (temperature_abs < 0)
  {
    temperature_sign = "-";
    temperature_abs = -temperature_abs;
  }
  quality = readings[0].online ? "good" : "missing";
  /* The unamplified AO-02 signal uses only a few ADC codes. Keep the trial
   * readings explicitly suspect until a precision ADC/front end is fitted. */
  oxygen_quality = oxygen_online ? "suspect" : "missing";
  methane_quality = methane_online ? "suspect" : "missing";
  co_quality = co_online ? "suspect" : "missing";
  fan_quality = ((fan1_power != NULL) && fan1_power->online) ?
                (fan1_power->plausible ? "good" : "suspect") : "missing";
  current_abs = ((fan1_power != NULL) ? fan1_power->current_microamps : 0L);
  power_abs = ((fan1_power != NULL) ? fan1_power->power_microwatts : 0L);
  current_sign = (current_abs < 0L) ? "-" : "";
  power_sign = (power_abs < 0L) ? "-" : "";
  if (current_abs < 0L) current_abs = -current_abs;
  if (power_abs < 0L) power_abs = -power_abs;
  length = snprintf(message, sizeof(message),
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
    "{\"assetCode\":\"ENV-01\",\"metric\":\"temperature\",\"value\":%s%ld.%02ld,\"unit\":\"degC\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"ENV-01\",\"metric\":\"humidity\",\"value\":%lu.%02lu,\"unit\":\"%%RH\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"smoke.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"flame.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"LEVEL-L01\",\"metric\":\"level.detected\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"oxygen.raw\",\"value\":%u,\"unit\":\"adc\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"oxygen.voltage\",\"value\":%lu.%03lu,\"unit\":\"mV\",\"quality\":\"%s\"}]}\r\n",
    (unsigned long)sequence,
    temperature_sign, (long)(temperature_abs / 100), (long)(temperature_abs % 100), quality,
    (unsigned long)(readings[0].humidity_centi_rh / 100U),
    (unsigned long)(readings[0].humidity_centi_rh % 100U), quality,
    (unsigned int)smoke_detected, (unsigned int)flame_detected,
    (unsigned int)level_is_detected,
    (unsigned int)oxygen_raw, oxygen_quality,
    (unsigned long)(oxygen_microvolts / 1000UL),
    (unsigned long)(oxygen_microvolts % 1000UL), oxygen_quality);
  if (length > 0 && length < (int)sizeof(message))
  {
    (void)HAL_UART_Transmit(&huart2, (uint8_t *)message, (uint16_t)length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message, (uint16_t)length, 1000U);
  }
  while (esp_rx_count != 0U) Command_Poll();
  length = snprintf(methane_message, sizeof(methane_message),
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
    "{\"assetCode\":\"GAS-01\",\"metric\":\"flame.rawLevel\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"methane.raw\",\"value\":%u,\"unit\":\"adc\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"methane.voltage\",\"value\":%lu.%03lu,\"unit\":\"mV\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"co.raw\",\"value\":%u,\"unit\":\"adc\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"co.voltage\",\"value\":%lu.%03lu,\"unit\":\"mV\",\"quality\":\"%s\"}]}\r\n",
    (unsigned long)sequence, (unsigned int)flame_raw_level,
    (unsigned int)methane_raw, methane_quality,
    (unsigned long)(methane_microvolts / 1000UL),
    (unsigned long)(methane_microvolts % 1000UL), methane_quality,
    (unsigned int)co_raw, co_quality,
    (unsigned long)(co_microvolts / 1000UL),
    (unsigned long)(co_microvolts % 1000UL), co_quality);
  if (length > 0 && length < (int)sizeof(methane_message))
  {
    (void)HAL_UART_Transmit(&huart2, (uint8_t *)methane_message, (uint16_t)length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)methane_message, (uint16_t)length, 1000U);
  }
  while (esp_rx_count != 0U) Command_Poll();
  length = snprintf(gas_status_message, sizeof(gas_status_message),
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
    "{\"assetCode\":\"GAS-01\",\"metric\":\"oxygen.warning\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"oxygen.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"methane.warning\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"methane.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"co.warning\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"GAS-01\",\"metric\":\"co.alarm\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"}]}\r\n",
    (unsigned long)sequence,
    (unsigned int)oxygen_warning, (unsigned int)oxygen_alarm,
    (unsigned int)methane_warning, (unsigned int)methane_alarm,
    (unsigned int)co_warning, (unsigned int)co_alarm);
  if (length > 0 && length < (int)sizeof(gas_status_message))
  {
    (void)HAL_UART_Transmit(&huart2, (uint8_t *)gas_status_message, (uint16_t)length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)gas_status_message, (uint16_t)length, 1000U);
  }
  while (esp_rx_count != 0U) Command_Poll();
  length = snprintf(fan_message, sizeof(fan_message),
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
    "{\"assetCode\":\"FAN-01\",\"metric\":\"supply.voltage\",\"value\":%lu.%03lu,\"unit\":\"V\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"FAN-01\",\"metric\":\"motor.current\",\"value\":%s%ld.%03ld,\"unit\":\"mA\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"FAN-01\",\"metric\":\"power\",\"value\":%s%ld.%03ld,\"unit\":\"W\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"FAN-01\",\"metric\":\"rotational.speed\",\"value\":%lu,\"unit\":\"rpm\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-01\",\"metric\":\"target.dutyPercent\",\"value\":%u,\"unit\":\"percent\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-01\",\"metric\":\"relay\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-01\",\"metric\":\"control.autoVentilation\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-01\",\"metric\":\"control.cooldown\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"}],"
    "\"diag\":{\"uart2RxBytes\":%lu,\"uart2Lines\":%lu,\"uart2Drops\":%lu,"
    "\"inaBusRaw\":%u,\"inaShuntRaw\":%d,\"inaCurrentRaw\":%d,"
    "\"inaPowerRaw\":%u,\"inaCalibration\":%u,\"inaManufacturer\":%u,"
    "\"inaDieId\":%u,\"inaConfig\":%u,\"inaFault\":%u,"
    "\"relayActive\":%u,\"pwmPercent\":%u}}\r\n",
    (unsigned long)sequence,
    (unsigned long)((fan1_power != NULL) ? fan1_power->bus_microvolts / 1000000UL : 0UL),
    (unsigned long)((fan1_power != NULL) ? (fan1_power->bus_microvolts % 1000000UL) / 1000UL : 0UL), fan_quality,
    current_sign, (long)(current_abs / 1000L), (long)(current_abs % 1000L), fan_quality,
    power_sign, (long)(power_abs / 1000000L), (long)((power_abs % 1000000L) / 1000L), fan_quality,
    (unsigned long)fan1_rpm, (unsigned int)g_actuator.fan1_pwm_percent,
    (unsigned int)g_actuator.relay_on, (unsigned int)gas_ventilation_active,
    (unsigned int)gas_ventilation_cooling,
    (unsigned long)esp_rx_bytes, (unsigned long)esp_rx_completed_lines,
    (unsigned long)esp_rx_dropped_lines,
    (unsigned int)((fan1_power != NULL) ? fan1_power->bus_raw : 0U),
    (int)((fan1_power != NULL) ? fan1_power->shunt_raw : 0),
    (int)((fan1_power != NULL) ? fan1_power->current_raw : 0),
    (unsigned int)((fan1_power != NULL) ? fan1_power->power_raw : 0U),
    (unsigned int)((fan1_power != NULL) ? fan1_power->calibration_raw : 0U),
    (unsigned int)((fan1_power != NULL) ? fan1_power->manufacturer_id : 0U),
    (unsigned int)((fan1_power != NULL) ? fan1_power->die_id : 0U),
    (unsigned int)((fan1_power != NULL) ? fan1_power->config_raw : 0U),
    (unsigned int)((fan1_power != NULL) ? fan1_power->fault : INA226_FAULT_COMMUNICATION),
    (unsigned int)g_actuator.relay_on, (unsigned int)g_actuator.fan1_pwm_percent);
  if (length > 0 && length < (int)sizeof(fan_message))
  {
    (void)HAL_UART_Transmit(&huart2, (uint8_t *)fan_message, (uint16_t)length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)fan_message, (uint16_t)length, 1000U);
  }
  while (esp_rx_count != 0U) Command_Poll();

  fan_quality = ((fan2_power != NULL) && fan2_power->online) ?
                (fan2_power->plausible ? "good" : "suspect") : "missing";
  current_abs = ((fan2_power != NULL) ? fan2_power->current_microamps : 0L);
  power_abs = ((fan2_power != NULL) ? fan2_power->power_microwatts : 0L);
  current_sign = (current_abs < 0L) ? "-" : "";
  power_sign = (power_abs < 0L) ? "-" : "";
  if (current_abs < 0L) current_abs = -current_abs;
  if (power_abs < 0L) power_abs = -power_abs;
  length = snprintf(fan2_message, sizeof(fan2_message),
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
    "{\"assetCode\":\"FAN-02\",\"metric\":\"supply.voltage\",\"value\":%lu.%03lu,\"unit\":\"V\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"FAN-02\",\"metric\":\"motor.current\",\"value\":%s%ld.%03ld,\"unit\":\"mA\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"FAN-02\",\"metric\":\"power\",\"value\":%s%ld.%03ld,\"unit\":\"W\",\"quality\":\"%s\"},"
    "{\"assetCode\":\"FAN-02\",\"metric\":\"rotational.speed\",\"value\":%lu,\"unit\":\"rpm\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-02\",\"metric\":\"target.dutyPercent\",\"value\":%u,\"unit\":\"percent\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-02\",\"metric\":\"relay\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-02\",\"metric\":\"control.autoVentilation\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"FAN-02\",\"metric\":\"control.cooldown\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"}],"
    "\"diag\":{\"inaBusRaw\":%u,\"inaCurrentRaw\":%d,\"inaPowerRaw\":%u,"
    "\"inaCalibration\":%u,\"inaManufacturer\":%u,\"inaDieId\":%u,"
    "\"inaConfig\":%u,\"inaFault\":%u,\"relayActive\":%u,"
    "\"pwmPercent\":%u}}\r\n",
    (unsigned long)sequence,
    (unsigned long)((fan2_power != NULL) ? fan2_power->bus_microvolts / 1000000UL : 0UL),
    (unsigned long)((fan2_power != NULL) ? (fan2_power->bus_microvolts % 1000000UL) / 1000UL : 0UL), fan_quality,
    current_sign, (long)(current_abs / 1000L), (long)(current_abs % 1000L), fan_quality,
    power_sign, (long)(power_abs / 1000000L), (long)((power_abs % 1000000L) / 1000L), fan_quality,
    (unsigned long)fan2_rpm, (unsigned int)g_actuator.fan2_pwm_percent,
    (unsigned int)g_actuator.relay_on, (unsigned int)gas_ventilation_active,
    (unsigned int)gas_ventilation_cooling,
    (unsigned int)((fan2_power != NULL) ? fan2_power->bus_raw : 0U),
    (int)((fan2_power != NULL) ? fan2_power->current_raw : 0),
    (unsigned int)((fan2_power != NULL) ? fan2_power->power_raw : 0U),
    (unsigned int)((fan2_power != NULL) ? fan2_power->calibration_raw : 0U),
    (unsigned int)((fan2_power != NULL) ? fan2_power->manufacturer_id : 0U),
    (unsigned int)((fan2_power != NULL) ? fan2_power->die_id : 0U),
    (unsigned int)((fan2_power != NULL) ? fan2_power->config_raw : 0U),
    (unsigned int)((fan2_power != NULL) ? fan2_power->fault : INA226_FAULT_COMMUNICATION),
    (unsigned int)g_actuator.relay_on, (unsigned int)g_actuator.fan2_pwm_percent);
  if (length > 0 && length < (int)sizeof(fan2_message))
  {
    (void)HAL_UART_Transmit(&huart2, (uint8_t *)fan2_message, (uint16_t)length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)fan2_message, (uint16_t)length, 1000U);
  }
  while (esp_rx_count != 0U) Command_Poll();
  length = snprintf(actuator_message, sizeof(actuator_message),
    "{\"schema\":\"ut.telemetry.v1\",\"seq\":%lu,\"readings\":["
    "{\"assetCode\":\"CTRL-01\",\"metric\":\"led.mode\",\"value\":%u,\"unit\":\"enum\",\"quality\":\"good\"},"
    "{\"assetCode\":\"CTRL-01\",\"metric\":\"led.brightnessPercent\",\"value\":%u,\"unit\":\"percent\",\"quality\":\"good\"},"
    "{\"assetCode\":\"CTRL-01\",\"metric\":\"buzzer.active\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"},"
    "{\"assetCode\":\"CTRL-01\",\"metric\":\"buzzer.muted\",\"value\":%u,\"unit\":\"bool\",\"quality\":\"good\"}]}\r\n",
    (unsigned long)sequence,
    (unsigned int)g_actuator.led_mode, (unsigned int)g_actuator.led_brightness_percent,
    (unsigned int)g_actuator.buzzer_on, (unsigned int)g_actuator.buzzer_muted);
  if (length > 0 && length < (int)sizeof(actuator_message))
  {
    (void)HAL_UART_Transmit(&huart2, (uint8_t *)actuator_message, (uint16_t)length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)actuator_message, (uint16_t)length, 1000U);
  }
  while (esp_rx_count != 0U) Command_Poll();
}

/* MH-FMG is a high-level-triggered active buzzer.  PB0 is deliberately
 * dedicated to it and starts low so a reset cannot leave the buzzer sounding. */
static void Buzzer_Silence(void)
{
  HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_RESET);
  g_actuator.buzzer_on = 0U;
}

static void Buzzer_Start(uint32_t duration_ms)
{
  HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_SET);
  buzzer_started_at = HAL_GetTick();
  buzzer_duration_ms = duration_ms;
  g_actuator.buzzer_on = 1U;
}

/* The installed relay module is set to high-level trigger.  PA1 is held low
 * before it is configured as an output, so power-up, timeout and safe-state are off. */
static void Relay_Disable(void)
{
  HAL_GPIO_WritePin(RELAY_GPIO_Port, RELAY_Pin, GPIO_PIN_RESET);
  g_actuator.relay_on = 0U;
}

static void Relay_Enable(uint32_t duration_ms)
{
  HAL_GPIO_WritePin(RELAY_GPIO_Port, RELAY_Pin, GPIO_PIN_SET);
  relay_started_at = HAL_GetTick();
  relay_duration_ms = duration_ms;
  g_actuator.relay_on = 1U;
}

/* The MQ board comparator is powered from 5 V and its DO output is divided
 * to 3.3 V before PB12.  LM393 pulls DO low when the trimmer threshold is
 * crossed, so a stable low level is the local smoke alarm. */
static void Smoke_Poll(uint32_t now)
{
  uint8_t raw_alarm;
  uint8_t next_alarm;

  if ((now - smoke_last_sample_at) < SMOKE_SAMPLE_INTERVAL_MS) return;
  smoke_last_sample_at = now;
  raw_alarm = (HAL_GPIO_ReadPin(SMOKE_GPIO_Port, SMOKE_Pin) == GPIO_PIN_RESET) ? 1U : 0U;
  if (raw_alarm != 0U)
  {
    if (smoke_active_samples < SMOKE_STABLE_SAMPLE_COUNT) ++smoke_active_samples;
  }
  else
    smoke_active_samples = 0U;

  next_alarm = (smoke_active_samples >= SMOKE_STABLE_SAMPLE_COUNT) ? 1U : 0U;
  if (next_alarm == smoke_alarm) return;
  smoke_alarm = next_alarm;
  if (smoke_alarm != 0U)
  {
    /* A new alarm invalidates any user mute and stops a timed buzzer so the
     * local safety indication remains independent of the network path. */
    NodeACommand_AlarmActivated(&g_actuator);
    Buzzer_Start(0xFFFFFFFFUL);
    Led_Render(now);
  }
  else
  {
    if ((flame_alarm == 0U) && (gas_alarm == 0U))
    {
      Buzzer_Silence();
      Led_Render(now);
    }
  }
}

/* The 3.3 V LM393 flame module drives PB14 directly. Its comparator output
 * is active-low when the trimmer threshold is crossed. Fire assertion is
 * immediate; the alarm is held long enough to survive slow sensor/telemetry
 * work and to guarantee that at least one cloud telemetry cycle observes it. */
static void Flame_Poll(uint32_t now)
{
  uint8_t raw_detected;

  if ((now - flame_last_sample_at) < FLAME_SAMPLE_INTERVAL_MS) return;
  flame_last_sample_at = now;
  flame_raw_level = (HAL_GPIO_ReadPin(FLAME_GPIO_Port, FLAME_Pin) == GPIO_PIN_SET) ? 1U : 0U;
  raw_detected = (flame_raw_level == 0U) ? 1U : 0U;
  if (raw_detected != 0U)
  {
    flame_last_detected_at = now;
    if (flame_alarm == 0U)
    {
      flame_alarm = 1U;
      NodeACommand_AlarmActivated(&g_actuator);
      Buzzer_Start(0xFFFFFFFFUL);
      Led_Render(now);
    }
    return;
  }
  if ((flame_alarm != 0U) &&
      ((now - flame_last_detected_at) >= FLAME_ALARM_HOLD_MS))
  {
    flame_alarm = 0U;
    if ((smoke_alarm == 0U) && (gas_alarm == 0U))
    {
      Buzzer_Silence();
      Led_Render(now);
    }
  }
}

/* The liquid-level module runs from 5 V. Its DO signal passes through an
 * external 10 kOhm / 10 kOhm divider before PC0, and is sampled only as a
 * digital input. The first bench assumption is low=liquid detected; the
 * four-sample debounce applies to both wet and dry transitions. */
static void Level_Poll(uint32_t now)
{
  uint8_t raw_detected;

  if ((now - level_last_sample_at) < LEVEL_SAMPLE_INTERVAL_MS) return;
  level_last_sample_at = now;
  raw_detected = (HAL_GPIO_ReadPin(LEVEL_GPIO_Port, LEVEL_Pin) == GPIO_PIN_RESET) ? 1U : 0U;
  if (raw_detected != level_candidate)
  {
    level_candidate = raw_detected;
    level_candidate_samples = 1U;
  }
  else if (level_candidate_samples < LEVEL_STABLE_SAMPLE_COUNT)
    ++level_candidate_samples;

  if (level_candidate_samples >= LEVEL_STABLE_SAMPLE_COUNT)
    level_detected = level_candidate;
}

/* SPI2 on PB15 runs at 4 MHz from the 8 MHz APB1 clock.  Each WS2812 bit is
 * encoded as five SPI bits: 0=10000 and 1=11100, giving a 1.25 us cell. */
static uint8_t *Ws2812_EncodeByte(uint8_t value, uint8_t *output,
                                  uint8_t *pending, uint8_t *pending_bits)
{
  uint8_t source_bit;
  for (source_bit = 0x80U; source_bit != 0U; source_bit >>= 1U)
  {
    uint8_t encoded = ((value & source_bit) != 0U) ? 0x1CU : 0x10U;
    uint8_t encoded_bit;
    for (encoded_bit = 0x10U; encoded_bit != 0U; encoded_bit >>= 1U)
    {
      *pending = (uint8_t)((*pending << 1U) | (((encoded & encoded_bit) != 0U) ? 1U : 0U));
      if (++(*pending_bits) == 8U)
      {
        *output++ = *pending;
        *pending = 0U;
        *pending_bits = 0U;
      }
    }
  }
  return output;
}

static void MX_WS2812_SPI_Init(void)
{
  GPIO_InitTypeDef gpio = {0};
  __HAL_RCC_DMA1_CLK_ENABLE();
  __HAL_RCC_SPI2_CLK_ENABLE();
  gpio.Pin = WS2812_Pin;
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(WS2812_GPIO_Port, &gpio);
  SPI2->CR1 = SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI;
  SPI2->CR2 = 0U;
  SPI2->CR1 |= SPI_CR1_SPE;
}

static void Ws2812_SendEncoded(uint16_t length)
{
  /* Keep MOSI low for one complete SPI byte before DMA begins.  This prevents
   * the first WS2812 high pulse from inheriting the SPI start half-cycle. */
  while ((SPI2->SR & SPI_SR_TXE) == 0U) { }
  *(__IO uint8_t *)&SPI2->DR = 0U;
  while ((SPI2->SR & SPI_SR_BSY) != 0U) { }
  (void)SPI2->DR;
  (void)SPI2->SR;

  DMA1_Channel5->CCR = 0U;
  DMA1_Channel5->CNDTR = length;
  DMA1_Channel5->CPAR = (uint32_t)&SPI2->DR;
  DMA1_Channel5->CMAR = (uint32_t)ws2812_encoded;
  DMA1_Channel5->CCR = DMA_CCR_DIR | DMA_CCR_MINC | DMA_CCR_PL_1;
  SPI2->CR2 |= SPI_CR2_TXDMAEN;
  DMA1_Channel5->CCR |= DMA_CCR_EN;
  while (DMA1_Channel5->CNDTR != 0U) { }
  while ((SPI2->SR & SPI_SR_BSY) != 0U) { }
  DMA1_Channel5->CCR = 0U;
  SPI2->CR2 &= ~SPI_CR2_TXDMAEN;
  (void)SPI2->DR;
  (void)SPI2->SR;
}

static void Ws2812_Show(uint8_t red, uint8_t green, uint8_t blue)
{
  uint8_t *output = ws2812_encoded;
  uint8_t pending = 0U;
  uint8_t pending_bits = 0U;
  uint8_t pixel;

  for (pixel = 0U; pixel < WS2812_PIXEL_COUNT; ++pixel)
  {
    output = Ws2812_EncodeByte(green, output, &pending, &pending_bits); /* WS2812B serial order is GRB. */
    output = Ws2812_EncodeByte(red, output, &pending, &pending_bits);
    output = Ws2812_EncodeByte(blue, output, &pending, &pending_bits);
  }
  Ws2812_SendEncoded((uint16_t)(output - ws2812_encoded));
  HAL_Delay(1U); /* Low reset interval exceeds the WS2812B latch requirement. */
}

static uint8_t Led_BreathLevel(uint32_t now)
{
  const uint32_t phase = now % 3000U;
  if (phase < 1500U) return (uint8_t)((phase * 255U) / 1500U);
  return (uint8_t)(((3000U - phase) * 255U) / 1500U);
}

static void Led_ColorForMode(uint8_t mode, uint8_t brightness_percent,
                             uint32_t now, uint8_t *red, uint8_t *green,
                             uint8_t *blue)
{
  const uint8_t scale =
      (uint8_t)(((uint32_t)brightness_percent * 255U) / 100U);
  uint8_t level = scale;

  if (mode == NODE_A_LED_BREATHE)
    level = (uint8_t)(((uint32_t)Led_BreathLevel(now) * scale) / 255U);
  else if (mode == NODE_A_LED_FLASH)
    level = ((now / 500U) & 1U) ? scale : 0U;

  *red = 0U;
  *green = 0U;
  *blue = 0U;
  switch (mode)
  {
    case NODE_A_LED_WHITE:   *red = *green = *blue = level; break;
    case NODE_A_LED_GREEN:   *green = level; break;
    case NODE_A_LED_YELLOW:  *red = level; *green = level / 2U; break;
    case NODE_A_LED_RED:     *red = level; break;
    case NODE_A_LED_BLUE:    *blue = level; break;
    case NODE_A_LED_BREATHE: *red = *green = *blue = level; break; /* white breath */
    case NODE_A_LED_FLASH:   *red = *green = *blue = level; break; /* white flash */
    default: break; /* off */
  }
}

/* Safety always owns the LED: an alarm forces red, a gas warning forces
 * yellow, and only a fully clear state renders the user-commanded mode. */
static void Led_Render(uint32_t now)
{
  uint8_t red;
  uint8_t green;
  uint8_t blue;

  if ((smoke_alarm != 0U) || (flame_alarm != 0U) || (gas_alarm != 0U))
  {
    Ws2812_Show(WS2812_TEST_BRIGHTNESS, 0U, 0U);
    return;
  }
  if (gas_warning != 0U)
  {
    Ws2812_Show(WS2812_TEST_BRIGHTNESS, WS2812_TEST_BRIGHTNESS / 2U, 0U);
    return;
  }
  Led_ColorForMode(g_actuator.led_mode, g_actuator.led_brightness_percent, now,
                   &red, &green, &blue);
  Ws2812_Show(red, green, blue);
}

static uint8_t Command_IsForThisController(const char *topic)
{
  static const char command_topic[] = "ut/v1/CTRL-01/cmd";
  const size_t length = sizeof(command_topic) - 1U;
  return (strncmp(topic, command_topic, length) == 0) &&
         ((topic[length] == '\0') || (topic[length] == '/'));
}

static void Safety_Snapshot(NodeASafetyState *safety)
{
  safety->smoke_alarm = (smoke_alarm != 0U) || (test_safety_smoke != 0U);
  safety->flame_alarm = (flame_alarm != 0U) || (test_safety_flame != 0U);
  safety->gas_alarm = (gas_alarm != 0U) || (test_safety_gas != 0U);
  safety->gas_warning = gas_warning;
  safety->gas_ventilation_active =
      (gas_ventilation_active != 0U) || (test_safety_vent != 0U);
}

static void Command_SendAck(const char *command_id, const char *status,
                            const char *reason, uint32_t applied_value)
{
  char json[192];
  size_t length = NodeACommand_FormatAck(json, sizeof(json), command_id,
                                         status, reason, applied_value);
  if ((length > 0U) && ((length + 2U) <= sizeof(json)))
  {
    json[length++] = '\r';
    json[length++] = '\n';
    (void)HAL_UART_Transmit(&huart2, (uint8_t *)json, (uint16_t)length, 1000U);
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)json, (uint16_t)length, 1000U);
  }
}

static void CommitActuators(const NodeACommand *command, uint32_t now,
                            const NodeAActuatorState *before)
{
  const uint32_t elapsed_ms = now - command->received_at_ms;

  /* PWM is idempotent, so re-applying the committed duty is always safe. */
  Fan1Pwm_SetPercent(g_actuator.fan1_pwm_percent);
  Fan2Pwm_SetPercent(g_actuator.fan2_pwm_percent);

  /* Timed actuators are only re-armed when the command changed their state, so
   * a read-only `status` command can never reset an active relay/buzzer timer. */
  if (g_actuator.relay_on != before->relay_on)
  {
    if (g_actuator.relay_on != 0U)
    {
      const uint32_t duration =
          (command->action == NODE_A_ACTION_FANS_BOTH_START)
              ? 0xFFFFFFFFUL : (command->ttl_ms - elapsed_ms);
      Relay_Enable(duration);
    }
    else
      Relay_Disable();
  }
  if (g_actuator.buzzer_on != before->buzzer_on)
  {
    if (g_actuator.buzzer_on != 0U)
    {
      const uint32_t duration =
          (command->action == NODE_A_ACTION_BUZZER_TEST)
              ? BUZZER_TEST_DURATION_MS : (command->ttl_ms - elapsed_ms);
      Buzzer_Start(duration);
    }
    else
      Buzzer_Silence();
  }
  if ((g_actuator.led_mode != before->led_mode) ||
      (g_actuator.led_brightness_percent != before->led_brightness_percent))
    Led_Render(now);
}

/* Every Web, IoTDA and menu-originated `ut.command.v1` command passes through
 * this single dispatcher path: parse, dedup, TTL/safety/value decision, then
 * commit and acknowledge only after the in-memory state is accepted. */
static void Command_ProcessPayload(const char *payload, uint32_t received_at)
{
  NodeACommand command;
  NodeASafetyState safety;
  NodeAActuatorState before;
  NodeAActuatorState next;
  NodeACommandResult result;
  uint32_t now;

  if (!NodeACommand_ParseHeader(payload, &command))
  {
    Command_SendAck("unknown", "rejected", "invalid_command", 0U);
    return;
  }
  if (NodeACommand_IsDuplicate(&command_dedup, command.command_id))
  {
    Command_SendAck(command.command_id, "duplicate", "cmdId_seen", 0U);
    return;
  }
  if (!NodeACommand_ParseBody(payload, &command))
  {
    NodeACommand_Remember(&command_dedup, command.command_id);
    Command_SendAck(command.command_id, "rejected", "invalid_or_missing_ttl", 0U);
    return;
  }

  command.received_at_ms = received_at;
  now = HAL_GetTick();
  Safety_Snapshot(&safety);
  before = g_actuator;
  next = before;
  result = NodeACommand_Apply(&command, now, &safety, &next);

  if (result.status == NODE_A_STATUS_EXPIRED)
  {
    NodeACommand_Remember(&command_dedup, command.command_id);
    Command_SendAck(command.command_id, "expired", "ttl_elapsed", 0U);
    return;
  }
  if (result.status == NODE_A_STATUS_REJECTED)
  {
    NodeACommand_Remember(&command_dedup, command.command_id);
    Command_SendAck(command.command_id, "rejected", result.reason, 0U);
    return;
  }

  NodeACommand_Remember(&command_dedup, command.command_id);
  g_actuator = next;
  CommitActuators(&command, now, &before);
  Command_SendAck(command.command_id, "accepted", result.reason,
                  result.applied_value);
}

static void Command_HandleLine(char *line, uint32_t received_at)
{
  char *topic;
  char *payload;

  if (strncmp(line, "MQTT|", 5U) != 0) return;
  topic = line + 5U;
  payload = strchr(topic, '|');
  if (payload == NULL) return;
  *payload++ = '\0';
  if (!Command_IsForThisController(topic)) return;
  Command_ProcessPayload(payload, received_at);
}

static void Command_Poll(void)
{
  char line[ESP_RX_LINE_SIZE];
  uint16_t length;
  uint32_t received_at;

  if (esp_rx_count == 0U) return;
  __disable_irq();
  length = esp_rx_lengths[esp_rx_head];
  if (length >= sizeof(line)) length = sizeof(line) - 1U;
  (void)memcpy(line, (const void *)esp_rx_lines[esp_rx_head], length);
  line[length] = '\0';
  received_at = esp_rx_received_at[esp_rx_head];
  esp_rx_head = (uint8_t)((esp_rx_head + 1U) % ESP_RX_QUEUE_CAPACITY);
  --esp_rx_count;
  __enable_irq();
  Command_HandleLine(line, received_at);
}

static void NodeTest_ReportState(void)
{
  char message[160];
  const int length = snprintf(message, sizeof(message),
    "#STATE fan1=%u fan2=%u relay=%u buzzer=%u muted=%u led_mode=%u led_bright=%u smoke=%u flame=%u gas=%u vent=%u\r\n",
    (unsigned int)g_actuator.fan1_pwm_percent,
    (unsigned int)g_actuator.fan2_pwm_percent,
    (unsigned int)g_actuator.relay_on, (unsigned int)g_actuator.buzzer_on,
    (unsigned int)g_actuator.buzzer_muted, (unsigned int)g_actuator.led_mode,
    (unsigned int)g_actuator.led_brightness_percent,
    (unsigned int)((smoke_alarm != 0U) || (test_safety_smoke != 0U)),
    (unsigned int)((flame_alarm != 0U) || (test_safety_flame != 0U)),
    (unsigned int)((gas_alarm != 0U) || (test_safety_gas != 0U)),
    (unsigned int)((gas_ventilation_active != 0U) || (test_safety_vent != 0U)));
  if ((length > 0) && (length < (int)sizeof(message)))
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message, (uint16_t)length, 1000U);
}

static void NodeTest_HandleLine(void)
{
  unsigned int smoke;
  unsigned int flame;
  unsigned int gas;
  unsigned int vent;

  if (strcmp(node_test_line, "#NODETEST RESET") == 0)
  {
    NodeACommand_DedupInit(&command_dedup);
    g_actuator.fan1_pwm_percent = 100U;
    g_actuator.fan2_pwm_percent = 100U;
    g_actuator.relay_on = 0U;
    g_actuator.buzzer_on = 0U;
    g_actuator.buzzer_muted = 0U;
    g_actuator.led_mode = NODE_A_LED_OFF;
    g_actuator.led_brightness_percent = 100U;
    test_safety_smoke = 0U;
    test_safety_flame = 0U;
    test_safety_gas = 0U;
    test_safety_vent = 0U;
    Fan1Pwm_SetPercent(g_actuator.fan1_pwm_percent);
    Fan2Pwm_SetPercent(g_actuator.fan2_pwm_percent);
    Buzzer_Silence();
    Relay_Disable();
    Led_Render(HAL_GetTick());
    NodeTest_ReportState();
    return;
  }
  if (sscanf(node_test_line, "#NODETEST SAFETY %u %u %u %u",
             &smoke, &flame, &gas, &vent) == 4)
  {
    if ((smoke > 1U) || (flame > 1U) || (gas > 1U) || (vent > 1U)) return;
    test_safety_smoke = (uint8_t)smoke;
    test_safety_flame = (uint8_t)flame;
    test_safety_gas = (uint8_t)gas;
    test_safety_vent = (uint8_t)vent;
    NodeTest_ReportState();
    return;
  }
  if (strncmp(node_test_line, "#NODETEST CMD ", 14U) == 0)
  {
    Command_ProcessPayload(node_test_line + 14U, HAL_GetTick());
    return;
  }
  if (strcmp(node_test_line, "#NODETEST TELEMETRY") == 0)
  {
    test_force_telemetry = 1U;
    return;
  }
  if (strcmp(node_test_line, "#NODETEST STATE") == 0)
  {
    NodeTest_ReportState();
    return;
  }
}

static void NodeTest_Poll(void)
{
  uint8_t character;

  while (HAL_UART_Receive(&huart1, &character, 1U, 0U) == HAL_OK)
  {
    if (character == '\n')
    {
      node_test_line[node_test_length] = '\0';
      NodeTest_HandleLine();
      node_test_length = 0U;
    }
    else if (character != '\r')
    {
      if (node_test_length < (NODE_TEST_LINE_SIZE - 1U))
        node_test_line[node_test_length++] = (char)character;
      else
        node_test_length = 0U;
    }
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
  if (uart->Instance != USART2) return;
  ++esp_rx_bytes;
  if (esp_rx_character == '\n')
  {
    if ((esp_rx_discarding == 0U) && (esp_rx_length > 0U))
    {
      ++esp_rx_completed_lines;
      /* ESP diagnostic replies such as #PUBLISHED share USART2 with downlink
       * commands.  They must never occupy the bounded command queue. */
      if ((esp_rx_length >= 5U) &&
          (esp_rx_lines[esp_rx_tail][0] == 'M') &&
          (esp_rx_lines[esp_rx_tail][1] == 'Q') &&
          (esp_rx_lines[esp_rx_tail][2] == 'T') &&
          (esp_rx_lines[esp_rx_tail][3] == 'T') &&
          (esp_rx_lines[esp_rx_tail][4] == '|'))
      {
        if (esp_rx_count < ESP_RX_QUEUE_CAPACITY)
        {
          esp_rx_lengths[esp_rx_tail] = esp_rx_length;
          esp_rx_received_at[esp_rx_tail] = HAL_GetTick();
          esp_rx_tail = (uint8_t)((esp_rx_tail + 1U) % ESP_RX_QUEUE_CAPACITY);
          ++esp_rx_count;
        }
        else
          ++esp_rx_dropped_lines;
      }
    }
    else if (esp_rx_discarding != 0U)
      ++esp_rx_dropped_lines;
    esp_rx_length = 0U;
    esp_rx_discarding = 0U;
  }
  else if ((esp_rx_character != '\r') && (esp_rx_discarding == 0U))
  {
    if (esp_rx_count >= ESP_RX_QUEUE_CAPACITY) esp_rx_discarding = 1U;
    else if (esp_rx_length < (ESP_RX_LINE_SIZE - 1U))
      esp_rx_lines[esp_rx_tail][esp_rx_length++] = (char)esp_rx_character;
    else { esp_rx_length = 0U; esp_rx_discarding = 1U; }
  }
  (void)HAL_UART_Receive_IT(&huart2, &esp_rx_character, 1U);
}

int main(void)
{
  Sht30Reading readings[3] = {0};
  uint16_t oxygen_raw = 0U;
  uint32_t oxygen_microvolts = 0UL;
  uint8_t oxygen_online = 0U;
  uint16_t methane_raw = 0U;
  uint32_t methane_microvolts = 0UL;
  uint8_t methane_online = 0U;
  uint16_t co_raw = 0U;
  uint32_t co_microvolts = 0UL;
  uint8_t co_online = 0U;
  GasAdcFilter oxygen_filter = {0};
  GasAdcFilter methane_filter = {0};
  GasAdcFilter co_filter = {0};
  Ina226Reading fan_power = {0};
  Ina226Reading fan2_power = {0};
  uint32_t fan_rpm = 0U;
  uint32_t fan2_rpm = 0U;
  uint32_t last_telemetry = HAL_MAX_DELAY;
  uint32_t last_led = HAL_MAX_DELAY;
  uint32_t last_led_anim = HAL_MAX_DELAY;

  HAL_Init(); SystemClock_Config(); MX_GPIO_Init(); MX_FAN1_PWM_Init(); MX_WS2812_SPI_Init();
  fan1_tach_last_sample_at = HAL_GetTick();
  fan2_tach_last_sample_at = fan1_tach_last_sample_at;
  NodeACommand_DedupInit(&command_dedup);
  Led_Render(HAL_GetTick());
  MX_ADC1_Init();
  if (HAL_ADCEx_Calibration_Start(&hadc1) != HAL_OK) Error_Handler();
  MX_USART1_UART_Init(); MX_USART2_UART_Init();
  if (HAL_UART_Receive_IT(&huart2, &esp_rx_character, 1U) != HAL_OK) Error_Handler();
  (void)HAL_UART_Transmit(&huart1, (uint8_t *)"#NODE node-a boot\r\n", 19U, 1000U);
  for (;;)
  {
    uint32_t now;
    uint8_t alarm_active;

    while (esp_rx_count != 0U) Command_Poll();
    NodeTest_Poll();
    /* A command may start a timed actuator. Read the clock afterwards so a
     * just-written start timestamp can never appear to be in the future. */
    now = HAL_GetTick();
    Smoke_Poll(now);
    Flame_Poll(now);
    Level_Poll(now);
    GasVentilation_Update(now);
    alarm_active = ((smoke_alarm != 0U) || (flame_alarm != 0U) || (gas_alarm != 0U)) ? 1U : 0U;
    if ((alarm_active == 0U) && (g_actuator.buzzer_on != 0U) &&
        ((now - buzzer_started_at) >= buzzer_duration_ms))
      Buzzer_Silence();
    if (alarm_active != 0U)
    {
      if (g_actuator.buzzer_muted != 0U)
        HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_RESET);
      else
        HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_SET);
    }
    if ((gas_ventilation_active == 0U) && (g_actuator.relay_on != 0U) &&
        ((now - relay_started_at) >= relay_duration_ms))
      Relay_Disable();
    if ((test_force_telemetry != 0U) ||
        ((now - last_telemetry) >= TELEMETRY_INTERVAL_MS))
    {
      (void)Sht30_Read(&i2c1_bus, SHT30_ADDRESS_44, &readings[0]);
      (void)Sht30_Read(&i2c1_bus, SHT30_ADDRESS_45, &readings[1]);
      (void)Sht30_Read(&i2c2_bus, SHT30_ADDRESS_44, &readings[2]);
      oxygen_online = GasAdc_ReadRaw(NODE_A_OXYGEN_ADC_CHANNEL, &oxygen_raw);
      if (oxygen_online != 0U) oxygen_raw = GasAdcFilter_Update(&oxygen_filter, oxygen_raw);
      oxygen_microvolts = NODE_A_ADC_RAW_TO_UV(oxygen_raw);
      methane_online = GasAdc_ReadRaw(NODE_A_METHANE_ADC_CHANNEL, &methane_raw);
      if (methane_online != 0U) methane_raw = GasAdcFilter_Update(&methane_filter, methane_raw);
      methane_microvolts = NODE_A_ADC_RAW_TO_UV(methane_raw);
      co_online = GasAdc_ReadRaw(NODE_A_CO_ADC_CHANNEL, &co_raw);
      if (co_online != 0U) co_raw = GasAdcFilter_Update(&co_filter, co_raw);
      co_microvolts = NODE_A_ADC_RAW_TO_UV(co_raw);
      if ((oxygen_filter.count >= 3U) && (methane_filter.count >= 3U) &&
          (co_filter.count >= 3U))
        GasAlarm_Update(oxygen_raw, oxygen_online, methane_raw, methane_online,
                        co_raw, co_online);
      (void)Ina226_Read(&i2c1_bus, &ina226_fan1_state, &fan_power);
      (void)Ina226_Read(&i2c2_bus, &ina226_fan2_state, &fan2_power);
      /* Sensor acquisition is deliberately slow on the software I2C buses.
       * Timestamp the pulse window after those reads so pulses accumulated
       * during acquisition are divided by the matching real elapsed time. */
      {
        const uint32_t tach_now = HAL_GetTick();
        fan_rpm = Fan1Tach_ReadRpm(tach_now);
        fan2_rpm = Fan2Tach_ReadRpm(tach_now);
      }
      SendTelemetry(readings, smoke_alarm, flame_alarm, level_detected, oxygen_raw,
                    oxygen_microvolts, oxygen_online, methane_raw,
                    methane_microvolts, methane_online, co_raw,
                    co_microvolts, co_online, &fan_power, fan_rpm,
                    &fan2_power, fan2_rpm);
      last_telemetry = now;
      test_force_telemetry = 0U;
    }
    if ((now - last_led) >= LED_INTERVAL_MS)
    {
      HAL_GPIO_TogglePin(LED_GPIO_Port, LED_Pin); last_led = now;
    }
    if ((now - last_led_anim) >= LED_ANIM_INTERVAL_MS)
    {
      last_led_anim = now;
      Led_Render(now);
    }
  }
}

void SystemClock_Config(void)
{
  RCC_OscInitTypeDef oscillator = {0};
  RCC_ClkInitTypeDef clock = {0};
  oscillator.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  oscillator.HSIState = RCC_HSI_ON;
  oscillator.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  oscillator.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&oscillator) != HAL_OK) Error_Handler();
  clock.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  clock.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  clock.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clock.APB1CLKDivider = RCC_HCLK_DIV1;
  clock.APB2CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_0) != HAL_OK) Error_Handler();
}

static uint16_t GasAdcFilter_Update(GasAdcFilter *filter, uint16_t sample)
{
  uint16_t median;
  if (filter == NULL) return sample;
  if (filter->count < 3U)
  {
    filter->samples[filter->count++] = sample;
    filter->filtered = (filter->count == 1U) ? sample :
                       NODE_A_EMA_QUARTER(filter->filtered, sample);
    if (filter->count == 3U) filter->next = 0U;
    return filter->filtered;
  }
  filter->samples[filter->next] = sample;
  filter->next = (uint8_t)((filter->next + 1U) % 3U);
  median = NODE_A_MEDIAN3(filter->samples[0], filter->samples[1], filter->samples[2]);
  filter->filtered = NODE_A_EMA_QUARTER(filter->filtered, median);
  return filter->filtered;
}

static void GasAlarm_Update(uint16_t oxygen_raw, uint8_t oxygen_online,
                            uint16_t methane_raw, uint8_t methane_online,
                            uint16_t co_raw, uint8_t co_online)
{
  const uint8_t previous_warning = gas_warning;
  const uint8_t previous_alarm = gas_alarm;

  oxygen_warning = (oxygen_online != 0U) ?
      NODE_A_LOW_ALARM_STATE(oxygen_warning, oxygen_raw,
                             NODE_A_OXYGEN_WARNING_ON_RAW,
                             NODE_A_OXYGEN_WARNING_OFF_RAW) : 0U;
  oxygen_alarm = (oxygen_online != 0U) ?
      NODE_A_LOW_ALARM_STATE(oxygen_alarm, oxygen_raw,
                             NODE_A_OXYGEN_ALARM_ON_RAW,
                             NODE_A_OXYGEN_ALARM_OFF_RAW) : 0U;
  methane_warning = (methane_online != 0U) ?
      NODE_A_HIGH_ALARM_STATE(methane_warning, methane_raw,
                              NODE_A_METHANE_WARNING_ON_RAW,
                              NODE_A_METHANE_WARNING_OFF_RAW) : 0U;
  methane_alarm = (methane_online != 0U) ?
      NODE_A_HIGH_ALARM_STATE(methane_alarm, methane_raw,
                              NODE_A_METHANE_ALARM_ON_RAW,
                              NODE_A_METHANE_ALARM_OFF_RAW) : 0U;
  co_warning = (co_online != 0U) ?
      NODE_A_HIGH_ALARM_STATE(co_warning, co_raw,
                              NODE_A_CO_WARNING_ON_RAW,
                              NODE_A_CO_WARNING_OFF_RAW) : 0U;
  co_alarm = (co_online != 0U) ?
      NODE_A_HIGH_ALARM_STATE(co_alarm, co_raw,
                              NODE_A_CO_ALARM_ON_RAW,
                              NODE_A_CO_ALARM_OFF_RAW) : 0U;
  gas_warning = NODE_A_OPERATIONAL_GAS_ALARM(
      oxygen_warning, methane_warning, co_warning);
  gas_alarm = NODE_A_OPERATIONAL_GAS_ALARM(
      oxygen_alarm, methane_alarm, co_alarm);

  if ((gas_warning == previous_warning) && (gas_alarm == previous_alarm)) return;
  if ((gas_alarm != 0U) && (previous_alarm == 0U))
    NodeACommand_AlarmActivated(&g_actuator);
  if ((smoke_alarm != 0U) || (flame_alarm != 0U) || (gas_alarm != 0U))
  {
    Buzzer_Start(0xFFFFFFFFUL);
    Led_Render(HAL_GetTick());
  }
  else if (gas_warning != 0U)
  {
    Buzzer_Silence();
    Led_Render(HAL_GetTick());
  }
  else
  {
    Buzzer_Silence();
    Led_Render(HAL_GetTick());
  }
}

static void GasVentilation_Update(uint32_t now)
{
  if (gas_alarm != 0U)
  {
    gas_ventilation_active = 1U;
    gas_ventilation_cooling = 0U;
  }
  else if ((gas_ventilation_active != 0U) && (gas_ventilation_cooling == 0U))
  {
    gas_ventilation_cooling = 1U;
    gas_ventilation_clear_started_at = now;
  }
  else if ((gas_ventilation_active != 0U) &&
           (NODE_A_GAS_VENTILATION_SHOULD_RUN(
               gas_alarm, gas_ventilation_cooling,
               now - gas_ventilation_clear_started_at) == 0U))
  {
    gas_ventilation_active = 0U;
    gas_ventilation_cooling = 0U;
    Relay_Disable();
    return;
  }

  if (gas_ventilation_active != 0U)
  {
    if (g_actuator.fan1_pwm_percent != 100U) Fan1Pwm_SetPercent(100U);
    if (g_actuator.fan2_pwm_percent != 100U) Fan2Pwm_SetPercent(100U);
    if (g_actuator.relay_on == 0U) Relay_Enable(0xFFFFFFFFUL);
  }
}

static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef gpio = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOB_CLK_ENABLE(); __HAL_RCC_GPIOC_CLK_ENABLE();
  HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(BUZZER_GPIO_Port, BUZZER_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(RELAY_GPIO_Port, RELAY_Pin, GPIO_PIN_RESET);
  gpio.Pin = LED_Pin; gpio.Mode = GPIO_MODE_OUTPUT_PP; gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LED_GPIO_Port, &gpio);
  gpio.Pin = BUZZER_Pin; gpio.Mode = GPIO_MODE_OUTPUT_PP; gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(BUZZER_GPIO_Port, &gpio);
  gpio.Pin = RELAY_Pin; gpio.Mode = GPIO_MODE_OUTPUT_PP; gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(RELAY_GPIO_Port, &gpio);
  gpio.Pin = SMOKE_Pin; gpio.Mode = GPIO_MODE_INPUT; gpio.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(SMOKE_GPIO_Port, &gpio);
  gpio.Pin = FLAME_Pin; gpio.Mode = GPIO_MODE_INPUT; gpio.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(FLAME_GPIO_Port, &gpio);
  gpio.Pin = LEVEL_Pin; gpio.Mode = GPIO_MODE_INPUT; gpio.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(LEVEL_GPIO_Port, &gpio);
  /* Standard four-wire PC fan TACH is open collector.  The external 10 kOhm
   * pull-up to 3.3 V defines a safe logic level; the internal pull-up is also
   * enabled so a temporarily disconnected resistor cannot leave PA6 floating. */
  gpio.Pin = FAN1_TACH_Pin; gpio.Mode = GPIO_MODE_IT_RISING; gpio.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(FAN1_TACH_GPIO_Port, &gpio);
  gpio.Pin = FAN2_TACH_Pin; gpio.Mode = GPIO_MODE_IT_RISING; gpio.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(FAN2_TACH_GPIO_Port, &gpio);
  HAL_NVIC_SetPriority(EXTI9_5_IRQn, 2U, 0U);
  HAL_NVIC_EnableIRQ(EXTI9_5_IRQn);
  HAL_GPIO_WritePin(GPIOB, i2c1_bus.scl_pin | i2c1_bus.sda_pin | i2c2_bus.scl_pin | i2c2_bus.sda_pin, GPIO_PIN_SET);
  gpio.Pin = i2c1_bus.scl_pin | i2c1_bus.sda_pin | i2c2_bus.scl_pin | i2c2_bus.sda_pin;
  gpio.Mode = GPIO_MODE_OUTPUT_OD; gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &gpio);
}

static void MX_ADC1_Init(void)
{
  ADC_ChannelConfTypeDef channel = {0};
  hadc1.Instance = ADC1;
  hadc1.Init.ScanConvMode = ADC_SCAN_DISABLE;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.NbrOfConversion = 1;
  if (HAL_ADC_Init(&hadc1) != HAL_OK) Error_Handler();
  channel.Channel = NODE_A_CO_ADC_CHANNEL;
  channel.Rank = ADC_REGULAR_RANK_1;
  channel.SamplingTime = ADC_SAMPLETIME_239CYCLES_5;
  if (HAL_ADC_ConfigChannel(&hadc1, &channel) != HAL_OK) Error_Handler();
}

static uint8_t GasAdc_ReadRaw(uint32_t adc_channel, uint16_t *raw)
{
  ADC_ChannelConfTypeDef channel = {0};
  uint32_t sum = 0UL;
  uint16_t valid = 0U;
  uint16_t index;
  if (raw == NULL) return 0U;
  channel.Channel = adc_channel;
  channel.Rank = ADC_REGULAR_RANK_1;
  channel.SamplingTime = ADC_SAMPLETIME_239CYCLES_5;
  if (HAL_ADC_ConfigChannel(&hadc1, &channel) != HAL_OK) return 0U;
  for (index = 0U; index < GAS_ADC_SAMPLE_COUNT; ++index)
  {
    if (HAL_ADC_Start(&hadc1) != HAL_OK) continue;
    if (HAL_ADC_PollForConversion(&hadc1, 10U) == HAL_OK)
    {
      sum += HAL_ADC_GetValue(&hadc1);
      ++valid;
    }
    (void)HAL_ADC_Stop(&hadc1);
  }
  if (valid == 0U)
  {
    *raw = 0U;
    return 0U;
  }
  *raw = (uint16_t)((sum + (valid / 2U)) / valid);
  return 1U;
}

static void MX_USART2_UART_Init(void)
{
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 9600;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK) Error_Handler();
}

static void MX_USART1_UART_Init(void)
{
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 9600;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK) Error_Handler();
}

void Error_Handler(void)
{
  __disable_irq();
  while (1) { }
}
