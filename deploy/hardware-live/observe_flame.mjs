/** Observe physical flame MQTT -> committed API events. Never publish or inject. */
import { readFileSync, writeFileSync, appendFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const require=createRequire(new URL('../../services/iotda-gateway/package.json',import.meta.url));
const mqtt=require('mqtt');const WebSocket=require('ws');
const root=new URL('../../',import.meta.url), runtime=new URL('.hardware-live/',root);
const read=path=>JSON.parse(readFileSync(new URL(path,root),'utf8'));
const access=read('.hardware-live/access.json');
const login=await fetch('http://127.0.0.1:8000/api/auth/login/',{method:'POST',headers:{'content-type':'application/json'},
  body:JSON.stringify({email:access.account,password:access.password})}).then(r=>r.json());
if(!login.accessToken)throw Error('Commissioning login failed.');
const headers={authorization:`Bearer ${login.accessToken}`};
const ready=await fetch('http://127.0.0.1:8000/api/ready/').then(r=>r.json());
if(ready.profile!=='hardware-live')throw Error('Use the isolated hardware commissioning profile.');
const inspection=await fetch('http://127.0.0.1:8000/api/assistant/inspection/',{headers}).then(r=>r.json());
const snapshot=inspection.evidence[0].data;
const flames=Object.fromEntries(snapshot.items.filter(b=>b.physicalTag.startsWith('FLAME-')).map(b=>[b.assetCode,
  {station:b.stationId,controller:b.controllerId,target:b.targetNode}]));
if(Object.keys(flames).length!==5)throw Error('Expected five current flame mappings.');
const stamp=new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d+Z$/,'Z');
const folder=new URL('flame-acceptance-'+stamp+'/',runtime);mkdirSync(folder,{recursive:true});
const path=name=>new URL(name,folder);
const startedAt=new Date().toISOString();
const states={}, wsStates={};let completed=false,deadline,timer,received=0;
const mq=mqtt.connect('mqtt://127.0.0.1:1884',{connectTimeout:5000,reconnectPeriod:2000});
const ws=new WebSocket('ws://127.0.0.1:8000/ws/events/',{origin:'http://127.0.0.1:5173'});
function log(kind,data){appendFileSync(path('events.jsonl'),JSON.stringify({receivedAt:new Date().toISOString(),kind,...data})+'\n');}
function state(code){return states[code]??={mqttActive:false,mqttReturnedZero:false,committedActive:false,alertOpen:false,alertResolved:false};}
function finish(reason){
  if(completed)return;completed=true;clearTimeout(timer);clearTimeout(deadline);mq.end(true);ws.close();
  const result={startedAt,finishedAt:new Date().toISOString(),reason,mqttFrames:received,flameMap:flames,states,
    hardwareCommands:0,modelCalls:0,browserHighlight:'requires_user_observation',
    boundary:'Real MQTT, committed telemetry/alert/asset events only; no simulated measurement or browser-rendering claim.'};
  writeFileSync(path('summary.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({summary:fileURLToPath(path('summary.json')),...result}));
}
function mayFinish(){
  if(Object.values(states).some(s=>s.mqttActive&&s.mqttReturnedZero&&s.committedActive&&s.alertOpen&&s.alertResolved)&&!timer)
    timer=setTimeout(()=>finish('physical-trigger-and-recovery-observed'),4000);
}
mq.on('connect',()=>mq.subscribe(['CTRL-01','CTRL-02','CTRL-03','CTRL-04'].map(id=>`ut/v1/${id}/telemetry`),{qos:1},err=>{
  if(err)console.error(err.message);else console.log('READY: physical flame observer; start with centre P5 / FLAME-05.');
}));
mq.on('message',(topic,bytes,packet)=>{
  if(packet.retain)return;
  try{
    const frame=JSON.parse(bytes.toString());received++;
    for(const r of frame.readings??[]){
      if(!flames[r.assetCode]||r.metric!=='flame.alarm')continue;
      const s=state(r.assetCode);
      log('mqtt',{topic,frameId:frame.frameId,controllerId:frame.controllerId,sourceTime:frame.ts,reading:r});
      if(r.value===1&&!s.mqttActive){s.mqttActive=true;console.log(`PHYSICAL_INPUT ${r.assetCode} ${flames[r.assetCode].station} value=1 quality=${r.quality}`);}
      if(s.mqttActive&&r.value===0&&!s.mqttReturnedZero){s.mqttReturnedZero=true;console.log(`PHYSICAL_INPUT ${r.assetCode} returned to 0`);}
    }mayFinish();
  }catch(e){log('decode_error',{message:e.message});}
});
mq.on('error',e=>console.error('MQTT:',e.message));
ws.on('open',()=>ws.send(JSON.stringify({type:'auth',token:login.accessToken})));
ws.on('message',bytes=>{
  try{
    const event=JSON.parse(bytes.toString()),p=event.payload??{},code=p.assetCode??p.code;
    if(!flames[code])return;
    if(event.type==='telemetry'&&p.metricKey!=='flame.alarm')return;
    if(event.type==='alert'&&p.ruleKey!=='flame.alarm')return;
    log('committed_websocket',{event});const s=state(code);
    if(event.type==='telemetry'&&p.value===1)s.committedActive=true;
    if(event.type==='alert'){
      if(p.status==='open')s.alertOpen=true;if(p.status==='resolved')s.alertResolved=true;
      const key=code+':alert';if(wsStates[key]!==p.status){console.log(`ALERT ${code} ${flames[code].station} ${p.status} severity=${p.severity} id=${p.id}`);wsStates[key]=p.status;}
    }
    if(event.type==='asset'&&wsStates[code]!==p.status){console.log(`ASSET ${code} mesh=${p.mesh} state=${p.status}`);wsStates[code]=p.status;}
    mayFinish();
  }catch(e){log('websocket_error',{message:e.message});}
});
ws.on('error',e=>console.error('WebSocket:',e.message));
deadline=setTimeout(()=>finish('observation-window-ended'),180000);
process.on('SIGINT',()=>finish('observer-stopped'));
