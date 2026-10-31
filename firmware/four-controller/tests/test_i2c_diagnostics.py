"""Execute the real SHT/I2C source slice with scripted GPIO in ARM emulation.

This checks software behavior, not electrical timing, pullups or real hardware.
No serial ports are opened. Uses native GCC in CI or the existing ARM test dependencies.
"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'.agent-eval/firmware-native-tools'))
spec=importlib.util.spec_from_file_location('firmware_runner',HERE/'run_tests.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

STUB=r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include "test_support.h"
#include "board_io.h"
#include "digital.h"
typedef struct {unsigned unused;} GPIO_TypeDef;
typedef struct {unsigned unused;} ADC_HandleTypeDef;
typedef enum {GPIO_PIN_RESET=0,GPIO_PIN_SET=1} GPIO_PinState;
static struct {uint32_t CYCCNT;} fake_dwt;
#define DWT (&fake_dwt)
#define __NOP() (++fake_dwt.CYCCNT)
static uint32_t SystemCoreClock=200000U,now=12345U;
static unsigned reads,writes,queued,position,tx_count,bits,active;
static unsigned forced_scl_low,advance_tick_on_write,scl_low_for_reads,scl_reads;
static uint8_t queue[256],tx[32],shift,scl=1,sda=1;
uint32_t HAL_GetTick(void){return now;}
void HAL_GPIO_WritePin(GPIO_TypeDef *port,uint16_t pin,GPIO_PinState state){
 (void)port;++writes;now+=advance_tick_on_write;
 if(pin==2U){
  if(scl&&sda!=state){active=state==0;bits=0;shift=0;}
  sda=(uint8_t)state;
 }else{
  if(active&&!scl&&state){
   if(bits<8U)shift=(uint8_t)((shift<<1U)|sda);
   if(bits==7U&&tx_count<sizeof tx)tx[tx_count++]=shift;
   bits=(bits+1U)%9U;if(!bits)shift=0;
  }
  scl=(uint8_t)state;
 }
}
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *port,uint16_t pin){
 (void)port;++reads;
 if(pin==1U){++scl_reads;if(forced_scl_low)return GPIO_PIN_RESET;
  if(scl_low_for_reads){--scl_low_for_reads;return GPIO_PIN_RESET;}return (GPIO_PinState)scl;}
 return position<queued?(GPIO_PinState)queue[position++]:GPIO_PIN_SET;
}
static void add(unsigned bit){queue[queued++]=(uint8_t)bit;}
static void byte(uint8_t value){for(unsigned i=0;i<8U;i++)add((value>>(7U-i))&1U);}
static void clear(void){reads=writes=queued=position=tx_count=bits=active=0;scl=sda=1;shift=0;forced_scl_low=advance_tick_on_write=scl_low_for_reads=scl_reads=0;}
enum {SENSOR_SHT=1,SENSOR_MQ2,SENSOR_FLAME,SENSOR_LEVEL,SENSOR_O2};
typedef struct {unsigned type;uint8_t i2c_address;uint32_t adc_channel;} SensorDef;
static SensorDef test_sensor={SENSOR_SHT,0x45U,0U};
static struct {SensorDef *sensors;} board_config={&test_sensor};
static uint32_t __get_PRIMASK(void){return 0;}
static void __disable_irq(void){}
static void __set_PRIMASK(uint32_t v){(void)v;}
static uint8_t Adc_ReadRaw(uint32_t c,uint16_t *r){(void)c;*r=123;return 1;}
static uint16_t Adc_ToMillivolts(uint16_t r){return r;}
'''

TEST=r'''
volatile UtTestResults ut_test_results;
void test_entry(void){
 memset((void *)&ut_test_results,0,sizeof ut_test_results);
 i2c_bus.scl_pin=1U;i2c_bus.sda_pin=2U;
 GROUP();
 for(unsigned stage=1;stage<=3U;stage++){
  clear();for(unsigned i=1;i<stage;i++)add(0);add(1);
  CHECK(!Sht30_Begin(0x45U));CHECK(BoardIo_ShtDebug==stage);
  CHECK(tx_count==stage);CHECK(tx[0]==0x8aU);
 }
 clear();add(0);add(0);add(0);CHECK(Sht30_Begin(0x45U));CHECK(BoardIo_ShtDebug==0U);
 CHECK(tx_count==3U&&tx[1]==0x24U&&tx[2]==0U);
 GROUP();SensorSample sample={.value=1234,.aux=5678,.status=SENSOR_STATUS_OK};
 clear();add(1);CHECK(!Sht30_Finish(0x45U,&sample));
 CHECK(BoardIo_ShtDebug==4U&&sample.status==SENSOR_STATUS_MISSING);
 CHECK(sample.value==1234U&&sample.aux==5678U);
 GROUP();uint8_t raw[6]={0x66,0x66,0,0x80,0,0};
 raw[2]=Sht30_Crc(raw,2);raw[5]=Sht30_Crc(raw+3,2);
 clear();add(0);for(unsigned i=0;i<6;i++)byte(raw[i]);
 CHECK(Sht30_Finish(0x45U,&sample));CHECK(sample.status==SENSOR_STATUS_OK);
 CHECK(sample.value==2500U&&sample.aux==5000U);CHECK(sht_raw_read==now);
 GROUP();raw[2]^=1U;clear();add(0);for(unsigned i=0;i<6;i++)byte(raw[i]);
 CHECK(!Sht30_Finish(0x45U,&sample));CHECK(BoardIo_ShtDebug==5U);
 CHECK(sample.status==SENSOR_STATUS_MISSING&&sample.value==2500U);
 GROUP();raw[2]^=1U;raw[5]^=1U;clear();add(0);for(unsigned i=0;i<6;i++)byte(raw[i]);
 CHECK(!Sht30_Finish(0x45U,&sample));CHECK(BoardIo_ShtDebug==6U);
 CHECK(sample.status==SENSOR_STATUS_MISSING&&sample.aux==5000U);
 GROUP();BoardIoI2cDiagnostics d;
 clear();sht_phase=1U;CHECK(!BoardIo_GetI2cDiagnostics(&d));CHECK(!reads&&!writes);
 sht_phase=0U;CHECK(!BoardIo_GetI2cDiagnostics(NULL));CHECK(!reads&&!writes);
 GROUP();clear();add(0);CHECK(BoardIo_GetI2cDiagnostics(&d));
 CHECK(!d.probes_run&&!d.ack_mask&&!d.idle_sda&&d.idle_scl);CHECK(!writes);
 clear();forced_scl_low=1;add(1);CHECK(BoardIo_GetI2cDiagnostics(&d));
 CHECK(!d.probes_run&&!d.idle_scl&&d.idle_sda);CHECK(!writes);
 GROUP();clear();add(1);add(0);add(0);add(1);
 sht_address=0x44U;sht_good=7;sht_failed=3;sht_last_good=12000U;
 CHECK(BoardIo_GetI2cDiagnostics(&d));CHECK(d.probes_run&&d.ack_mask==3U);
 CHECK(tx_count==3&&tx[0]==0x80U&&tx[1]==0x88U&&tx[2]==0x8aU);
 CHECK(d.good==7U&&d.failed==3U&&d.last_good_ms==12000U);
 CHECK(d.address==0x44U&&d.stage==6U&&BoardIo_ShtDebug==6U);
 CHECK(d.raw_read_ms==now&&d.raw[5]==raw[5]);
 GROUP();clear();add(1);add(0);add(1);add(0);
 CHECK(BoardIo_GetI2cDiagnostics(&d));CHECK(d.ack_mask==5U);
 CHECK(sample.status==SENSOR_STATUS_MISSING);
 GROUP();clear();forced_scl_low=1;add(0);I2c_Start();
 CHECK(!I2c_WriteByte(0x8aU));I2c_Stop();CHECK(scl==1U&&sda==1U);
 GROUP();clear();advance_tick_on_write=1U;sample_count=1;cursor=0;sht_phase=0;
 BoardIo_ShtFoundAddr=0;BoardIo_ShtDebug=0;now=1000U;attempted[0]=now-2000U;
 add(0);add(0);add(0);BoardIo_Poll(1000U);
 CHECK(sht_phase==1U);CHECK(sht_started==now);
 uint32_t clocks=writes;advance_tick_on_write=0;now+=19U;BoardIo_Poll(now);
 CHECK(sht_phase==1U&&writes==clocks);
 clear();raw[5]^=1U;add(0);for(unsigned i=0;i<6U;i++)byte(raw[i]);
 uint32_t previous_good=sht_good;now+=1U;BoardIo_Poll(now);
 CHECK(!sht_phase&&sht_good==previous_good+1U);
 CHECK(samples[0].status==SENSOR_STATUS_OK&&samples[0].value==2500U);
 CHECK(sht_last_good==now);
 GROUP();clear();forced_scl_low=1;sample.value=1234U;
 CHECK(!Sht30_Begin(0x45U)&&BoardIo_ShtDebug==7U);
 CHECK(reads<=70U&&writes<=10U);CHECK(scl==1U&&sda==1U);
 CHECK(!Sht30_Finish(0x45U,&sample)&&BoardIo_ShtDebug==7U);
 CHECK(sample.status==SENSOR_STATUS_MISSING&&sample.value==1234U);
 uint16_t held=0xabcdU;
 CHECK(!BoardIo_I2cRead16(0x40U,2U,&held)&&held==0xabcdU);
 CHECK(!BoardIo_I2cWrite16(0x40U,5U,5120U));
 GROUP();clear();scl_low_for_reads=3U;add(0);
 I2c_Start();CHECK(!i2c_clock_fault);CHECK(I2c_WriteByte(0x8aU));
 I2c_Stop();CHECK(!i2c_clock_fault&&scl_reads>9U);
 ut_test_results.done=0x5554U;
}
#ifndef UT_TEST_EMULATED
int main(void){test_entry();printf("{\"checks\":%lu,\"failures\":%lu,\"firstLine\":%lu,\"groups\":%lu}\n",
 (unsigned long)ut_test_results.checks,(unsigned long)ut_test_results.failures,
 (unsigned long)ut_test_results.first_line,(unsigned long)ut_test_results.groups);
 return ut_test_results.failures?1:0;}
#endif
'''

class I2cDiagnosticsTests(unittest.TestCase):
    def test_actual_driver_with_scripted_gpio(self):
        source=(HERE.parent/'Core/Src/board_io.c').read_text(encoding='utf-8')
        driver=source[source.index('typedef struct'):source.index('/* ---------- ADC ---------- */')]
        driver+='\n'+source[source.index('void BoardIo_Poll'):source.index('/* Compatibility entry point')]
        arm=bool(shutil.which('arm-none-eabi-gcc') and importlib.util.find_spec('unicorn'))
        compiler=shutil.which('arm-none-eabi-gcc' if arm else 'gcc')
        if not compiler:self.skipTest('Native GCC or ARM GCC with emulator is required')
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);c=folder/'test.c';elf=folder/('test.elf' if arm else 'test.native')
            c.write_text(STUB+'\n'+driver+'\n'+TEST,encoding='utf-8')
            command=[compiler,'-std=c11','-Os','-ffunction-sections','-fdata-sections',
                '-I',str(HERE),'-I',str(HERE.parent/'Core/Inc'),'-I',str(HERE.parent/'common'),
                str(c),'-o',str(elf)]
            if arm:command+=['-mcpu=cortex-m3','-mthumb','-DUT_TEST_EMULATED=1','-nostartfiles',
                '--specs=nano.specs','--specs=nosys.specs','-Wl,--gc-sections','-Wl,-T,'+str(HERE/'arm-test.ld')]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            if arm:result=runner.emulate(elf)
            else:
                completed=subprocess.run([str(elf)],capture_output=True,text=True)
                self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
                result=json.loads(completed.stdout)
            print(json.dumps({'scope':'actual SHT/I2C source with scripted GPIO; no electrical simulation',**result}))
            self.assertGreaterEqual(result['groups'],13)
            self.assertEqual(result['failures'],0,result)

if __name__=='__main__':unittest.main()
