<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink } from 'vue-router';
import { ArrowUpRight, Bot } from 'lucide-vue-next';
import type { Alert, Asset, WorkOrder } from '../types';
import { agentTaskLocation } from '../utils/agentTaskEntry';

const props = defineProps<{assets:Asset[]; alerts:Alert[]; orders:WorkOrder[]; modelPaused:boolean}>();
const activeAlert = computed(() => props.alerts.filter(item => ['open','acknowledged'].includes(item.status) && item.assetCode)
  .sort((a,b) => Number(b.severity==='critical')-Number(a.severity==='critical') || Date.parse(b.openedAt)-Date.parse(a.openedAt))[0]);
const diagnosisEntry = computed(() => {
  const alert=activeAlert.value;
  const asset=props.assets.find(item=>item.code===alert?.assetCode);
  return agentTaskLocation('diagnosis',{station:asset && /^P[1-5]$/.test(asset.zone) ? asset.zone : alert ? 'all' : 'P5',
    ...(asset ? {asset:asset.code} : {}),...(alert ? {alert:alert.code} : {})});
});
const reviewOrder = computed(() => props.orders.find(item=>item.status==='pending_review'));
</script>

<template>
  <section class="agent-mission-hub" aria-labelledby="agent-mission-title">
    <header><div class="mission-heading"><Bot aria-hidden="true" /><div><h2 id="agent-mission-title">交给Agent的运维任务</h2><p>从观测取证到独立复核，让每个结论都能找到依据。</p></div></div><RouterLink to="/agent-workbench" class="mission-open">进入任务工作台<ArrowUpRight aria-hidden="true" /></RouterLink></header>
    <div class="mission-content">
      <div class="mission-choices" aria-label="准备运维任务">
        <RouterLink :to="agentTaskLocation('inspection',{station:'all'})"><div><strong>巡检五站31路</strong><span>核对覆盖、过期、质量与活动告警</span></div><b>准备巡检<ArrowUpRight aria-hidden="true" /></b></RouterLink>
        <RouterLink :to="diagnosisEntry"><div><strong>排查告警与设备</strong><span>{{ activeAlert ? `${activeAlert.assetCode} · ${activeAlert.title}` : '暂无已加载活动告警，可先准备P5证据核查' }}</span></div><b>准备排障<ArrowUpRight aria-hidden="true" /></b></RouterLink>
        <RouterLink :to="agentTaskLocation('review',reviewOrder ? {order:reviewOrder.code,station:'all'} : {station:'all'})"><div><strong>复核处置是否恢复</strong><span>{{ reviewOrder ? `${reviewOrder.code} · ${reviewOrder.title}` : '选择工单，比较新观测和处置记录' }}</span></div><b>准备复核<ArrowUpRight aria-hidden="true" /></b></RouterLink>
      </div>
      <aside class="mission-method" aria-label="三Agent职责说明"><h3>三角色如何协作</h3><ol><li><b>取证Agent</b><span>选择快照、趋势与反馈工具，整理事实。</span></li><li><b>诊断Agent</b><span>检索规程，比较原因并提出检查与草案。</span></li><li><b>复核Agent</b><span>检查引用、冲突和动作条件，必要时退回修改。</span></li></ol><p>这是职责说明；实际任务可能补充取证、修改，或因证据不足停止。</p></aside>
    </div>
    <footer><span>{{ modelPaused ? '当前环境暂停模型调用，可准备任务或查看历史。' : '入口只准备任务；核对目标并明确开始后才调用模型。' }}</span><span>动作与工单仍需人工确认</span></footer>
  </section>
</template>

<style scoped>
.agent-mission-hub{min-width:0;margin:0 0 24px;border:1px solid var(--ops-line);border-radius:12px;background:var(--ops-panel);color:var(--ops-text)}
header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;padding:22px 24px;border-bottom:1px solid var(--ops-line-soft)}.mission-heading{display:flex;align-items:flex-start;gap:12px;min-width:0}.mission-heading>svg{width:28px;height:28px;flex-shrink:0;color:var(--ops-signal)}h2{margin:0;font-size:19px;line-height:1.4}header p{margin:6px 0 0;color:var(--ops-muted);font-size:13px;line-height:1.6}.mission-open{display:inline-flex;align-items:center;gap:6px;min-height:40px;font-size:13px;font-weight:600;color:var(--ops-signal)}.mission-open svg,.mission-choices b svg{width:16px;height:16px}
.mission-content{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(240px,1fr)}.mission-choices{min-width:0;padding:0 24px}.mission-choices>a{display:flex;justify-content:space-between;align-items:center;gap:16px;min-height:90px;padding:18px 0;border-bottom:1px solid var(--ops-line-soft)}.mission-choices>a:last-child{border-bottom:0}.mission-choices>a>div{min-width:0;display:grid;gap:5px}.mission-choices strong{font-size:15px}.mission-choices span{font-size:12px;line-height:1.7;color:var(--ops-muted);overflow-wrap:anywhere}.mission-choices b{display:inline-flex;align-items:center;gap:4px;flex-shrink:0;font-size:12px;color:var(--ops-signal)}.mission-choices a:hover strong{color:var(--ops-signal)}
.mission-method{padding:20px 24px;background:var(--ops-bg-deep);border-left:1px solid var(--ops-line-soft);border-radius:0 0 12px 0}h3{margin:0 0 16px;font-size:14px}.mission-method ol{display:grid;gap:14px;list-style:none;margin:0;padding:0}.mission-method li{display:grid;gap:4px}.mission-method b{font-size:13px}.mission-method span,.mission-method p{font-size:12px;line-height:1.6;color:var(--ops-muted)}.mission-method p{margin:16px 0 0}footer{display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px 20px;padding:12px 24px;border-top:1px solid var(--ops-line-soft);color:var(--ops-muted);font-size:12px;line-height:1.7}
a:focus-visible{outline:2px solid var(--ops-signal);outline-offset:3px;border-radius:5px}@media(max-width:1000px){.mission-content{grid-template-columns:minmax(0,1fr)}.mission-method{border-left:0;border-top:1px solid var(--ops-line-soft)}.mission-method ol{grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}@media(max-width:600px){header{padding:18px 16px}h2{font-size:17px}.mission-choices{padding:0 16px}.mission-choices>a{gap:10px;align-items:flex-start;min-height:90px}.mission-choices b{min-height:32px}.mission-method{padding:16px}.mission-method ol{grid-template-columns:minmax(0,1fr);gap:12px}.mission-open{min-height:44px}footer{padding:12px 16px}}
</style>
