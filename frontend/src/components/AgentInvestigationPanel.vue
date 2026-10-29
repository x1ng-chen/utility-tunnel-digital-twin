<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api, type InvestigationCase } from '../services/api';

type Json = Record<string, unknown>;
const props = defineProps<{station:string;running:boolean;modelCallsDisabled:boolean;lastRunId?:string;lastRunStatus?:string}>();
const emit = defineEmits<{'select-case':[value:InvestigationCase|null];'continue-case':[value:InvestigationCase]}>();
const entries = ref<InvestigationCase[]>([]), selected = ref<InvestigationCase|null>(null);
const loaded = ref(false), busy = ref(false), error = ref(''), notice = ref('');
const creating = ref(false);
const formStation = ref(props.station === 'all' ? 'P5' : props.station), asset = ref(''), title = ref('');
const reports = ref<Record<string,string>>({});
const source = computed(() => selected.value?.source?.label || selected.value?.source?.mode || '来源未记录，不能推断为现场数据');
const states:Record<string,string> = {open:'待调查',investigating:'调查中',waiting:'等待补证',awaiting_feedback:'等待补证',resolved:'已标记处理',candidate:'候选原因',supported:'本轮有支持',contradicted:'已有反证',unresolved:'仍未判定',pending:'待检查',completed:'已报告完成',unavailable:'无法执行'};
const list = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const describe = (value:unknown) => typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value);
function fail(cause:unknown) {
  const response = (cause as {response?:{status?:number;data?:{message?:string}}}).response;
  error.value = response?.status === 409 ? '档案已被更新，请刷新档案后重新核对再提交。你的检查报告仍保留在输入框。' : response?.data?.message || '档案操作失败，请检查登录状态和服务后重试。';
}
function requireSession() {
  if (sessionStorage.getItem('ut-django-token')) return true;
  error.value = '请先登录数据服务，再保存或查询排障档案。';
  return false;
}
async function load() {
  if (busy.value || !requireSession()) return;
  busy.value = true; error.value = '';
  try { const {data} = await api.investigationCases(); entries.value = Array.isArray(data) ? data : data.items || []; loaded.value = true; }
  catch (cause) { fail(cause); } finally { busy.value = false; }
}
async function select(id:string) {
  if (busy.value || !requireSession()) return;
  busy.value = true; error.value = ''; notice.value = '';
  try { selected.value = (await api.investigationCase(id)).data; emit('select-case', selected.value); }
  catch (cause) { fail(cause); } finally { busy.value = false; }
}
async function create() {
  if (busy.value || props.running || !requireSession()) return;
  busy.value = true; error.value = ''; notice.value = '';
  try {
    const {data} = await api.createInvestigationCase({station_id:formStation.value,...(asset.value.trim()?{asset_code:asset.value.trim()}:{}),...(title.value.trim()?{title:title.value.trim()}:{})});
    selected.value = data; entries.value = [data,...entries.value.filter(item=>item.id!==data.id)]; loaded.value = true;
    emit('select-case', data); creating.value=false; notice.value = '已保存排障档案，尚未调用模型。核对目标后可继续调查。';
  } catch (cause) { fail(cause); } finally { busy.value = false; }
}
async function feedback(check:Json,status:'completed'|'unavailable') {
  if (!selected.value || busy.value) return;
  const checkId = String(check.id || ''), report = (reports.value[checkId] || '').trim();
  if (!checkId || !report) { error.value = '请填写这项检查实际观察到的结果，或说明无法执行的原因。'; return; }
  busy.value = true; error.value = ''; notice.value = '';
  try {
    selected.value = (await api.investigationFeedback(selected.value.id,{check_id:checkId,status,report,revision:selected.value.revision})).data;
    emit('select-case', selected.value); notice.value = '已保存为人工报告；未将其升级为设备测量，也未自动判定故障恢复。';
    delete reports.value[checkId];
  } catch (cause) { fail(cause); } finally { busy.value = false; }
}
function release() { selected.value = null; emit('select-case',null); notice.value = '后续任务不再关联此档案；已有记录保留。'; }
function continueCase() { if(selected.value && !busy.value && !props.running && !props.modelCallsDisabled) emit('continue-case',selected.value); }
watch(()=>props.station,value=>{ if(!selected.value && value!=='all') formStation.value=value; });
watch(()=>[props.lastRunId,props.lastRunStatus],async ([id,status])=>{
  if(id && ['completed','failed','cancelled'].includes(status || '') && selected.value && !busy.value) await select(selected.value.id);
});
</script>

<template>
  <section class="investigation-panel" aria-labelledby="investigation-title">
    <header><div><h2 id="investigation-title">可接续排障档案</h2><p>保留假设、反证和检查结果。等待人工时暂停，续查会冻结新一轮证据。</p></div><div class="actions"><button :disabled="busy || running" @click="creating=!creating">{{ creating ? '收起新建表单' : '新建档案' }}</button><button :disabled="busy" @click="load">{{ busy ? '正在读取…' : '加载档案' }}</button></div></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <div class="case-entry">
      <form v-if="creating" class="case-create" @submit.prevent="create">
        <label>检测站<select v-model="formStation"><option v-for="s in ['P1','P2','P3','P4','P5']" :key="s">{{ s }}</option></select></label>
        <label>设备编码（可选）<input v-model="asset" maxlength="50" placeholder="如 FLAME-05" /></label>
        <label class="case-title">档案名称（可选）<input v-model="title" maxlength="120" placeholder="本次需要持续跟进的问题" /></label>
        <button :disabled="busy || running" type="submit">创建排障档案</button>
      </form>
      <label v-if="entries.length" class="case-picker">已有档案<select :value="selected?.id || ''" :disabled="busy" @change="select(($event.target as HTMLSelectElement).value)"><option value="" disabled>选择自己的排障档案</option><option v-for="item in entries" :key="item.id" :value="item.id">{{ item.stationId }} · {{ item.title || item.id.slice(0,8) }}</option></select></label>
      <p v-else-if="loaded" class="help">暂无可见档案。创建档案只保存调查目标，不会自动启动Agent。</p>
    </div>
    <div v-if="selected" class="case-detail">
      <header><div><h3>{{ selected.title || '未命名排障' }}</h3><p>{{ selected.stationId }}<template v-if="selected.assetCode"> · {{ selected.assetCode }}</template> · {{ states[selected.status] || selected.status }} · 版本 {{ selected.revision }}</p></div><div class="actions"><button :disabled="busy" @click="select(selected.id)">刷新档案</button><button :disabled="busy || running" @click="release">解除任务关联</button><button class="primary" :disabled="busy || running || modelCallsDisabled" @click="continueCase">继续调查（调用模型）</button></div></header>
      <p class="help">本档案来源：{{ source }}。接线布局 {{ selected.layoutVersion || '未记录' }}；展示版本 {{ selected.presentationVersion || '未记录' }}。检查完成不等于恢复，工单仍需人工结单。</p>
      <div class="case-evidence">
        <section><h4>调查假设</h4><p v-if="!selected.hypotheses?.length" class="help">首轮调查结束后显示实际提出的假设，不预置根因。</p>
          <article v-for="(hypothesis,index) in selected.hypotheses || []" :key="String(hypothesis.id || index)"><h5>{{ hypothesis.label || hypothesis.title || hypothesis.hypothesis || '未命名假设' }}</h5><p>{{ states[String(hypothesis.status)] || hypothesis.status }}</p><dl><dt>支持引用</dt><dd>{{ list(hypothesis.supportRefs).map(describe).join('、') || '未记录' }}</dd><dt>反证引用</dt><dd>{{ list(hypothesis.counterRefs).map(describe).join('、') || '未记录' }}</dd><dt>仍缺证据</dt><dd>{{ list(hypothesis.missing).map(describe).join('；') || '未记录缺项，不能据此认定充分' }}</dd></dl><small>关联快照 {{ hypothesis.snapshotHash || '未记录' }}</small></article>
        </section>
        <section><h4>待检查项与人工报告</h4><p v-if="!selected.checks?.length" class="help">尚无检查项。调查生成后，可在这里反馈实际结果。</p>
          <article v-for="(check,index) in selected.checks || []" :key="String(check.id || index)"><h5>{{ check.label || check.title || check.tool || '未命名检查' }}</h5><p>{{ check.kind === 'human' ? '人工检查' : '软件检查' }} · {{ states[String(check.status)] || check.status }}</p><p v-if="check.report" class="human-report">人工报告：{{ check.report }}</p><small v-if="list(check.evidenceRefs).length">引用 {{ list(check.evidenceRefs).map(describe).join('、') }}</small>
            <form v-if="check.status === 'pending' && check.kind === 'human'" @submit.prevent="feedback(check,'completed')"><label :for="`check-${check.id}`">实际观察或无法执行的原因<textarea :id="`check-${check.id}`" v-model="reports[String(check.id)]" maxlength="2000" rows="3" /></label><div class="actions"><button :disabled="busy || running" type="submit">记录检查完成</button><button :disabled="busy || running" type="button" @click="feedback(check,'unavailable')">记录无法执行</button></div></form>
          </article>
        </section>
      </div>
      <details><summary>查看 {{ selected.runs?.length || 0 }} 轮调查与修改历史</summary><p v-for="item in selected.runs || []" :key="String(item.id)">任务 {{ item.id }} · {{ item.status }} · 快照 {{ item.snapshotHash || '尚未冻结' }}</p><pre>{{ JSON.stringify(selected.history || [],null,2) }}</pre></details>
    </div>
  </section>
</template>

<style scoped>
.investigation-panel{padding:24px;border:1px solid var(--ops-line,#d8e2ee);border-radius:12px;background:var(--ops-panel,#fff);min-width:0;color:var(--ops-text,#1c3049)}header{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px}h2{font-size:18px;margin:0 0 8px}h3{font-size:16px;margin:0 0 6px}h4{font-size:14px;margin:0 0 12px}h5{font-size:13px;margin:0 0 6px}p{max-width:75ch;font-size:13px;line-height:1.7;margin:4px 0 12px;overflow-wrap:anywhere}header>div>p,.help,small{color:var(--ops-muted,#53657b)}.help,small{font-size:12px}.case-create{display:grid;grid-template-columns:100px minmax(130px,1fr) minmax(180px,2fr) auto;gap:12px;align-items:end;margin:20px 0}.case-picker{max-width:540px}.case-detail{margin-top:24px;padding-top:20px;border-top:1px solid var(--ops-line,#d8e2ee)}.case-evidence{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:24px;min-width:0}.case-evidence>section{min-width:0}article{border-top:1px solid var(--ops-line-soft,#e5ebf3);padding:14px 0}.case-evidence article:first-of-type{border-top:0}.actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}label{display:grid;gap:6px;font-size:12px;font-weight:600;min-width:0}input,select,textarea,button{box-sizing:border-box;max-width:100%;min-height:42px;border:1px solid var(--ops-line,#d8e2ee);border-radius:7px;padding:9px 11px;color:var(--ops-text,#1c3049);background:var(--ops-panel,#fff);font:inherit;font-size:13px}input,select,textarea{width:100%;caret-color:var(--ops-signal,#1766c3)}textarea{resize:vertical;min-height:86px}button{cursor:pointer;font-weight:600}button:hover:not(:disabled){border-color:var(--ops-signal,#1766c3);background:var(--ops-signal-soft,#eaf3ff)}button:disabled{opacity:.6;cursor:not-allowed}.primary{background:var(--ops-signal,#1766c3);color:var(--ops-on-signal,#fff)}:is(input,select,textarea,button,summary):focus-visible{outline:2px solid var(--ops-signal,#1766c3);outline-offset:3px}form .actions{margin-top:8px}dl{display:grid;grid-template-columns:72px minmax(0,1fr);gap:7px 10px;font-size:12px;line-height:1.6}dt{color:var(--ops-muted,#53657b)}dd{margin:0;overflow-wrap:anywhere}.human-report{white-space:pre-wrap}details{margin-top:16px}summary{min-height:36px;cursor:pointer;color:var(--ops-signal,#1766c3);font-size:13px}pre{overflow:auto;max-height:260px;background:var(--ops-bg-deep,#f8fafc);padding:12px;font:12px/1.6 ui-monospace,monospace}.error{color:var(--ops-danger,#b9364d)}.notice{color:var(--ops-ok,#167451)}@media(max-width:1000px){.case-create{grid-template-columns:1fr 1fr}.case-title{grid-column:1/-1}.case-evidence{grid-template-columns:1fr}}@media(max-width:560px){.investigation-panel{padding:16px}.case-create{grid-template-columns:1fr}.case-title{grid-column:auto}.actions>button{flex:1 1 140px}}
</style>
