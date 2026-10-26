<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { Send, Sparkles, Trash2, X } from 'lucide-vue-next';
import { useRouter } from 'vue-router';
import { useAiAssistantStore } from '../stores/aiAssistant';
import { useOperationsStore } from '../stores/operations';
import { useAuthStore } from '../stores/auth';
import { api, type AgentProposal, type AgentDataContext } from '../services/api';
import '../assets/ai-assistant.css';

const props = defineProps<{ pageName: string }>();
const assistant = useAiAssistantStore();
const operations = useOperationsStore();
const auth = useAuthStore();
const router = useRouter();
const locationError = ref('');
const dataContext = ref<AgentDataContext | null>(null);
const modelNotice = ref('');
const selectedStation = ref('P5');
const selectedAsset = ref('MQ4-05');
const selectedOrder = ref('');
const taskAssets = computed(() => operations.assets.filter(a => a.isActive !== false));
watch(taskAssets, (assets) => {
  if (assets.length && !assets.some(a => a.code === selectedAsset.value)) selectedAsset.value = assets[0].code;
}, { immediate: true });
async function runTask(kind: 'diagnosis' | 'draft' | 'review', orderCode = '') {
  let question = '';
  if (kind === 'diagnosis') question = `排查${selectedStation.value}告警，结合邻站、双风机和手册，列出事实、候选原因、反证、缺失证据和下一项检查。`;
  if (kind === 'draft' && canSubmit.value) question = `核查资产${selectedAsset.value}最新快照和已有工单，查手册后准备待确认处置草案，不直接创建。`;
  const code = orderCode || selectedOrder.value;
  if (kind === 'review' && /^[A-Z0-9][A-Z0-9_-]{1,49}$/.test(code)) question = `只读复核工单${code}，区分通信、新采样、活动告警与人工验收，不自动结单。`;
  if (question && available.value && !assistant.pending) {
    try { await assistant.send(question, props.pageName, kind === 'diagnosis' ? { kind: 'diagnosis', station_id: selectedStation.value } : kind === 'draft' ? { kind: 'draft', asset_code: selectedAsset.value } : { kind: 'review', work_order_code: code }); } catch { /* Store owns error display. */ }
  }
}
const confirmation = ref<AgentProposal | null>(null);
const submission = ref(false);
const proposalStates = ref(new Map<AgentProposal, { key: string; code?: string; error?: string }>());
const canSubmit = computed(() => auth.user?.role === 'administrator' || auth.user?.role === 'operator');
const open = ref(false);
const draft = ref('');
const input = ref<HTMLTextAreaElement | null>(null);
const log = ref<HTMLElement | null>(null);
const available = computed(() => operations.source === 'api' && !operations.offline);

watch(open, async (isOpen) => {
  if (isOpen) {
    await nextTick(); input.value?.focus();
    if (available.value) {
      try { const { data } = await api.agentContext(); dataContext.value = data.dataContext; modelNotice.value = data.modelNotice; }
      catch { dataContext.value = null; }
    }
  }
});

watch(() => assistant.messages.length, (length) => {
  if (!length) { confirmation.value = null; proposalStates.value.clear(); }
});

const toolLabels: Record<string, string> = {
  runtime_overview: '核查运行概览', open_alerts: '读取活动告警', asset_snapshot: '核查资产与最新测量',
  telemetry_trend: '统计指标趋势', active_work_orders: '排查重复工单', lookup_runbook: '检索排查手册',
  draft_work_order: '生成处置草案',
  station_snapshot: '五站传感器巡检', diagnose_station: '检测点多证据排障', review_work_order: '维修后只读复核',
};

function openLocation(code: string) {
  if (!/^[A-Z0-9][A-Z0-9_-]{1,39}$/.test(code) || !operations.assets.some(a => a.code === code && a.isActive !== false)) {
    locationError.value = '设备尚未在当前台账中找到，请刷新数据并核对身份。';
    return;
  }
  locationError.value = '';
  void router.push({ path: '/twin-3d', query: { asset: code, source: 'agent' } });
  open.value = false;
}

async function inspect() {
  if (!available.value || assistant.pending) return;
  try { await assistant.inspect(); } catch { /* Store displays the failure. */ }
}

async function submitProposal() {
  const proposal = confirmation.value;
  if (!proposal || submission.value || !available.value || !canSubmit.value) return;
  const state = proposalStates.value.get(proposal) || { key: `agent-${crypto.randomUUID()}` };
  proposalStates.value.set(proposal, state);
  if (state.code) return;
  state.error = '';
  submission.value = true;
  try {
    const result = await api.createWorkOrder({ assetCode: proposal.assetCode, title: proposal.title,
      description: proposal.description, priority: proposal.priority }, state.key);
    // Do not display a late response after logout/clear.
    if (confirmation.value === proposal) {
      proposalStates.value.set(proposal, { ...state, code: result.data.code });
      selectedOrder.value = result.data.code;
      confirmation.value = null;
    }
  } catch (cause: unknown) {
    const failure = cause as { response?: { data?: { message?: string } } };
    if (confirmation.value === proposal) proposalStates.value.set(proposal, { ...state,
      error: failure.response?.data?.message || '提交失败；再次确认会使用同一幂等键，避免重复创建。' });
  } finally { submission.value = false; }
}

async function send() {
  if (!available.value || !draft.value.trim() || assistant.pending) return;
  try {
    await assistant.send(draft.value, props.pageName);
    draft.value = '';
    await nextTick();
    log.value?.scrollTo({ top: log.value.scrollHeight, behavior: 'smooth' });
    input.value?.focus();
  } catch { /* The store displays the request error and keeps the draft for retry. */ }
}

function onInputKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    void send();
  }
}
</script>

<template>
  <button class="ai-assistant-launcher" type="button" :aria-expanded="open" aria-controls="ai-assistant-panel" aria-label="打开 AI 助手" @click="open = !open">
    <Sparkles /><span>AI 助手</span>
  </button>
  <Teleport to="body">
    <section v-if="open" id="ai-assistant-panel" class="ai-assistant-panel" role="dialog" aria-label="AI 助手" @keydown.esc="open = false">
      <header class="ai-assistant-header">
        <span class="ai-assistant-avatar"><Sparkles /></span>
        <div><strong>管廊运维 Agent</strong><small>数据核查 · 排查手册 · 人工确认</small></div>
        <button type="button" aria-label="清空对话" title="清空对话" :disabled="assistant.pending || !assistant.messages.length" @click="assistant.clear()"><Trash2 /></button>
        <button type="button" aria-label="关闭 AI 助手" title="关闭" @click="open = false"><X /></button>
      </header>
      <div class="ai-agent-context" role="status">
        <strong>{{ dataContext?.label || '数据来源未核实；请核对每次查询的来源标记' }}</strong>
        <small v-if="dataContext?.scenarioId">场景：{{ dataContext.scenarioId }}</small>
        <small v-if="modelNotice">{{ modelNotice }}</small>
      </div>
      <div class="ai-agent-shortcuts">
        <button type="button" :disabled="!available || assistant.pending" @click="inspect">五站31路巡检</button>
        <small>直接查询平台，不需要模型密钥</small>
      </div>
      <div class="ai-agent-workflow" aria-label="运维任务流程">
        <label>检测点<select v-model="selectedStation" aria-label="选择排障检测点"><option v-for="station in ['P1','P2','P3','P4','P5']" :key="station">{{ station }}</option></select></label>
        <button type="button" :disabled="!available || assistant.pending" @click="runTask('diagnosis')">排查检测点</button>
        <label>设备<select v-model="selectedAsset" aria-label="选择草案设备"><option v-for="asset in taskAssets" :key="asset.code" :value="asset.code">{{ asset.code }}</option></select></label>
        <button type="button" :disabled="!available || !canSubmit || !selectedAsset || assistant.pending" @click="runTask('draft')">生成处置草案</button>
        <label>工单<input v-model="selectedOrder" aria-label="复核工单编号" placeholder="选择或输入工单编号" maxlength="50" list="agent-review-orders" /></label>
        <datalist id="agent-review-orders"><option v-for="order in operations.workOrders" :key="order.code" :value="order.code" /></datalist>
        <button type="button" :disabled="!available || !selectedOrder || assistant.pending" @click="runTask('review')">复核工单</button>
      </div>
      <div ref="log" class="ai-assistant-log" role="log" aria-live="polite" aria-label="对话记录">
        <div v-if="!assistant.messages.length" class="ai-assistant-intro">
          查询带来源的数据 → 展示核查证据 → 生成处置草案。不会自动控制硬件。
          <button v-for="question in ['巡检P1到P5，列出31路缺项、过期和不良数据', '排查P5告警，比较相邻检测点与两台风机的证据，并引用手册来源', '查询已有工单后生成处置草案，确认后再提交']" :key="question" type="button" @click="draft = question">{{ question }}</button>
        </div>
        <div v-for="(message, index) in assistant.messages" :key="index" :class="['ai-assistant-message', message.role]">
          <small>{{ message.role === 'user' ? '你' : 'AI 助手' }}</small><p>{{ message.content }}</p>
          <small v-if="message.mode">{{ message.mode === 'tool_verified' ? '已调用平台工具，具体事实请核对下方证据' : '未查询现场数据，仅解释/建议' }}</small>
          <div v-if="message.inspection" class="ai-agent-inspection">
            <strong>[{{ message.inspection.evidenceId }}] 传感器巡检 · 所需观测可用 {{ message.inspection.usable }}/{{ message.inspection.expected }}</strong>
            <small v-if="message.runtime?.dataContext.mode === 'simulated_test'">模拟场景观测可用 {{ message.inspection.scenarioUsable ?? 0 }}/{{ message.inspection.expected }}；不计入现场可用数</small>
            <small v-if="message.inspection.dataIssueSensorCount != null">输入质量/时间/接入异常：{{ message.inspection.dataIssueSensorCount }}个物理模块（去重）；告警另列</small>
            <table><thead><tr><th>检测点</th><th>台账/设计</th><th>{{ message.runtime?.dataContext.mode === 'simulated_test' ? '现场/场景可用' : '观测可用' }}</th><th>活动告警</th></tr></thead>
              <tbody><tr v-for="station in message.inspection.stations" :key="station.stationId">
                <td>{{ station.stationId }}</td><td>{{ station.registered }}/{{ station.expected }}</td>
                <td>{{ station.usable }}<template v-if="message.runtime?.dataContext.mode === 'simulated_test'"> / {{ station.scenarioUsable ?? 0 }}</template></td><td>{{ station.alertCount }}</td>
              </tr></tbody></table>
            <small v-if="message.inspection.missingAssetCodes.length">台账缺项：{{ message.inspection.missingAssetCodes.join('、') }}</small>
            <small>可用观测不代表实物接线已验收或环境安全。</small>
          </div>
          <div v-if="message.runtime" class="ai-agent-runtime">
            <strong>{{ message.runtime.dataContext.label }}</strong>
            <small>布局 {{ message.runtime.layoutVersion }} · 请求 {{ message.runtime.requestId || '未知' }}</small>
            <small>模型 {{ message.runtime.providerModels.join('、') || '未返回实际模型标识' }} · {{ message.runtime.modelCalls }}次调用 · {{ message.runtime.elapsedMs ?? '?' }}ms</small>
            <small>Token {{ message.runtime.tokens?.total_tokens ?? '未知' }} · 费用{{ message.runtime.cost == null ? '待账单核对' : message.runtime.cost }}</small>
          </div>
          <div v-if="message.diagnosis" class="ai-agent-diagnosis">
            <strong>多证据排障 · 候选解释</strong>
            <article v-for="candidate in message.diagnosis.candidates" :key="candidate.code + candidate.title">
              <b>{{ candidate.title }}</b><p>依据：{{ candidate.support.join('；') }}</p>
              <p>反证：{{ candidate.counterevidence.join('；') || '当前无充分反证，不代表候选已证实' }}</p>
              <p>缺口：{{ candidate.missing.join('；') || '仍需人工复核' }}</p>
              <p>下一步：{{ candidate.nextCheck }}</p>
            </article><small>{{ message.diagnosis.boundary }}</small>
          </div>
          <details v-if="message.traces?.length" class="ai-agent-evidence">
            <summary>核查过程与证据（{{ message.traces.length }}）</summary>
            <div v-for="trace in message.traces" :key="trace.evidenceId" class="ai-agent-trace">
              [{{ trace.evidenceId }}] {{ toolLabels[trace.tool] || trace.tool }} · {{ trace.status === 'ok' ? '完成' : '拒绝' }} · {{ trace.durationMs }} ms
            </div>
            <details v-for="item in message.evidence" :key="item.id">
              <summary>[{{ item.id }}] {{ toolLabels[item.tool] || item.tool }} · {{ new Date(item.queriedAt).toLocaleTimeString() }}</summary>
              <pre>{{ JSON.stringify(item.data, null, 2) }}</pre>
            </details>
          </details>
          <details v-if="message.locations?.length" class="ai-agent-locations">
            <summary>设备与三维入口（{{ message.locations.length }}）</summary>
            <div v-for="location in message.locations" :key="location.assetCode" class="ai-agent-location">
              <b>{{ location.stationId }} · {{ location.physicalTag }} · {{ location.controllerId }}</b>
              <small>[{{ location.evidenceId }}] {{ location.mappingStatus === 'active_model_node_verified' ? '激活模型节点已核对，实物身份仍需确认' : '模型映射待核验：' + location.mappingStatus }}</small>
              <button type="button" @click="openLocation(location.assetCode)">查看 {{ location.assetCode }}</button>
            </div>
          </details>
          <div v-for="(proposal, proposalIndex) in message.proposals" :key="proposalIndex" class="ai-agent-proposal">
            <strong>待确认工单 · {{ proposal.assetCode }}</strong>
            <p>{{ proposal.title }}</p><p>{{ proposal.description }}</p>
            <small>优先级：{{ { low: '低', normal: '普通', high: '高', urgent: '紧急' }[proposal.priority] }}；草案不等于已处置</small>
            <span v-if="proposalStates.get(proposal)?.code">已创建：{{ proposalStates.get(proposal)?.code }}<button type="button" :disabled="assistant.pending" @click="runTask('review', proposalStates.get(proposal)?.code)">复核这张工单</button></span>
            <button v-else type="button" :disabled="!canSubmit || !available || submission" @click="confirmation = proposal">审阅并确认创建</button>
          </div>
        </div>
        <p v-if="assistant.pending" class="ai-assistant-pending" role="status">正在核查数据并整理建议，最多约一分钟…</p>
      </div>
      <div v-if="confirmation" class="ai-agent-confirm" role="alertdialog" aria-label="确认创建工单">
        <strong>确认创建 {{ confirmation.assetCode }} 的处置工单？</strong>
        <p>请核对上方草案与数据时间。这不会执行风机、继电器或其他硬件操作。</p>
        <p v-if="proposalStates.get(confirmation)?.error" role="alert">{{ proposalStates.get(confirmation)?.error }}</p>
        <button type="button" :disabled="submission" @click="confirmation = null">取消</button>
        <button type="button" :disabled="submission || !available || !canSubmit" @click="submitProposal">{{ submission ? '提交中…' : '确认创建' }}</button>
      </div>
      <div v-if="!available" class="ai-assistant-status" role="status">登录并连接数据服务后可使用 AI 助手。</div>
      <div v-if="assistant.error" class="ai-assistant-error" role="alert">{{ assistant.error }}</div>
      <div v-if="locationError" class="ai-assistant-error" role="alert">{{ locationError }}</div>
      <div class="ai-assistant-compose">
        <label for="ai-assistant-question">输入问题</label>
        <textarea id="ai-assistant-question" ref="input" v-model="draft" rows="2" maxlength="2000" placeholder="输入问题，Enter 发送，Shift+Enter 换行" :disabled="!available || assistant.pending" @keydown="onInputKeydown" />
        <button type="button" aria-label="发送给 AI 助手" :disabled="!available || assistant.pending || !draft.trim()" @click="send"><Send /></button>
      </div>
      <p class="ai-assistant-footnote">必要的设备数据将发送至模型服务；数据库快照不等于实时现场。未标定气体量不可用于安全判断。</p>
    </section>
  </Teleport>
</template>
