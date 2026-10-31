<script setup lang="ts">
type Json=Record<string,unknown>;
type AgentStep={role:string;startedAt:string;output:Json|null;traces:Json[];calls:Json[]};
const props=defineProps<{steps:AgentStep[];running:boolean}>();
const roles:Record<string,string>={evidence:'取证Agent',diagnosis:'诊断Agent',review:'复核Agent',single:'单Agent基线'};
const tools:Record<string,string>={station_snapshot:'巡检站点快照',collect_station_evidence:'查询本站、邻站与风机证据',knowledge_search:'检索规程与缺陷',lookup_runbook:'查询运维手册',asset_snapshot:'查询设备快照',telemetry_trend:'查询历史趋势',recent_alerts:'查询告警',recent_commands:'查询控制记录',draft_work_order:'提出工单草案',propose_control:'提出仿真动作草案',cost_estimate:'测算任务成本'};
const decisions:Record<string,string>={pass:'复核通过',revise:'要求修改',insufficient:'证据不足'};
const array=(value:unknown):unknown[]=>Array.isArray(value)?value:[];
function text(value:unknown):string{if(typeof value==='string')return value;if(value&&typeof value==='object'){const item=value as Json;for(const key of ['summary','message','reason','hypothesis','cause','title'])if(typeof item[key]==='string')return item[key] as string;return JSON.stringify(value);}return String(value??'');}
function stepState(step:AgentStep,index:number){return step.output?'已有结构化输出':props.running&&index===props.steps.length-1?'执行中':'未完成，记录保留';}
</script>
<template>
  <section class="agent-trace" aria-label="实际Agent执行阶段"><p class="trace-boundary">以下来自本任务的实际阶段与工具记录。复核通过不等于现场验收；未执行阶段不显示为已完成。</p>
    <ol class="agent-handoffs"><li v-for="(step,index) in steps" :key="index"><header><div><h3>{{ roles[step.role]||step.role }}</h3><span>{{ stepState(step,index) }}</span></div><time>{{ step.startedAt }}</time></header>
      <p>{{ step.output?.summary || '尚未取得本阶段有效输出。' }}</p>
      <dl class="trace-counts"><div><dt>实际模型请求</dt><dd>{{ step.calls.length }}</dd></div><div><dt>实际工具记录</dt><dd>{{ step.traces.length }}</dd></div></dl>
      <ul v-if="step.traces.length" class="trace-tools" aria-label="本阶段实际工具调用"><li v-for="(trace,n) in step.traces" :key="String(trace.id||n)"><div><code>{{ trace.id }}</code><strong>{{ tools[String(trace.tool)]||trace.tool }}</strong><span :class="{rejected:trace.status!=='ok'}">{{ trace.status==='ok'?'已返回':'拒绝／失败' }}</span></div><small v-if="trace.queriedAt">查询时间 {{ trace.queriedAt }}</small><details><summary>参数与返回证据</summary><pre>{{ JSON.stringify(trace,null,2) }}</pre></details></li></ul>
      <p v-if="array(step.output?.evidence_ids).length" class="trace-citations">引用证据：<code v-for="id in array(step.output?.evidence_ids)" :key="String(id)">{{ id }}</code></p>
      <section v-if="array(step.output?.candidates).length"><h4>候选原因（待核查）</h4><ul><li v-for="(item,n) in array(step.output?.candidates)" :key="n">{{ text(item) }}</li></ul></section>
      <section v-if="array(step.output?.missing).length"><h4>缺失信息</h4><ul><li v-for="(item,n) in array(step.output?.missing)" :key="n">{{ text(item) }}</li></ul></section>
      <section v-if="array(step.output?.next_checks).length"><h4>下一项检查</h4><ul><li v-for="(item,n) in array(step.output?.next_checks)" :key="n">{{ text(item) }}</li></ul></section>
      <section v-if="step.output?.decision" class="review-decision"><h4>{{ decisions[String(step.output.decision)]||step.output.decision }}</h4><ul><li v-for="(item,n) in array(step.output.findings)" :key="n">{{ text(item) }}</li></ul></section>
      <details><summary>完整阶段记录与结构化断言</summary><pre>{{ JSON.stringify(step,null,2) }}</pre></details>
    </li></ol>
  </section>
</template>
<style scoped>
.agent-trace{min-width:0}.trace-boundary{font-size:12px;color:var(--ops-muted);line-height:1.7}.agent-handoffs{padding:0;list-style:none;margin:20px 0;display:grid;gap:20px}.agent-handoffs>li{min-width:0;padding:0 0 20px;border-bottom:1px solid var(--ops-line)}header{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px}header>div{display:flex;align-items:center;flex-wrap:wrap;gap:8px}h3{font-size:16px;margin:0}header span{font-size:11px;color:var(--ops-signal);padding:3px 7px;border:1px solid var(--ops-line);border-radius:5px}time{font-size:11px;color:var(--ops-muted);overflow-wrap:anywhere}p,li{font-size:13px;line-height:1.7;overflow-wrap:anywhere}h4{font-size:13px;margin:16px 0 6px}.trace-counts{display:flex;flex-wrap:wrap;gap:16px;margin:12px 0;font-size:12px}.trace-counts>div{display:flex;gap:8px}.trace-counts dt{color:var(--ops-muted)}dd{margin:0;font-variant-numeric:tabular-nums}.trace-tools{list-style:none;padding:0;margin:12px 0}.trace-tools>li{padding:12px 0;border-top:1px solid var(--ops-line-soft)}.trace-tools>li>div{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.trace-tools strong{font-size:12px}.trace-tools span,.trace-tools small{font-size:11px;color:var(--ops-muted)}.trace-tools .rejected{color:var(--ops-danger)}code{font-size:12px}.trace-citations{display:flex;flex-wrap:wrap;gap:8px}.trace-citations code{padding:0 5px;border-radius:4px;background:var(--ops-raised)}details{margin-top:8px}summary{min-height:32px;cursor:pointer;font-size:12px;color:var(--ops-signal)}summary:focus-visible{outline:2px solid var(--ops-signal);outline-offset:2px}pre{max-width:100%;overflow:auto;max-height:320px;padding:12px;background:var(--ops-bg-deep);font:12px/1.6 ui-monospace,monospace;white-space:pre}.review-decision{padding:12px 14px;border:1px solid var(--ops-line);border-radius:8px;background:var(--ops-bg-deep)}.review-decision h4{margin-top:0}
</style>
