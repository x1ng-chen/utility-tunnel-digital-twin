import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { api } from '../services/api';
import { useAuthStore } from './auth';
import type { Alert, Asset, AuditEntry, Dashboard, Telemetry, Threshold, WorkOrder } from '../types';

type ReportKind = 'alerts' | 'workOrders' | 'assets' | 'daily';
const demoTransitions: Record<WorkOrder['status'], WorkOrder['status'][]> = {
  draft: ['open', 'cancelled'],
  open: ['assigned', 'cancelled'],
  assigned: ['in_progress', 'cancelled'],
  in_progress: ['pending_review', 'cancelled'],
  pending_review: ['completed', 'in_progress'],
  completed: [],
  cancelled: [],
};
let localSequence = 0;

function responseStatus(cause: unknown): number | null {
  if (typeof cause !== 'object' || !cause || !('response' in cause)) return null;
  const response = (cause as { response?: { status?: unknown } }).response;
  return typeof response?.status === 'number' ? response.status : null;
}

function nextLocalId(): number {
  localSequence += 1;
  // Keep demo identifiers unique even when two actions occur in one millisecond.
  return Date.now() * 1000 + localSequence;
}

function requestKey(prefix: string): string {
  const suffix = typeof globalThis.crypto?.randomUUID === 'function' ? globalThis.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`.slice(0, 80);
}

export const useOperationsStore = defineStore('operations', () => {
  const auth = useAuthStore();
  const dashboard = ref<Dashboard>({ assets: { total: 12, online: 5 }, health: { value: 100 }, openAlerts: 2, activeWorkOrders: 2, telemetry: { id: 1, assetCode: 'ENV-01', metric: '环境温度', value: 26.4, unit: '°C', quality: 'good', recordedAt: new Date().toISOString() } });
  const assets = ref<Asset[]>(seedAssets());
  const alerts = ref<Alert[]>(seedAlerts());
  const workOrders = ref<WorkOrder[]>(seedOrders());
  const thresholds = ref<Threshold[]>(seedThresholds());
  const telemetry = ref<Telemetry[]>([]);
  const audit = ref<AuditEntry[]>([]);
  const loading = ref(false);
  const source = ref<'demo' | 'api'>('demo');
  const offline = ref(false);
  const syncError = ref('');
  const lastSyncedAt = ref<string | null>(null);
  const notice = ref('');
  const openAlerts = computed(() => alerts.value.filter((item) => item.status === 'open').length);
  const activeOrders = computed(() => workOrders.value.filter((item) => !['completed', 'cancelled'].includes(item.status)).length);

  function expireApiSession() {
    auth.expireSession();
    offline.value = true;
    syncError.value = '登录状态已过期，请重新登录。';
    notice.value = '登录状态已过期，请重新登录。';
  }

  async function runApiMutation<T>(request: () => Promise<T>): Promise<T> {
    try {
      return await request();
    } catch (cause: unknown) {
      if (responseStatus(cause) === 401) expireApiSession();
      throw cause;
    }
  }

  async function refresh(mode: 'demo' | 'api' = source.value) {
    source.value = mode;
    if (mode === 'demo') {
      offline.value = false;
      syncError.value = '';
      lastSyncedAt.value = new Date().toISOString();
      tick();
      return;
    }
    loading.value = true;
    syncError.value = '';
    try {
      const listParams = { page: 1, pageSize: 100 };
      const [dashboardResponse, assetsResponse, alertsResponse, ordersResponse, thresholdsResponse, telemetryResponse, auditResponse] = await Promise.all([api.dashboard(), api.assets(listParams), api.alerts(listParams), api.workOrders(listParams), api.thresholds(), api.telemetry(listParams), api.audit(listParams)]);
      dashboard.value = dashboardResponse.data; assets.value = assetsResponse.data.items; alerts.value = alertsResponse.data.items; workOrders.value = ordersResponse.data.items; thresholds.value = thresholdsResponse.data.items; telemetry.value = telemetryResponse.data.items; audit.value = auditResponse.data.items;
      offline.value = false;
      lastSyncedAt.value = new Date().toISOString();
    } catch (cause: unknown) {
      if (responseStatus(cause) === 401) {
        expireApiSession();
      } else {
        offline.value = true;
        syncError.value = apiErrorMessage(cause);
        notice.value = 'Django API 暂不可用，当前为只读离线快照。';
      }
    }
    finally { loading.value = false; }
  }

  function tick() {
    const current = dashboard.value.telemetry;
    if (current) dashboard.value.telemetry = { ...current, value: Math.max(0, Number((current.value + Math.sin(Date.now() / 800) * 7).toFixed(2))), recordedAt: new Date().toISOString() };
    dashboard.value = { ...dashboard.value, openAlerts: openAlerts.value, activeWorkOrders: activeOrders.value };
  }

  async function acknowledge(alert: Alert) {
    if (offline.value) throw new Error('Django API 当前离线，离线快照为只读状态。');
    if (source.value === 'demo' && alert.status !== 'open') throw new Error('只有待确认告警可以确认');
    const response = source.value === 'api' ? await runApiMutation(() => api.acknowledge(alert.id)) : null;
    Object.assign(alert, response?.data ?? { status: 'acknowledged', acknowledgedAt: new Date().toISOString(), acknowledgedBy: auth.user?.displayName || '演示用户' });
    if (source.value === 'demo') appendAudit('alert.acknowledged', 'alert', alert.id, { code: alert.code });
    else await syncAudit();
    notice.value = `${alert.code} 已确认`;
  }

  async function createAlertOrder(alert: Alert) {
    if (offline.value) throw new Error('Django API 当前离线，离线快照为只读状态。');
    const existing = workOrders.value.find((item) => item.sourceAlertId === alert.id);
    if (existing) { notice.value = `${alert.code} 已有关联工单`; return existing; }
    if (!alert.assetCode) throw new Error('告警缺少关联资产，无法创建工单');
    const response = source.value === 'api' ? await runApiMutation(() => api.createAlertWorkOrder(alert.id)) : null;
    const now = new Date().toISOString();
    const next: WorkOrder = response?.data ?? { id: nextLocalId(), code: `WO-${now.slice(2, 10).replaceAll('-', '')}-${String(localSequence).padStart(2, '0')}`, sourceAlertId: alert.id, assetCode: alert.assetCode, title: `处置 ${alert.code}：${alert.title}`, priority: alert.severity === 'critical' ? 'urgent' : 'high', status: 'open', createdAt: now, updatedAt: now, version: 1 };
    workOrders.value.unshift(next);
    if (source.value === 'demo') appendAudit('work_order.created_from_alert', 'work_order', next.id, { alertCode: alert.code, assetCode: alert.assetCode });
    else await syncAudit();
    notice.value = '已创建关联工单';
    return next;
  }

  async function transition(order: WorkOrder, to: WorkOrder['status']) {
    if (offline.value) throw new Error('Django API 当前离线，离线快照为只读状态。');
    if (source.value === 'demo' && !demoTransitions[order.status].includes(to)) throw new Error('无效的工单状态流转');
    if (source.value === 'demo' && to === 'completed' && auth.user?.role !== 'administrator') throw new Error('只有管理员可以完成工单');
    const previous = order.status;
    const response = source.value === 'api' ? await runApiMutation(() => api.transitionWorkOrder(order.id, to, order.version)) : null;
    Object.assign(order, response?.data ?? { status: to, assigneeName: to === 'assigned' ? (auth.user?.displayName || '演示运维员') : order.assigneeName, updatedAt: new Date().toISOString(), completedAt: to === 'completed' ? new Date().toISOString() : order.completedAt, version: order.version + 1 });
    if (source.value === 'demo' && to === 'completed') {
      const linkedAlert = order.sourceAlertId ? alerts.value.find((item) => item.id === order.sourceAlertId) : undefined;
      if (linkedAlert && ['open', 'acknowledged'].includes(linkedAlert.status)) {
        linkedAlert.status = 'resolved';
        linkedAlert.resolvedAt = new Date().toISOString();
      }
      const asset = assets.value.find((item) => item.code === order.assetCode);
      const hasActiveAlert = alerts.value.some((item) => item.assetCode === order.assetCode && ['open', 'acknowledged'].includes(item.status));
      if (asset && !hasActiveAlert) asset.status = 'normal';
    }
    if (source.value === 'demo') appendAudit('work_order.transitioned', 'work_order', order.id, { from: previous, to });
    else await syncAudit();
    notice.value = `${order.code} 已更新为 ${to}`;
  }

  async function updateThreshold(threshold: Threshold, warning: number, alarm: number) {
    if (offline.value) throw new Error('Django API 当前离线，离线快照为只读状态。');
    if (!Number.isFinite(warning) || !Number.isFinite(alarm) || warning < 0 || alarm <= warning) throw new Error('报警阈值必须大于预警阈值');
    const response = source.value === 'api' ? await runApiMutation(() => api.updateThreshold(threshold.key, { warning, alarm, version: threshold.version })) : null;
    if (response?.data) {
      Object.assign(threshold, response.data);
    } else {
      threshold.warning = warning; threshold.alarm = alarm; threshold.version += 1;
    }
    if (source.value === 'demo') appendAudit('setting.threshold.update', 'threshold', threshold.key, { warning, alarm, version: threshold.version });
    else await syncAudit();
    notice.value = `${threshold.label} 阈值已保存`;
  }

  async function createWorkOrder(input: { assetCode: string; title: string; description?: string; priority: WorkOrder['priority'] }) {
    if (offline.value) throw new Error('Django API 当前离线，离线快照为只读状态。');
    const title = input.title.trim();
    if (!title) throw new Error('工单标题不能为空');
    const asset = assets.value.find((item) => item.code === input.assetCode);
    if (!asset) throw new Error('请选择有效的关联资产');
    const response = source.value === 'api' ? await runApiMutation(() => api.createWorkOrder({ ...input, title }, requestKey('work-order'))) : null;
    const now = new Date().toISOString();
    const next: WorkOrder = response?.data ?? {
      id: nextLocalId(),
      code: `WO-${now.slice(2, 10).replaceAll('-', '')}-${String(localSequence).padStart(2, '0')}`,
      sourceAlertId: null,
      assetCode: input.assetCode,
      title,
      description: input.description?.trim() || '',
      priority: input.priority,
      status: 'open',
      assigneeName: null,
      dueAt: null,
      completedAt: null,
      createdAt: now,
      updatedAt: now,
      version: 1,
    };
    workOrders.value.unshift(next);
    if (source.value === 'demo') appendAudit('work_order.created_manual', 'work_order', next.id, { assetCode: next.assetCode, priority: next.priority });
    else await syncAudit();
    notice.value = `${next.code} 已创建`;
    return next;
  }

  async function createReport(report: ReportKind) {
    if (source.value === 'api') await runApiMutation(() => api.report(report, requestKey('report')));
    downloadReport(report);
    if (source.value === 'demo') appendAudit('report.export', 'report_export', report, { report, format: 'csv' });
    else await syncAudit();
    notice.value = `${report} 报表已生成`;
  }

  function appendAudit(action: string, resourceType: string, resourceId: number | string, detail: Record<string, unknown>) {
    const occurredAt = new Date().toISOString();
    audit.value.unshift({ id: nextLocalId(), actorName: auth.user?.displayName || '演示用户', action, resourceType, resourceId: String(resourceId), detail, requestId: `demo-${localSequence}`, occurredAt });
  }

  async function syncAudit() {
    try { audit.value = (await api.audit({ page: 1, pageSize: 100 })).data.items; } catch (cause: unknown) {
      if (responseStatus(cause) === 401) expireApiSession();
      /* The primary mutation already succeeded; keep the last audit view. */
    }
  }

  function downloadReport(report: ReportKind) {
    if (typeof window === 'undefined' || typeof document === 'undefined' || typeof Blob === 'undefined') return;
    const rows = report === 'alerts' ? alerts.value : report === 'workOrders' ? workOrders.value : report === 'assets' ? assets.value : [{ ...dashboard.value, telemetry: dashboard.value.telemetry }];
    const headers = rows.length ? Object.keys(rows[0]) : ['report'];
    const csv = `\uFEFF${[headers, ...rows.map((row) => headers.map((header) => row[header as keyof typeof row]))].map((row) => row.map((value) => csvCell(value)).join(',')).join('\r\n')}`;
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = `utility-tunnel-${report}-${new Date().toISOString().slice(0, 10)}.csv`; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  return { dashboard, assets, alerts, workOrders, thresholds, telemetry, audit, loading, source, offline, syncError, lastSyncedAt, notice, openAlerts, activeOrders, refresh, tick, acknowledge, createAlertOrder, createWorkOrder, transition, updateThreshold, createReport };
});

function apiErrorMessage(cause: unknown): string {
  if (typeof cause === 'object' && cause && 'response' in cause) {
    const response = (cause as { response?: { data?: { message?: string } } }).response;
    return response?.data?.message || 'API 请求失败，请稍后重试。';
  }
  return '无法连接 Django API，请检查服务状态。';
}

function seedAssets(): Asset[] {
  const now = new Date().toISOString();
  const anchor = { latitude: 31.2304, longitude: 121.4737, locationSource: 'demo_anchor' as const };
  return [
    { id: 1, code: 'CTRL-01', hardwareCode: 'H-01', name: 'STM32F103RCT6 主控板', zone: 'CTRL', type: '控制器', status: 'normal', integrationStatus: 'verified', interface: '板载 GPIO / ADC / EXTI', capabilities: ['系统调度', '数据采集', '本地状态输出'], mesh: 'MESH_CTRL_01', position: { x: 15, y: 52, z: 0 }, ...anchor, installationNote: '实物主控板；当前固件入口与调度逻辑已验证。', lastSeenAt: now },
    { id: 2, code: 'LED-01', hardwareCode: 'H-02', name: '5V RGB 灯带', zone: 'UT-ZA', type: '执行器', status: 'unknown', integrationStatus: 'pending_verification', interface: '5V 单总线（待确认）', capabilities: ['状态灯效', '告警联动'], mesh: 'MESH_LED_01', position: { x: 24, y: 32, z: 0 }, latitude: 31.230455, longitude: 121.47376, locationSource: 'demo_anchor', installationNote: '实物已到位；供电能力和时序尚未验证，当前固件未接入。', lastSeenAt: null },
    { id: 3, code: 'DISP-01', hardwareCode: 'H-03', name: 'ST7735S TFT 显示屏', zone: 'CTRL', type: '显示模块', status: 'normal', integrationStatus: 'verified', interface: 'PB4-PB9 软件 SPI', capabilities: ['温湿度显示', '水位显示', '振动状态显示'], mesh: 'MESH_DISP_01', position: { x: 20, y: 62, z: 0 }, latitude: 31.230415, longitude: 121.473715, locationSource: 'demo_anchor', installationNote: '实物与当前固件已验证。', lastSeenAt: now },
    { id: 4, code: 'SEEP-W01', hardwareCode: 'H-04', name: '水位传感器', zone: 'UT-ZB', type: '测点', status: 'warning', integrationStatus: 'calibration_required', interface: 'PC0 / ADC1_IN10', capabilities: ['8 次采样平均', '水位趋势', '阈值告警'], mesh: 'MESH_SEEP_W01', position: { x: 58, y: 70, z: 0 }, latitude: 31.230505, longitude: 121.47391, locationSource: 'demo_anchor', installationNote: '固件已接入；阈值 1000 为临时值，需完成现场标定。', lastSeenAt: now },
    { id: 5, code: 'MOIST-01', hardwareCode: 'H-05', name: '土壤湿度传感器', zone: 'UT-ZB', type: '辅助测点', status: 'unknown', integrationStatus: 'optional', interface: '模拟量（待分配）', capabilities: ['辅助湿度趋势'], mesh: 'MESH_MOIST_01', position: { x: 64, y: 64, z: 0 }, latitude: 31.230535, longitude: 121.473955, locationSource: 'demo_anchor', installationNote: '仅作辅助展示，不用于安全联锁，当前固件未接入。', lastSeenAt: null },
    { id: 6, code: 'ENV-01', hardwareCode: 'H-06', name: 'DHT11 温湿度传感器', zone: 'UT-ZA', type: '环境测点', status: 'normal', integrationStatus: 'verified', interface: 'PA1 单总线', capabilities: ['环境温度', '环境湿度', '约 2 秒采样'], mesh: 'MESH_ENV_01', position: { x: 34, y: 44, z: 0 }, latitude: 31.230475, longitude: 121.473815, locationSource: 'demo_anchor', installationNote: '实物与当前固件已验证。', lastSeenAt: now },
    { id: 7, code: 'VIB-01', hardwareCode: 'H-07', name: 'SW-420 振动传感器', zone: 'UT-ZC', type: '安全测点', status: 'warning', integrationStatus: 'firmware_connected', interface: 'PA4 / EXTI4 双边沿', capabilities: ['振动事件', '5 秒状态锁存'], mesh: 'MESH_VIB_01', position: { x: 76, y: 44, z: 0 }, latitude: 31.23059, longitude: 121.47407, locationSource: 'demo_anchor', installationNote: '固件已接入，等待实体振动场景复核。', lastSeenAt: now },
    { id: 8, code: 'BUZZ-01', hardwareCode: 'H-08', name: '有源蜂鸣器', zone: 'CTRL', type: '声光执行器', status: 'unknown', integrationStatus: 'pending_verification', interface: 'GPIO（待分配）', capabilities: ['本地声报警'], mesh: 'MESH_BUZZ_01', position: { x: 26, y: 58, z: 0 }, latitude: 31.23043, longitude: 121.47373, locationSource: 'demo_anchor', installationNote: '实物已到位；电平与工作电压待确认，当前固件未接入。', lastSeenAt: null },
    { id: 9, code: 'RELAY-01', hardwareCode: 'H-09', name: '5V 继电器模块', zone: 'CTRL', type: '控制执行器', status: 'unknown', integrationStatus: 'pending_verification', interface: 'GPIO（待分配）', capabilities: ['隔离开关控制'], mesh: 'MESH_RELAY_01', position: { x: 31, y: 62, z: 0 }, latitude: 31.230445, longitude: 121.473745, locationSource: 'demo_anchor', installationNote: '实物已到位；触发电平待确认，当前固件未接入。', lastSeenAt: null },
    { id: 10, code: 'FAN-01', hardwareCode: 'H-10', name: '小风扇与 IN-A/IN-B 驱动', zone: 'UT-ZC', type: '通风执行器', status: 'unknown', integrationStatus: 'pending_verification', interface: '双路 GPIO（待分配）', capabilities: ['启停控制', '通风联动'], mesh: 'MESH_FAN_01', position: { x: 84, y: 34, z: 0 }, latitude: 31.23063, longitude: 121.474125, locationSource: 'demo_anchor', installationNote: '电气和反馈链路待验证，当前固件未接入。', lastSeenAt: null },
    { id: 11, code: 'BT-01', hardwareCode: 'H-11', name: 'HC-05 蓝牙模块', zone: 'CTRL', type: '可选通信模块', status: 'unknown', integrationStatus: 'optional', interface: 'UART（待分配）', capabilities: ['近场调试通信'], mesh: 'MESH_BT_01', position: { x: 36, y: 56, z: 0 }, latitude: 31.23046, longitude: 121.47376, locationSource: 'demo_anchor', installationNote: '可选模块，不属于核心数据链路，当前固件未接入。', lastSeenAt: null },
    { id: 12, code: 'PCB-01', hardwareCode: 'H-25', name: '洞洞板', zone: 'CTRL', type: '施工辅材', status: 'unknown', integrationStatus: 'non_operational', interface: '无', capabilities: ['转接与固定'], mesh: 'MESH_PCB_01', position: { x: 41, y: 63, z: 0 }, latitude: 31.230475, longitude: 121.473775, locationSource: 'demo_anchor', installationNote: '非运行资产，仅用于电气转接和实体安装。', lastSeenAt: null },
  ];
}
function seedAlerts(): Alert[] { return [{ id: 1, code: 'ALM-260826-003', assetCode: 'SEEP-W01', severity: 'warning', category: '水浸趋势', status: 'open', title: '水浸趋势异常', detail: '渗水趋势上升，需确认现场情况并安排巡检。', openedAt: '2026-08-26T00:00:00Z' }, { id: 2, code: 'ALM-260826-002', assetCode: 'FAN-01', severity: 'critical', category: '设备反馈', status: 'acknowledged', title: '风机反馈丢失', detail: '执行反馈暂未返回，正在等待工单复核。', openedAt: '2026-08-26T00:00:00Z', acknowledgedBy: '运维员' }, { id: 3, code: 'ALM-260826-001', assetCode: 'CTRL-01', severity: 'warning', category: '通信质量', status: 'open', title: '控制器通信质量波动', detail: '控制器出现短时延迟抖动，建议建立巡检工单并观察后续遥测。', openedAt: '2026-08-26T00:00:00Z' }]; }
function seedOrders(): WorkOrder[] { return [{ id: 1, code: 'WO-260826-08', sourceAlertId: 1, assetCode: 'SEEP-W01', title: '检查 UT-ZB 接水盘与水位探针', priority: 'high', status: 'open', createdAt: '2026-08-26T00:00:00Z', updatedAt: '2026-08-26T00:00:00Z', version: 1 }, { id: 2, code: 'WO-260826-06', sourceAlertId: 2, assetCode: 'FAN-01', title: '复核风机反馈与现场状态', priority: 'urgent', status: 'in_progress', assigneeName: '运维组 A', createdAt: '2026-08-26T00:00:00Z', updatedAt: '2026-08-26T00:00:00Z', version: 1 }]; }
function seedThresholds(): Threshold[] { return [{ key: 'temperature', label: '环境温度', warning: 28, alarm: 32, unit: '°C', version: 1 }, { key: 'humidity', label: '环境湿度', warning: 75, alarm: 85, unit: '%RH', version: 1 }, { key: 'water', label: '水浸趋势', warning: 20, alarm: 45, unit: '秒', version: 1 }]; }

export function csvCell(value: unknown): string {
  const text = value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  // Prefix formula-like strings so spreadsheet applications cannot execute
  // exported user-controlled values as formulas (CSV injection defense).
  const safeText = typeof value === 'string' && /^[=+\-@]/.test(text) ? `'${text}` : text;
  return /[",\r\n]/.test(safeText) ? `"${safeText.replaceAll('"', '""')}"` : safeText;
}
