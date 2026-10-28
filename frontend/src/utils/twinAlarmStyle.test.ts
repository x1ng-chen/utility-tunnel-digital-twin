import { describe, expect, it } from 'vitest';
import { BoxGeometry, Color, Group, Mesh, MeshStandardMaterial, Scene } from 'three';
import type { Alert, Asset } from '../types';
import { collectVisualAlarms, paintTwinMaterial, visualIntensity } from './twinAlarmStyle';
import { createAlarmEffects } from './twinAlarmEffects';
import { layoutAlarmLabels } from './alarmLabelLayout';

const asset={id:5,code:'FLAME-05',name:'火焰5',zone:'P5',mesh:'FLAME-05',status:'normal'} as Asset;
const alert={id:408,assetCode:'FLAME-05',ruleKey:'flame.alarm',title:'火焰数字输入超过报警阈值',severity:'critical',status:'open'} as Alert;
describe('visible alarm lifecycle',()=>{
  it('marks only the reported sensor, retains acknowledged alarms and removes resolved ones',()=>{
    const other={...asset,id:4,code:'FLAME-04'};
    expect(collectVisualAlarms([asset,other],[alert])).toMatchObject([{assetCode:'FLAME-05',zone:'P5',title:'火焰告警'}]);
    expect(collectVisualAlarms([asset],[{...alert,status:'acknowledged'}])).toHaveLength(1);
    expect(collectVisualAlarms([asset],[{...alert,status:'resolved'}])).toEqual([]);
    expect(collectVisualAlarms([asset],[{...alert,severity:'info'}])).toEqual([]);
    expect(collectVisualAlarms([{...asset,status:'alarm'}],[])).toHaveLength(1);
  });
  it('restores the same normal material after repeated alarms without accumulating a red tint',()=>{
    const material=new MeshStandardMaterial({color:0x638b90,emissive:0x101522});
    const baseline={color:material.color.clone(),emissive:material.emissive.clone()};
    paintTwinMaterial(material,baseline,'normal',false,false);
    const normal={color:material.color.clone(),emissive:material.emissive.clone(),intensity:material.emissiveIntensity};
    for(let n=0;n<10;n++)paintTwinMaterial(material,baseline,'alarm',true,true);
    expect(material.emissiveIntensity).toBeGreaterThan(normal.intensity*5);
    paintTwinMaterial(material,baseline,'normal',false,false);
    expect(material.color.equals(normal.color)).toBe(true);
    expect(material.emissive.equals(normal.emissive)).toBe(true);
    expect(visualIntensity('alarm',false,true,0)).toBeGreaterThan(visualIntensity('normal',true,false,0));
    material.dispose();
  });
  it('creates world markers without moving the sensor and fully disposes them on recovery',()=>{
    const scene=new Scene(),object=new Mesh(new BoxGeometry(.02,.025,.012),new MeshStandardMaterial());
    object.position.set(.375,.16,-.328);scene.add(object);scene.updateMatrixWorld(true);
    const before=object.matrixWorld.clone(),fx=createAlarmEffects(scene);
    const visual=collectVisualAlarms([asset],[alert])[0];
    fx.sync([{...visual,object}],.6);expect(fx.size).toBe(1);
    const marker=scene.getObjectByName('ALARM_MARKER_FLAME-05')!;
    expect(marker.position.distanceTo(object.position)).toBeLessThan(.00001);
    let disposed=0;marker.traverse(item=>{if(item instanceof Mesh)item.geometry.addEventListener('dispose',()=>disposed++);});
    fx.update(1);fx.update(2,true);
    expect(object.matrixWorld.equals(before)).toBe(true);
    fx.sync([{...visual,object}],.6);expect(scene.getObjectByName(marker.name)).toBe(marker);
    fx.sync([],.6);expect(fx.size).toBe(0);expect(scene.getObjectByName(marker.name)).toBeUndefined();expect(disposed).toBeGreaterThan(0);
    fx.dispose();expect(scene.children).toEqual([object]);object.geometry.dispose();object.material.dispose();
  });
  it('does not fabricate a position for empty or invalid geometry',()=>{
    const fx=createAlarmEffects(new Group());
    const visual=collectVisualAlarms([asset],[alert])[0];
    const object=new Mesh(new BoxGeometry(.02,.025,.012),new MeshStandardMaterial());
    fx.sync([{...visual,object}],.6);expect(fx.size).toBe(1);
    fx.sync([{...visual,object:new Group()}],.6);
    expect(fx.size).toBe(0);expect(fx.anchors()).toEqual([]);fx.dispose();
    object.geometry.dispose();object.material.dispose();
  });
  it('separates overlapping labels, preserves exact anchors and bounds labels on small screens',()=>{
    const base=collectVisualAlarms([asset],[alert])[0];
    const points=Array.from({length:4},(_,i)=>({...base,assetCode:'FLAME-0'+(i+1),anchorX:360+i,anchorY:320+i}));
    const labels=layoutAlarmLabels(points,900,560);
    expect(labels).toHaveLength(4);
    for(const label of labels){expect(label.x).toBeGreaterThanOrEqual(12);expect(label.x+label.width).toBeLessThanOrEqual(888);}
    for(let i=0;i<labels.length;i++)for(let j=i+1;j<labels.length;j++)
      expect(Math.abs(labels[i].x-labels[j].x)>=labels[i].width+8 || Math.abs(labels[i].y-labels[j].y)>=76).toBe(true);
    expect(labels.map(x=>x.anchorX)).toEqual(points.map(x=>x.anchorX));
    expect(layoutAlarmLabels(points,360,500)).toHaveLength(3);
    expect(layoutAlarmLabels(points,0,0)).toEqual([]);
  });
});
