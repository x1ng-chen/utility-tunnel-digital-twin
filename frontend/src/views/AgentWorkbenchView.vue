<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import { api } from '../services/api';
import { useAuthStore } from '../stores/auth';

type Json = Record<string, unknown>;
type Run = { id: string; status: string; stage: string; error: string; input: Json;
  steps: { role: string; startedAt: string; output: Json | null; traces: Json[]; calls: Json[] }[];
  result: { reply?: string; taskOutcome?: string; review?: Json; evidence?: Json[]; proposals?: Json[]; controlProposals?: Json[];
    locations?: { assetCode: string; stationId: string; mappingStatus: string }[] };
  runtime: { modelCalls?: number; toolCalls?: number; elapsedMs?: number; tokens?: Json | null; tokenUsageComplete?: boolean } };
const auth = useAuthStore();
const canWrite = computed(() => ['administrator', 'operator'].includes(auth.user?.role || ''));
const admin = computed(() => auth.user?.role === 'administrator');
const run = ref<Run | null>(null), history = ref<Run[]>([]);
const error = ref(''), notice = ref(''), busy = ref(false);
const station = ref('P5'), kind = ref('diagnosis'), mode = ref('multi'), asset = ref('MQ4-05'), order = ref('');
const proposeAction=ref(false),fanTarget=ref('FAN-01'),fanPwm=ref(60);
const prompt = ref('核查本站异常，比较邻站、风机反馈和控制记录，检索适用手册；列出候选原因、反证和下一项检查。');
const sourceLabel = ref('数据来源待核实'), modelNotice = ref('');
const session = ref<Json | null>(null), cases = ref<string[]>([]), caseId = ref('INS-01');
const query = ref('风机有电流但没有转速'), historyKnowledge = ref(false), knowledge = ref<Json | null>(null);
const cost = ref<Json | null>(null), watts1 = ref(3.6), watts2 = ref(3.6), minutes = ref(10), price = ref(1);
const laborSeconds = ref(60), hourlyRate = ref(30);
const roiEnabled=ref(false), investment=ref(1000), annualBenefit=ref(100), annualOperatingCost=ref(50);
const confirmation = ref<{ type: 'command' | 'order'; data: Json; index: number } | null>(null);
const active = computed(() => !!run.value && ['queued', 'running'].includes(run.value.status));
const roles: Record<string, string> = { evidence: '取证Agent', diagnosis: '诊断Agent', review: '复核Agent', single: '单Agent基线' };
const outcomes:Record<string,string>={reviewed:'已独立复核',observed:'已取得巡检证据',single_agent_unreviewed:'单Agent结果，未经独立复核',unresolved_review:'复核意见尚未解决',existing_work_order:'已有工单，未重复生成',no_confirmable_draft:'未形成可确认工单',no_confirmable_action:'未形成可确认动作'};
let timer: ReturnType<typeof setTimeout> | undefined;
let alive = true;
function fail(cause: unknown) { error.value = (cause as { response?: { data?: { message?: string } } }).response?.data?.message || '操作失败，请检查服务与权限。'; }
async function poll() {
  if (!run.value || !alive) return;
  try { const { data } = await api.agentRun(run.value.id); if (alive) run.value = data; }
  catch (cause) { fail(cause); }
  if (alive && active.value) timer = setTimeout(poll, 1500);
}
async function start(previous = false) {
  if (busy.value || active.value) return;
  busy.value = true; error.value = ''; notice.value = ''; confirmation.value = null;
  try {
    const { data } = await api.createAgentRun({ kind: kind.value, station_id: station.value, mode: mode.value,
      prompt: prompt.value, ...(kind.value === 'draft' ? { asset_code: asset.value } : {}),
      ...(kind.value === 'review' ? { work_order_code: order.value } : {}),
      ...(kind.value === 'diagnosis' && mode.value === 'multi' && proposeAction.value ? {control_request:{asset_code:fanTarget.value,intent:'pwm',value:fanPwm.value}} : {}),
      ...(previous && run.value ? { previous_run_id: run.value.id } : {}) }, crypto.randomUUID());
    run.value = data; timer = setTimeout(poll, 500);
  } catch (cause) { fail(cause); } finally { busy.value = false; }
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
  try { const { data } = await api.agentContext(); sourceLabel.value = data.dataContext.label; modelNotice.value = data.modelNotice; } catch { /* unknown provenance stays visible */ }
  try { const { data } = await api.demoSession(); session.value = data.session; cases.value = data.cases; } catch { /* endpoint intentionally absent outside sandbox */ }
  try { history.value = (await api.agentRuns()).data; if (history.value[0]) { run.value = history.value[0]; if (active.value) void poll(); } } catch (cause) { fail(cause); }
});
onUnmounted(() => { alive = false; if (timer) clearTimeout(timer); });
</script>

<template>
  <AppShell>
    <main class="agent-workbench">
      <header><span>可追溯运维</span><h1>多Agent工作台</h1><p>取证、诊断、复核，以及经过人工确认的仿真处置。</p></header>
      <aside class="source" role="status"><strong>{{ sourceLabel }}</strong><p>{{ modelNotice }}</p></aside>
      <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
      <section v-if="session" class="panel"><h2>演示场景</h2><p>模拟测试 · 阶段 {{ session.phase }} · {{ session.running ? '持续采样' : '已暂停，观测将正常过期' }} · 已采样 {{ session.tick }} 轮</p>
        <div class="controls"><select v-model="caseId" aria-label="演示场景"><option v-for="id in cases" :key="id">{{ id }}</option></select>
          <template v-if="admin"><button @click="demoAction('reset')">重置场景</button><button @click="demoAction('start')">开始采样</button><button @click="demoAction('pause')">暂停采样</button><button @click="demoAction('advance')">推进阶段</button></template>
          <small v-else>场景控制由管理员操作；本账号可以查询。</small></div>
      </section>
      <section class="panel"><h2>发起运维任务</h2><div class="controls">
        <label>检测点<select v-model="station"><option v-for="s in ['all','P1','P2','P3','P4','P5']" :key="s">{{ s }}</option></select></label>
        <label>任务<select v-model="kind"><option value="inspection">五站巡检</option><option value="diagnosis">证据排障</option><option value="draft" :disabled="!canWrite">工单草案</option><option value="review">恢复复核</option></select></label>
        <label>运行方式<select v-model="mode"><option value="multi">三Agent协作</option><option value="single">单Agent对照</option></select></label>
        <label v-if="kind === 'draft'">设备编码<input v-model="asset" /></label><label v-if="kind === 'review'">工单编号<input v-model="order" /></label>
      </div><div v-if="canWrite && kind === 'diagnosis' && mode === 'multi'" class="controls"><label class="check-label"><input v-model="proposeAction" type="checkbox" />同时生成待复核的仿真风机动作草案</label><template v-if="proposeAction"><label>风机<select v-model="fanTarget"><option>FAN-01</option><option>FAN-02</option></select></label><label>PWM %<input v-model.number="fanPwm" type="number" min="0" max="100" /></label></template></div><label>任务说明<textarea v-model="prompt" maxlength="2000" rows="3" /></label>
        <div class="controls"><button :disabled="busy || active" @click="start()">开始任务（调用模型）</button><button :disabled="busy || active || run?.status !== 'completed'" @click="start(true)">重新核查新证据</button><button v-if="active" @click="cancel">取消任务</button></div>
        <p>提交后实际调用已配置的DeepSeek；调用用量与失败会保留。原悬浮助手继续可用。</p>
        <label v-if="history.length">历史任务<select @change="selectRun(($event.target as HTMLSelectElement).value)"><option v-for="item in history" :key="item.id" :value="item.id">{{ item.id.slice(0, 8) }} · {{ item.status }}</option></select></label>
      </section>
      <section v-if="run" class="panel"><h2>任务 {{ run.id.slice(0, 8) }} · {{ run.status }}</h2><p v-if="run.error" role="alert">{{ run.error }}</p>
        <p>模型调用 {{ run.runtime.modelCalls ?? 0 }} · 工具调用 {{ run.runtime.toolCalls ?? 0 }} · 耗时 {{ run.runtime.elapsedMs ?? 0 }} ms · Token {{ run.runtime.tokens?.total_tokens ?? '未知' }} {{ run.runtime.tokenUsageComplete === false ? '（用量可能不完整）' : '' }}</p>
        <ol class="timeline"><li v-for="(step, index) in run.steps" :key="index"><h3>{{ roles[step.role] || step.role }}</h3><small>{{ step.startedAt }}</small>
          <p>{{ step.output?.summary || '正在执行实际查询与模型调用…' }}</p><details><summary>本阶段证据和调用记录</summary><pre>{{ JSON.stringify(step, null, 2) }}</pre></details></li></ol>
        <h3 v-if="run.result.reply">本次结论</h3><p v-if="run.result.taskOutcome">任务结果：{{ outcomes[run.result.taskOutcome] || run.result.taskOutcome }}</p><p>{{ run.result.reply }}</p><p v-if="run.result.review">复核：{{ run.result.review.decision }} · {{ run.result.review.summary }}。复核通过不等于现场验收或全部事实正确。</p>
        <details v-if="run.result.evidence?.length"><summary>查看原始证据</summary><pre>{{ JSON.stringify(run.result.evidence, null, 2) }}</pre></details>
        <div class="controls"><RouterLink v-for="location in run.result.locations || []" :key="location.assetCode" :to="{path:'/twin-3d',query:{asset:location.assetCode,source:'agent'}}">{{ location.stationId }} · {{ location.assetCode }} · {{ location.mappingStatus }}</RouterLink></div>
        <div v-if="canWrite"><article v-for="(proposal, index) in run.result.proposals || []" :key="index"><h3>待确认工单：{{ proposal.title }}</h3><p>{{ proposal.description }}</p><button @click="confirmation = {type:'order',data:proposal,index}">审阅工单草案</button></article>
          <article v-for="(proposal, index) in run.result.controlProposals || []" :key="index"><p>仿真动作：{{ proposal.asset_code }} · {{ proposal.intent }} → {{ proposal.value }}</p><button :disabled="!session" @click="previewCommand(index)">审阅仿真动作</button></article></div>
        <div class="controls"><button v-for="format in ['json','csv','html']" :key="format" @click="download(format)">导出 {{ format.toUpperCase() }}</button></div>
      </section>
      <section v-if="confirmation" class="panel confirmation" role="alertdialog" aria-label="人工确认处置"><h2>确认{{ confirmation.type === 'command' ? '仿真动作' : '测试工单' }}</h2><pre>{{ JSON.stringify(confirmation.data, null, 2) }}</pre><p>请核对目标、动作与来源。此操作不会下发真实硬件。</p><button :disabled="busy" @click="confirm(true)">确认执行</button><button :disabled="busy" @click="confirm(false)">取消</button></section>
      <section class="panel"><h2>规程与缺陷检索</h2><div class="controls"><input v-model="query" aria-label="知识检索问题" maxlength="500" /><label class="check-label"><input v-model="historyKnowledge" type="checkbox" />包含旧双节点历史案例</label><button @click="search">检索依据</button></div>
        <p v-if="knowledge">检索方式：{{ knowledge.mode }} · {{ knowledge.fallbackReason || '' }}</p><ul v-if="knowledge?.missing"><li v-for="gap in (knowledge.missing as string[])" :key="gap">{{ gap }}</li></ul>
        <details v-for="hit in (knowledge?.hits as Json[] || [])" :key="String(hit.id)"><summary>{{ hit.id }} · {{ hit.sourceKind }} · {{ hit.source }} · {{ hit.version }}</summary><pre>{{ hit.text }}</pre><small>适用布局：{{ hit.layout }}；验证状态：{{ hit.verification }}</small></details>
      </section>
      <section class="panel"><h2>双风机能耗与任务成本</h2><p>以下为可调整的模拟参数，非现场电费或实际节能成果；不含MQ加热等其他负载。</p><div class="controls">
        <label>风机1功率 W<input v-model.number="watts1" type="number" min="0" /></label><label>风机2功率 W<input v-model.number="watts2" type="number" min="0" /></label><label>时间 分钟<input v-model.number="minutes" type="number" min="1" max="60" /></label><label>电价 元/kWh<input v-model.number="price" type="number" min="0" step="0.1" /></label><label>人工耗时 秒<input v-model.number="laborSeconds" type="number" min="0" /></label><label>人工单价 元/小时<input v-model.number="hourlyRate" type="number" min="0" /></label><button @click="calculate">计算模拟情景</button></div>
        <label class="check-label"><input v-model="roiEnabled" type="checkbox" />附加ROI假设测算（不预测事故损失）</label>
        <div v-if="roiEnabled" class="controls"><label>投入 元<input v-model.number="investment" type="number" min="1" /></label><label>假设年收益 元<input v-model.number="annualBenefit" type="number" min="0" /></label><label>假设年运行费 元<input v-model.number="annualOperatingCost" type="number" min="0" /></label></div>
        <dl v-if="cost"><dt>已覆盖电量 kWh</dt><dd>{{ cost.knownKwh }}</dd><dt>电费 元</dt><dd>{{ cost.electricityCost ?? '缺少完整功率或电价，无法计算' }}</dd><dt>工时当量 元</dt><dd>{{ cost.laborEquivalentCost }}</dd><dt>模型费用</dt><dd>待实际账单核对</dd><dt>未知风机采样时长 秒</dt><dd>{{ cost.unknownFanSeconds }}</dd><dt>观测转动时长 秒</dt><dd>{{ cost.runtimeSeconds }}</dd><dt>观测启停上升次数</dt><dd>{{ cost.startsObserved }}（不推断缺失区间）</dd></dl>
        <div v-if="cost?.roi"><p>参数化情景，未证明实际收益；净收益敏感性为±50%的假设。</p><pre>{{ JSON.stringify(cost.roi, null, 2) }}</pre></div>
      </section>
    </main>
  </AppShell>
</template>

<style scoped>
.agent-workbench{max-width:1200px;margin:auto;padding:24px;display:grid;gap:20px;color:var(--text-primary,#14263d)}h1{font-size:30px;margin:8px 0}h2{font-size:20px;margin:0 0 14px}h3{font-size:16px}.panel,.source{padding:22px;border:1px solid #d7e1ea;border-radius:14px;background:var(--surface,#fff)}.source{background:#eef5ff}.controls{display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin:12px 0}label{display:grid;gap:6px;font-size:14px}input,select,textarea,button{font:inherit;padding:10px;border:1px solid #b6c5d5;border-radius:7px;max-width:100%;box-sizing:border-box}textarea{width:100%;resize:vertical}button{cursor:pointer;background:#edf4ff;color:#17365b}button:disabled{opacity:.5;cursor:default}input[type=checkbox]{width:auto}.timeline{padding-left:26px}.timeline li{border-left:3px solid #739ac8;padding:0 0 20px 18px}.timeline li:last-child{padding-bottom:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:420px;overflow:auto;background:#f3f6fa;padding:12px}details{margin:12px 0}summary{cursor:pointer;overflow-wrap:anywhere}.error{color:#a82020}.confirmation{border:2px solid #668cb9}p{line-height:1.65;overflow-wrap:anywhere}a{padding:6px;color:#185a9d}dl{display:grid;grid-template-columns:minmax(140px,1fr) 2fr;gap:8px}dd{margin:0;overflow-wrap:anywhere}@media(max-width:700px){.agent-workbench{padding:12px}.panel,.source{padding:14px}.controls{align-items:stretch;flex-direction:column}label,input,select{width:100%}h1{font-size:24px}}
</style>

<style scoped>
.agent-workbench{min-width:0;grid-template-columns:minmax(0,1fr)}.panel{min-width:0}.check-label{display:flex;align-items:center;gap:8px}.check-label input[type=checkbox]{width:16px;height:16px;padding:0;flex:0 0 16px}
</style>
