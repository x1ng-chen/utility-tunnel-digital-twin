<script setup lang="ts">
import { computed } from 'vue';
type Json=Record<string,unknown>;
const props=defineProps<{result:Json}>();
const array=(value:unknown):Json[]=>Array.isArray(value)?value.filter(item=>item&&typeof item==='object') as Json[]:[];
const decisions=computed(()=>array(props.result.decisionTrace));
const topology=computed(()=>props.result.topologyContext && typeof props.result.topologyContext==='object' ? props.result.topologyContext as Json : null);
const edges=computed(()=>array(topology.value?.edges));
const procedures=computed(()=>props.result.procedureContext && typeof props.result.procedureContext==='object' ? props.result.procedureContext as Json : null);
const display=(value:unknown)=>typeof value==='string'?value:value==null?'未记录':JSON.stringify(value);
</script>
<template>
  <section class="decision-evidence" aria-label="新增能力的实际执行记录">
    <h3>本地决策与关联证据</h3>
    <p class="boundary">AnyJev仅选择允许的只读检查。选项分布不等于火灾或故障发生概率，不授权硬件动作。</p>
    <p v-if="!decisions.length" class="help">本任务未记录本地路由调用；不能据页面入口认定AnyJev已经执行。</p>
    <ol v-else class="decisions">
      <li v-for="(item,index) in decisions" :key="index"><header><strong>{{ item.status === 'selected' ? '选择只读检查' : '回退原取证流程' }}</strong><span>{{ item.model || '模型未记录' }}</span></header>
        <p v-if="item.status === 'selected'">选项：{{ display(item.selectedOption) }}<template v-if="item.executedTool">；实际工具：{{ item.executedTool }}</template><template v-if="item.executedEvidenceId">；证据：{{ item.executedEvidenceId }}</template></p>
        <p v-else class="fallback">回退原因：{{ item.fallbackReason || '未记录原因，请检查完整轨迹' }}</p>
        <small>模型版本 {{ item.modelRevision || '未记录' }} · 运行统计 {{ display(item.runtime) }} · 前两项log概率差 {{ item.logProbabilityGap ?? '未知' }}</small>
        <details><summary>查看候选分布、实际用量与完整路由记录</summary><pre>{{ JSON.stringify(item,null,2) }}</pre></details>
      </li>
    </ol>
    <details v-if="topology"><summary>冻结的设备关系与影响范围</summary><p class="boundary">这是配置关系及其推导，不是原始测量，也不能单独证明共同根因。</p>
      <p>关系版本 {{ topology.version || topology.topologyVersion || '未记录' }} · 目标 {{ topology.target || '见完整关系' }}</p>
      <div v-if="edges.length" class="table-wrap"><table><thead><tr><th>对象</th><th>关系</th><th>关联对象</th></tr></thead><tbody><tr v-for="(edge,index) in edges" :key="index"><td>{{ display(edge.from || edge.source) }}</td><td>{{ edge.relation || edge.kind || edge.type }}</td><td>{{ display(edge.to || edge.target) }}</td></tr></tbody></table></div>
      <pre>{{ JSON.stringify(topology,null,2) }}</pre>
    </details>
    <details v-if="procedures"><summary>本任务使用的受审检查模板</summary><p class="boundary">模板只定义检查步骤，不能代替本轮证据。未匹配、未批准和版本不一致的模板不得执行。</p><pre>{{ JSON.stringify(procedures,null,2) }}</pre></details>
    <details v-if="result.branchComparison"><summary>本任务的独立仿真分支</summary><p class="boundary">场景模型与假设下的推演，不能当作真实通风预测或现场动作回执。</p><pre>{{ JSON.stringify(result.branchComparison,null,2) }}</pre></details>
    <details v-if="result.failureAnalysis"><summary>本任务的失败轨迹分析</summary><p class="boundary">定位可检查的违规步骤；无法确定关键失败点时保留不确定性。</p><pre>{{ JSON.stringify(result.failureAnalysis,null,2) }}</pre></details>
  </section>
</template>
<style scoped>
.decision-evidence{min-width:0}h3{font-size:15px;margin:16px 0 8px}p{font-size:13px;line-height:1.7;overflow-wrap:anywhere}.boundary,.help,small{color:var(--ops-muted,#53657b);font-size:12px}.decisions{list-style:none;padding:0;margin:16px 0}.decisions>li{border-top:1px solid var(--ops-line-soft,#e5ebf3);padding:14px 0}header{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font-size:13px}header span{color:var(--ops-muted,#53657b);font-size:12px}.fallback{color:var(--ops-warn,#926c18)}details{margin-top:12px}summary{min-height:36px;cursor:pointer;color:var(--ops-signal,#1766c3);font-size:13px}summary:focus-visible{outline:2px solid var(--ops-signal,#1766c3);outline-offset:3px}pre{overflow:auto;max-width:100%;max-height:300px;background:var(--ops-bg-deep,#f8fafc);padding:12px;font:12px/1.6 ui-monospace,monospace}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}td,th{text-align:left;padding:9px;border-bottom:1px solid var(--ops-line-soft,#e5ebf3);overflow-wrap:anywhere}th{color:var(--ops-muted,#53657b)}
</style>
