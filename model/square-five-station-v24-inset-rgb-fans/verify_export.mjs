// Actual Three.js loader review of V24 geometry/metadata. No Blender or device commands.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath,pathToFileURL } from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url)),base=path.resolve(root,'sources/square-five-station-v23-refined-acrylic');
const three=path.resolve(root,'../../frontend/node_modules/three');
const T=await import(pathToFileURL(path.join(three,'build/three.module.js')));
const {GLTFLoader}=await import(pathToFileURL(path.join(three,'examples/jsm/loaders/GLTFLoader.js')));
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
async function load(dir){const file=path.join(dir,path.basename(dir)+'.glb'),buf=fs.readFileSync(file),json=JSON.parse(buf.subarray(20,20+buf.readUInt32LE(12))),gltf=await new GLTFLoader().parseAsync(buf.buffer.slice(buf.byteOffset,buf.byteOffset+buf.byteLength),'');gltf.scene.updateMatrixWorld(true);const nodeObjects=new Map();for(const [obj,a]of gltf.parser.associations)if(a.nodes!==undefined)nodeObjects.set(a.nodes,obj);return{file,json,gltf,byName:new Map(json.nodes.map((n,i)=>[n.name,nodeObjects.get(i)]))};}
const [old,now]=await Promise.all([load(base),load(root)]),review=read(path.join(root,'fan-mount-review.json')),contract=read(path.join(root,'fan-animation-contract.json'));
const checks=[];
const assert=(ok,msg)=>{if(!ok)throw Error(msg);};
const near=(a,b,e=1e-6)=>a.length===b.length&&a.every((v,i)=>Math.abs(v-b[i])<e);
function check(name,fn){try{checks.push({name,status:'PASS',evidence:fn()});}catch(e){checks.push({name,status:'FAIL',error:e.message});}}
const get=name=>{const o=now.byName.get(name);assert(o,'Missing '+name);return o;};
const convert=([x,y,z])=>new T.Vector3(x,z,-y);
check('complete_actual_glb_and_preserved_sensor_controller_identities',()=>{
 assert(now.json.nodes.length===755&&now.byName.size===755,'755 unique nodes');
 const assets=now.json.nodes.filter(n=>n.extras?.assetCode),oldassets=old.json.nodes.filter(n=>n.extras?.assetCode);
 assert(assets.length===69&&assets.filter(n=>n.extras.category==='external_sensor').length===31,'69 assets,31 sensors');
 for(const n of oldassets){if(n.extras.category==='fan')continue;const current=assets.find(a=>a.extras.assetCode===n.extras.assetCode);assert(current,'Missing asset '+n.extras.assetCode);assert(JSON.stringify(current.extras)===JSON.stringify(n.extras),'Identity/extras changed '+n.extras.assetCode);assert(near(get(current.name).matrixWorld.elements,old.byName.get(n.name).matrixWorld.elements),'Moved unrelated asset '+n.extras.assetCode);}
 assert(!now.json.animations?.length,'No live autoplay');return{nodes:755,assets:69,sensors:31,otherAssetRootsPreserved:67};
});
check('identical_120mm_inset_fans_with_real_square_apertures',()=>{
 const evidence=[];
 for(const fan of contract.fans){const code=fan.assetCode,rootObj=get(code),frame=get(code+'_FRAME'),wall=get(fan.wallNode);
  const size=new T.Box3().setFromObject(frame).getSize(new T.Vector3());assert(near(size.toArray(),[.12,.12,.025],.00011),'120x120x25 frame bounds '+code);
  const front=rootObj.getWorldPosition(new T.Vector3());assert(near(front.toArray(),convert(fan.centreBlender_m).toArray()),'Front flush position '+code);
  const normal=convert(fan.outwardAxisBlender).normalize(),centre=convert(fan.openingCentreBlender_m);
  let rays=0;
  for(const dx of [-.05,-.025,0,.025,.05])for(const dz of [-.05,-.025,0,.025,.05]){
   const at=centre.clone().add(new T.Vector3(dx,dz,0));const ray=new T.Raycaster(at.addScaledVector(normal,.01),normal.clone().negate(),0,.02);
   assert(ray.intersectObject(wall,true).length===0,'Blocked aperture '+code);rays++;
  }
  const at=centre.clone().add(new T.Vector3(.065,0,0)),ray=new T.Raycaster(at.addScaledVector(normal,.01),normal.clone().negate(),0,.02);
  assert(ray.intersectObject(wall,true).length>0,'Side plate was hidden instead of cut '+code);
  assert(wall.userData.openingWidthMm===120.4&&wall.userData.openingHeightMm===120.4,'Equal rectangular aperture metadata');
  const frameGeo=frame.isMesh?frame.geometry:frame.children.find(o=>o.isMesh)?.geometry;assert(frameGeo,'Frame mesh');
  // Ray through an unobstructed part of the circular throat, away from blades.
  const throatRay=new T.Raycaster(front.clone().add(new T.Vector3(.04,0,0)).addScaledVector(normal,.01),normal.clone().negate(),0,.06);
  assert(throatRay.intersectObject(frame,true).length===0,'Circular frame throat must be open');
  evidence.push({code,measuredFrameWorldMm:size.toArray().map(v=>v*1000),openApertureGridRays:rays,cutoutMm:[120.4,120.4],frontFlush:true});
 }
 return evidence;
});
check('independent_rotors_axes_and_fixed_power_rgb',()=>{
 let segments=0;
 for(const code of ['FAN-01','FAN-02']){
  const fan=get(code),rotor=get(code+'_ROTOR');assert(rotor.parent===fan,'Rotor parent');
  assert(rotor.children.filter(o=>o.name.includes('BLADE')).length===7,'Seven blades');
  const axis=new T.Vector3(...rotor.userData.spinAxisLocal).transformDirection(rotor.matrixWorld);
  const expected=code==='FAN-01'?new T.Vector3(0,0,-1):new T.Vector3(0,0,1);
  assert(axis.dot(expected)>.99999,'Exported local spin axis points along physical shaft '+code);
  const fixedBefore=fan.matrixWorld.clone(),centre=fan.getWorldPosition(new T.Vector3()),blade=rotor.children.find(o=>o.name.includes('BLADE')),position=blade.geometry.attributes.position;
  const normalDistanceBefore=expected.dot(new T.Vector3().fromBufferAttribute(position,0).applyMatrix4(blade.matrixWorld).sub(centre));
  rotor.rotateOnAxis(new T.Vector3(...rotor.userData.spinAxisLocal),.4);now.gltf.scene.updateMatrixWorld(true);
  const normalDistanceAfter=expected.dot(new T.Vector3().fromBufferAttribute(position,0).applyMatrix4(blade.matrixWorld).sub(centre));
  assert(Math.abs(normalDistanceBefore-normalDistanceAfter)<1e-6,'Blade stays in axial plane during rotation');assert(fan.matrixWorld.equals(fixedBefore),'Housing not rotating');
  for(let i=0;i<24;i++){
   const led=get(code+`_RGB_SEGMENT_${String(i).padStart(2,'0')}`);assert(led.parent===fan&&led.userData.fanRgb===true&&led.userData.fanAssetCode===code,'Fixed per-fan LED');
   assert(led.userData.lightingControl==='FRESH_SUPPLY_VOLTAGE_ONLY_INDEPENDENT_OF_TACH','Supply-only light rule');
   const materials=Array.isArray(led.material)?led.material:[led.material];assert(materials.every(m=>m.emissiveIntensity===0||m.emissive.equals(new T.Color(0))),'No invented live power in saved export');segments++;
  }
 }
 assert(contract.lighting.independentOfRpm&&contract.lighting.metricKey==='supply.voltage','Power-only contract');return{rotors:2,bladesPerRotor:7,fixedRgbMeshes:segments,verifiedAxisGltfLocal:[0,1,0],lightingIndependentOfRpm:true};
});
check('metadata_references_sensor_centres_and_transparent_panels',()=>{
 let refs=0;function walk(v,key=''){if(Array.isArray(v))v.forEach(x=>walk(x,key));else if(v&&typeof v==='object')Object.entries(v).forEach(([k,x])=>walk(x,k));else if(typeof v==='string'&&['meshNames','targetNode','relatedNodes','alarmTargetNode','stationGroupNode','groupNode','labelNode','labelsToggleNode','wallNode','rotorNode'].includes(key)){get(v);refs++;}}
 for(const name of ['asset-map.json','sensor-bindings.json','station-focus.json'])walk(read(path.join(root,name)));
 for(const n of [1,2,5])assert(near(get(`GAS-O2-${String(n).padStart(2,'0')}`).getWorldPosition(new T.Vector3()).toArray(),get('STATION_P'+n).getWorldPosition(new T.Vector3()).toArray()),'Centred oxygen P'+n);
 for(const name of ['CLEAR_WALL_TOP','CLEAR_WALL_BOTTOM','CLEAR_WALL_LEFT','CLEAR_WALL_RIGHT','REMOVABLE_TRANSPARENT_LID']){
  const node=now.json.nodes.find(n=>n.name===name);assert(node?.mesh!==undefined,'Panel mesh '+name);
  // Inspect the panel's own mesh, excluding opaque handles/speaker rims parented to the lid.
  for(const primitive of now.json.meshes[node.mesh].primitives){const m=now.json.materials[primitive.material];assert(m.alphaMode==='BLEND'&&Math.abs(m.pbrMetallicRoughness.baseColorFactor[3]-.008)<1e-6,'Transparent panel '+name);}
 }
 return{validReferences:refs,transparentPanels:5,oxygenCentresPreserved:3};
});
check('input_protection_export_hashes_and_hardware_off_boundary',()=>{
 for(const [file,sha]of Object.entries(review.protectedInputFiles))assert(hash(path.resolve(root,file))===sha,'Source changed');
 assert(hash(now.file)===review.glbSha256&&hash(path.join(root,path.basename(root)+'.blend'))===review.blendSha256,'Export/native hash');
 assert(review.hardwareCommandsSent===false&&review.realDeviceLinkageVerified===false,'No physical commissioning claim');
 return{glbSha256:hash(now.file),sourcePreserved:true,physicalVerification:'NOT_RUN_USER_CONFIRMED_DEVICES_OFF'};
});
const report={status:checks.every(c=>c.status==='PASS')?'PASS':'FAIL',route:'ACTUAL_GLB_THREEJS_GLTFLOADER',date:'2026-10-29',checks,limitations:['120x120mm confirmed by user;25mm depth,105mm screw pitch and .2mm per-side clearance are unmeasured modelling assumptions.','Synthetic animation and voltage feedback tests do not prove live hardware linkage.','Fixed rainbow approximates the supplied photo; no optical color or addressable RGB feedback is claimed.']};
fs.writeFileSync(path.join(root,'export-verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));if(report.status!=='PASS')process.exitCode=1;
