#include <Arduino.h>
#include <ArduinoJson.h>
#include <atomic>
#include <esp_system.h>
#include <sys/time.h>
#include "command_json.h"
#include "command_ledger.h"
#include "device_map.h"
#include "telemetry_encode.h"
#if defined(UT_NETWORK_COMPILE_CHECK)
#include "secrets.example.h"
#define HAVE_NET 1
#elif __has_include("secrets.h")
#include "secrets.h"
#define HAVE_NET 1
#else
#define HAVE_NET 0
#endif
#if HAVE_NET
#include <WiFi.h>
#include <PubSubClient.h>
#include <Preferences.h>
#endif
static HardwareSerial bus(1);
static uint32_t gateway_session,command_nonce,poll_at,bus_errors;
static std::atomic<uint32_t> publish_drops{0};
static char boot_id[24];
static const uint8_t order[4]={4,3,2,1};

struct Node {
  uint16_t regs[UT_INPUT_COUNT];
  uint32_t at,uptime,epoch,session;
  bool online,synchronized;
};
static Node nodes[4];
struct NetMessage { char topic[48],payload[4096];uint32_t at;bool telemetry; };
static QueueHandle_t telemetry_queue,ack_queue,command_queue;
static NetMessage outbound;
static StaticJsonDocument<6144> document;
static void enqueue(const char *topic,bool telemetry)
{
  if(document.overflowed()||measureJson(document)>=sizeof outbound.payload-64U){++publish_drops;return;}
  strlcpy(outbound.topic,topic,sizeof outbound.topic);
  serializeJson(document,outbound.payload,sizeof outbound.payload);
  outbound.at=millis();outbound.telemetry=telemetry;
  if(telemetry) {
    size_t length=strlen(outbound.payload);
    /* UART0 diagnostics must never block the UART1 bus scheduler. A slow USB
     * reader can lose diagnostic lines; MQTT routing is independent. */
    if(Serial.availableForWrite()>=(int)(length+1U)) {
      Serial.write((const uint8_t *)outbound.payload,length);Serial.write('\n');
    }
  }
  if(xQueueSend(telemetry?telemetry_queue:ack_queue,&outbound,0)!=pdTRUE)++publish_drops;
}
static void add_crc(uint8_t *p,size_t n)
{uint16_t c=ut_crc(p,n);p[n]=(uint8_t)c;p[n+1U]=(uint8_t)(c>>8);}
/* Sole UART owner: loop task. Network callbacks only put bounded commands on
 * a queue; reconnect/DNS/MQTT can never block STM32 bus polling. */
static bool exchange(uint8_t *request,size_t size,uint8_t *reply,size_t expected,bool write)
{
  delay(4);while(bus.available())bus.read();
  bus.write(request,size);bus.flush();
  uint8_t incoming[512];size_t used=0;bool overflow=false;
  uint32_t start=millis(),last=start;
  while(!ut_due(millis(),start,300U)) {
    while(bus.available()) {
      int c=bus.read();
      if(used<sizeof incoming)incoming[used++]=(uint8_t)c;else overflow=true;
      last=millis();
    }
    if(!overflow&&used>=expected&&ut_due(millis(),last,4U)) {
      size_t first=(used>=size&&!memcmp(incoming,request,size))?size:0U;
      for(size_t i=first;i+expected<=used;i++) {
        const uint8_t *p=incoming+i;
        bool valid=write?ut_ack_matches(p,expected,request[0],16U,ut_u16(request+2),ut_u16(request+4)):
          (p[0]==request[0]&&p[1]==4U&&p[2]==expected-5U&&ut_crc(p,expected)==0U);
        if(valid){memcpy(reply,p,expected);return true;}
      }
    }
    delay(1);
  }
  ++bus_errors;return false;
}
static bool read_regs(uint8_t board,uint16_t start,uint16_t count,uint16_t *data)
{
  uint8_t p[8]={board,4U,0,0,0,0},reply[UT_INPUT_COUNT*2U+5U];
  ut_put(p+2,start);ut_put(p+4,count);add_crc(p,6U);
  if(!exchange(p,sizeof p,reply,count*2U+5U,false))return false;
  for(unsigned i=0;i<count;i++)data[i]=ut_u16(reply+3U+i*2U);
  return true;
}
static bool write_regs(uint8_t board,uint16_t start,const uint16_t *data,uint16_t count)
{
  uint8_t p[UT_VIEW_COUNT*2U+9U]={board,16U,0,0,0,0},reply[8];
  if(count>UT_VIEW_COUNT)return false;
  ut_put(p+2,start);ut_put(p+4,count);p[6]=(uint8_t)(count*2U);
  for(unsigned i=0;i<count;i++)ut_put(p+7U+i*2U,data[i]);
  add_crc(p,7U+count*2U);
  return exchange(p,9U+count*2U,reply,sizeof reply,true);
}
static uint16_t execute(uint8_t board,uint16_t code,uint16_t value,uint16_t ttl)
{
  if(board<1U||board>4U||!ut_capable(board,code))return UT_RESULT_UNSUPPORTED;
  if(!nodes[board-1U].online||!nodes[board-1U].synchronized)return UT_RESULT_UNKNOWN;
  if(++command_nonce==0U){gateway_session=esp_random()|1U;++command_nonce;}
  uint32_t nonce=command_nonce;
  uint16_t data[8]={code,value,ttl,(uint16_t)(gateway_session>>16),(uint16_t)gateway_session,
    (uint16_t)(nonce>>16),(uint16_t)nonce,0U};
  if(!write_regs(board,0U,data,8U))return UT_RESULT_UNKNOWN;
  uint16_t result[6];
  if(!read_regs(board,80U,6U,result))return UT_RESULT_UNKNOWN;
  if(result[0]!=data[3]||result[1]!=data[4]||result[2]!=data[5]||result[3]!=data[6])return UT_RESULT_UNKNOWN;
  return result[4]>=1U&&result[4]<=UT_RESULT_UNKNOWN?result[4]:UT_RESULT_UNKNOWN;
}
static uint64_t utc_ms()
{ struct timeval tv;gettimeofday(&tv,nullptr);return (uint64_t)tv.tv_sec*1000ULL+tv.tv_usec/1000U; }
static bool clock_ready(){return utc_ms()>1767225600000ULL;}
static bool inventory_valid(uint8_t board,const uint16_t *r)
{ return ut_snapshot_valid(board,r,UT_INPUT_COUNT); }
static uint32_t u32(const uint16_t *r,unsigned at) { return ut_reg32(r,at); }
static void emit(uint8_t board,uint32_t transit)
{
  Node &node=nodes[board-1U];char stamp[32]={0};
  if(clock_ready()) {
    uint64_t now=utc_ms();time_t seconds=(time_t)(now/1000ULL);struct tm tm;gmtime_r(&seconds,&tm);
    snprintf(stamp,sizeof stamp,"%04d-%02d-%02dT%02d:%02d:%02d.%03uZ",tm.tm_year+1900,tm.tm_mon+1,tm.tm_mday,tm.tm_hour,tm.tm_min,tm.tm_sec,(unsigned)(now%1000ULL));
  }
  if(!ut_telemetry(document,board,node.regs,boot_id,node.epoch,transit,stamp)){++publish_drops;return;}
  char topic[48];snprintf(topic,sizeof topic,"ut/v1/CTRL-%02u/telemetry",board);enqueue(topic,true);
}
static uint32_t menu_seen,menu_epoch;
static uint16_t menu_result;
static void handle_menu(const Node &owner)
{
  const uint16_t *r=owner.regs;uint32_t nonce=u32(r,87U);
  if(!r[94]||!r[92]||!nonce||r[89]<1U||r[89]>4U)return;
  if(menu_seen!=nonce||menu_epoch!=owner.epoch) {
    menu_seen=nonce;menu_epoch=owner.epoch;
    uint32_t start=millis();
    menu_result=r[92]<=400U?UT_RESULT_EXPIRED:execute((uint8_t)r[89],r[90],r[91],(uint16_t)(r[92]-300U));
    if(ut_due(millis(),start,r[92]))menu_result=UT_RESULT_UNKNOWN;
  }
  /* Retry the correlated result when its ACK was lost, never execute again. */
  uint16_t ack[3]={(uint16_t)(nonce>>16),(uint16_t)nonce,menu_result};
  (void)write_regs(2U,UT_MENU_ACK_BASE,ack,3U);
}
static void poll(uint8_t board)
{
  Node &n=nodes[board-1U];uint16_t regs[UT_INPUT_COUNT];uint32_t start=millis();
  bool ok=read_regs(board,0U,UT_INPUT_COUNT,regs)&&inventory_valid(board,regs);
  n.online=ok;
  if(!ok)return; /* No refreshed telemetry/heartbeat for an absent node. */
  uint32_t uptime=u32(regs,4U);
  /* A node starts unsynchronized after EVERY reset, including same-second
   * resets. No dependence on an uptime decrease to distinguish a reused nonce. */
  if(n.synchronized&&!(regs[95]&2U)) {
    n.synchronized=false;n.session=0U;++n.epoch;
    if(board==2U){menu_seen=0U;menu_result=UT_RESULT_UNKNOWN;}
  }
  if(!n.synchronized) {
    n.online=false;
    if(!n.session)n.session=esp_random()|1U;
    uint16_t token[2]={(uint16_t)(n.session>>16),(uint16_t)n.session};
    if(write_regs(board,UT_BOOT_SESSION_BASE,token,2U))n.synchronized=true;
    return; /* Publish only the subsequent freshly polled snapshot. */
  }
  memcpy(n.regs,regs,sizeof regs);n.at=millis();n.uptime=uptime;
  emit(board,(uint32_t)(millis()-start));
  if(board==2U)handle_menu(n);
  uint16_t selected=nodes[1].regs[93];
  if(nodes[1].online&&selected==board)(void)write_regs(2U,UT_VIEW_BASE,regs,UT_VIEW_COUNT);
  Serial.printf("{\"board\":%u,\"seq\":%u,\"busErrors\":%lu,\"publishDrops\":%lu}\n",board,regs[6],(unsigned long)bus_errors,(unsigned long)publish_drops.load());
}
struct Cache { UtRequest request;uint16_t result;bool used; };
static Cache cache[64];
static bool command_store_ready;
#if HAVE_NET
static Preferences command_store;
#endif
static bool save_command(unsigned index)
{
#if HAVE_NET
  if(!command_store_ready||index>=64U)return false;
  UtLedgerRecord record=ut_ledger_make(cache[index].request,cache[index].result);
  char key[8];snprintf(key,sizeof key,"c%02u",index);
  return command_store.putBytes(key,&record,sizeof record)==sizeof record;
#else
  (void)index;return false;
#endif
}
static void load_commands()
{
#if HAVE_NET
  command_store_ready=command_store.begin("ut-cmd-v2",false);
  if(!command_store_ready)return;
  for(unsigned i=0;i<64U;i++) {
    char key[8];snprintf(key,sizeof key,"c%02u",i);
    if(!command_store.isKey(key))continue;
    UtLedgerRecord record;
    size_t length=command_store.getBytesLength(key);
    if(length!=sizeof record||command_store.getBytes(key,&record,sizeof record)!=sizeof record||
        !ut_ledger_read(&record,sizeof record,record)) {command_store_ready=false;return;}
    cache[i].request=record.request;cache[i].result=record.result;cache[i].used=true;
  }
#endif
}

static bool same(const UtRequest &a,const UtRequest &b)
{ return a.board==b.board&&a.code==b.code&&a.value==b.value&&a.ttl==b.ttl&&a.issuedAtMs==b.issuedAtMs; }
static void command_ack(const UtRequest &r,uint16_t result,const char *override_reason=nullptr)
{
  document.clear();document["schema"]="ut.command-ack.v2";document["cmdId"]=r.cmdId;
  document["controllerId"]=String("CTRL-0")+r.board;
  document["status"]=result==UT_RESULT_OK?"accepted":(result==UT_RESULT_UNKNOWN?"unknown":"rejected");
  const char *reasons[]={"invalid","outputs_applied_feedback_required","unsupported","invalid","expired","local_protection","conflicting_replay","execution_unknown"};
  document["reason"]=override_reason?override_reason:reasons[result<=UT_RESULT_UNKNOWN?result:0U];document["physicalStateVerified"]=false;
  char topic[48];snprintf(topic,sizeof topic,"ut/v1/CTRL-%02u/cmd_ack",r.board);enqueue(topic,false);
}
static void process_command(UtRequest &r)
{
  uint64_t now=utc_ms();uint16_t result=UT_RESULT_INVALID;Cache *free_slot=nullptr;
  if(!command_store_ready){command_ack(r,result,"command_storage_unavailable");return;}
  if(!clock_ready()||r.issuedAtMs>now+2000ULL){command_ack(r,result);return;}
  if(now>=r.issuedAtMs+r.ttl||ut_due(millis(),r.receivedAt,r.ttl)){command_ack(r,UT_RESULT_EXPIRED);return;}
  for(Cache &e:cache) {
    if(e.used&&!strcmp(e.request.cmdId,r.cmdId)){command_ack(r,same(e.request,r)?e.result:UT_RESULT_CONFLICT);return;}
    if(!e.used||now>=e.request.issuedAtMs+e.request.ttl)free_slot=&e;
  }
  /* Never evict an unexpired command. Capacity exhaustion rejects the request. */
  if(!free_slot){command_ack(r,UT_RESULT_INVALID);return;}
  uint32_t remaining=(uint32_t)(r.issuedAtMs+r.ttl-now);
  uint32_t queue_remaining=r.ttl-(uint32_t)(millis()-r.receivedAt);
  if(remaining>queue_remaining)remaining=queue_remaining;
  if(remaining<400U){command_ack(r,UT_RESULT_EXPIRED);return;}
  free_slot->request=r;free_slot->used=true;free_slot->result=UT_RESULT_UNKNOWN;
  unsigned index=(unsigned)(free_slot-cache);
  /* Durable intent precedes UART I/O. A reboot finds UNKNOWN and never sends
   * the same MQTT cmdId again, even when the last result was not saved. */
  if(!save_command(index)) {
    command_store_ready=false;command_ack(r,UT_RESULT_INVALID,"command_storage_unavailable");return;
  }
  now=utc_ms();
  if(now>=r.issuedAtMs+r.ttl||ut_due(millis(),r.receivedAt,r.ttl))result=UT_RESULT_EXPIRED;
  else {
    remaining=(uint32_t)(r.issuedAtMs+r.ttl-now);
    queue_remaining=r.ttl-(uint32_t)(millis()-r.receivedAt);
    if(remaining>queue_remaining)remaining=queue_remaining;
    result=remaining<400U?UT_RESULT_EXPIRED:execute(r.board,r.code,r.value,(uint16_t)(remaining-300U));
  }
  if(utc_ms()>=r.issuedAtMs+r.ttl&&result==UT_RESULT_OK)result=UT_RESULT_UNKNOWN;
  free_slot->result=result;
  if(!save_command(index)){command_store_ready=false;result=UT_RESULT_UNKNOWN;}
  command_ack(r,result);
}
#if HAVE_NET
static WiFiClient transport;
static PubSubClient mqtt(transport);
static void on_command(char *topic,uint8_t *payload,unsigned int length)
{
  UtRequest r;
  if(!ut_request_parse((const char *)payload,length,r))return;
  char expected[48];snprintf(expected,sizeof expected,"ut/v1/CTRL-%02u/cmd",r.board);
  if(strcmp(topic,expected))return;
  r.receivedAt=millis();
  /* No UART, actuator, shared JSON document, or blocking calls in callback. */
  if(xQueueSend(command_queue,&r,0)!=pdTRUE)++publish_drops;
}
static void network_task(void *)
{
  WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  configTime(0,0,"pool.ntp.org","time.cloudflare.com");
  mqtt.setServer(MQTT_HOST,MQTT_PORT);mqtt.setCallback(on_command);
  mqtt.setBufferSize(4096);mqtt.setSocketTimeout(1);mqtt.setKeepAlive(15);
  transport.setTimeout(1000);
  NetMessage msg;uint32_t attempt=millis()-5000U;
  char client_id[48];snprintf(client_id,sizeof client_id,"ut-gw-%s",boot_id);
  for(;;) {
    if(WiFi.status()==WL_CONNECTED&&!mqtt.connected()&&ut_due(millis(),attempt,5000U)) {
      attempt=millis();
      if(mqtt.connect(client_id,MQTT_USERNAME,MQTT_PASSWORD,"ut/v1/GW-01/status",1,true,"{\"online\":false}")) {
        for(unsigned i=1;i<=4U;i++){char t[48];snprintf(t,sizeof t,"ut/v1/CTRL-%02u/cmd",i);mqtt.subscribe(t,1);}
        mqtt.publish("ut/v1/GW-01/status","{\"online\":true}",true);
      }
    }
    if(mqtt.connected())mqtt.loop();
    bool have=xQueueReceive(ack_queue,&msg,0)==pdTRUE;
    if(!have)have=xQueueReceive(telemetry_queue,&msg,0)==pdTRUE;
    if(have) {
      /* No delayed telemetry replay pretending to be a current observation. */
      if((msg.telemetry&&ut_due(millis(),msg.at,500U))||!mqtt.connected()||!mqtt.publish(msg.topic,msg.payload,false))++publish_drops;
    }
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}
#endif
void setup()
{
  Serial.setTxBufferSize(8192);Serial.begin(115200);bus.setRxBufferSize(512);bus.begin(19200,SERIAL_8E1,18,17);
  load_commands();
  gateway_session=esp_random()|1U;snprintf(boot_id,sizeof boot_id,"%08lx%08lx",(unsigned long)gateway_session,(unsigned long)esp_random());
  telemetry_queue=xQueueCreate(8,sizeof(NetMessage));ack_queue=xQueueCreate(8,sizeof(NetMessage));command_queue=xQueueCreate(8,sizeof(UtRequest));
  if(!telemetry_queue||!ack_queue||!command_queue){Serial.println("QUEUE_ALLOCATION_FAILED");for(;;)delay(1000);}
#if HAVE_NET
  if(xTaskCreatePinnedToCore(network_task,"ut-net",16384,nullptr,1,nullptr,0)!=pdPASS){Serial.println("NETWORK_TASK_FAILED");}
#endif
  Serial.println("FOUR_GATEWAY_V2.0 19200-8E1 network isolated from bus");
}
void loop()
{
  static unsigned next;
  UtRequest r;
  if(xQueueReceive(command_queue,&r,0)==pdTRUE)process_command(r);
  if(ut_due(millis(),poll_at,500U)){poll_at=millis();poll(order[next++%4U]);}
#if !HAVE_NET
  /* Offline firmware is diagnostic only; it does not pretend to publish. */
  NetMessage discarded;
  while(xQueueReceive(telemetry_queue,&discarded,0)==pdTRUE){}
  while(xQueueReceive(ack_queue,&discarded,0)==pdTRUE){}
#endif
  delay(1);
}
