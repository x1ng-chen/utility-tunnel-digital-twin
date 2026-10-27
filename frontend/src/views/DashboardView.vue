<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useNow } from '@vueuse/core';
import { feedbackValue, outputOwner } from '../utils/controllerControls';
import { Activity, ArrowUpRight, Box, ClipboardCheck, Clock3, Download, Fan, History, Lightbulb, Power, RefreshCw, ScanLine, Server, ShieldAlert, ShieldCheck } from 'lucide-vue-next';
import AppShell from '../components/AppShell.vue';
import '../assets/dashboard-polish.css';
import DashboardSignal from '../components/DashboardSignal.vue';
import { api, type AgentDataContext, type ControllerAction } from '../services/api';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import { presentAudit } from '../utils/audit';
import { resolveTwinVisualState, twinStateLabel, type TwinVisualState } from '../services/twin3d';

const store = useOperationsStore();
const auth = useAuthStore();
const clock = useNow({ interval: 1000 });
const dataContext = ref<AgentDataContext | null>(null);
const commandProtocol = ref('unknown');
const controlDisabled = ref(true);
const fourController = computed(() => commandProtocol.value === 'four-controller-v2');
watch(() => store.source, async (source, _, onCleanup) => {
  let outdated = false;
  onCleanup(() => { outdated = true; });
  dataContext.value = null;
  commandProtocol.value = 'unknown';controlDisabled.value = true;
  if (source === 'api') {
    try {
      const { data } = await api.agentContext();
      if (!outdated) dataContext.value = data.dataContext;
      const capability = await api.controllerCommandCapabilities();
      if (!outdated) { commandProtocol.value = capability.data.protocol;controlDisabled.value = capability.data.controlDisabled; }
    } catch { /* Unknown provenance must not become a claim of live hardware data. */ }
  }
}, { immediate: true });
const dataAvailability = computed(() => {
  if (store.source !== 'api') return '演示数据，仅供界面预览';
  if (dataContext.value?.mode === 'simulated_test') return store.offline ? '模拟测试 · 数据服务暂不可用' : dataContext.value.label;
  if (store.offline) return '数据服务暂不可用，保留最近记录';
  if (!dataContext.value) return '平台记录；数据来源待核实';
  return store.dashboard.assets.online > 0 ? '平台存在在线记录；现场状态需核验' : '暂无在线记录，等待设备上报';
});
const mapAssets = computed(() => store.assets.map((asset) => ({ ...asset, visualState: resolveTwinVisualState(asset, store.alerts) })));
const mapStates: TwinVisualState[] = ['alarm', 'warning', 'normal', 'unknown'];
const signalOffline = computed(() => store.offline || store.dashboard.assets.online === 0 || store.assets.find((item) => item.code === store.dashboard.telemetry?.assetCode)?.status === 'offline');
const signalThreshold = computed(() => store.thresholds.find((item) => item.key === store.dashboard.telemetry?.metricKey)?.warning);
const reportError = ref('');
const exporting = ref(false);
const commandError = ref('');
const commandResult = ref('');
const commandSending = ref(false);
const pendingCommand = ref<{ action: ControllerAction; dutyPercent?: number; controller: string } | null>(null);
const canControlEquipment = computed(() => store.source === 'api' && !store.offline && !controlDisabled.value && ['operator', 'administrator'].includes(auth.user?.role || ''));
const fanLive = computed(() => {
  const latest = (assetCode: string, metricKey: string) => store.telemetry
    .filter((item) => item.assetCode === assetCode && (item.metricKey === metricKey || item.metric === metricKey))
    .sort((left, right) => new Date(right.recordedAt).getTime() - new Date(left.recordedAt).getTime())[0];
  return {
    fan1: { rpm: latest('FAN-01', 'rotational.speed'), current: latest('FAN-01', 'motor.current'), power: latest('FAN-01', 'power') },
    fan2: { rpm: latest('FAN-02', 'rotational.speed'), current: latest('FAN-02', 'motor.current'), power: latest('FAN-02', 'power') },
  };
});


async function sync() {
  reportError.value = '';
  await store.refresh(store.source);
  if (store.syncError) reportError.value = store.syncError;
}

async function report() {
  reportError.value = '';
  exporting.value = true;
  try {
    await store.createReport('daily');
  } catch (cause) {
    reportError.value = cause instanceof Error ? cause.message : '报表导出失败，请稍后重试。';
  } finally {
    exporting.value = false;
  }
}

const commandLabel = (action: ControllerAction, dutyPercent?: number) => ({
  relay_on: '接通风机供电（最长10秒）', relay_off: '断开风机供电',
  fan_pwm: `设置风机 1 PWM 为 ${dutyPercent}%（最长10秒）`, fan2_pwm: `设置风机 2 PWM 为 ${dutyPercent}%（最长10秒）`,
  buzzer_on: '开启蜂鸣器（10秒）', buzzer_off: '关闭蜂鸣器', auto: '恢复本地自动模式',
  led_blue: '切换灯带为蓝色', led_green: '切换灯带为绿色', led_red: '切换灯带为红色', led_off: '关闭灯带',
}[action]);

function requestControllerCommand(action: ControllerAction, dutyPercent?: number, target?: string) {
  if (!canControlEquipment.value || commandSending.value) return;
  commandError.value = '';
  commandResult.value = '';
  const controller = outputOwner(action, commandProtocol.value, target);
  pendingCommand.value = { action, dutyPercent, controller };
}

function cancelControllerCommand() {
  pendingCommand.value = null;
}

async function confirmControllerCommand() {
  const pending = pendingCommand.value;
  if (!pending || !canControlEquipment.value || commandSending.value) return;
  commandError.value = '';
  commandResult.value = '';
  commandSending.value = true;
  try {
    const confirmation = await api.controllerCommandConfirmation(pending.action, pending.dutyPercent, pending.controller);
    const response = await api.controllerCommand(pending.action, confirmation.data.confirmationToken, pending.dutyPercent, pending.controller);
    const ack = response.data.ack as { status?: string; reason?: string } | null;
    commandResult.value = ack?.status === 'accepted'
      ? (fourController.value ? '控制器已应用输出；是否运转仍需核对新鲜测速及供电反馈。手动设置最长保持10秒。' : `设备已确认：${ack.reason || pending.action}`)
      : ack?.status === 'rejected' ? `控制器拒绝命令：${ack.reason || '请检查本地保护与参数'}`
      : '执行结果未知；请先检查反馈，系统不会自动重发。';
    pendingCommand.value = null;
    await store.refresh('api');
  } catch (cause) {
    commandError.value = cause instanceof Error ? cause.message : '设备命令下发失败，请稍后重试。';
  } finally {
    commandSending.value = false;
  }
}
</script>


<template>
  <AppShell class="dashboard-shell">
    <div class="dashboard-workspace">
      <section class="hero dashboard-heading">
        <div>
          <div class="dashboard-context"><span class="context-line" />综合管廊运维工作台</div>
          <h1>运行，一眼掌握</h1>
          <p>从现场感知到处置闭环，让每一项运行状态都有据可查。</p>
        </div>
        <div class="section-actions">
          <button class="primary-button compact-button refresh-button" :disabled="store.loading" @click="sync"><RefreshCw :class="{ 'is-refreshing': store.loading }" aria-hidden="true" />{{ store.loading ? '同步中…' : '刷新数据' }}</button>
          <button class="primary-button snapshot-button" :disabled="exporting" @click="report"><Download aria-hidden="true" />{{ exporting ? '正在生成…' : '导出运行快照' }}</button>
        </div>
      </section>
      <div class="dashboard-data-bar">
        <span class="data-availability" :class="{ 'has-data': dataContext?.mode === 'database_observation' && store.dashboard.assets.online > 0 && !store.offline }"><i />{{ dataAvailability }}</span>
        <span class="dashboard-sync-time"><Clock3 aria-hidden="true" />{{ store.lastSyncedAt ? '最近同步 ' + new Date(store.lastSyncedAt).toLocaleString('zh-CN') : '尚未完成数据同步' }}</span>
      </div>
      <p v-if="reportError" class="inline-message error-message dashboard-error" role="alert">{{ reportError }}</p>

      <section class="metric-grid dashboard-metrics" aria-label="关键运行指标">
        <article class="metric-card">
          <div class="metric-top"><span>在线设备</span><span class="metric-icon"><Server aria-hidden="true" /></span></div>
          <strong>{{ store.dashboard.assets.online }}<small>/ {{ store.dashboard.assets.total }}</small></strong>
          <em><span class="metric-dot" :class="{ online: store.source === 'api' && !store.offline && store.dashboard.assets.online > 0 }" />按约定上报周期判定</em>
        </article>
        <article class="metric-card">
          <div class="metric-top"><span>环境健康度</span><span class="metric-icon"><Activity aria-hidden="true" /></span></div>
          <strong>{{ store.dashboard.assets.online > 0 ? store.dashboard.health.value : '--' }}<small v-if="store.dashboard.assets.online > 0">%</small></strong>
          <em>{{ store.dashboard.assets.online === 0 ? '暂无在线设备，等待评估' : store.dashboard.assets.online < store.dashboard.assets.total ? '部分设备离线，请结合告警核查' : '依据已上报数据计算，请结合告警核查' }}</em>
        </article>
        <article class="metric-card metric-attention">
          <div class="metric-top"><span>待确认事件</span><span class="metric-icon"><ShieldAlert aria-hidden="true" /></span></div>
          <strong>{{ String(store.openAlerts).padStart(2, '0') }}<small>项</small></strong>
          <em>{{ store.offline ? '保留最近同步的事件数量' : store.openAlerts ? '存在待处理事件，请及时核查' : '当前无待确认事件' }}</em>
        </article>
        <article class="metric-card">
          <div class="metric-top"><span>进行中工单</span><span class="metric-icon"><ClipboardCheck aria-hidden="true" /></span></div>
          <strong>{{ String(store.activeOrders).padStart(2, '0') }}<small>项</small></strong>
          <em v-if="store.dashboard.workOrderSla?.overdue" class="metric-overdue">{{ store.dashboard.workOrderSla.overdue }} 项已超时，优先处置</em>
          <em v-else-if="store.dashboard.workOrderSla?.dueSoon">{{ store.dashboard.workOrderSla.dueSoon }} 项将在 4 小时内到期</em>
          <em v-else>{{ store.offline ? '保留最近同步的工单数量' : store.activeOrders ? '处理时限正常' : '当前无进行中工单' }}</em>
        </article>
      </section>

      <section class="dashboard-grid dashboard-overview">
        <article class="panel twin-panel">
          <header class="panel-head">
            <div class="panel-title"><span class="panel-symbol"><Box aria-hidden="true" /></span><div><h2>管廊实时态势</h2><p>设备状态与告警位置概览</p></div></div>
            <RouterLink to="/twin-3d">三维孪生<ArrowUpRight aria-hidden="true" /></RouterLink>
          </header>
          <div class="tunnel-map" :class="{ 'map-awaiting': !mapAssets.length }">
            <div class="map-grid" aria-hidden="true" />
            <svg class="tunnel-blueprint" viewBox="0 0 640 300" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
              <path class="blueprint-chamber" d="M105 55H535V245H105Z" />
              <path class="blueprint-inner" d="M130 80H510V220H130Z" />
              <path class="blueprint-pipe" d="M35 115H225V185H605M35 145H195V215H605" />
              <path class="blueprint-service" d="M320 30V270M80 150H560" />
              <path class="blueprint-mark" d="M95 45H115M105 35V55M525 45H545M535 35V55M95 255H115M105 245V265M525 255H545M535 245V265" />
            </svg>
            <div class="map-caption"><span>设备位置示意</span><small>状态随数据更新</small></div>
            <div v-if="!mapAssets.length" class="map-empty" role="status">
              <span class="map-empty-symbol"><ScanLine aria-hidden="true" /></span>
              <strong>等待设备接入</strong>
              <p>完成台账与遥测接入后，设备状态将在这里呈现。</p>
              <RouterLink to="/assets">查看设备台账<ArrowUpRight aria-hidden="true" /></RouterLink>
            </div>
            <RouterLink v-for="asset in mapAssets" :key="asset.id" class="map-node" :class="asset.visualState" :to="{ path: '/twin-3d', query: { asset: asset.code } }" :aria-label="`查看${asset.name}：${twinStateLabel(asset.visualState)}`" :style="{ left: `${asset.position.x}%`, top: `${asset.position.y}%` }"><i /><span>{{ asset.code }}</span></RouterLink>
          </div>
          <div class="map-legend"><span v-for="state in mapStates" :key="state"><i :class="state" />{{ twinStateLabel(state) }}<b>{{ mapAssets.filter((item) => item.visualState === state).length }}</b></span></div>
          <p class="map-disclaimer">位置仅作示意，不代表真实坐标。点击设备可进入三维定位；在线数量以上方统计为准。</p>
        </article>
        <DashboardSignal theme="light" :selected="store.dashboard.telemetry" :samples="store.telemetry" :offline="signalOffline" :threshold="signalThreshold" />
      </section>

      <section class="dashboard-grid lower-grid dashboard-operations">
        <article class="panel activity-panel">
          <header class="panel-head">
            <div class="panel-title"><span class="panel-symbol"><History aria-hidden="true" /></span><div><h2>最新运行动态</h2><p>关键操作与处置记录</p></div></div>
            <RouterLink to="/audit">全部记录<ArrowUpRight aria-hidden="true" /></RouterLink>
          </header>
          <div class="activity-timeline">
            <div v-for="item in store.audit.slice(0, 4)" :key="item.id" class="activity-item">
              <i aria-hidden="true" /><time>{{ new Date(item.occurredAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</time>
              <div><b>{{ presentAudit(item).title }}</b><p>{{ presentAudit(item).description }}</p></div>
            </div>
            <div v-if="!store.audit.length" class="dashboard-empty"><History aria-hidden="true" /><strong>暂无运行动态</strong><p>登录、配置与运维操作完成后，记录会出现在这里。</p></div>
          </div>
          <footer class="activity-footer"><ShieldCheck aria-hidden="true" />关键操作全程留痕，可追溯、可复核</footer>
        </article>
        <article class="panel control-panel">
          <header class="panel-head">
            <div class="panel-title"><span class="panel-symbol"><Fan aria-hidden="true" /></span><div><h2>双风机控制</h2><p>{{ fourController ? 'FAN-01 → CTRL-04 · FAN-02 → CTRL-02' : (commandProtocol === 'legacy' ? '旧协议联调 · CTRL-01' : '控制配置待加载') }}</p></div></div>
            <span class="control-confirm-tag"><ShieldCheck aria-hidden="true" />二次确认</span>
          </header>
          <div class="control-body">
            <div class="fan-live-grid">
              <div class="fan-unit"><div class="fan-unit-heading"><span class="fan-device-icon"><Fan aria-hidden="true" /></span><b>FAN-01</b><small>风机 1</small></div><strong>{{ feedbackValue(fanLive.fan1.rpm, clock.getTime()) }}<small> RPM</small></strong><span class="fan-electrical">{{ feedbackValue(fanLive.fan1.current, clock.getTime(), 2) }} mA<span>·</span>{{ feedbackValue(fanLive.fan1.power, clock.getTime(), 3) }} W</span><span class="control-group-title">PWM设定</span><div class="fan-actions fan-speed-actions"><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan_pwm', 30)">30%</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan_pwm', 60)">60%</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan_pwm', 100)">100%</button></div></div>
              <div class="fan-unit"><div class="fan-unit-heading"><span class="fan-device-icon"><Fan aria-hidden="true" /></span><b>FAN-02</b><small>风机 2</small></div><strong>{{ feedbackValue(fanLive.fan2.rpm, clock.getTime()) }}<small> RPM</small></strong><span class="fan-electrical">{{ feedbackValue(fanLive.fan2.current, clock.getTime(), 2) }} mA<span>·</span>{{ feedbackValue(fanLive.fan2.power, clock.getTime(), 3) }} W</span><span class="control-group-title">PWM设定</span><div class="fan-actions fan-speed-actions"><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan2_pwm', 30)">30%</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan2_pwm', 60)">60%</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan2_pwm', 100)">100%</button></div></div>
            </div>
            <div v-if="!fourController" class="shared-power"><span class="control-group-title"><Power aria-hidden="true" />共用电源</span><div class="fan-actions"><button class="fan-start-action" :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('relay_on')"><Power aria-hidden="true" />{{ commandSending ? '下发中…' : '启动风扇（10秒）' }}</button><button class="stop-action" :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('relay_off')">立即停止</button></div></div>
            <div v-if="fourController" class="shared-power">
              <div v-for="fan in [{ code: 'FAN-01', controller: 'CTRL-04' }, { code: 'FAN-02', controller: 'CTRL-02' }]" :key="fan.code">
                <span class="control-group-title">{{ fan.code }} · {{ fan.controller }} 独立供电</span>
                <div class="fan-actions"><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('relay_on', undefined, fan.controller)">供电10秒</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('relay_off', undefined, fan.controller)">断开供电</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('auto', undefined, fan.controller)">恢复自动</button></div>
              </div>
            </div>
            <div class="lighting-row"><span class="control-group-title"><Lightbulb aria-hidden="true" />灯带联调</span><div class="lighting-actions"><button class="light-blue" :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('led_blue')">蓝色</button><button class="light-green" :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('led_green')">绿色</button><button class="light-red" :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('led_red')">红色</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('led_off')">熄灭</button></div></div>
            <p class="control-note">{{ fourController ? '每台风机独立供电与PWM；手动输出最长10秒，本地报警优先。回执不能代替运行反馈；带*为未核实或待标定读数，缺失或过期显示—。' : '旧 CTRL-01 协议：仅用于旧系统联调。部署四节点固件后，需启用服务端四节点协议配置。' }}</p>
            <small v-if="!canControlEquipment" class="control-access-note">请使用在线 API 模式并以运维员或管理员身份登录。</small>
            <p v-if="commandResult" class="command-ok" role="status">{{ commandResult }}</p><p v-if="commandError" class="command-error" role="alert">{{ commandError }}</p>
          </div>
        </article>
      </section>
      <footer class="dashboard-footer"><span>综合管廊数字孪生运维平台</span><span><ShieldCheck aria-hidden="true" />感知 · 处置 · 复核 · 归档</span></footer>
    </div>
    <div v-if="pendingCommand" class="command-confirmation-mask" role="presentation" @click.self="cancelControllerCommand">
      <section class="command-confirmation" role="dialog" aria-modal="true" aria-labelledby="command-confirmation-title">
        <span class="confirmation-symbol"><ShieldCheck aria-hidden="true" /></span><h2 id="command-confirmation-title">确认下发设备命令</h2>
        <p>即将向 <strong>{{ pendingCommand.controller }}</strong> 下发：<strong>{{ commandLabel(pendingCommand.action, pendingCommand.dutyPercent) }}</strong>。</p>
        <p>系统会签发 2 分钟内有效且只能使用一次的确认凭据；若通信超时，不会自动重发。</p>
        <div><button type="button" :disabled="commandSending" @click="cancelControllerCommand">取消</button><button type="button" class="confirm-command" :disabled="commandSending" @click="confirmControllerCommand">{{ commandSending ? '正在下发…' : '确认并下发' }}</button></div>
      </section>
    </div>
  </AppShell>
</template>
