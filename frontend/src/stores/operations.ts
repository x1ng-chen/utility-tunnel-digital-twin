import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { api } from '../services/api';
import { useAuthStore } from './auth';
import type { Alert, Asset, AssetMutation, AuditEntry, Dashboard, HardwareBinding, SpatialFeature, Telemetry, TelemetryIngestResult, TelemetryQuery, TelemetryReading, TelemetrySummary, Threshold, WorkOrder } from '../types';

type ReportKind = 'alerts' | 'workOrders' | 'assets' | 'daily' | 'telemetry';
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

/**
 * Keep existing records alive across polling cycles. Besides reducing rendering
 * work, this prevents an operator's focused control from being replaced while
 * they are about to click it.
 */
export function reconcileRecords<T extends { id: number | string }>(current: T[], incoming: T[]): T[] {
  const existing = new Map(current.map((item) => [item.id, item]));
  return incoming.map((item) => {
    const retained = existing.get(item.id);
    if (!retained) return item;
    Object.assign(retained, item);
    return retained;
  });
}

export const useOperationsStore = defineStore('operations', () => {
  const auth = useAuthStore();
  const dashboard = ref<Dashboard>({ assets: { total: 19, online: 7 }, health: { value: 100 }, openAlerts: 2, activeWorkOrders: 2, telemetry: { id: 1, assetCode: 'ENV-01', metric: '环境温度', value: 26.4, unit: '°C', quality: 'good', recordedAt: new Date().toISOString() } });
  const assets = ref<Asset[]>(seedAssets());
  const spatialFeatures = ref<SpatialFeature[]>([]);
  const hardwareBindings = ref<HardwareBinding[]>(seedHardwareBindings());
  const alerts = ref<Alert[]>(seedAlerts());
  const workOrders = ref<WorkOrder[]>(seedOrders());
  const thresholds = ref<Threshold[]>(seedThresholds());
  const telemetry = ref<Telemetry[]>(seedTelemetry());
  const telemetryInsights = ref<Telemetry[]>([]);
  const telemetryInsightsTotal = ref(0);
  const telemetrySummary = ref<TelemetrySummary>(summarizeTelemetry([]));
  const telemetryInsightsLoading = ref(false);
  const telemetryInsightsError = ref('');
  const audit = ref<AuditEntry[]>([]);
  const loading = ref(false);
  const source = ref<'demo' | 'api'>('demo');
  const offline = ref(false);
  const syncError = ref('');
  const lastSyncedAt = ref<string | null>(null);
  const noticeText = ref('');
  const noticeRevision = ref(0);
  const notice = computed({
    get: () => noticeText.value,
    set: (message: string) => {
      noticeText.value = message;
      // Identical messages still represent separate completed operations.
      noticeRevision.value += 1;
    },
  });
  const openAlerts = computed(() => alerts.value.filter((item) => item.status === 'open').length);
  const activeOrders = computed(() => workOrders.value.filter((item) => !['completed', 'cancelled'].includes(item.status)).length);
  let liveRefreshPromise: Promise<void> | null = null;

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
      recalculateAssetSummary();
      return;
    }
    loading.value = true;
    syncError.value = '';
    try {
      const listParams = { page: 1, pageSize: 100 };
      const gisStatus = auth.user?.role === 'administrator' ? 'all' : 'published';
      const [dashboardResponse, assetsResponse, alertsResponse, ordersResponse, thresholdsResponse, telemetryResponse, auditResponse, gisResponse, bindingsResponse] = await Promise.all([api.dashboard(), api.assets(listParams), api.alerts(listParams), api.workOrders(listParams), api.thresholds(), api.telemetry(listParams), api.audit(listParams), api.gisFeatures({ status: gisStatus }), api.hardwareBindings(listParams)]);
      dashboard.value = dashboardResponse.data; assets.value = reconcileRecords(assets.value, assetsResponse.data.items); alerts.value = reconcileRecords(alerts.value, alertsResponse.data.items); workOrders.value = reconcileRecords(workOrders.value, ordersResponse.data.items); thresholds.value = thresholdsResponse.data.items; telemetry.value = reconcileRecords(telemetry.value, telemetryResponse.data.items); audit.value = reconcileRecords(audit.value, auditResponse.data.items); spatialFeatures.value = reconcileRecords(spatialFeatures.value, normalizeSpatialFeatures(gisResponse.data.features)); hardwareBindings.value = reconcileRecords(hardwareBindings.value, bindingsResponse.data.items);
      offline.value = false;
      lastSyncedAt.value = new Date().toISOString();
    } catch (cause: unknown) {
      if (responseStatus(cause) === 401) {
        expireApiSession();
      } else {
        offline.value = true;
        syncError.value = apiErrorMessage(cause);
        notice.value = '数据服务暂不可用，当前为只读离线快照。';
      }
    }
    finally { loading.value = false; }
  }

  async function refreshLive() {
    if (source.value !== 'api' || !auth.isAuthenticated) return;
    if (liveRefreshPromise) return liveRefreshPromise;
    liveRefreshPromise = (async () => {
      try {
        const listParams = { page: 1, pageSize: 100 };
        const [dashboardResponse, assetsResponse, alertsResponse, ordersResponse, telemetryResponse] = await Promise.all([
          api.dashboard(), api.assets(listParams), api.alerts(listParams), api.workOrders(listParams), api.telemetry(listParams),
        ]);
        dashboard.value = dashboardResponse.data;
        assets.value = reconcileRecords(assets.value, assetsResponse.data.items);
        alerts.value = reconcileRecords(alerts.value, alertsResponse.data.items);
        workOrders.value = reconcileRecords(workOrders.value, ordersResponse.data.items);
        telemetry.value = reconcileRecords(telemetry.value, telemetryResponse.data.items);
        offline.value = false;
        syncError.value = '';
        lastSyncedAt.value = new Date().toISOString();
      } catch (cause: unknown) {
        if (responseStatus(cause) === 401) expireApiSession();
        else {
          offline.value = true;
          syncError.value = apiErrorMessage(cause);
        }
      } finally {
        liveRefreshPromise = null;
      }
    })();
    return liveRefreshPromise;
  }

  function tick() {
    const current = dashboard.value.telemetry;
    if (current) dashboard.value.telemetry = { ...current, value: Math.max(0, Number((current.value + Math.sin(Date.now() / 800) * 7).toFixed(2))), recordedAt: new Date().toISOString() };
    dashboard.value = { ...dashboard.value, openAlerts: openAlerts.value, activeWorkOrders: activeOrders.value };
  }

  async function acknowledge(alert: Alert) {
    if (offline.value) throw new Error('数据服务当前离线，离线快照为只读状态。');
    if (source.value === 'demo' && alert.status !== 'open') throw new Error('只有待确认告警可以确认');
    const response = source.value === 'api' ? await runApiMutation(() => api.acknowledge(alert.id)) : null;
    Object.assign(alert, response?.data ?? { status: 'acknowledged', acknowledgedAt: new Date().toISOString(), acknowledgedBy: auth.user?.displayName || '演示用户' });
    if (source.value === 'demo') appendAudit('alert.acknowledged', 'alert', alert.id, { code: alert.code });
    else await syncAudit();
    notice.value = `${alert.code} 已确认`;
  }

  async function createAlertOrder(alert: Alert) {
    if (offline.value) throw new Error('数据服务当前离线，离线快照为只读状态。');
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

  async function transition(order: WorkOrder, to: WorkOrder['status'], note = '') {
    if (offline.value) throw new Error('数据服务当前离线，离线快照为只读状态。');
    if (source.value === 'demo' && !demoTransitions[order.status].includes(to)) throw new Error('无效的工单状态流转');
    if (source.value === 'demo' && to === 'completed' && auth.user?.role !== 'administrator') throw new Error('只有管理员可以完成工单');
    const previous = order.status;
    const response = source.value === 'api' ? await runApiMutation(() => api.transitionWorkOrder(order.id, to, order.version, note)) : null;
    Object.assign(order, response?.data ?? { status: to, assigneeName: to === 'assigned' ? (auth.user?.displayName || '演示运维员') : order.assigneeName, updatedAt: new Date().toISOString(), completedAt: to === 'completed' ? new Date().toISOString() : order.completedAt, version: order.version + 1 });
    if (source.value === 'demo') {
      order.timeline = [{ id: nextLocalId(), eventType: 'transition', fromStatus: previous, toStatus: to, note, actorName: auth.user?.displayName || '当前用户', createdAt: new Date().toISOString() }, ...(order.timeline || [])];
    }
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
    if (offline.value) throw new Error('数据服务当前离线，离线快照为只读状态。');
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
    if (offline.value) throw new Error('数据服务当前离线，离线快照为只读状态。');
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

  async function createAsset(input: AssetMutation) {
    assertAssetWriteAllowed();
    const response = await runApiMutation(() => api.createAsset(input as unknown as Record<string, unknown>));
    const created = response.data as Asset;
    assets.value.unshift(created);
    recalculateAssetSummary();
    await syncAudit();
    notice.value = `${created.code} 已创建`;
    return created;
  }

  async function updateAsset(asset: Asset, input: Partial<AssetMutation>) {
    assertAssetWriteAllowed();
    const response = await runApiMutation(() => api.updateAsset(asset.id, { ...input, version: asset.version }));
    const updated = response.data as Asset;
    const currentIndex = assets.value.findIndex((item) => item.id === updated.id);
    if (!updated.isActive && currentIndex >= 0) assets.value.splice(currentIndex, 1);
    else if (currentIndex >= 0) Object.assign(assets.value[currentIndex], updated);
    else if (updated.isActive) assets.value.unshift(updated);
    recalculateAssetSummary();
    await syncAudit();
    notice.value = `${updated.code} 已更新`;
    return updated;
  }

  function assertAssetWriteAllowed() {
    if (auth.user?.role !== 'administrator') throw new Error('只有管理员可以维护资产主数据。');
    if (source.value !== 'api') throw new Error('资产主数据仅允许写入受控数据服务。');
    if (offline.value) throw new Error('数据服务当前离线，离线快照为只读状态。');
  }

  function assertGisWriteAllowed() {
    if (auth.user?.role !== 'administrator') throw new Error('只有管理员可以维护 GIS 空间数据和硬件接入契约。');
    if (source.value !== 'api') throw new Error('GIS 空间数据仅允许写入受控数据服务。');
    if (offline.value) throw new Error('数据服务当前离线，离线快照为只读状态。');
  }

  async function importGisFeatures(payload: Record<string, unknown>) {
    assertGisWriteAllowed();
    const response = await runApiMutation(() => api.importGisFeatures(payload));
    spatialFeatures.value = [...normalizeSpatialFeatures(response.data.features), ...spatialFeatures.value.filter((feature) => !response.data.features.some((item: { id?: string; properties: SpatialFeature }) => Number(item.id ?? item.properties.id) === feature.id))];
    await syncAudit();
    notice.value = `已导入 ${response.data.meta.created} 个 GIS 空间对象，待审核后方可发布。`;
    return response.data;
  }

  async function updateGisFeature(feature: SpatialFeature, payload: Record<string, unknown>) {
    assertGisWriteAllowed();
    const response = await runApiMutation(() => api.updateGisFeature(feature.id, { ...payload, version: feature.version }));
    const updated = normalizeSpatialFeatures([response.data])[0];
    spatialFeatures.value = spatialFeatures.value.map((item) => item.id === updated.id ? updated : item);
    await syncAudit();
    notice.value = `${updated.code} 已更新为 ${updated.status === 'published' ? '已发布' : updated.status} 状态。`;
    return updated;
  }

  async function createHardwareBinding(payload: Record<string, unknown>) {
    assertGisWriteAllowed();
    const response = await runApiMutation(() => api.createHardwareBinding(payload));
    hardwareBindings.value.unshift(response.data as HardwareBinding);
    await syncAudit();
    notice.value = `${response.data.assetCode} 的硬件接入契约已预留。`;
    return response.data as HardwareBinding;
  }

  function recalculateAssetSummary() {
    const active = assets.value.filter((item) => item.isActive);
    dashboard.value = { ...dashboard.value, assets: { total: active.length, online: active.filter((item) => ['normal', 'warning', 'alarm'].includes(item.status)).length } };
  }

  async function createReport(report: ReportKind) {
    if (report === 'telemetry' && source.value !== 'api') throw new Error('完整历史导出需要连接数据服务。');
    if (source.value === 'api') {
      const record = await runApiMutation(() => api.report(report, requestKey('report')));
      const exported = await api.downloadReport(record.data.id);
      downloadBlob(exported.data, record.data.fileName || `utility-tunnel-${report}.csv`);
      await syncAudit();
    } else {
      downloadReport(report);
      appendAudit('report.export', 'report_export', report, { report, format: 'csv' });
    }
    notice.value = `${{ alerts: '告警', workOrders: '工单', assets: '设备', daily: '运行', telemetry: '历史遥测' }[report]}报表已生成`;
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

  async function ingestTelemetry(readings: TelemetryReading[]): Promise<TelemetryIngestResult> {
    if (source.value !== 'api') throw new Error('遥测写入仅允许使用受控数据服务。');
    if (offline.value) throw new Error('数据服务当前离线，无法写入遥测。');
    if (auth.user?.role === 'viewer') throw new Error('当前角色没有遥测写入权限。');
    const response = await runApiMutation(() => api.ingestTelemetry(readings as unknown as Record<string, unknown>[]));
    await refresh('api');
    notice.value = `遥测批次已处理：新增 ${response.data.created}，重复 ${response.data.duplicates}`;
    return response.data as TelemetryIngestResult;
  }

  let telemetryRequestSequence = 0;
  async function loadTelemetryInsights(query: TelemetryQuery = {}, page = 1) {
    const requestSequence = ++telemetryRequestSequence;
    telemetryInsightsLoading.value = true;
    telemetryInsightsError.value = '';
    try {
      if (!Number.isSafeInteger(page) || page < 1) throw new Error('历史数据页码无效。');
      const recordedFrom = query.recordedFrom ? new Date(query.recordedFrom).getTime() : null;
      const recordedTo = query.recordedTo ? new Date(query.recordedTo).getTime() : null;
      if ((recordedFrom != null && !Number.isFinite(recordedFrom)) || (recordedTo != null && !Number.isFinite(recordedTo))) throw new Error('采集时间格式无效。');
      if (recordedFrom != null && recordedTo != null && recordedFrom > recordedTo) throw new Error('开始时间不能晚于结束时间。');
      if (source.value === 'demo') {
        const filtered = telemetry.value.filter((item) => telemetryMatchesQuery(item, query)).sort((left, right) => new Date(right.recordedAt).getTime() - new Date(left.recordedAt).getTime() || right.id - left.id);
        telemetryInsights.value = filtered.slice((page - 1) * 100, page * 100);
        telemetryInsightsTotal.value = filtered.length;
        telemetrySummary.value = summarizeTelemetry(filtered);
        return;
      }
      const params = Object.fromEntries(Object.entries(query).filter(([, value]) => value)) as Record<string, string>;
      const [historyResponse, summaryResponse] = await Promise.all([
        api.telemetry({ ...params, page, pageSize: 100 }),
        api.telemetrySummary(params),
      ]);
      if (requestSequence !== telemetryRequestSequence) return false;
      telemetryInsights.value = historyResponse.data.items;
      telemetryInsightsTotal.value = historyResponse.data.total;
      telemetrySummary.value = summaryResponse.data;
    } catch (cause: unknown) {
      if (requestSequence !== telemetryRequestSequence) return false;
      const status = responseStatus(cause);
      if (status === 401) expireApiSession();
      telemetryInsightsError.value = status != null ? apiErrorMessage(cause) : cause instanceof Error ? cause.message : '遥测查询失败，请稍后重试。';
      throw new Error(telemetryInsightsError.value);
    } finally {
      if (requestSequence === telemetryRequestSequence) telemetryInsightsLoading.value = false;
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

  function downloadBlob(blob: Blob, fileName: string) {
    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = url; link.download = fileName; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  return { dashboard, assets, spatialFeatures, hardwareBindings, alerts, workOrders, thresholds, telemetry, telemetryInsights, telemetryInsightsTotal, telemetrySummary, telemetryInsightsLoading, telemetryInsightsError, audit, loading, source, offline, syncError, lastSyncedAt, notice, noticeRevision, openAlerts, activeOrders, refresh, refreshLive, tick, acknowledge, createAlertOrder, createWorkOrder, createAsset, updateAsset, importGisFeatures, updateGisFeature, createHardwareBinding, transition, updateThreshold, createReport, ingestTelemetry, loadTelemetryInsights };
});

function telemetryMatchesQuery(item: Telemetry, query: TelemetryQuery): boolean {
  const recordedAt = new Date(item.recordedAt).getTime();
  return (!query.assetCode || item.assetCode === query.assetCode)
    && (!query.metricKey || item.metricKey === query.metricKey)
    && (!query.quality || item.quality === query.quality)
    && (!query.recordedFrom || recordedAt >= new Date(query.recordedFrom).getTime())
    && (!query.recordedTo || recordedAt <= new Date(query.recordedTo).getTime());
}

function normalizeSpatialFeatures(features: { id?: string; geometry: SpatialFeature['geometry']; properties: SpatialFeature }[]): SpatialFeature[] {
  return features.map((feature) => ({ ...feature.properties, id: Number(feature.id ?? feature.properties.id), geometry: feature.geometry }));
}

export function summarizeTelemetry(items: Telemetry[]): TelemetrySummary {
  const qualityCounts: TelemetrySummary['qualityCounts'] = { good: 0, suspect: 0, bad: 0, missing: 0 };
  for (const item of items) qualityCounts[item.quality] += 1;
  if (!items.length) return { sampleCount: 0, comparable: true, minimum: null, maximum: null, average: null, startedAt: null, endedAt: null, qualityCounts, latest: null };
  const ordered = [...items].sort((left, right) => new Date(right.recordedAt).getTime() - new Date(left.recordedAt).getTime() || right.id - left.id);
  const comparable = new Set(items.map((item) => `${item.metricKey || ''}\u0000${item.unit}`)).size <= 1;
  const values = items.map((item) => item.value);
  return {
    sampleCount: items.length,
    comparable,
    minimum: comparable ? Math.min(...values) : null,
    maximum: comparable ? Math.max(...values) : null,
    average: comparable ? values.reduce((total, value) => total + value, 0) / values.length : null,
    startedAt: ordered.at(-1)!.recordedAt,
    endedAt: ordered[0].recordedAt,
    qualityCounts,
    latest: ordered[0],
  };
}

function apiErrorMessage(cause: unknown): string {
  if (typeof cause === 'object' && cause && 'response' in cause) {
    const response = (cause as { response?: { data?: { message?: string } } }).response;
    return response?.data?.message || 'API 请求失败，请稍后重试。';
  }
  return '无法连接数据服务，请检查服务状态。';
}

function seedAssets(): Asset[] {
  const now = new Date().toISOString();
  const anchor = { latitude: 31.2304, longitude: 121.4737, locationSource: 'demo_anchor' as const };
  return [
    { id: 1, code: 'CTRL-01', hardwareCode: 'H-01', name: 'STM32F103RCT6 主控板', zone: 'CTRL', type: '控制器', status: 'normal', integrationStatus: 'verified', interface: '板载 GPIO / ADC / EXTI', capabilities: ['系统调度', '数据采集', '本地状态输出'], mesh: 'CTRL-01', position: { x: 15, y: 52, z: 0 }, ...anchor, installationNote: '实物主控板；当前固件入口与调度逻辑已验证。', lastSeenAt: now },
    { id: 2, code: 'LED-01', hardwareCode: 'H-02', name: '5V RGB 灯带', zone: 'UT-ZA', type: '执行器', status: 'unknown', integrationStatus: 'pending_verification', interface: '5V 单总线（待确认）', capabilities: ['状态灯效', '告警联动'], mesh: 'MESH_LED_01', position: { x: 24, y: 32, z: 0 }, latitude: 31.230455, longitude: 121.47376, locationSource: 'demo_anchor', installationNote: '实物已到位；供电能力和时序尚未验证，当前固件未接入。', lastSeenAt: null },
    { id: 3, code: 'DISP-01', hardwareCode: 'H-03', name: 'ST7735S TFT 显示屏', zone: 'CTRL', type: '显示模块', status: 'unknown', integrationStatus: 'pending_verification', interface: 'Node A SPI3 PB3/PB5+PC4-PC7；Node B SPI1 PA5/PA7+PB6-PB9', capabilities: ['Node A 状态副屏', 'Node B 菜单主屏'], mesh: 'MESH_DISP_01', position: { x: 20, y: 62, z: 0 }, latitude: 31.230415, longitude: 121.473715, locationSource: 'demo_anchor', installationNote: '由 PB4-PB9 软件 SPI 单屏方案改为双屏硬件 SPI；实物接线与显示均未验证，状态以 docs/acceptance/双屏菜单实机验收.md 为准。', lastSeenAt: null },
    { id: 4, code: 'SEEP-W01', hardwareCode: 'H-04', name: '水位传感器', zone: 'UT-ZB', type: '测点', status: 'warning', integrationStatus: 'calibration_required', interface: 'PC0 / ADC1_IN10', capabilities: ['8 次采样平均', '水位趋势', '阈值告警'], mesh: 'MESH_SEEP_W01', position: { x: 58, y: 70, z: 0 }, latitude: 31.230505, longitude: 121.47391, locationSource: 'demo_anchor', installationNote: '固件已接入；阈值 1000 为临时值，需完成现场标定。', lastSeenAt: now },
    { id: 5, code: 'MOIST-01', hardwareCode: 'H-05', name: '土壤湿度传感器', zone: 'UT-ZB', type: '辅助测点', status: 'unknown', integrationStatus: 'optional', interface: '模拟量（待分配）', capabilities: ['辅助湿度趋势'], mesh: 'MESH_MOIST_01', position: { x: 64, y: 64, z: 0 }, latitude: 31.230535, longitude: 121.473955, locationSource: 'demo_anchor', installationNote: '仅作辅助展示，不用于安全联锁，当前固件未接入。', lastSeenAt: null },
    { id: 6, code: 'ENV-01', hardwareCode: 'H-06', name: 'DHT11 温湿度传感器', zone: 'UT-ZA', type: '环境测点', status: 'normal', integrationStatus: 'verified', interface: 'PA1 单总线', capabilities: ['环境温度', '环境湿度', '约 2 秒采样'], mesh: 'ENV-01', position: { x: 34, y: 44, z: 0 }, latitude: 31.230475, longitude: 121.473815, locationSource: 'demo_anchor', installationNote: '实物与当前固件已验证。', lastSeenAt: now },
    { id: 7, code: 'VIB-01', hardwareCode: 'H-07', name: 'SW-420 振动传感器', zone: 'UT-ZC', type: '安全测点', status: 'warning', integrationStatus: 'firmware_connected', interface: 'PA4 / EXTI4 双边沿', capabilities: ['振动事件', '5 秒状态锁存'], mesh: 'MESH_VIB_01', position: { x: 76, y: 44, z: 0 }, latitude: 31.23059, longitude: 121.47407, locationSource: 'demo_anchor', installationNote: '固件已接入，等待实体振动场景复核。', lastSeenAt: now },
    { id: 8, code: 'BUZZ-01', hardwareCode: 'H-08', name: '有源蜂鸣器', zone: 'CTRL', type: '声光执行器', status: 'unknown', integrationStatus: 'pending_verification', interface: 'GPIO（待分配）', capabilities: ['本地声报警'], mesh: 'MESH_BUZZ_01', position: { x: 26, y: 58, z: 0 }, latitude: 31.23043, longitude: 121.47373, locationSource: 'demo_anchor', installationNote: '实物已到位；电平与工作电压待确认，当前固件未接入。', lastSeenAt: null },
    { id: 9, code: 'RELAY-01', hardwareCode: 'H-09', name: '5V 继电器模块', zone: 'CTRL', type: '控制执行器', status: 'unknown', integrationStatus: 'pending_verification', interface: 'GPIO（待分配）', capabilities: ['隔离开关控制'], mesh: 'MESH_RELAY_01', position: { x: 31, y: 62, z: 0 }, latitude: 31.230445, longitude: 121.473745, locationSource: 'demo_anchor', installationNote: '实物已到位；触发电平待确认，当前固件未接入。', lastSeenAt: null },
    { id: 10, code: 'FAN-01', hardwareCode: 'H-10', name: '小风扇与 IN-A/IN-B 驱动', zone: 'UT-ZC', type: '通风执行器', status: 'unknown', integrationStatus: 'pending_verification', interface: '双路 GPIO（待分配）', capabilities: ['启停控制', '通风联动'], mesh: 'FAN-01', position: { x: 84, y: 34, z: 0 }, latitude: 31.23063, longitude: 121.474125, locationSource: 'demo_anchor', installationNote: '电气和反馈链路待验证，当前固件未接入。', lastSeenAt: null },
    { id: 19, code: 'FAN-02', hardwareCode: 'H-12-02', name: '排风风机', zone: 'UT-ZC', type: '通风执行器', status: 'normal', integrationStatus: 'firmware_connected', interface: 'PB10/PB11 INA226；PA7 TACH；PB9 PWM', capabilities: ['启停控制', 'PWM调速', '转速反馈', '电流检测'], mesh: 'FAN-02', position: { x: 88, y: 34, z: 0 }, latitude: 31.230632, longitude: 121.474128, locationSource: 'demo_anchor', installationNote: '12V 四线排风风机；与 FAN-01 共用 PA1 继电器总使能，独立 INA226、TACH 与 PWM 已完成台架验证。', lastSeenAt: now },
    { id: 11, code: 'NET-01', hardwareCode: 'H-11', name: 'ESP8266-01S 通信模块', zone: 'CTRL', type: '无线通信模块', status: 'normal', integrationStatus: 'verified', interface: 'USART2 9600 bit/s / MQTT', capabilities: ['Wi-Fi 联网', 'MQTT 上报', '断线重连'], mesh: 'MESH_ESP01S_01', position: { x: 36, y: 56, z: 0 }, latitude: 31.23046, longitude: 121.47376, locationSource: 'demo_anchor', installationNote: '唯一无线通信链路；已完成 STM32 真机连接与 IoTDA 数据上行。', lastSeenAt: now },
    { id: 12, code: 'PCB-01', hardwareCode: 'H-25', name: '洞洞板', zone: 'CTRL', type: '施工辅材', status: 'unknown', integrationStatus: 'non_operational', interface: '无', capabilities: ['转接与固定'], mesh: 'MESH_PCB_01', position: { x: 41, y: 63, z: 0 }, latitude: 31.230475, longitude: 121.473775, locationSource: 'demo_anchor', installationNote: '非运行资产，仅用于电气转接和实体安装。', lastSeenAt: null },
    { id: 14, code: 'LEVEL-L01', name: '液位1 · 排水段', zone: 'UT-ZB', type: '管道液位测点', status: 'unknown', integrationStatus: 'pending_verification', interface: '待分配', capabilities: ['排水段独立液位检测'], mesh: 'MESH_V12-FSIR02_L01_PROBE', position: { x: 52, y: 82, z: 0 }, latitude: null, longitude: null, locationSource: 'unassigned', installationNote: '二维位置仅为示意锚点，非测绘坐标。FS-IR02 排水段独立测点；未接入、未标定，不复用 SEEP-W01 遥测。', lastSeenAt: null },
    { id: 15, code: 'LEVEL-L02', name: '液位2 · 吸水段', zone: 'UT-ZB', type: '管道液位测点', status: 'unknown', integrationStatus: 'pending_verification', interface: '待分配', capabilities: ['吸水段独立液位检测'], mesh: 'MESH_V12-FSIR02_L02_PROBE', position: { x: 72, y: 74, z: 0 }, latitude: null, longitude: null, locationSource: 'unassigned', installationNote: '二维位置仅为示意锚点，非测绘坐标。FS-IR02 吸水段独立测点；未接入、未标定，不复用 SEEP-W01 遥测。', lastSeenAt: null },
    { id: 16, code: 'LEVEL-L03', name: '液位3 · 泵入口', zone: 'UT-ZB', type: '管道液位测点', status: 'unknown', integrationStatus: 'pending_verification', interface: '待分配', capabilities: ['泵入口独立液位检测'], mesh: 'MESH_V12-FSIR02_L03_PROBE', position: { x: 80, y: 82, z: 0 }, latitude: null, longitude: null, locationSource: 'unassigned', installationNote: '二维位置仅为示意锚点，非测绘坐标。FS-IR02 泵入口独立测点；未接入、未标定，不复用 SEEP-W01 遥测。', lastSeenAt: null },
    { id: 17, code: 'LEVEL-L04', name: '液位4 · 阀后段', zone: 'UT-ZB', type: '管道液位测点', status: 'unknown', integrationStatus: 'pending_verification', interface: '待分配', capabilities: ['阀后段独立液位检测'], mesh: 'MESH_V12-FSIR02_L04_PROBE', position: { x: 89, y: 67, z: 0 }, latitude: null, longitude: null, locationSource: 'unassigned', installationNote: '二维位置仅为示意锚点，非测绘坐标。FS-IR02 阀后段独立测点；未接入、未标定，不复用 SEEP-W01 遥测。', lastSeenAt: null },
    { id: 18, code: 'LEVEL-L05', name: '液位5 · 回水段', zone: 'UT-ZB', type: '管道液位测点', status: 'unknown', integrationStatus: 'pending_verification', interface: '待分配', capabilities: ['回水段独立液位检测'], mesh: 'MESH_V12-FSIR02_L05_PROBE', position: { x: 60, y: 54, z: 0 }, latitude: null, longitude: null, locationSource: 'unassigned', installationNote: '二维位置仅为示意锚点，非测绘坐标。FS-IR02 回水段独立测点；未接入、未标定，不复用 SEEP-W01 遥测。', lastSeenAt: null },
    { id: 13, code: 'GAS-01', hardwareCode: 'H-12', name: '气体与火焰监测节点', zone: 'UT-ZC', type: '环境测点', status: 'normal', integrationStatus: 'firmware_connected', interface: 'PC1氧气 / PC2甲烷 / PB12烟雾 / PB14火焰', capabilities: ['氧气检测', '甲烷检测', '烟雾告警', '火焰告警'], mesh: 'MESH_GAS_SAMPLE_MANIFOLD_01', position: { x: 80, y: 45, z: 0 }, latitude: 31.23061, longitude: 121.474095, locationSource: 'demo_anchor', installationNote: 'PB14连接3.3V供电的LM393红外火焰模块DO，低电平立即触发，火焰消失后保持告警12秒。', lastSeenAt: now },
  ].map((asset) => ({ ...asset, isActive: true, version: 1 })) as Asset[];
}
function seedHardwareBindings(): HardwareBinding[] {
  return seedAssets().map(({ code: assetCode }, index) => ({
    id: index + 1,
    assetCode,
    protocol: 'mqtt',
    deviceIdentifier: `ut-demo-${assetCode.toLowerCase()}`,
    endpoint: `ut/v1/${assetCode.toLowerCase()}/telemetry`,
    expectedIntervalSeconds: 60,
    status: 'reserved',
    connectivity: 'awaiting_data',
    lastHeartbeatAt: null,
    heartbeatAgeSeconds: null,
    heartbeatDueAt: null,
    version: 1,
  }));
}
function seedAlerts(): Alert[] { return [{ id: 1, code: 'ALM-260826-003', assetCode: 'SEEP-W01', severity: 'warning', category: '水浸趋势', status: 'open', title: '水浸趋势异常', detail: '渗水趋势上升，需确认现场情况并安排巡检。', openedAt: '2026-08-26T00:00:00Z' }, { id: 2, code: 'ALM-260826-002', assetCode: 'FAN-01', severity: 'critical', category: '设备反馈', status: 'acknowledged', title: '风机反馈丢失', detail: '执行反馈暂未返回，正在等待工单复核。', openedAt: '2026-08-26T00:00:00Z', acknowledgedBy: '运维员' }, { id: 3, code: 'ALM-260826-001', assetCode: 'CTRL-01', severity: 'warning', category: '通信质量', status: 'open', title: '控制器通信质量波动', detail: '控制器出现短时延迟抖动，建议建立巡检工单并观察后续遥测。', openedAt: '2026-08-26T00:00:00Z' }]; }
function seedOrders(): WorkOrder[] { return [{ id: 1, code: 'WO-260826-08', sourceAlertId: 1, assetCode: 'SEEP-W01', title: '检查 UT-ZB 接水盘与水位探针', priority: 'high', status: 'open', createdAt: '2026-08-26T00:00:00Z', updatedAt: '2026-08-26T00:00:00Z', version: 1 }, { id: 2, code: 'WO-260826-06', sourceAlertId: 2, assetCode: 'FAN-01', title: '复核风机反馈与现场状态', priority: 'urgent', status: 'in_progress', assigneeName: '运维组 A', createdAt: '2026-08-26T00:00:00Z', updatedAt: '2026-08-26T00:00:00Z', version: 1 }]; }
function seedThresholds(): Threshold[] { return [{ key: 'temperature', label: '环境温度', warning: 28, alarm: 32, unit: '°C', version: 1 }, { key: 'humidity', label: '环境湿度', warning: 75, alarm: 85, unit: '%RH', version: 1 }, { key: 'water', label: '水浸趋势', warning: 20, alarm: 45, unit: '秒', version: 1 }, { key: 'smoke.alarm', label: '烟雾告警', warning: 0.5, alarm: 0.9, unit: 'bool', version: 1 }, { key: 'flame.alarm', label: '火焰告警', warning: 0.5, alarm: 0.9, unit: 'bool', version: 1 }, { key: 'level.detected', label: '液位检测', warning: 0.5, alarm: 0.9, unit: 'bool', version: 1 }]; }
function seedTelemetry(): Telemetry[] {
  const now = Date.now();
  return Array.from({ length: 24 }, (_, index) => ({ id: index + 1, eventId: `demo:temperature:${index + 1}`, assetCode: 'ENV-01', metricKey: 'temperature', metric: '环境温度', value: Number((25.4 + Math.sin(index / 3) * 3.2).toFixed(2)), unit: '°C', quality: index === 7 ? 'suspect' : 'good', recordedAt: new Date(now - index * 5 * 60_000).toISOString(), ingestedAt: new Date(now - index * 5 * 60_000 + 500).toISOString() }));
}

export function csvCell(value: unknown): string {
  const text = value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  // Prefix formula-like strings so spreadsheet applications cannot execute
  // exported user-controlled values as formulas (CSV injection defense).
  const safeText = typeof value === 'string' && /^[=+\-@]/.test(text) ? `'${text}` : text;
  return /[",\r\n]/.test(safeText) ? `"${safeText.replaceAll('"', '""')}"` : safeText;
}
