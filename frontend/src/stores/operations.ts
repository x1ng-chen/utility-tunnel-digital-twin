import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { api } from '../services/api';
import type { Alert, Asset, AuditEntry, Dashboard, Telemetry, Threshold, WorkOrder } from '../types';

export const useOperationsStore = defineStore('operations', () => {
  const dashboard = ref<Dashboard>({ assets: { total: 4, online: 4 }, health: { value: 100 }, openAlerts: 2, activeWorkOrders: 2, telemetry: { id: 1, assetCode: 'FAN-01', metric: '风机转速', value: 1248, unit: 'rpm', quality: 'good', recordedAt: new Date().toISOString() } });
  const assets = ref<Asset[]>(seedAssets());
  const alerts = ref<Alert[]>(seedAlerts());
  const workOrders = ref<WorkOrder[]>(seedOrders());
  const thresholds = ref<Threshold[]>(seedThresholds());
  const telemetry = ref<Telemetry[]>([]);
  const audit = ref<AuditEntry[]>([]);
  const loading = ref(false);
  const source = ref<'demo' | 'api'>('demo');
  const notice = ref('');
  const openAlerts = computed(() => alerts.value.filter((item) => item.status === 'open').length);
  const activeOrders = computed(() => workOrders.value.filter((item) => !['completed', 'cancelled'].includes(item.status)).length);

  async function refresh(mode: 'demo' | 'api' = source.value) {
    source.value = mode;
    if (mode === 'demo') { tick(); return; }
    loading.value = true;
    try {
      const [dashboardResponse, assetsResponse, alertsResponse, ordersResponse, thresholdsResponse, telemetryResponse, auditResponse] = await Promise.all([api.dashboard(), api.assets(), api.alerts(), api.workOrders(), api.thresholds(), api.telemetry(), api.audit()]);
      dashboard.value = dashboardResponse.data; assets.value = assetsResponse.data.items; alerts.value = alertsResponse.data.items; workOrders.value = ordersResponse.data.items; thresholds.value = thresholdsResponse.data.items; telemetry.value = telemetryResponse.data.items; audit.value = auditResponse.data.items;
    } catch { notice.value = 'Django API 暂不可用，已保持本地演示数据。'; source.value = 'demo'; }
    finally { loading.value = false; }
  }

  function tick() {
    const current = dashboard.value.telemetry;
    if (current) dashboard.value.telemetry = { ...current, value: Math.max(0, Number((current.value + Math.sin(Date.now() / 800) * 7).toFixed(2))), recordedAt: new Date().toISOString() };
    dashboard.value = { ...dashboard.value, openAlerts: openAlerts.value, activeWorkOrders: activeOrders.value };
  }

  async function acknowledge(alert: Alert) { const response = source.value === 'api' ? await api.acknowledge(alert.id) : null; Object.assign(alert, response?.data ?? { status: 'acknowledged', acknowledgedAt: new Date().toISOString() }); notice.value = `${alert.code} 已确认`; }
  async function createAlertOrder(alert: Alert) { const response = source.value === 'api' ? await api.createAlertWorkOrder(alert.id) : null; const now = new Date().toISOString(); const next: WorkOrder = response?.data ?? { id: Date.now(), code: `WO-${now.slice(2, 10).replaceAll('-', '')}-${workOrders.value.length + 1}`, sourceAlertId: alert.id, assetCode: alert.assetCode || 'UNKNOWN', title: `处置 ${alert.code}：${alert.title}`, priority: alert.severity === 'critical' ? 'urgent' : 'high', status: 'open', createdAt: now, updatedAt: now, version: 1 }; workOrders.value.unshift(next); notice.value = '已创建关联工单'; }
  async function transition(order: WorkOrder, to: WorkOrder['status']) { const response = source.value === 'api' ? await api.transitionWorkOrder(order.id, to) : null; Object.assign(order, response?.data ?? { status: to, updatedAt: new Date().toISOString() }); notice.value = `${order.code} 已更新为 ${to}`; }
  async function updateThreshold(threshold: Threshold, warning: number, alarm: number) { if (warning < 0 || alarm <= warning) throw new Error('报警阈值必须大于预警阈值'); if (source.value === 'api') await api.updateThreshold(threshold.key, { warning, alarm, version: threshold.version }); threshold.warning = warning; threshold.alarm = alarm; threshold.version += 1; notice.value = `${threshold.label} 阈值已保存`; }
  async function createReport(report: string) { if (source.value === 'api') await api.report(report); notice.value = `${report} 报表已生成`; }

  return { dashboard, assets, alerts, workOrders, thresholds, telemetry, audit, loading, source, notice, openAlerts, activeOrders, refresh, tick, acknowledge, createAlertOrder, transition, updateThreshold, createReport };
});

function seedAssets(): Asset[] { return [{ id: 1, code: 'CTRL-01', name: '现场控制器', zone: 'UT-ZA', type: '控制器', status: 'normal', mesh: 'MESH_CTRL_01', position: { x: 20, y: 50, z: 0 }, lastSeenAt: new Date().toISOString() }, { id: 2, code: 'FAN-01', name: '送风机 #01', zone: 'UT-ZB', type: '执行器', status: 'normal', mesh: 'MESH_FAN_01', position: { x: 52, y: 38, z: 0 }, lastSeenAt: new Date().toISOString() }, { id: 3, code: 'SEEP-W01', name: '渗水监测点', zone: 'UT-ZB', type: '测点', status: 'warning', mesh: 'MESH_SEEP_W01', position: { x: 70, y: 68, z: 0 }, lastSeenAt: new Date().toISOString() }, { id: 4, code: 'GAS-01', name: '甲烷监测节点', zone: 'UT-ZC', type: '测点', status: 'normal', mesh: 'MESH_GAS_01', position: { x: 84, y: 44, z: 0 }, lastSeenAt: new Date().toISOString() }]; }
function seedAlerts(): Alert[] { return [{ id: 1, code: 'ALM-260826-003', assetCode: 'SEEP-W01', severity: 'warning', category: '水浸趋势', status: 'open', title: '水浸趋势异常', detail: '渗水趋势上升，需确认现场情况并安排巡检。', openedAt: '2026-08-26T00:00:00Z' }, { id: 2, code: 'ALM-260826-002', assetCode: 'FAN-01', severity: 'critical', category: '设备反馈', status: 'acknowledged', title: '风机反馈丢失', detail: '执行反馈暂未返回，正在等待工单复核。', openedAt: '2026-08-26T00:00:00Z', acknowledgedBy: '运维员' }, { id: 3, code: 'ALM-260826-001', assetCode: 'CTRL-01', severity: 'warning', category: '通信质量', status: 'open', title: '控制器通信质量波动', detail: '控制器出现短时延迟抖动，建议建立巡检工单并观察后续遥测。', openedAt: '2026-08-26T00:00:00Z' }]; }
function seedOrders(): WorkOrder[] { return [{ id: 1, code: 'WO-260826-08', sourceAlertId: 1, assetCode: 'SEEP-W01', title: '检查 UT-ZB 接水盘与水位探针', priority: 'high', status: 'open', createdAt: '2026-08-26T00:00:00Z', updatedAt: '2026-08-26T00:00:00Z', version: 1 }, { id: 2, code: 'WO-260826-06', sourceAlertId: 2, assetCode: 'FAN-01', title: '复核风机反馈与现场状态', priority: 'urgent', status: 'in_progress', assigneeName: '运维组 A', createdAt: '2026-08-26T00:00:00Z', updatedAt: '2026-08-26T00:00:00Z', version: 1 }]; }
function seedThresholds(): Threshold[] { return [{ key: 'temperature', label: '环境温度', warning: 28, alarm: 32, unit: '°C', version: 1 }, { key: 'humidity', label: '环境湿度', warning: 75, alarm: 85, unit: '%RH', version: 1 }, { key: 'water', label: '水浸趋势', warning: 20, alarm: 45, unit: '秒', version: 1 }]; }
