<script setup lang="ts">
import { computed, ref } from 'vue';
import { useNow } from '@vueuse/core';
import { Download, Fan, Lightbulb, RefreshCw, TrendingUp } from 'lucide-vue-next';
import AppShell from '../components/AppShell.vue';
import DashboardSignal from '../components/DashboardSignal.vue';
import { api, type ControllerAction } from '../services/api';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import { presentAudit } from '../utils/audit';
import { resolveTwinVisualState, twinStateLabel, type TwinVisualState } from '../services/twin3d';
import type { Telemetry } from '../types';
import { latestTelemetry, telemetryState, telemetryStateLabel } from '../utils/telemetryState';

const store = useOperationsStore();
const auth = useAuthStore();
const now = useNow({ interval: 10_000 });
const mapAssets = computed(() => store.assets.map((asset) => ({ ...asset, visualState: resolveTwinVisualState(asset, store.alerts) })));
const mapStates: TwinVisualState[] = ['alarm', 'warning', 'normal', 'unknown'];
const signalOffline = computed(() => store.offline || store.dashboard.assets.online === 0 || store.assets.find((item) => item.code === store.dashboard.telemetry?.assetCode)?.status === 'offline');
const signalThreshold = computed(() => store.thresholds.find((item) => item.key === store.dashboard.telemetry?.metricKey)?.warning);
const signalAsset = computed(() => store.assets.find((item) => item.code === store.dashboard.telemetry?.assetCode));
const signalBinding = computed(() => store.hardwareBindings.find((item) => item.assetCode === signalAsset.value?.code));
const sourceLabel = computed(() => store.source === 'demo' ? '演示数据' : store.offline ? 'API 离线快照' : store.realtimeState === 'connected' ? 'API 实时连接' : 'API 快照 · 实时连接恢复中');
const reportError = ref('');
const exporting = ref(false);
const commandError = ref('');
const commandResult = ref('');
const commandSending = ref(false);
const lastConfirmedCommand = ref<{ label: string; at: string } | null>(null);
const pendingCommand = ref<{ action: ControllerAction; dutyPercent?: number } | null>(null);
const canControlEquipment = computed(() => store.source === 'api' && !store.offline && ['operator', 'administrator'].includes(auth.user?.role || ''));
const fanLive = computed(() => {
  const latest = (assetCode: string, metricKey: string) => latestTelemetry(store.telemetry, assetCode, metricKey);
  return {
    fan1: { rpm: latest('FAN-01', 'rotational.speed'), current: latest('FAN-01', 'motor.current'), power: latest('FAN-01', 'power') },
    fan2: { rpm: latest('FAN-02', 'rotational.speed'), current: latest('FAN-02', 'motor.current'), power: latest('FAN-02', 'power') },
  };
});

function fanValue(reading: Telemetry | undefined, digits = 0) {
  return !reading || reading.quality === 'bad' || reading.quality === 'missing' || !Number.isFinite(reading.value) ? '—' : reading.value.toFixed(digits);
}

function fanState(assetCode: string, reading: Telemetry | undefined) {
  const asset = store.assets.find((item) => item.code === assetCode);
  const binding = store.hardwareBindings.find((item) => item.assetCode === assetCode);
  return telemetryStateLabel[telemetryState(reading, asset, binding, store.source, store.offline, now.value.getTime())];
}

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
  relay_on: '启动风扇（10 秒）', relay_off: '立即停止风扇',
  fan_pwm: `设置风机 1 转速为 ${dutyPercent}%`, fan2_pwm: `设置风机 2 转速为 ${dutyPercent}%`,
  led_blue: '切换灯带为蓝色', led_green: '切换灯带为绿色', led_red: '切换灯带为红色', led_off: '关闭灯带',
}[action]);

function requestControllerCommand(action: ControllerAction, dutyPercent?: number) {
  if (!canControlEquipment.value || commandSending.value) return;
  commandError.value = '';
  commandResult.value = '';
  pendingCommand.value = { action, dutyPercent };
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
    const confirmation = await api.controllerCommandConfirmation(pending.action, pending.dutyPercent);
    const response = await api.controllerCommand(pending.action, confirmation.data.confirmationToken, pending.dutyPercent);
    const ack = response.data.ack as { status?: string; reason?: string } | null;
    if (ack?.status === 'accepted') {
      lastConfirmedCommand.value = { label: commandLabel(pending.action, pending.dutyPercent), at: new Date().toISOString() };
      commandResult.value = `已收到设备回执：${ack.reason || pending.action}。请以随后上报的设备状态核对实际效果。`;
    } else if (ack) {
      commandError.value = `设备未接受命令：${ack.reason || ack.status || '原因待核查'}`;
    } else {
      commandResult.value = '命令已发布，等待设备回执；当前执行结果未确认。';
    }
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
  <AppShell>
    <section class="hero">
      <div><span class="eyebrow light">CONTROL ROOM · LIVE FEED</span><h1>运行，一眼掌握</h1><p>集中掌握综合管廊运行状态，所有关键操作均记录审计。</p><p class="dashboard-source" role="status">数据来源：{{ sourceLabel }}</p><p v-if="store.lastSyncedAt">最近同步：{{ new Date(store.lastSyncedAt).toLocaleString('zh-CN') }}</p><p v-if="reportError" class="inline-message error-message" role="alert">{{ reportError }}</p></div>
      <div class="section-actions"><button class="primary-button compact-button" :disabled="store.loading" @click="sync"><RefreshCw />{{ store.loading ? '同步中…' : '刷新数据' }}</button><button class="primary-button" :disabled="exporting" @click="report"><Download />{{ exporting ? '正在生成…' : '导出运行快照' }}</button></div>
    </section>
    <section class="metric-grid">
      <article class="metric-card accent-blue" data-index="01"><span>在线设备 <TrendingUp /></span><strong>{{ store.dashboard.assets.online }}<small>/ {{ store.dashboard.assets.total }}</small></strong><em>按约定上报周期判定</em></article>
      <article class="metric-card accent-mint" data-index="02">
        <span>环境健康度 <TrendingUp /></span>
        <strong>{{ store.dashboard.assets.online > 0 ? store.dashboard.health.value : '--' }}<small v-if="store.dashboard.assets.online > 0">%</small></strong>
        <em>{{ store.dashboard.assets.online === 0 ? '无在线设备，暂无法判断' : store.dashboard.assets.online < store.dashboard.assets.total ? '部分设备离线，请结合告警核查' : '依据已上报数据计算，请结合告警核查' }}</em>
      </article>
      <article class="metric-card accent-amber" data-index="03"><span>待确认事件 <TrendingUp /></span><strong>{{ String(store.openAlerts).padStart(2, '0') }}<small>项</small></strong><em>需关注</em></article>
      <article class="metric-card accent-violet" data-index="04"><span>进行中工单 <TrendingUp /></span><strong>{{ String(store.activeOrders).padStart(2, '0') }}<small>项</small></strong><em v-if="store.dashboard.workOrderSla?.overdue">{{ store.dashboard.workOrderSla.overdue }} 项已超时，优先处置</em><em v-else-if="store.dashboard.workOrderSla?.dueSoon">{{ store.dashboard.workOrderSla.dueSoon }} 项将在 4 小时内到期</em><em v-else>处理时限正常</em></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel twin-panel">
        <div class="panel-head"><div><span class="eyebrow">TWIN PULSE</span><h2>管廊实时态势</h2></div><RouterLink to="/twin-3d">进入三维孪生 →</RouterLink></div>
        <div class="tunnel-map">
          <div class="map-grid" /><div class="map-track track-one" /><div class="map-track track-two" />
          <RouterLink v-for="asset in mapAssets" :key="asset.id" class="map-node" :class="asset.visualState" :to="{ path: '/twin-3d', query: { asset: asset.code } }" :aria-label="`查看${asset.name}：${twinStateLabel(asset.visualState)}`" :style="{ left: `${asset.position.x}%`, top: `${asset.position.y}%` }"><i /><span>{{ asset.code }}</span></RouterLink>
          <div class="map-legend"><span v-for="state in mapStates" :key="state"><i :class="state" />{{ twinStateLabel(state) }} {{ mapAssets.filter((item) => item.visualState === state).length }}</span></div>
        </div>
        <p class="map-disclaimer">位置示意，不代表真实坐标；状态与三维告警一致，在线数量请查看上方统计。点击设备可定位三维模型。</p>
      </article>
      <DashboardSignal :selected="store.dashboard.telemetry" :samples="store.telemetry" :offline="signalOffline" :source="store.source" :asset="signalAsset" :binding="signalBinding" :threshold="signalThreshold" />
    </section>
    <section class="dashboard-grid lower-grid">
      <article class="panel activity-panel"><div class="panel-head"><div><span class="eyebrow">ACTIVITY STREAM</span><h2>最新运行动态</h2></div><RouterLink to="/audit">审计追踪 →</RouterLink></div><div v-for="item in store.audit.slice(0, 4)" :key="item.id" class="activity-item"><i /><time>{{ new Date(item.occurredAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</time><div><b>{{ presentAudit(item).title }}</b><p>{{ presentAudit(item).description }}</p></div></div><div v-if="!store.audit.length" class="empty-state">当前暂无审计记录。</div></article>
      <article class="panel control-panel">
        <div class="panel-head"><div><span class="eyebrow">CTRL-01 · MQTT</span><h2>双风机控制</h2></div><Fan /></div>
        <p>两台风机共用继电器总使能，转速与电流独立采集，PWM 可分别调节。每次下发都需二次确认，确认凭据仅可使用一次。</p>
        <div class="fan-live-grid">
          <div><b>FAN-01</b><strong>{{ fanValue(fanLive.fan1.rpm) }}<small> RPM</small></strong><span>{{ fanValue(fanLive.fan1.current, 2) }} mA · {{ fanValue(fanLive.fan1.power, 3) }} W</span><small>{{ fanState('FAN-01', fanLive.fan1.rpm) }} · {{ fanLive.fan1.rpm ? new Date(fanLive.fan1.rpm.recordedAt).toLocaleString('zh-CN') : '暂无采集时间' }}</small></div>
          <div><b>FAN-02</b><strong>{{ fanValue(fanLive.fan2.rpm) }}<small> RPM</small></strong><span>{{ fanValue(fanLive.fan2.current, 2) }} mA · {{ fanValue(fanLive.fan2.power, 3) }} W</span><small>{{ fanState('FAN-02', fanLive.fan2.rpm) }} · {{ fanLive.fan2.rpm ? new Date(fanLive.fan2.rpm.recordedAt).toLocaleString('zh-CN') : '暂无采集时间' }}</small></div>
        </div>
        <span class="control-group-title"><Fan />共用电源</span><div class="fan-actions"><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('relay_on')">{{ commandSending ? '下发中…' : '启动风扇（10秒）' }}</button><button class="stop-action" :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('relay_off')">立即停止</button></div>
        <span class="control-group-title"><Fan />风机 1 转速</span><div class="fan-actions fan-speed-actions"><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan_pwm', 30)">30%</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan_pwm', 60)">60%</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan_pwm', 100)">100%</button></div>
        <span class="control-group-title"><Fan />风机 2 转速</span><div class="fan-actions fan-speed-actions"><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan2_pwm', 30)">30%</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan2_pwm', 60)">60%</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('fan2_pwm', 100)">100%</button></div>
        <span class="control-group-title"><Lightbulb />灯带联调</span><div class="lighting-actions"><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('led_blue')">蓝色</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('led_green')">绿色</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('led_red')">红色</button><button :disabled="!canControlEquipment || commandSending" @click="requestControllerCommand('led_off')">熄灭</button></div>
        <small v-if="!canControlEquipment">请使用在线 API 模式并以运维员或管理员身份登录。</small>
        <p v-if="lastConfirmedCommand" class="command-last-receipt">本页最近回执：{{ lastConfirmedCommand.label }} · {{ new Date(lastConfirmedCommand.at).toLocaleTimeString('zh-CN') }}。当前实际状态请以遥测核对。</p>
        <b v-if="commandResult" class="command-ok" role="status">{{ commandResult }}</b><b v-if="commandError" class="command-error" role="alert">{{ commandError }}</b>
      </article>
    </section>
    <div v-if="pendingCommand" class="command-confirmation-mask" role="presentation" @click.self="cancelControllerCommand">
      <section class="command-confirmation" role="dialog" aria-modal="true" aria-labelledby="command-confirmation-title">
        <span class="eyebrow">安全控制确认</span><h2 id="command-confirmation-title">确认下发设备命令</h2>
        <p>即将向 <strong>CTRL-01</strong> 下发：<strong>{{ commandLabel(pendingCommand.action, pendingCommand.dutyPercent) }}</strong>。</p>
        <p>系统会签发 2 分钟内有效且只能使用一次的确认凭据；若通信超时，不会自动重发。</p>
        <div><button type="button" :disabled="commandSending" @click="cancelControllerCommand">取消</button><button type="button" class="confirm-command" :disabled="commandSending" @click="confirmControllerCommand">{{ commandSending ? '正在下发…' : '确认并下发' }}</button></div>
      </section>
    </div>
  </AppShell>
</template>

<style scoped>
.map-node { text-decoration: none; }
.dashboard-source { display: inline-block; padding: 5px 10px; border: 1px solid var(--ops-line); border-radius: 6px; color: var(--ops-signal); }
.fan-live-grid div > small { display: block; margin-top: 5px; color: var(--ops-muted); }
.fan-speed-actions button:first-child { border-color: #35547c; background: #152842; color: #b5c9eb; }
.command-last-receipt { margin-top: 12px; color: var(--ops-muted); font-size: 12px; }
.command-confirmation-mask { position: fixed; z-index: 12100; inset: 0; display: grid; place-items: center; padding: 18px; background: rgba(0, 0, 0, .72); }
.command-confirmation { width: min(480px, 100%); padding: 24px; border: 1px solid var(--ops-signal); background: var(--ops-bg-deep); box-shadow: 16px 16px 0 rgba(0, 0, 0, .55); }
.command-confirmation h2 { margin: 10px 0 16px; font-size: 24px; }
.command-confirmation p { color: var(--ops-muted); line-height: 1.7; }
.command-confirmation p strong { color: var(--ops-text); }
.command-confirmation > div { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 10px; margin-top: 22px; }
.command-confirmation button { min-height: 42px; padding: 0 16px; border: 1px solid var(--ops-line); color: var(--ops-text); background: transparent; }
.command-confirmation .confirm-command { border-color: var(--ops-danger); color: #fff; background: var(--ops-danger); }
.map-node:focus-visible { outline: 2px solid var(--ops-signal); outline-offset: 5px; z-index: 3; }
.map-node.alarm i, .map-legend i.alarm { background: #ff526e; box-shadow: 0 0 0 5px #ff526e22; }
.map-node.unknown i, .map-legend i.unknown { background: #8191a7; box-shadow: 0 0 0 5px #8191a722; }
.map-legend { flex-wrap: wrap; gap: 10px; }
.map-disclaimer { padding: 0 20px 15px; color: var(--ops-muted); font-size: 11px; line-height: 1.7; }
@media (max-width: 600px) {
  .tunnel-map { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-content: start; gap: 10px; height: auto; min-height: 0; padding: 18px 12px; }
  .tunnel-map .map-grid, .tunnel-map .map-track, .tunnel-map::after { display: none; }
  .tunnel-map .map-node { position: relative; inset: auto !important; display: flex; align-items: center; gap: 10px; min-width: 0; min-height: 44px; padding: 10px; border: 1px solid var(--ops-line); transform: none !important; animation: none; }
  .tunnel-map .map-node i { flex-shrink: 0; }
  .tunnel-map .map-node span { min-width: 0; overflow-wrap: anywhere; white-space: normal; }
  .tunnel-map .map-legend { grid-column: 1 / -1; position: static; margin-top: 8px; }
}
</style>
