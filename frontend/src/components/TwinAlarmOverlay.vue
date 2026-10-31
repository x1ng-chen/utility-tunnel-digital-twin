<script setup lang="ts">
import { computed } from 'vue';
import { Crosshair, Flame, TriangleAlert } from 'lucide-vue-next';
import type { AlarmLabel } from '../utils/alarmLabelLayout';
import type { VisualAlarm } from '../utils/twinAlarmStyle';

const props=defineProps<{alarms:VisualAlarm[];labels:AlarmLabel[];unplacedCodes:string[]}>();
const emit=defineEmits<{select:[assetCode:string]}>();
const primary=computed(()=>props.alarms[0]);
</script>

<template>
  <div v-if="primary" :class="['twin-alarm-overlay',primary.severity]" data-testid="twin-alarm-overlay">
    <div class="twin-alarm-edge" aria-hidden="true" />
    <svg class="twin-alarm-leaders" aria-hidden="true">
      <g v-for="label in labels" :key="label.assetCode" :class="label.severity">
        <path :d="`M ${label.anchorX} ${label.anchorY} L ${label.x+12} ${label.y+62} L ${label.x+28} ${label.y+62}`" />
        <circle :cx="label.anchorX" :cy="label.anchorY" r="4" />
      </g>
    </svg>
    <TransitionGroup name="alarm-tag" tag="div" class="twin-alarm-tags" aria-label="告警位置标注">
      <button v-for="label in labels" :key="label.assetCode" type="button"
        :class="['twin-alarm-tag',label.severity]" :style="{left:`${label.x}px`,top:`${label.y}px`,width:`${label.width}px`}" 
        :aria-label="`定位${label.zone} ${label.assetCode} ${label.title}`" :title="`${label.title} · 点击定位${label.assetCode}`"
        @pointerdown.stop @click.stop="emit('select',label.assetCode)">
        <span class="twin-alarm-tag-icon"><Flame v-if="label.assetCode.startsWith('FLAME-')" /><TriangleAlert v-else /></span>
        <span class="twin-alarm-tag-copy"><span class="twin-alarm-tag-heading"><b>{{ label.zone }}</b><em>{{ label.severity==='critical'?'严重告警':'关注告警' }}</em></span><strong>{{ label.title }}</strong><small>{{ label.assetCode }}<Crosshair /></small></span>
      </button>
    </TransitionGroup>
    <section :class="['twin-alarm-summary',primary.severity]" role="status" aria-live="polite" aria-label="当前未解除告警">
      <span class="twin-alarm-summary-symbol"><TriangleAlert /><i /></span>
      <div><span class="twin-alarm-summary-eyebrow">告警定位 <b>{{ alarms.length }} 处</b></span><strong>{{ primary.zone }} · {{ primary.title }}</strong><small>{{ unplacedCodes.length ? `${unplacedCodes.length}处三维位置未绑定，请核查资产映射` : `${primary.assetCode} · 对应设备已标记` }}</small></div>
      <button type="button" :disabled="unplacedCodes.includes(primary.assetCode)" @pointerdown.stop @click.stop="emit('select',primary.assetCode)"><Crosshair />定位</button>
    </section>
  </div>
</template>

<style scoped>
.twin-alarm-overlay{--alarm:#ff3157;--alarm-rgb:255,49,87;position:absolute;inset:0;z-index:8;pointer-events:none;overflow:hidden;border-radius:inherit}
.twin-alarm-overlay.warning{--alarm:#ffb34d;--alarm-rgb:255,179,77}
.twin-alarm-edge{position:absolute;inset:1px;border:2px solid rgba(var(--alarm-rgb),.68);border-radius:inherit;box-shadow:inset 0 0 34px rgba(var(--alarm-rgb),.12);animation:alarm-edge-breathe 2.8s ease-in-out infinite}
.twin-alarm-leaders{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.twin-alarm-leaders path{fill:none;stroke:#ff466a;stroke-width:1.6;stroke-dasharray:4 3;filter:drop-shadow(0 0 3px #ff315788)}
.twin-alarm-leaders circle{fill:#ff3157;stroke:#fff;stroke-width:2}
.twin-alarm-leaders .warning path{stroke:#ffb34d}.twin-alarm-leaders .warning circle{fill:#ffb34d}
.twin-alarm-tag{--tag:#ff3157;position:absolute;display:flex;align-items:center;gap:10px;min-height:58px;padding:9px 11px;border:1px solid #ff6387;border-left:3px solid var(--tag);border-radius:10px;background:linear-gradient(120deg,rgba(90,21,47,.97),rgba(18,27,47,.98));box-shadow:0 9px 28px #15213b38,0 0 0 3px #ff315713;color:#fff;text-align:left;cursor:pointer;pointer-events:auto;transition:box-shadow .18s,border-color .18s;isolation:isolate}
.twin-alarm-tag.warning{--tag:#ffb34d;border-color:#ffc66e;background:linear-gradient(120deg,#593b1af7,#131e33fa)}
.twin-alarm-tag:hover,.twin-alarm-tag:focus-visible{outline:2px solid #fff;outline-offset:3px;box-shadow:0 0 0 5px #ff31572b,0 10px 32px #15213b55}
.twin-alarm-tag-icon{display:grid;place-items:center;flex:0 0 29px;width:29px;height:35px;border-radius:7px;background:#ff315725;color:#ffadbf}.twin-alarm-tag-icon svg{width:23px;height:23px;filter:drop-shadow(0 0 7px #ff3157aa)}
.warning .twin-alarm-tag-icon{color:#ffe1a7;background:#ffb34d20}.twin-alarm-tag-copy{display:grid;gap:3px;min-width:0;flex:1}.twin-alarm-tag-heading{display:flex;align-items:center;gap:7px}.twin-alarm-tag-heading b{color:#fff;font:800 14px ui-monospace,monospace}.twin-alarm-tag-heading em{padding:2px 4px;border:1px solid #ff92aa66;border-radius:4px;color:#ffb4c5;font-size:8px;font-style:normal;line-height:1.1;white-space:nowrap}.warning .twin-alarm-tag-heading em{color:#ffe0a1;border-color:#ffcb6e66}
.twin-alarm-tag-copy strong{overflow:hidden;max-width:100%;text-overflow:ellipsis;white-space:nowrap;color:#fff;font-size:11px;line-height:1.4}.twin-alarm-tag-copy small{display:flex;align-items:center;justify-content:space-between;color:#e6cbd6;font:9px ui-monospace,monospace}.twin-alarm-tag-copy small svg{width:11px;height:11px;color:#ffb7c7}
.twin-alarm-summary{position:absolute;left:16px;bottom:18px;display:flex;align-items:center;gap:12px;max-width:calc(100% - 32px);padding:12px 13px;border:1px solid #ff6387;border-radius:12px;background:linear-gradient(115deg,#4b172bf5,#111d33fa);box-shadow:0 12px 36px #19254433,0 0 0 4px #ff315710;color:#fff;pointer-events:auto}
.twin-alarm-summary.warning{border-color:#ffc56d;background:linear-gradient(115deg,#50381cf5,#111d33fa)}.twin-alarm-summary-symbol{position:relative;display:grid;place-items:center;flex:0 0 35px;width:35px;height:38px;border-radius:9px;background:#ff315725;color:#ff8fa8}.twin-alarm-summary-symbol svg{width:23px;height:23px}.twin-alarm-summary-symbol i{position:absolute;inset:-4px;border:1px solid #ff31576b;border-radius:13px;animation:alarm-edge-breathe 2.8s ease-in-out infinite}
.twin-alarm-summary>div{display:grid;gap:4px;min-width:0}.twin-alarm-summary-eyebrow{display:flex;align-items:center;gap:10px;color:#ffb8c9;font-size:9px;letter-spacing:.08em}.twin-alarm-summary-eyebrow b{padding:2px 5px;border-radius:4px;background:#ff31572b;color:#fff;font-size:9px;letter-spacing:0}.twin-alarm-summary strong{overflow:hidden;max-width:280px;text-overflow:ellipsis;white-space:nowrap;font-size:13px;font-weight:800}.twin-alarm-summary small{color:#e6cbd6;font-size:9px;line-height:1.3}
.twin-alarm-summary button{display:flex;align-items:center;gap:5px;flex:0 0 auto;min-height:34px;margin-left:6px;padding:0 10px;border:1px solid #ff96ad88;border-radius:7px;background:#ff315725;color:#fff;font-size:10px;font-weight:700;cursor:pointer}.twin-alarm-summary button svg{width:14px;height:14px}.twin-alarm-summary button:hover{background:#ff31574d}.twin-alarm-summary button:disabled{opacity:.4;cursor:not-allowed}
.alarm-tag-enter-active,.alarm-tag-leave-active{transition:opacity .18s ease,scale .18s ease}.alarm-tag-enter-from,.alarm-tag-leave-to{opacity:0;scale:.92}
@keyframes alarm-edge-breathe{0%,100%{opacity:.62}50%{opacity:1}}
@media(max-width:520px){.twin-alarm-summary{left:10px;bottom:12px;max-width:calc(100% - 20px);gap:8px;padding:10px}.twin-alarm-summary strong{max-width:180px;font-size:12px}.twin-alarm-summary button{padding:0 7px}.twin-alarm-summary-symbol{flex-basis:28px;width:28px}.twin-alarm-tag{gap:7px;padding:8px}.twin-alarm-tag-icon{flex-basis:24px;width:24px}.twin-alarm-tag-heading b{font-size:12px}}
@media(prefers-reduced-motion:reduce){.twin-alarm-edge,.twin-alarm-summary-symbol i{animation:none}.alarm-tag-enter-active,.alarm-tag-leave-active{transition:none}}
</style>
