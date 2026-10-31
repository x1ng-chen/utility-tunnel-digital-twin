/* Deliberately compile the current production driver in this diagnostic TU.
 * Only its static I2C/SHT functions are reachable; ADC/telemetry/Poll are not run.
 * Business source, timings and CRC acceptance are unchanged. */
#if !defined(UT_SHT_DIAGNOSTIC) || BOARD_ID != 2
#error "CTRL-02 diagnostic target only"
#endif
#include "../../Core/Src/board_io.c"

void DiagSoft_Init(void)
{
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  i2c_bus.port=GPIOB;i2c_bus.scl_pin=GPIO_PIN_10;i2c_bus.sda_pin=GPIO_PIN_11;
  BoardIo_ReinitI2c();
}

uint8_t DiagSoft_Read(uint8_t address,uint8_t raw[6],uint32_t *error)
{
  memset((void *)BoardIo_ShtRaw,0,sizeof BoardIo_ShtRaw);
  if(!Sht30_Begin(address)){*error=BoardIo_ShtDebug;return 0;}
  HAL_Delay(50U);
  SensorSample sample={0};
  uint8_t ok=Sht30_Finish(address,&sample);
  for(unsigned i=0;i<6U;i++)raw[i]=BoardIo_ShtRaw[i];
  *error=BoardIo_ShtDebug;
  return ok;
}
