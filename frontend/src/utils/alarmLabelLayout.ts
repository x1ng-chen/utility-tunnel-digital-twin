import type { VisualAlarm } from './twinAlarmStyle';
export type AlarmAnchor = VisualAlarm & {anchorX:number; anchorY:number};
export type AlarmLabel = AlarmAnchor & {x:number; y:number; width:number};

/** Move labels, never sensor coordinates. Leaders retain each exact anchor. */
export function layoutAlarmLabels(points: AlarmAnchor[], width: number, height: number): AlarmLabel[] {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width < 60 || height < 80) return [];
  const margin = 12, labelWidth = Math.min(174, width-margin*2), labelHeight = 68;
  const top = height > 300 ? 106 : margin;
  const clampX = (x:number) => Math.max(margin,Math.min(width-labelWidth-margin,x));
  const clampY = (y:number) => Math.max(top,Math.min(height-labelHeight-72,y));
  const placed:AlarmLabel[]=[];
  for (const point of points.slice(0,width < 520 ? 3 : 6)) {
    if (!Number.isFinite(point.anchorX) || !Number.isFinite(point.anchorY)) continue;
    const candidates = [-78,-140,30,92,-202].flatMap(dy => [18,-labelWidth-18].map(dx=>({x:clampX(point.anchorX+dx),y:clampY(point.anchorY+dy)})));
    const overlap = (position:{x:number;y:number}) => placed.reduce((sum,other)=>sum+
      Math.max(0,Math.min(position.x+labelWidth+8,other.x+labelWidth+8)-Math.max(position.x,other.x))*
      Math.max(0,Math.min(position.y+labelHeight+8,other.y+labelHeight+8)-Math.max(position.y,other.y)),0);
    const candidate = candidates.find(c=>overlap(c)===0) ?? candidates.reduce((best,c)=>overlap(c)<overlap(best)?c:best,candidates[0]);
    placed.push({...point,...candidate,width:labelWidth});
  }
  return placed;
}
