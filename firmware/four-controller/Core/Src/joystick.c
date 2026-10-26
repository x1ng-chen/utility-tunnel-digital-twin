#include "joystick.h"
#include "board_io.h"
#include "stm32f1xx_hal.h"

#define JOY_X_CHANNEL ADC_CHANNEL_10   /* PC0 */
#define JOY_Y_CHANNEL ADC_CHANNEL_11   /* PC1 */
#define JOY_SW_PIN    GPIO_PIN_4       /* PC4，内部上拉，按下为低 */

void Joystick_Init(void)
{
  GPIO_InitTypeDef gpio = {0};

  __HAL_RCC_GPIOC_CLK_ENABLE();

  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1;
  gpio.Mode = GPIO_MODE_ANALOG;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &gpio);

  gpio.Pin = JOY_SW_PIN;
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOC, &gpio);
}

void Joystick_Read(uint16_t *x, uint16_t *y, uint8_t *pressed)
{
  uint16_t raw = 0U;

  if (x != NULL)
  {
    *x = BoardIo_AdcRead(JOY_X_CHANNEL, &raw) ? raw : 2048U;
  }
  if (y != NULL)
  {
    *y = BoardIo_AdcRead(JOY_Y_CHANNEL, &raw) ? raw : 2048U;
  }
  if (pressed != NULL)
  {
    *pressed = (HAL_GPIO_ReadPin(GPIOC, JOY_SW_PIN) == GPIO_PIN_RESET) ? 1U : 0U;
  }
}
