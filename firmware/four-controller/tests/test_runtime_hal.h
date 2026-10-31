#ifndef UT_TEST_RUNTIME_HAL_H
#define UT_TEST_RUNTIME_HAL_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
static uint32_t fake_time;
static uint32_t millis(){return fake_time;}
struct MockSerial {
  char input[4096]{},output[8192]{};size_t pos=0,end=0,written=0;
  int available(){return (int)(end-pos);}
  int read(){return pos<end?(unsigned char)input[pos++]:-1;}
  int availableForWrite(){return (int)(sizeof output-written-1U);}
  size_t write(const uint8_t *p,size_t n){if(n>(size_t)availableForWrite())return 0;memcpy(output+written,p,n);written+=n;output[written]=0;return n;}
  void feed(const char *p){pos=0;end=strlen(p);memcpy(input,p,end);}
  void clear(){pos=end=written=0;memset(input,0,sizeof input);memset(output,0,sizeof output);}
};
static MockSerial Serial;
struct MockESP {unsigned restarts=0;void restart(){++restarts;}};
static MockESP ESP;
struct MockNvs {uint8_t data[1024]{};size_t size=0;unsigned writes=0;bool writable=true,readback=true;};
static MockNvs nvs;
class Preferences {
public:
  bool begin(const char *,bool){return true;}
  bool isKey(const char *){return nvs.size!=0;}
  size_t getBytesLength(const char *){return nvs.size;}
  size_t getBytes(const char *,void *p,size_t n){if(!nvs.readback||n<nvs.size)return 0;memcpy(p,nvs.data,nvs.size);return nvs.size;}
  size_t putBytes(const char *,const void *p,size_t n){if(!nvs.writable||n>sizeof nvs.data)return 0;memcpy(nvs.data,p,n);nvs.size=n;++nvs.writes;return n;}
};
#endif
