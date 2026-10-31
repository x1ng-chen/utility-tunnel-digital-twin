import { Box3, BoxGeometry, BufferGeometry, DoubleSide, EdgesGeometry, Group, Line, LineBasicMaterial,
  LineSegments, Mesh, MeshBasicMaterial, Object3D, RingGeometry, SphereGeometry, Vector3 } from 'three';
import type { VisualAlarm } from './twinAlarmStyle';
export type AlarmTarget = VisualAlarm & {object:Object3D};

/** Lightweight markers live outside the model. No lights, bloom, or model scaling. */
export function createAlarmEffects(parent:Object3D) {
  const root=new Group();root.name='TWIN_ACTIVE_ALARM_EFFECTS';parent.add(root);
  const entries=new Map<string,{target:AlarmTarget;group:Group;rings:Mesh<RingGeometry,MeshBasicMaterial>[];
    outline:LineSegments<EdgesGeometry,LineBasicMaterial>;anchor:Vector3;severity:string}>();
  function remove(code:string) {
    const item=entries.get(code);if(!item)return;
    item.group.traverse(o=>{
      if (o instanceof Mesh || o instanceof Line || o instanceof LineSegments) {
        o.geometry.dispose();(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose());
      }
    });item.group.removeFromParent();entries.delete(code);
  }
  function sync(targets:AlarmTarget[], sceneRadius:number) {
    const next=new Set(targets.map(t=>t.assetCode));
    for(const code of entries.keys())if(!next.has(code))remove(code);
    for(const target of targets) {
      const old=entries.get(target.assetCode);
      if(old&&old.target.object===target.object&&old.severity===target.severity){old.target=target;continue;}
      remove(target.assetCode);
      const bounds=new Box3().setFromObject(target.object);
      if(bounds.isEmpty()||![...bounds.min.toArray(),...bounds.max.toArray()].every(Number.isFinite))continue;
      const center=bounds.getCenter(new Vector3()),size=bounds.getSize(new Vector3());
      const minimum=Math.max(.005,sceneRadius*.012);
      const radius=Math.min(Math.max(size.x,size.z)*.85+minimum,sceneRadius*.07);
      const color=target.severity==='critical'?0xff3157:0xffab35;
      const group=new Group();group.name='ALARM_MARKER_'+target.assetCode;group.position.copy(center);root.add(group);
      const rings=[0,1].map(i=>{
        const mesh=new Mesh(new RingGeometry(radius*.84,radius,64),new MeshBasicMaterial({color,transparent:true,
          opacity:.72,side:DoubleSide,depthTest:false,depthWrite:false,toneMapped:false}));
        mesh.rotation.x=-Math.PI/2;mesh.position.y=-size.y/2+minimum*.2;mesh.renderOrder=100+i;group.add(mesh);return mesh;
      });
      const box=new BoxGeometry(Math.max(size.x+minimum,minimum*2),Math.max(size.y+minimum,minimum*2),Math.max(size.z+minimum,minimum*2));
      const edges=new EdgesGeometry(box);box.dispose();
      const outline=new LineSegments(edges,new LineBasicMaterial({color,transparent:true,opacity:.92,depthTest:false,depthWrite:false,toneMapped:false}));
      outline.renderOrder=104;group.add(outline);
      const height=size.y/2+minimum*5;
      const leader=new Line(new BufferGeometry().setFromPoints([new Vector3(0,size.y/2,0),new Vector3(0,height,0)]),
        new LineBasicMaterial({color,transparent:true,opacity:.85,depthTest:false,depthWrite:false,toneMapped:false}));
      leader.renderOrder=105;group.add(leader);
      const tip=new Mesh(new SphereGeometry(minimum*.55,10,8),new MeshBasicMaterial({color:0xffffff,transparent:true,opacity:1,depthTest:false,depthWrite:false,toneMapped:false}));
      tip.position.y=height;tip.renderOrder=106;group.add(tip);
      entries.set(target.assetCode,{target,group,rings,outline,anchor:center.clone().add(new Vector3(0,height,0)),severity:target.severity});
    }
  }
  return {
    sync,
    update(seconds:number,reducedMotion=false){
      for(const item of entries.values()) {
        item.rings.forEach((ring,i)=>{
          const phase=reducedMotion ? .3 : ((seconds/2.4+i*.5)%1+1)%1;
          ring.scale.setScalar(1+phase*.85);ring.material.opacity=reducedMotion?.6:(1-phase)*.68;
        });
        item.outline.material.opacity=reducedMotion?.9:.8+Math.sin(seconds*2.7)*.14;
      }
    },
    anchors(){return [...entries.values()].map(item=>({...item.target,world:item.anchor}));},
    get size(){return entries.size;},
    clear(){for(const code of [...entries.keys()])remove(code);},
    dispose(){this.clear();root.removeFromParent();},
  };
}
