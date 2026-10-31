/** Explicit, short, single-fan bench exercise. Never called by API, Agent or CI. */
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync, appendFileSync, mkdirSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const require = createRequire(new URL('../../services/iotda-gateway/package.json', import.meta.url));
const mqtt = require('mqtt');
const args = process.argv.slice(2), number = args[args.indexOf('--fan')+1];
assert.ok(args.includes('--fan') && ['1','2'].includes(number), 'Select --fan 1 or --fan 2');
const fan = `FAN-0${number}`, controller = number==='1' ? 'CTRL-04' : 'CTRL-02';
if (!args.includes('--run')) {console.log(JSON.stringify({dryRun:true, fan, controller, sequence:['fresh idle/alarm preflight','100% + relay on','50% if voltage/speed observed','relay off + PWM zero','verify new off telemetry'], maxCommandTtlMs:15000})); process.exit(0);}
const runtime = new URL('../../.hardware-live/', import.meta.url);
const stamp = new Date().toISOString().replace(/[-:.]/g,'');
const folder = new URL(`fan-test-${number}-${stamp}/`, runtime); mkdirSync(folder,{recursive:true});
const env = readFileSync(new URL('.env',runtime),'utf8');
const broker = env.match(/^LOCAL_MQTT_URL=(.+)$/m)?.[1].trim(); assert.ok(broker);
const frames = new Map(), pending = new Map(), commands=[], phases=[];
let phase='baseline', connected=false, subscribed=false, error=null, attempted=false;
const log = (kind,data) => appendFileSync(new URL('events.jsonl',folder), JSON.stringify({receivedAt:new Date().toISOString(),kind,phase,...data})+'\n');
const client = mqtt.connect(broker,{clientId:`bench-${fan}-${Date.now()}`,reconnectPeriod:0,connectTimeout:4000});
client.on('connect',()=>{connected=true;client.subscribe(['ut/v1/CTRL-02/telemetry','ut/v1/CTRL-04/telemetry',`ut/v1/${controller}/cmd_ack`],{qos:1},e=>{if(e)error=e.message;else subscribed=true;});});
client.on('error',e=>{error=e.message;});
client.on('message',(topic,bytes,packet)=>{
  if(packet.retain)return;
  try {
    const data=JSON.parse(bytes);
    if(topic.endsWith('/telemetry')) {
      const relevant=(data.readings??[]).filter(r=>r.assetCode?.startsWith('FAN-')||['smoke.alarm','flame.alarm'].includes(r.metric));
      frames.set(data.controllerId,{at:Date.now(),frameId:data.frameId,clockSource:data.clockSource,readings:relevant});
      log('telemetry',{topic,frameId:data.frameId,controllerId:data.controllerId,readings:relevant});
    } else {
      log('ack',{topic,data});
      const p=pending.get(data.cmdId);
      if(p && data.controllerId===controller && data.schema==='ut.command-ack.v2'){pending.delete(data.cmdId);clearTimeout(p.timer);p.resolve(data);}
    }
  } catch(e){log('decode_error',{message:e.message});}
});
const sleep = ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function waitFor(check,ms){const end=Date.now()+ms;while(!check()){if(error)throw Error(error);if(Date.now()>=end)throw Error('Fresh telemetry/connection wait timed out');await sleep(100);}}
function current(board=controller){const f=frames.get(board);assert.ok(f && Date.now()-f.at<4000,`${board}: stale telemetry`);return f;}
function fanValues(board=controller){return Object.fromEntries(current(board).readings.filter(r=>r.assetCode?.startsWith('FAN-')).map(r=>[r.metric,{value:r.value,quality:r.quality,unit:r.unit}]));}
async function send(command,value,ttlMs=15000){
  assert.ok(['fan','relay'].includes(command)); assert.ok(ttlMs<=15000);
  const cmd={schema:'ut.command.v2',cmdId:`bench-${fan}-${Date.now()}-${commands.length}`,controllerId:controller,command,value,issuedAtMs:Date.now(),ttlMs};
  commands.push(cmd);log('command',{topic:`ut/v1/${controller}/cmd`,command:cmd});attempted=true;
  const ack=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(cmd.cmdId);reject(Error(`No correlated ACK: ${cmd.cmdId}; no automatic retry`));},4000);
    pending.set(cmd.cmdId,{resolve,reject,timer});
    client.publish(`ut/v1/${controller}/cmd`,JSON.stringify(cmd),{qos:1,retain:false},e=>{if(e){clearTimeout(timer);pending.delete(cmd.cmdId);reject(e);}});
  });
  log('correlated_result',{commandId:cmd.cmdId,ack});
  assert.equal(ack.status,'accepted',`Command ${command} refused: ${ack.reason}`);
  return ack;
}
function record(name){const value={phase:name,at:new Date().toISOString(),target:fanValues(),other:fanValues(controller==='CTRL-04'?'CTRL-02':'CTRL-04')};phases.push(value);console.log(JSON.stringify(value));}
try {
  await waitFor(()=>connected&&subscribed&&frames.has('CTRL-02')&&frames.has('CTRL-04'),8000);
  for(const board of ['CTRL-02','CTRL-04']){
    const f=current(board), alarms=f.readings.filter(r=>['smoke.alarm','flame.alarm'].includes(r.metric));
    assert.equal(alarms.length,2);assert.ok(alarms.every(r=>r.quality==='good'&&r.value===0),`${board}: local smoke/flame protection active or unverified`);
    const v=fanValues(board);assert.equal(v['relay.commanded']?.value,0,`${board}: relay already enabled`);
    assert.equal(v['pwm.duty']?.value,0,`${board}: PWM already enabled`);
  }
  record('baseline');phase='full-speed';
  await send('fan',100);await send('relay',1);await sleep(4500);record('full-speed');
  const full=fanValues();
  if(full['supply.voltage']?.quality==='good' && full['supply.voltage'].value>=8 && full['rotational.speed']?.value>0){
    phase='half-speed';await send('fan',50,7000);await sleep(4000);record('half-speed');
  }else log('skip_half_speed',{reason:'No combined supply-voltage and tach evidence; stop to inspect wiring/power.'});
}catch(e){error=e.message;console.log(JSON.stringify({error}));}
finally {
  if(attempted&&connected){phase='stop';for(const [command,value] of [['relay',0],['fan',0]]){try{await send(command,value,5000);}catch(e){log('stop_error',{message:e.message});error??=e.message;}}}
  try {await sleep(4500);record('after-stop');}catch(e){error??=e.message;}
  const result={fan,controller,startedAt:stamp,finishedAt:new Date().toISOString(),error,commands,phases,
    authorization:'User requested testing after confirming both fans are fully connected.',
    executionMode:'explicit bounded bench MQTT, existing web/Agent control block unchanged',
    flashedFirmware:'R010 update not independently confirmed; do not certify current/power accuracy',
    speedCalibration:'PPR and TACH quality still require physical verification',browserAndPhysicalObservation:'user confirmation required',
    physicalStateVerified:false};
  writeFileSync(new URL('summary.json',folder),JSON.stringify(result,null,2));
  client.end(true);console.log(JSON.stringify({report:fileURLToPath(new URL('summary.json',folder)),error,commands:commands.length}));
  if(error)process.exitCode=1;
}
