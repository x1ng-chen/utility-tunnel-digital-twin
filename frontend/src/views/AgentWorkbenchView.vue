<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import AppShell from '../components/AppShell.vue';
import { api, type InvestigationCase } from '../services/api';
import { useAuthStore } from '../stores/auth';
import { useRoute } from 'vue-router';
import AgentRunTrace from '../components/AgentRunTrace.vue';
import AgentInvestigationPanel from '../components/AgentInvestigationPanel.vue';
import AgentDecisionEvidence from '../components/AgentDecisionEvidence.vue';
import AgentCapabilityTools from '../components/AgentCapabilityTools.vue';
import { agentTaskPrompt, readAgentTaskEntry, type AgentTaskEntry } from '../utils/agentTaskEntry';

type Json = Record<string, unknown>;
type Run = { id: string; status: string; stage: string; error: string; input: Json;
  source?: {label?:string;mode?:string}; snapshotHash?:string;
  steps: { role: string; startedAt: string; output: Json | null; traces: Json[]; calls: Json[] }[];
  result: { reply?: string; taskOutcome?: string; review?: Json; evidence?: Json[]; proposals?: Json[]; controlProposals?: Json[];
    guardrails?: { version: string; findings: Json[]; violations: Json[]; boundary: string };
    experienceContext?: { items: Json[]; hash?: string; enabled?: boolean };
    caseContext?:Json; topologyContext?:Json; decisionTrace?:Json[]; branchComparison?:Json; procedureContext?:Json; failureAnalysis?:Json;
    locations?: { assetCode: string; stationId: string; mappingStatus: string }[] };
  runtime: { modelCalls?: number; toolCalls?: number; elapsedMs?: number; tokens?: Json | null; tokenUsageComplete?: boolean } };
const auth = useAuthStore();
const route = useRoute();
const canWrite = computed(() => ['administrator', 'operator'].includes(auth.user?.role || ''));
const admin = computed(() => auth.user?.role === 'administrator');
const run = ref<Run | null>(null), history = ref<Run[]>([]);
const error = ref(''), notice = ref(''), busy = ref(false);
const station = ref('P5'), kind = ref('diagnosis'), mode = ref('multi'), asset = ref('MQ4-05'), order = ref('');
const proposeAction=ref(false),fanTarget=ref('FAN-01'),fanPwm=ref(60);
const prompt = ref('核查本站异常，比较邻站、风机反馈和控制记录，检索适用手册；列出候选原因、反证和下一项检查。');
const sourceLabel = ref('数据来源待核实'), modelNotice = ref('');
const modelCallsDisabled = ref(false);
const selectedInvestigation=ref<InvestigationCase|null>(null),selectedProcedure=ref<Json|null>(null);
const session = ref<Json | null>(null), cases = ref<string[]>([]), caseId = ref('INS-01');
const query = ref('风机有电流但没有转速'), historyKnowledge = ref(false), knowledge = ref<Json | null>(null);
const cost = ref<Json | null>(null), watts1 = ref(3.6), watts2 = ref(3.6), minutes = ref(10), price = ref(1);
const laborSeconds = ref(60), hourlyRate = ref(30);
const roiEnabled=ref(false), investment=ref(1000), annualBenefit=ref(100), annualOperatingCost=ref(50);
const confirmation = ref<{ type: 'command' | 'order'; data: Json; index: number } | null>(null);
const confirmationPanel = ref<HTMLElement>();
let confirmationOpener: HTMLElement | null = null;
watch(confirmation, async (pending) => {
  if (pending) {
    confirmationOpener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    await nextTick();
    confirmationPanel.value?.focus();
  } else {
    await nextTick();
    if (confirmationOpener?.isConnected) confirmationOpener.focus();
  }
});
const experiences = ref<Json[]>([]), experienceTruncated = ref(false), editing = ref<Json | null>(null), lessonText = ref('');
const experienceStates: Record<string, string> = {candidate:'候选，未批准',approved:'管理员已批准',rejected:'已驳回',retired:'已退役'};
const guardStates: Record<string, string> = {supported:'本来源下有证据支持',unsupported:'本来源下不支持',unknown:'证据不足'};
const active = computed(() => !!run.value && ['queued', 'running'].includes(run.value.status));
const preparedEntry = ref<AgentTaskEntry | null>(null);
watch(() => readAgentTaskEntry(route.query), entry => {
  if (!entry) { preparedEntry.value = null; return; }
  if (busy.value || active.value) return;
  if (entry.kind === 'draft' && !canWrite.value) { preparedEntry.value = null; error.value = '当前账号不能准备工单草案，可进行只读巡检、排障或复核。'; return; }
  kind.value = entry.kind; station.value = entry.station; mode.value = 'multi';
  if (entry.asset) asset.value = entry.asset;
  if (entry.order) order.value = entry.order;
  prompt.value = agentTaskPrompt(entry); preparedEntry.value = entry;
}, {immediate:true});
const inspected = computed(() => {
  const items=run.value?.result.evidence || [];
  const full=items.find(e=>e.status==='ok' && e.tool==='station_snapshot');
  if(full) return full.data as Json;
  const station=items.find(e=>e.status==='ok' && e.tool==='collect_station_evidence');
  return ((station?.data as Json | undefined)?.station as Json | undefined) || null;
});
const runStates: Record<string, string> = { queued: '等待执行', running: '正在执行', completed: '执行结束', failed: '执行失败', cancelled: '已取消', expired: '已过期' };
const outcomes:Record<string,string>={incomplete:'任务未完成，已有证据保留',reviewed:'已独立复核',observed:'已取得巡检证据',single_agent_unreviewed:'单Agent结果，未经独立复核',unresolved_review:'复核意见尚未解决',existing_work_order:'已有工单，未重复生成',no_confirmable_draft:'未形成可确认工单',no_confirmable_action:'未形成可确认动作'};
let timer: ReturnType<typeof setTimeout> | undefined;
let alive = true;
function fail(cause: unknown) { error.value = (cause as { response?: { data?: { message?: string } } }).response?.data?.message || '操作失败，请检查服务与权限。'; }
async function loadExperiences() {
  try { const { data } = await api.reviewExperiences(); experiences.value = data.items; experienceTruncated.value = data.truncated; }
  catch (cause) { fail(cause); }
}
async function experienceAction(item: Json, action: string, lesson?: string) {
  if (busy.value) return;
  busy.value = true; error.value = '';
  try {
    await api.transitionExperience(String(item.id), action, Number(item.revision), lesson);
    editing.value = null; await loadExperiences();
    notice.value = action === 'revise' ? '已生成新候选；原内容未覆盖。' : '经验状态已更新；审批不代表独立现场验证。';
  } catch (cause) { fail(cause); } finally { busy.value = false; }
}
async function poll() {
  if (!run.value || !alive) return;
  try { const { data } = await api.agentRun(run.value.id); if (alive) { run.value = data; if (!['queued','running'].includes(data.status) && canWrite.value) await loadExperiences(); } }
  catch (cause) { fail(cause); }
  if (alive && active.value) timer = setTimeout(poll, 1500);
}
async function start(previous = false) {
  if (busy.value || active.value || modelCallsDisabled.value) return;
  if (kind.value === 'draft' && !canWrite.value) return;
  if (kind.value === 'review' && !order.value.trim()) { error.value = '请先填写需要复核的工单编号。'; return; }
  if (kind.value === 'diagnosis' && selectedInvestigation.value && selectedInvestigation.value.stationId !== station.value) { error.value='任务检测站与排障档案不同，请重新选择档案或解除任务关联。'; return; }
  if (selectedProcedure.value?.stationId && selectedProcedure.value.stationId !== station.value) { error.value='任务检测站与已选检查模板不同，请移除模板或重新选择。'; return; }
  busy.value = true; error.value = ''; notice.value = ''; confirmation.value = null;
  try {
    const { data } = await api.createAgentRun({ kind: kind.value, station_id: station.value, mode: mode.value,
      prompt: prompt.value, ...(kind.value === 'draft' ? { asset_code: asset.value } : {}),
      ...(kind.value === 'review' ? { work_order_code: order.value } : {}),
      ...(kind.value === 'diagnosis' && selectedInvestigation.value ? {case_id:selectedInvestigation.value.id,...(selectedInvestigation.value.assetCode?{asset_code:selectedInvestigation.value.assetCode}:{})} : {}),
      ...(selectedProcedure.value ? {procedure_id:selectedProcedure.value.id} : {}),
      ...(kind.value === 'diagnosis' && mode.value === 'multi' && proposeAction.value ? {control_request:{asset_code:fanTarget.value,intent:'pwm',value:fanPwm.value}} : {}),
      ...(previous && run.value ? { previous_run_id: run.value.id } : {}) }, crypto.randomUUID());
    run.value = data; timer = setTimeout(poll, 500);
  } catch (cause) { fail(cause); } finally { busy.value = false; }
}
function selectInvestigation(value:InvestigationCase|null){selectedInvestigation.value=value;if(value){station.value=value.stationId;if(value.assetCode)asset.value=value.assetCode;}}
async function continueInvestigation(value:InvestigationCase){
  if(busy.value || active.value || modelCallsDisabled.value)return;
  selectInvestigation(value);kind.value='diagnosis';mode.value='multi';proposeAction.value=false;preparedEntry.value=null;
  prompt.value=`继续排查${value.stationId}${value.assetCode?`的${value.assetCode}`:''}：${value.title || '核对本档案的新观测和人工报告'}。比较已有假设的支持与反证，选择下一项允许的只读检查；保持不确定性，不自动结案。`;
  await start();
}
function prepareProcedure(value:Json){
  if(busy.value || active.value)return;
  selectedProcedure.value=value;kind.value='diagnosis';proposeAction.value=false;
  if(typeof value.stationId==='string' && /^P[1-5]$/.test(value.stationId))station.value=value.stationId;
  notice.value=`已准备检查模板“${value.title || value.id}”，尚未启动；请核对目标与档案关联后开始任务。`;
}
async function cancel() { if (!run.value) return; try { run.value = (await api.cancelAgentRun(run.value.id)).data; } catch (cause) { fail(cause); } }
async function selectRun(id: string) { if (timer) clearTimeout(timer); run.value = (await api.agentRun(id)).data; if (active.value) void poll(); }
async function demoAction(action: string) {
  try { await api.demoControl(action, action === 'reset' ? caseId.value : undefined); session.value = (await api.demoSession()).data.session; notice.value = '演示状态已更新，模型不会自动调用。'; }
  catch (cause) { fail(cause); }
}
async function search() { error.value = ''; try { knowledge.value = (await api.searchKnowledge(query.value, historyKnowledge.value)).data; } catch (cause) { fail(cause); } }
async function previewCommand(index: number) {
  if (!run.value) return;
  try { confirmation.value = { type: 'command', data: (await api.proposeDemoCommand(run.value.id, index)).data, index }; }
  catch (cause) { fail(cause); }
}
async function confirm(accept: boolean) {
  const pending = confirmation.value; if (!pending || !run.value || busy.value) return;
  busy.value = true;
  try {
    if (pending.type === 'command') {
      const { data } = await api.confirmDemoCommand(String(pending.data.actionId), accept ? 'confirm' : 'cancel');
      notice.value = `${data.state} · 模拟回执不证明现场转动或告警恢复。`;
    } else if (accept) {
      const proposal = pending.data;
      const { data } = await api.createWorkOrder({ assetCode: proposal.assetCode, title: proposal.title,
        description: proposal.description, priority: proposal.priority }, `run-${run.value.id}-${pending.index}`);
      order.value = data.code; notice.value = `已创建测试工单 ${data.code}；可选择“恢复复核”再次查询。`;
    } else notice.value = '已取消，未创建工单。';
    confirmation.value = null;
  } catch (cause) { fail(cause); } finally { busy.value = false; }
}
async function download(format: string) {
  if (!run.value) return;
  try { const { data } = await api.exportAgentRun(run.value.id, format); const url = URL.createObjectURL(data);
    const link = document.createElement('a'); link.href = url; link.download = `agent-${run.value.id}.${format}`;
    link.click(); URL.revokeObjectURL(url);
  } catch (cause) { fail(cause); }
}
async function calculate() {
  try {
    const end = new Date(), start = new Date(end.getTime() - minutes.value * 60000);
    cost.value = (await api.estimateCost({ start: start.toISOString(), end: end.toISOString(), source: 'SIMULATED_TEST',
      maxGapSeconds: Math.min(3600, minutes.value * 60),
      readings: [watts1.value, watts2.value].map((power, index) => ({ assetCode: `FAN-0${index + 1}`,
        at: start.toISOString(), power, unit: 'W', quality: 'good', rpm: 1200 })),
      tariffs: [{ start: start.toISOString(), end: end.toISOString(), price: price.value }],
      labor: { seconds: laborSeconds.value, hourlyRate: hourlyRate.value }, modelCost: null,
      ...(roiEnabled.value ? {roi:{investment:investment.value,annualBenefit:annualBenefit.value,annualOperatingCost:annualOperatingCost.value}} : {}) })).data;
  } catch (cause) { fail(cause); }
}
onMounted(async () => {
  if (!sessionStorage.getItem('ut-django-token')) { sourceLabel.value='当前为界面演示，请登录服务后使用运维任务。'; return; }
  try {
    const { data } = await api.agentContext(); sourceLabel.value = data.dataContext.label; modelNotice.value = data.modelNotice;
    modelCallsDisabled.value = data.dataContext.modelCallsDisabled === true;
    if (data.dataContext.demoControlsAvailable) { const demo=await api.demoSession(); session.value=demo.data.session; cases.value=demo.data.cases; }
  } catch { /* unknown provenance stays visible */ }
  try { history.value = (await api.agentRuns()).data; if (history.value[0]) { run.value = history.value[0]; if (active.value) void poll(); } } catch (cause) { fail(cause); }
  if (canWrite.value) await loadExperiences();
});
onUnmounted(() => { alive = false; if (timer) clearTimeout(timer); });
</script>

<template>
  <AppShell>
    <div class="agent-workbench">
      <header class="workbench-heading"><h1>多Agent工作台</h1><p>取证、诊断、复核，以及经过人工确认的仿真处置。</p></header>
      <p v-if="preparedEntry" class="prepared-task" role="status">已预选{{ preparedEntry.kind === 'inspection' ? '五站巡检' : preparedEntry.kind === 'review' ? '恢复复核' : preparedEntry.kind === 'draft' ? '工单草案' : '证据排障' }} · {{ preparedEntry.station === 'all' ? '全部五站' : preparedEntry.station }}<template v-if="preparedEntry.asset"> · {{ preparedEntry.asset }}</template><template v-if="preparedEntry.alert"> · {{ preparedEntry.alert }}</template><template v-if="preparedEntry.order"> · {{ preparedEntry.order }}</template>。请核对当前表单目标后开始；尚未调用模型或执行处置。</p>
      <aside class="source" role="status"><strong>{{ sourceLabel }}</strong><details v-if="modelNotice" class="model-context"><summary>模型与布局说明</summary><p>{{ modelNotice }}</p></details></aside>
      <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="notice" role="status" class="workbench-notice">{{ notice }}</p>
      <section v-if="session" class="panel demo-session"><h2>演示场景</h2><p>模拟测试 · 阶段 {{ session.phase }} · {{ session.running ? '持续采样' : '已暂停，观测将正常过期' }} · 已采样 {{ session.tick }} 轮</p>
        <div class="controls"><select v-model="caseId" aria-label="演示场景"><option v-for="id in cases" :key="id">{{ id }}</option></select>
          <template v-if="admin"><button @click="demoAction('reset')">重置场景</button><button @click="demoAction('start')">开始采样</button><button @click="demoAction('pause')">暂停采样</button><button @click="demoAction('advance')">推进阶段</button></template>
          <small v-else>场景控制由管理员操作；本账号可以查询。</small></div>
      </section>
      <AgentInvestigationPanel :station="station" :running="active" :model-calls-disabled="modelCallsDisabled" :last-run-id="run?.input.case_id === selectedInvestigation?.id ? run?.id : undefined" :last-run-status="run?.input.case_id === selectedInvestigation?.id ? run?.status : undefined" @select-case="selectInvestigation" @continue-case="continueInvestigation" />
      <div class="workbench-primary">
      <section class="panel task-composer" aria-labelledby="agent-task-title"><h2 id="agent-task-title">发起运维任务</h2><div class="controls task-fields">
        <label>检测点<select v-model="station"><option v-for="s in ['all','P1','P2','P3','P4','P5']" :key="s" :value="s">{{ s === 'all' ? '全部五站' : s }}</option></select></label>
        <label>任务<select v-model="kind"><option value="inspection">五站巡检</option><option value="diagnosis">证据排障</option><option value="draft" :disabled="!canWrite">工单草案</option><option value="review">恢复复核</option></select></label>
        <label>运行方式<select v-model="mode"><option value="multi">三Agent协作</option><option value="single">单Agent对照</option></select></label>
        <label v-if="kind === 'draft'">设备编码<input v-model="asset" /></label><label v-if="kind === 'review'">工单编号<input v-model="order" /></label>
      </div><div v-if="canWrite && kind === 'diagnosis' && mode === 'multi'" class="controls action-options"><label class="check-label"><input v-model="proposeAction" type="checkbox" />同时生成待复核的仿真风机动作草案</label><template v-if="proposeAction"><label>风机<select v-model="fanTarget"><option>FAN-01</option><option>FAN-02</option></select></label><label>PWM %<input v-model.number="fanPwm" type="number" min="0" max="100" /></label></template></div><label>任务说明<textarea v-model="prompt" maxlength="2000" rows="5" /></label>
        <p v-if="selectedInvestigation && kind==='diagnosis'" class="field-help">本次关联排障档案：{{ selectedInvestigation.title }} · {{ selectedInvestigation.stationId }}。原假设和历史快照将保留。</p>
        <div v-if="selectedProcedure" class="controls"><p class="field-help">已准备只读模板：{{ selectedProcedure.title }} · {{ selectedProcedure.stationId }} · 版本 {{ selectedProcedure.revision }}</p><button :disabled="busy || active" @click="selectedProcedure=null">移除检查模板</button></div>
        <div class="controls task-actions"><button class="workbench-primary-action" :disabled="busy || active || modelCallsDisabled" @click="start()">开始任务（调用模型）</button><button :disabled="busy || active || modelCallsDisabled || run?.status !== 'completed'" @click="start(true)">重新核查新证据</button><button v-if="active" @click="cancel">取消任务</button></div>
        <p v-if="modelCallsDisabled" class="field-help" role="status">当前环境已暂停模型调用，仍可查看历史记录和使用只读工具。</p>
        <p v-else class="field-help">提交后实际调用已配置的DeepSeek；调用用量与失败会保留。原悬浮助手继续可用。</p>
        <label v-if="history.length" class="run-history">历史任务<select :value="run?.id" @change="selectRun(($event.target as HTMLSelectElement).value)"><option v-for="item in history" :key="item.id" :value="item.id">{{ item.id.slice(0, 8) }} · {{ runStates[item.status] || item.status }}</option></select></label>
      </section>
      <div class="workbench-results">
      <section v-if="confirmation" ref="confirmationPanel" class="panel confirmation" role="alertdialog" aria-modal="false" aria-label="人工确认处置" aria-describedby="agent-confirmation-notice" tabindex="-1"><h2>确认{{ confirmation.type === 'command' ? '仿真动作' : '测试工单' }}</h2><pre>{{ JSON.stringify(confirmation.data, null, 2) }}</pre><p id="agent-confirmation-notice">请核对目标、动作与来源。此操作不会下发真实硬件。</p><div class="controls"><button class="workbench-primary-action" :disabled="busy" @click="confirm(true)">确认执行</button><button :disabled="busy" @click="confirm(false)">取消</button></div></section>
      <section v-if="run" class="panel run-result" aria-labelledby="agent-run-title"><header class="run-heading"><h2 id="agent-run-title">任务 {{ run.id.slice(0, 8) }}</h2><span :class="['run-status', { 'is-active': active }]" role="status">{{ runStates[run.status] || run.status }}</span></header><p v-if="run.error" role="alert" class="error">{{ run.error }}</p>
        <dl class="run-metrics"><div><dt>模型调用</dt><dd>{{ run.runtime.modelCalls ?? 0 }}</dd></div><div><dt>工具调用</dt><dd>{{ run.runtime.toolCalls ?? 0 }}</dd></div><div><dt>耗时</dt><dd>{{ run.runtime.elapsedMs ?? 0 }} <small>ms</small></dd></div><div><dt>Token</dt><dd>{{ run.runtime.tokens?.total_tokens ?? '未知' }}</dd></div></dl><p v-if="run.runtime.tokenUsageComplete === false" class="field-help">用量可能不完整，以实际账单为准。</p>
        <p class="field-help">执行目标：{{ run.input.kind === 'inspection' ? '五站巡检' : run.input.kind === 'diagnosis' ? '证据排障' : run.input.kind === 'draft' ? '工单草案' : run.input.kind === 'review' ? '恢复复核' : '旧任务未记录类型' }} · {{ run.input.station_id || '范围未记录' }}<template v-if="run.input.asset_code"> · {{ run.input.asset_code }}</template><template v-if="run.input.work_order_code"> · {{ run.input.work_order_code }}</template></p>
        <p class="field-help">本任务来源：{{ run.source?.label || '旧任务未记录来源，不能据当前页面推断' }}<template v-if="run.snapshotHash"> · 冻结快照 {{ run.snapshotHash }}</template></p>
        <AgentRunTrace v-if="run.steps.length" :steps="run.steps" :running="active" />
        <p v-else class="result-empty-note">本任务尚无执行阶段记录；阶段将在实际执行后显示。</p>
        <AgentDecisionEvidence :result="run.result" />
        <h3 v-if="run.result.reply">模型解释</h3><p v-if="run.result.taskOutcome" class="task-outcome">任务结果：{{ outcomes[run.result.taskOutcome] || run.result.taskOutcome }}</p><p class="model-reply">{{ run.result.reply }}</p><p v-if="run.result.review">复核：{{ run.result.review.decision }} · {{ run.result.review.summary }}。复核通过不等于现场验收或全部事实正确。</p>
        <section class="derived-checks"><h3>规则判断与阻断原因</h3>
          <template v-if="run.result.guardrails"><p>规则版本 {{ run.result.guardrails.version }} · 推导不是原始测量</p>
            <p v-for="(v, i) in run.result.guardrails.violations" :key="i" role="alert">阻断 {{ v.ruleId }}：{{ v.message }}</p>
            <details><summary>查看 {{ run.result.guardrails.findings.length }} 项规则判断</summary>
              <article v-for="f in run.result.guardrails.findings" :key="String(f.id)"><strong>{{ f.assetCode }} · {{ f.ruleId }}</strong>
                <p>{{ guardStates[String(f.state)] || f.state }} · {{ f.sourceScope }}：{{ f.message }}</p>
                <small>原始证据 {{ f.evidenceIds }} · 缺项 {{ f.missing }}</small></article>
            </details><p>{{ run.result.guardrails.boundary }}</p></template>
          <p v-else>旧版本任务未记录护栏结果；不会倒填为已验证。</p>
        </section>
        <section><h3>本任务使用的复核经验</h3>
          <template v-if="run.result.experienceContext"><p>已加载 {{ run.result.experienceContext.items.length }} 条管理员审核的匹配经验；仅为低信任排查提醒。</p>
            <p v-if="run.result.experienceContext.enabled === false">本任务未启用经验检索。</p>
            <article v-for="item in run.result.experienceContext.items" :key="String(item.id)"><p>{{ item.lesson }}</p>
              <small>{{ item.station_id }} · {{ item.source_scope }} · {{ item.rule_version }} · 内容散列 {{ item.content_hash }}</small>
              <details><summary>已批准 · 条目版本 {{ item.revision }} · 查看冻结来源与版本</summary><pre>{{ JSON.stringify(item, null, 2) }}</pre></details></article></template>
          <p v-else>旧版本任务未记录经验上下文。</p>
        </section>
        <details v-if="run.result.evidence?.length"><summary>查看原始证据</summary><pre>{{ JSON.stringify(run.result.evidence, null, 2) }}</pre></details>
        <section v-if="inspected"><h3>本轮取证覆盖</h3><p>预期 {{ inspected.expected_sensor_count }} 个物理模块 · 已登记 {{ inspected.registered_sensor_count }} · 场景观测可用 {{ inspected.scenario_usable_sensor_count }} · 数据异常 {{ inspected.data_issue_sensor_count }}。场景可用不代表现场实测。</p><div class="sensor-table"><table><thead><tr><th>检测站</th><th>设备</th><th>主控</th><th>观测状态／缺项</th><th>三维绑定</th></tr></thead><tbody><tr v-for="sensor in (inspected.items as Json[] || [])" :key="String(sensor.assetCode)"><td>{{ sensor.stationId }}</td><td>{{ sensor.assetCode }}</td><td>{{ sensor.controllerId }}</td><td>{{ sensor.observation_state }} {{ sensor.data_issues }}</td><td>{{ sensor.mapping_status }}</td></tr></tbody></table></div></section>
        <div class="controls location-links"><RouterLink v-for="location in run.result.locations || []" :key="location.assetCode" :to="{path:'/twin-3d',query:{asset:location.assetCode,source:'agent'}}">{{ location.stationId }} · {{ location.assetCode }} · {{ location.mappingStatus }}</RouterLink></div>
        <div v-if="canWrite"><article v-for="(proposal, index) in run.result.proposals || []" :key="index"><h3>待确认工单：{{ proposal.title }}</h3><p>{{ proposal.description }}</p><button @click="confirmation = {type:'order',data:proposal,index}">审阅工单草案</button></article>
          <article v-for="(proposal, index) in run.result.controlProposals || []" :key="index"><p>仿真动作：{{ proposal.asset_code }} · {{ proposal.intent }} → {{ proposal.value }}</p><button :disabled="!session" @click="previewCommand(index)">审阅仿真动作</button></article></div>
        <div class="controls export-actions" aria-label="导出本任务记录"><button v-for="format in ['json','csv','html']" :key="format" @click="download(format)">导出 {{ format.toUpperCase() }}</button></div>
      </section>
      <section v-else class="panel run-empty" aria-labelledby="agent-result-title"><h2 id="agent-result-title">执行记录与诊断结果</h2><p>选择检测点和任务后开始运行；这里将保留实际取证、诊断、复核及工具调用记录。</p><ul><li>巡检：核对五站传感器覆盖与观测质量。</li><li>排障：比较证据、候选原因与下一项检查。</li><li>处置：草案经人工确认后才创建工单或执行仿真。</li></ul><p class="field-help">打开工作台不会自动调用模型或下发控制命令。</p></section>
      </div>
      </div>
      <div class="workbench-tools" aria-label="辅助运维工具">
      <AgentCapabilityTools :station="station" :run-id="run?.id" :run-status="run?.status" :can-write="canWrite" :admin="admin" @select-procedure="prepareProcedure" />
      <details class="panel tool-panel knowledge-panel"><summary class="tool-heading">规程与缺陷检索<span>查询适用依据及历史案例</span></summary><div class="tool-content"><div class="controls knowledge-fields"><label>知识检索问题<input v-model="query" maxlength="500" /></label><label class="check-label"><input v-model="historyKnowledge" type="checkbox" />包含旧双节点历史案例</label><button @click="search">检索依据</button></div>
        <p v-if="knowledge">检索方式：{{ knowledge.mode }} · {{ knowledge.fallbackReason || '' }}</p><ul v-if="knowledge?.missing"><li v-for="gap in (knowledge.missing as string[])" :key="gap">{{ gap }}</li></ul>
        <details v-for="hit in (knowledge?.hits as Json[] || [])" :key="String(hit.id)"><summary>{{ hit.id }} · {{ hit.sourceKind }} · {{ hit.source }} · {{ hit.version }}</summary><pre>{{ hit.text }}</pre><small>适用布局：{{ hit.layout }}；验证状态：{{ hit.verification }}</small></details>
      </div></details>
      <details v-if="canWrite" class="panel tool-panel experience-panel"><summary class="tool-heading">受控复核经验<span>查看提醒与审核记录</span></summary><div class="tool-content"><p>候选不是已验证知识；管理员审核脱敏条目后共享，原始私有任务不开放。审批不代替现场验证。</p>
        <button :disabled="busy" @click="loadExperiences">刷新经验</button><p v-if="experienceTruncated">列表已截断，请按任务或经验编号核查，不能视为完整清单。</p>
        <p v-if="!experiences.length">暂无可见经验。不会自动把历史记录批准为知识。</p>
        <article v-for="item in experiences" :key="String(item.id)" class="experience-card"><h3>{{ item.station_id }} · {{ item.asset_code }} · {{ experienceStates[String(item.status)] }}</h3>
          <p>{{ item.lesson }}</p><small>{{ item.source_scope }} · {{ item.category }} · 版本 {{ item.revision }}</small>
          <details><summary>适用版本、来源与审核记录</summary><pre>{{ JSON.stringify(item, null, 2) }}</pre></details>
          <div class="controls"><template v-if="item.canReview && item.status === 'candidate'"><button :disabled="busy" @click="experienceAction(item, 'approve')">批准共享</button><button :disabled="busy" @click="experienceAction(item, 'reject')">驳回候选</button></template>
            <button v-if="item.canReview && item.status === 'approved'" :disabled="busy" @click="experienceAction(item, 'retire')">退役经验</button>
            <button v-if="item.canRevise" :disabled="busy" @click="editing = item; lessonText = String(item.lesson)">修订为新候选</button></div>
        </article>
        <div v-if="editing"><label>脱敏提醒（最多300字）<textarea v-model="lessonText" maxlength="300" rows="3" /></label>
          <button :disabled="busy" @click="experienceAction(editing, 'revise', lessonText)">保存新候选</button><button :disabled="busy" @click="editing = null">取消修订</button></div>
      </div></details>
      <details class="panel tool-panel costs-panel"><summary class="tool-heading">双风机能耗与任务成本<span>仅作模拟情景测算</span></summary><div class="tool-content"><p>以下为可调整的模拟参数，非现场电费或实际节能成果；不含MQ加热等其他负载。</p><div class="controls cost-fields">
        <label>风机1功率 W<input v-model.number="watts1" type="number" min="0" /></label><label>风机2功率 W<input v-model.number="watts2" type="number" min="0" /></label><label>时间 分钟<input v-model.number="minutes" type="number" min="1" max="60" /></label><label>电价 元/kWh<input v-model.number="price" type="number" min="0" step="0.1" /></label><label>人工耗时 秒<input v-model.number="laborSeconds" type="number" min="0" /></label><label>人工单价 元/小时<input v-model.number="hourlyRate" type="number" min="0" /></label><button @click="calculate">计算模拟情景</button></div>
        <label class="check-label"><input v-model="roiEnabled" type="checkbox" />附加ROI假设测算（不预测事故损失）</label>
        <div v-if="roiEnabled" class="controls"><label>投入 元<input v-model.number="investment" type="number" min="1" /></label><label>假设年收益 元<input v-model.number="annualBenefit" type="number" min="0" /></label><label>假设年运行费 元<input v-model.number="annualOperatingCost" type="number" min="0" /></label></div>
        <dl v-if="cost"><dt>已覆盖电量 kWh</dt><dd>{{ cost.knownKwh }}</dd><dt>电费 元</dt><dd>{{ cost.electricityCost ?? '缺少完整功率或电价，无法计算' }}</dd><dt>工时当量 元</dt><dd>{{ cost.laborEquivalentCost }}</dd><dt>模型费用</dt><dd>待实际账单核对</dd><dt>未知风机采样时长 秒</dt><dd>{{ cost.unknownFanSeconds }}</dd><dt>观测转动时长 秒</dt><dd>{{ cost.runtimeSeconds }}</dd><dt>观测启停上升次数</dt><dd>{{ cost.startsObserved }}（不推断缺失区间）</dd></dl>
        <div v-if="cost?.roi"><p>参数化情景，未证明实际收益；净收益敏感性为±50%的假设。</p><pre>{{ JSON.stringify(cost.roi, null, 2) }}</pre></div>
      </div></details>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.agent-workbench {
  container: agent-workbench / inline-size;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
  width: 100%;
  max-width: 1480px;
  min-width: 0;
  margin-inline: auto;
  color: var(--ops-text, #1c3049);
  font-size: 14px;
  line-height: 1.6;
}
.workbench-heading h1 { margin: 0 0 8px; font-size: 26px; line-height: 1.25; letter-spacing: -.02em; }
.prepared-task { margin: 0; padding: 12px 16px; border: 1px solid var(--ops-line); border-radius: 8px; background: var(--ops-bg-deep); font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
.workbench-heading p { margin: 0; color: var(--ops-muted, #53657b); }
.agent-workbench .panel, .source {
  min-width: 0;
  padding: 24px;
  border: 1px solid var(--ops-line, #d8e2ee);
  border-radius: 12px;
  background: var(--ops-panel, #fff);
  box-shadow: none;
}
.source { padding: 12px 16px; background: var(--ops-signal-soft, #eaf3ff); color: var(--ops-text, #1c3049); }
.source strong { font-size: 13px; }
.source p { margin: 4px 0 0; font-size: 12px; }
.source .model-context { margin: 4px 0 0; }
.source .model-context summary { min-height: 32px; padding-block: 4px; font-size: 12px; font-weight: 600; }
.workbench-primary { display: grid; grid-template-columns: minmax(280px, .85fr) minmax(0, 1.25fr); align-items: start; gap: 24px; min-width: 0; }
.workbench-results { display: grid; align-content: start; gap: 20px; min-width: 0; }
.agent-workbench h2 { margin: 0 0 20px; font-size: 18px; line-height: 1.4; }
.agent-workbench h3 { margin: 24px 0 8px; font-size: 15px; line-height: 1.5; }
.agent-workbench p { max-width: 75ch; margin-block: 8px 12px; line-height: 1.7; overflow-wrap: anywhere; }
.agent-workbench small { color: var(--ops-muted, #53657b); font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
.agent-workbench .controls { display: flex; align-items: end; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
.agent-workbench label { display: grid; align-content: start; gap: 6px; min-width: 0; color: var(--ops-text, #1c3049); font-size: 13px; font-weight: 600; }
.agent-workbench input, .agent-workbench select, .agent-workbench textarea, .agent-workbench button {
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  border: 1px solid var(--ops-line, #d8e2ee);
  border-radius: 7px;
  padding: 10px 12px;
  color: var(--ops-text, #1c3049);
  font: inherit;
  line-height: 1.5;
}
.agent-workbench input, .agent-workbench select, .agent-workbench button { min-height: 42px; }
.agent-workbench input, .agent-workbench select, .agent-workbench textarea { width: 100%; caret-color: var(--ops-signal, #1766c3); }
.agent-workbench textarea { min-height: 144px; resize: vertical; }
.agent-workbench button { background: var(--ops-panel, #fff); font-weight: 600; cursor: pointer; transition: background-color .16s, border-color .16s; }
.agent-workbench button:hover:not(:disabled) { border-color: var(--ops-signal, #1766c3); background: var(--ops-signal-soft, #eaf3ff); }
.agent-workbench button:disabled { color: var(--ops-muted, #53657b); background: var(--ops-raised, #eef3fa); opacity: .65; cursor: not-allowed; }
.agent-workbench :is(input, select, textarea, button, a, summary):focus-visible { outline: 2px solid var(--ops-signal, #1766c3); outline-offset: 3px; }
.agent-workbench .workbench-primary-action { color: var(--ops-on-signal, #fff); background: var(--ops-signal, #1766c3); border-color: var(--ops-signal, #1766c3); }
.agent-workbench .workbench-primary-action:hover:not(:disabled) { background: #1155a5; color: #fff; }
.agent-workbench .task-fields, .agent-workbench .cost-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; }
.task-fields label:nth-child(3):last-child { grid-column: 1 / -1; }
.agent-workbench .check-label { display: flex; align-items: center; gap: 8px; min-height: 40px; font-weight: 400; }
.agent-workbench .check-label input[type=checkbox] { width: 18px; height: 18px; min-height: 18px; padding: 0; flex: 0 0 18px; accent-color: var(--ops-signal, #1766c3); }
.agent-workbench .action-options { padding-block: 4px 12px; border-bottom: 1px solid var(--ops-line-soft, #e5ebf3); }
.action-options > .check-label { flex-basis: 100%; }
.action-options > label:not(.check-label) { flex: 1 1 100px; }
.task-actions button { flex: 1 1 150px; }
.agent-workbench .field-help { color: var(--ops-muted, #53657b); font-size: 12px; line-height: 1.65; }
.run-history { padding-top: 20px; margin-top: 20px; border-top: 1px solid var(--ops-line-soft, #e5ebf3); }
.run-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.run-heading h2 { margin: 0; overflow-wrap: anywhere; }
.run-status { padding: 4px 8px; border: 1px solid var(--ops-line, #d8e2ee); border-radius: 6px; color: var(--ops-muted, #53657b); background: var(--ops-bg-deep, #f8fafc); font-size: 12px; white-space: nowrap; }
.run-status.is-active { color: var(--ops-signal, #1766c3); background: var(--ops-signal-soft, #eaf3ff); border-color: var(--ops-line, #d8e2ee); }
.agent-workbench dl { display: grid; grid-template-columns: minmax(120px, 1fr) 2fr; gap: 10px 16px; margin: 20px 0; }
.agent-workbench dd { min-width: 0; margin: 0; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.agent-workbench .run-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 0 0 20px; padding: 12px 0; border-block: 1px solid var(--ops-line-soft, #e5ebf3); }
.run-metrics dt { color: var(--ops-muted, #53657b); font-size: 12px; }
.run-metrics dd { margin-top: 4px; color: var(--ops-text, #1c3049); font-size: 16px; font-weight: 700; }
.timeline { margin: 20px 0; padding: 0 0 0 18px; list-style: none; }
.timeline li { position: relative; padding: 0 0 20px 20px; border-left: 1px solid var(--ops-line, #d8e2ee); }
.timeline li::before { position: absolute; top: 6px; left: -4px; width: 7px; height: 7px; border-radius: 50%; background: var(--ops-signal, #1766c3); content: ''; }
.timeline li:last-child { padding-bottom: 0; }
.step-heading { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 4px 12px; }
.step-heading h3 { margin: 0; }
.agent-workbench pre { max-width: 100%; max-height: 360px; overflow: auto; padding: 16px; border-radius: 6px; background: var(--ops-bg-deep, #f8fafc); color: var(--ops-text, #1c3049); white-space: pre; font: 12px/1.6 ui-monospace, Consolas, monospace; tab-size: 2; scrollbar-width: thin; scrollbar-color: var(--ops-dim, #64748b) transparent; }
.agent-workbench details { min-width: 0; margin-block: 12px; }
.agent-workbench summary { min-height: 36px; padding-block: 6px; cursor: pointer; color: var(--ops-signal, #1766c3); overflow-wrap: anywhere; }
.run-result > section { padding-block: 8px; border-top: 1px solid var(--ops-line-soft, #e5ebf3); }
.run-result > section h3 { margin-top: 16px; }
.run-result article + article { padding-top: 12px; margin-top: 12px; border-top: 1px solid var(--ops-line-soft, #e5ebf3); }
.model-reply { white-space: pre-wrap; }
.agent-workbench .task-outcome { color: var(--ops-signal, #1766c3); font-weight: 600; }
.agent-workbench .error { padding: 12px 16px; border: 1px solid var(--ops-danger-line, #e6b2bc); border-radius: 7px; color: var(--ops-danger, #b9364d); background: var(--ops-danger-soft, #fff1f3); }
.agent-workbench .workbench-notice { padding: 12px 16px; border: 1px solid var(--ops-ok-line, #b6d8c8); border-radius: 7px; color: var(--ops-ok, #167451); background: var(--ops-ok-soft, #eff8f3); }
.agent-workbench .confirmation { border-color: var(--ops-signal, #1766c3); }
.run-empty { min-height: 300px; }
.run-empty p, .run-empty li { color: var(--ops-muted, #53657b); }
.run-empty ul { margin: 24px 0; padding-left: 20px; }
.run-empty li { margin-block: 12px; }
.result-empty-note { color: var(--ops-muted, #53657b); }
.location-links:empty { display: none; }
.location-links a { display: inline-flex; align-items: center; min-height: 40px; max-width: 100%; padding: 8px 10px; border: 1px solid var(--ops-line, #d8e2ee); border-radius: 6px; color: var(--ops-signal, #1766c3); font-size: 12px; overflow-wrap: anywhere; }
.location-links a:hover { background: var(--ops-signal-soft, #eaf3ff); }
.export-actions { padding-top: 16px; border-top: 1px solid var(--ops-line-soft, #e5ebf3); }
.sensor-table { max-width: 100%; overflow: auto; }
.sensor-table table { width: 100%; min-width: 560px; border-collapse: collapse; font-size: 12px; }
.sensor-table th, .sensor-table td { padding: 10px; border-bottom: 1px solid var(--ops-line-soft, #e5ebf3); text-align: left; overflow-wrap: anywhere; }
.sensor-table th { color: var(--ops-muted, #53657b); background: var(--ops-bg-deep, #f8fafc); white-space: nowrap; }
.workbench-tools { display: grid; gap: 12px; min-width: 0; }
.agent-workbench .tool-panel { margin: 0; padding: 0 24px; }
.agent-workbench .tool-heading { min-height: 72px; padding-block: 22px; color: var(--ops-text, #1c3049); font-size: 15px; font-weight: 700; }
.tool-heading span { margin-left: 16px; color: var(--ops-muted, #53657b); font-size: 12px; font-weight: 400; }
.tool-content { padding-block: 0 20px; border-top: 1px solid var(--ops-line-soft, #e5ebf3); }
.knowledge-fields > label:first-child { flex: 1 1 300px; }
.knowledge-fields .check-label { flex: 1 1 240px; }
.experience-card { margin-top: 20px; padding-top: 12px; border-top: 1px solid var(--ops-line-soft, #e5ebf3); }
.experience-card h3 { margin-top: 8px; }
.cost-fields button { align-self: end; }
@container agent-workbench (max-width: 860px) {
  .workbench-primary { grid-template-columns: minmax(0, 1fr); }
  .agent-workbench .task-fields, .agent-workbench .cost-fields { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .task-fields label:nth-child(3):last-child { grid-column: auto; }
  .run-empty { min-height: 0; }
}
@container agent-workbench (max-width: 560px) {
  .agent-workbench .panel, .source { padding: 16px; }
  .agent-workbench .tool-panel { padding: 0 16px; }
  .agent-workbench .task-fields, .agent-workbench .cost-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .task-fields label:nth-child(3):last-child { grid-column: 1 / -1; }
  .tool-heading span { display: block; margin: 4px 0 0 16px; }
  .agent-workbench .run-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .agent-workbench input, .agent-workbench select, .agent-workbench button { min-height: 44px; }
}
@container agent-workbench (max-width: 360px) {
  .agent-workbench .task-fields, .agent-workbench .cost-fields { grid-template-columns: minmax(0, 1fr); }
  .task-fields label:nth-child(3):last-child { grid-column: auto; }
  .controls > button { width: 100%; }
}
@media (prefers-reduced-motion: reduce) { .agent-workbench button { transition: none; } }
</style>
