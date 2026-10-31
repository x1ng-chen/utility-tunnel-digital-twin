/** Passive SHT/INA comparison. Never publishes commands or injects measurements. */
import {readFileSync,writeFileSync,appendFileSync,mkdirSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const require=createRequire(new URL('../../services/iotda-gateway/package.json',import.meta.url));
const mqtt=require('mqtt');
const seconds=Number(process.argv[2]??15);
if(!Number.isInteger(seconds)||seconds<10||seconds>120)throw Error('Observation seconds must be 10..120');
const runtime=new URL('../../.hardware-live/',import.meta.url);
const broker=readFileSync(new URL('.env',runtime),'utf8').match(/^LOCAL_MQTT_URL=(.+)$/m)?.[1].trim();
if(!broker)throw Error('No configured MQTT URL');
const folder=new URL('sht-check-'+new Date().toISOString().replace(/[-:.]/g,'')+'/',runtime);
mkdirSync(folder,{recursive:true});
const states={};const errors=[];let subscribed=false;
const startedAt=new Date().toISOString();
const client=mqtt.connect(broker,{reconnectPeriod:0,connectTimeout:5000,clientId:'sht-readonly-'+Date.now()});
client.on('error',e=>errors.push(e.message));
client.on('connect',()=>client.subscribe('ut/v1/+/telemetry',{qos:1},e=>{
  if(e)errors.push(e.message);else {subscribed=true;console.log('READY: passive SHT/INA telemetry comparison; no hardware commands.');}
}));
client.on('message',(topic,bytes,packet)=>{
  if(packet.retain)return;
  try{
    const frame=JSON.parse(bytes);
    if(!/^CTRL-0[1-4]$/.test(frame.controllerId??''))return;
    appendFileSync(new URL('events.jsonl',folder),JSON.stringify({receivedAt:new Date().toISOString(),topic,frame})+'\n');
    const s=states[frame.controllerId]??={frames:0,frameIds:new Set(),validShtFrames:0,missingShtFrames:0};
    s.frames++;s.frameIds.add(frame.frameId);
    const readings=(frame.readings??[]).filter(r=>['temperature','humidity'].includes(r.metric));
    const valid=readings.length===2&&readings.every(r=>r.quality==='good'&&Number.isFinite(r.value)&&r.sampleAgeMs>=0&&r.sampleAgeMs<5000);
    if(valid)s.validShtFrames++;else s.missingShtFrames++;
    s.last={receivedAt:new Date().toISOString(),frameId:frame.frameId,sourceTime:frame.ts,readings,
      fanReadings:(frame.readings??[]).filter(r=>r.assetCode?.startsWith('FAN-'))};
  }catch(e){errors.push(e.message);}
});
setTimeout(()=>{
  client.end(true);
  const controllers=Object.fromEntries(Object.entries(states).map(([id,s])=>[id,{...s,frameIds:[...s.frameIds]}]));
  const result={startedAt,finishedAt:new Date().toISOString(),subscribed,seconds,errors,hardwareCommands:0,modelCalls:0,controllers};
  writeFileSync(new URL('summary.json',folder),JSON.stringify(result,null,2));
  console.log(JSON.stringify({report:fileURLToPath(new URL('summary.json',folder)),...result}));
  if(errors.length||!subscribed||!Object.keys(states).length)process.exitCode=1;
},seconds*1000);
