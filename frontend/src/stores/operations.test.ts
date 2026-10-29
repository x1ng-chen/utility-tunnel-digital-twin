// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from './auth';
import { reconcileRecords, summarizeTelemetry, upsertRealtimeRecord, useOperationsStore } from './operations';
import * as realtimeService from '../services/realtime';
import { api } from '../services/api';

describe('operations store', () => {
  beforeEach(() => { window.sessionStorage.clear(); setActivePinia(createPinia()); });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); window.sessionStorage.clear(); });

  function mockEmptyApiSnapshot() {
    vi.spyOn(api, 'dashboard').mockResolvedValue({ data: { assets: { total: 0, online: 0 }, health: { value: 0 }, openAlerts: 0, activeWorkOrders: 0, telemetry: null } } as never);
    vi.spyOn(api, 'assets').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'alerts').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'workOrders').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'thresholds').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'telemetry').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'audit').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'gisFeatures').mockResolvedValue({ data: { features: [] } } as never);
    vi.spyOn(api, 'hardwareBindings').mockResolvedValue({ data: { items: [] } } as never);
  }

  it('upserts a live delta without dropping unrelated records or replacing identity', () => {
    const retained = { id: 1, status: 'open' };
    const unrelated = { id: 2, status: 'open' };
    const current = [retained, unrelated];
    const updated = upsertRealtimeRecord(current, { id: 1, status: 'resolved' });
    expect(updated).toBe(current);
    expect(updated[0]).toBe(retained);
    expect(updated[1]).toBe(unrelated);
    expect(retained.status).toBe('resolved');
    const inserted = upsertRealtimeRecord(updated, { id: 3, status: 'open' });
    expect(inserted.map(item => item.id)).toEqual([3, 1, 2]);
    expect(inserted[1]).toBe(retained);
    expect(inserted[2]).toBe(unrelated);
    expect(upsertRealtimeRecord(inserted, { id: 4, status: 'open' }, 3).map(item => item.id)).toEqual([4, 3, 1]);
  });

  it('reapplies a push received during a stale REST live snapshot', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'viewer', 'demo');
    const store = useOperationsStore();
    store.source = 'api';
    vi.stubGlobal('window', { sessionStorage: { getItem: () => 'unit-test-token' } });
    let options!: realtimeService.RealtimeClientOptions;
    vi.spyOn(realtimeService, 'createRealtimeClient').mockImplementation((value) => {
      options = value;
      return { connect: vi.fn(), disconnect: vi.fn(), getState: () => 'idle', getLastSeq: () => 0 };
    });
    store.startRealtime();
    const old = { ...store.alerts[0]! };
    const other = { ...store.alerts[1]! };
    let resolveAlerts!: (value: never) => void;
    vi.spyOn(api, 'dashboard').mockResolvedValue({ data: store.dashboard } as never);
    vi.spyOn(api, 'assets').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'alerts').mockImplementation(() => new Promise(resolve => { resolveAlerts = resolve; }));
    vi.spyOn(api, 'workOrders').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'telemetry').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'hardwareBindings').mockResolvedValue({ data: { items: [] } } as never);
    const pending = store.refreshLive();
    await options.onEvent!({ epoch: 'test', seq: 1, type: 'alert', entityId: old.id, version: '2', updatedAt: null, payload: { ...old, status: 'resolved' } });
    resolveAlerts({ data: { items: [old, other] } } as never);
    await pending;
    expect(store.alerts.find(item => item.id === old.id)?.status).toBe('resolved');
    expect(store.alerts.some(item => item.id === other.id)).toBe(true);
    store.stopRealtime();
  });

  it('keeps independent fan observations and refreshes their actual heartbeats on live polling', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'viewer', 'demo');
    const store = useOperationsStore();
    store.source = 'api';
    mockEmptyApiSnapshot();
    const recordedAt = '2026-10-29T02:00:00Z';
    const general = { id: 801, assetCode: 'FLAME-05', metricKey: 'flame.alarm', value: 0, unit: 'bool', quality: 'good', recordedAt };
    const fan1 = { id: 802, assetCode: 'FAN-01', metricKey: 'rotational.speed', value: 1200, unit: 'rpm', quality: 'good', recordedAt };
    const fan2 = { id: 803, assetCode: 'FAN-02', metricKey: 'supply.voltage', value: 12, unit: 'V', quality: 'good', recordedAt };
    vi.mocked(api.telemetry).mockImplementation((params) => Promise.resolve({ data: { items: params?.assetCode === 'FAN-01' ? [fan1] : params?.assetCode === 'FAN-02' ? [fan2] : [general] } }) as never);
    vi.mocked(api.hardwareBindings).mockResolvedValue({ data: { items: [{ id: 80, assetCode: 'FAN-01', lastHeartbeatAt: recordedAt }] } } as never);
    await store.refreshLive();
    expect(store.telemetry.map(r => r.id).sort()).toEqual([801, 802, 803]);
    expect(store.hardwareBindings[0].lastHeartbeatAt).toBe(recordedAt);
    expect(vi.mocked(api.telemetry)).toHaveBeenCalledWith({ page: 1, pageSize: 30, assetCode: 'FAN-01' });
    expect(vi.mocked(api.telemetry)).toHaveBeenCalledWith({ page: 1, pageSize: 30, assetCode: 'FAN-02' });
  });

  it('treats repeated identical notices as new feedback events', () => {
    const store = useOperationsStore();
    store.notice = '阈值已保存';
    const first = store.noticeRevision;
    store.notice = '阈值已保存';
    expect(store.notice).toBe('阈值已保存');
    expect(store.noticeRevision).toBe(first + 1);
    store.notice = '';
    expect(store.notice).toBe('');
  });

  it('starts with the connected demo model', () => {
    const store = useOperationsStore();
    expect(store.assets).toHaveLength(19);
    expect(store.openAlerts).toBe(2);
    expect(store.activeOrders).toBe(2);
  });

  it('starts a restored API session with pending empty state rather than demo claims', () => {
    window.sessionStorage.setItem('ut-vue-user', JSON.stringify({ id: 42, email: 'operator@example.test', displayName: '测试运维员', role: 'operator' }));
    window.sessionStorage.setItem('ut-session-mode', 'api');
    window.sessionStorage.setItem('ut-django-token', 'unit-test-token');
    const store = useOperationsStore();
    expect(store.source).toBe('api');
    expect(store.loading).toBe(true);
    expect(store.dashboard).toMatchObject({ assets: { total: 0, online: 0 }, openAlerts: 0, activeWorkOrders: 0, telemetry: null });
    expect(store.assets).toEqual([]);
    expect(store.alerts).toEqual([]);
    expect(store.workOrders).toEqual([]);
    expect(store.telemetry).toEqual([]);
    expect(store.thresholds).toEqual([]);
    expect(store.hardwareBindings).toEqual([]);
    expect(store.lastSyncedAt).toBeNull();
  });

  it('removes synthetic records before an API snapshot settles and keeps them absent on failure', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'operator', 'demo');
    const store = useOperationsStore();
    expect(store.assets).toHaveLength(19);
    await store.loadTelemetryInsights();
    expect(store.telemetryInsights.length).toBeGreaterThan(0);
    mockEmptyApiSnapshot();
    let rejectSnapshot!: (cause: Error) => void;
    vi.mocked(api.dashboard).mockImplementationOnce(() => new Promise((_, reject) => { rejectSnapshot = reject; }));
    const pending = store.refresh('api');
    expect(store.source).toBe('api');
    expect(store.loading).toBe(true);
    expect(store.assets).toEqual([]);
    expect(store.alerts).toEqual([]);
    expect(store.workOrders).toEqual([]);
    expect(store.telemetry).toEqual([]);
    expect(store.telemetryInsights).toEqual([]);
    expect(store.telemetrySummary.sampleCount).toBe(0);
    expect(store.dashboard.telemetry).toBeNull();
    expect(store.lastSyncedAt).toBeNull();
    rejectSnapshot(new Error('test API unavailable'));
    await pending;
    expect(store.offline).toBe(true);
    expect(store.assets).toEqual([]);
    expect(store.openAlerts).toBe(0);
    expect(store.activeOrders).toBe(0);
    expect(store.dashboard.assets.total).toBe(0);
  });

  it('retains the last genuine API snapshot when a later refresh fails', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'operator', 'demo');
    const store = useOperationsStore();
    const actualAsset = { ...store.assets[0], id: 501, code: 'ACTUAL-CTRL-01', name: 'API测试控制器' };
    const actualReading = { ...store.telemetry[0], id: 601, assetCode: actualAsset.code, value: 33 };
    mockEmptyApiSnapshot();
    vi.mocked(api.assets).mockResolvedValue({ data: { items: [actualAsset] } } as never);
    vi.mocked(api.telemetry).mockResolvedValue({ data: { items: [actualReading] } } as never);
    vi.mocked(api.dashboard).mockResolvedValue({ data: { assets: { total: 1, online: 1 }, health: { value: 100 }, openAlerts: 0, activeWorkOrders: 0, telemetry: actualReading } } as never);
    await store.refresh('api');
    const retainedAsset = store.assets[0];
    const savedSync = store.lastSyncedAt;
    vi.mocked(api.dashboard).mockRejectedValueOnce(new Error('test connection lost'));
    await store.refresh('api');
    expect(store.offline).toBe(true);
    expect(store.source).toBe('api');
    expect(store.assets).toHaveLength(1);
    expect(store.assets[0]).toBe(retainedAsset);
    expect(store.assets[0].code).toBe(actualAsset.code);
    expect(store.telemetry[0].value).toBe(33);
    expect(store.lastSyncedAt).toBe(savedSync);
    expect(store.dashboard.assets.total).toBe(1);
    await store.refresh('demo');
    expect(store.source).toBe('demo');
    expect(store.assets).toHaveLength(19);
    expect(store.assets.some(item => item.code === actualAsset.code)).toBe(false);
    expect(store.openAlerts).toBe(2);
  });

  it('keeps five pipe stations unconnected and independent of the seep sensor', () => {
    const store = useOperationsStore();
    const levels = store.assets.filter(a => a.code.startsWith('LEVEL-L'));
    expect(levels).toHaveLength(5);
    expect(new Set(levels.map(a => a.mesh)).size).toBe(5);
    expect(new Set(levels.map(a => `${a.position.x},${a.position.y}`)).size).toBe(5);
    for (const asset of levels) {
      expect(asset.status).toBe('unknown');
      expect(asset.integrationStatus).toBe('pending_verification');
      expect(asset.lastSeenAt).toBeNull();
      expect(asset.locationSource).toBe('unassigned');
      expect(store.telemetry.some(t => t.assetCode === asset.code)).toBe(false);
      const binding = store.hardwareBindings.find(b => b.assetCode === asset.code)!;
      expect(binding.status).toBe('reserved');
      expect(binding.lastHeartbeatAt).toBeNull();
    }
    expect(store.assets.some(a => a.code === 'BT-01')).toBe(false);
    expect(store.assets.some(a => a.code === 'NET-01')).toBe(true);
  });

  it('preserves record identity while applying live polling updates', () => {
    const retained = { id: 1, status: 'open', title: '原工单' };
    const result = reconcileRecords([retained], [{ id: 1, status: 'assigned', title: '更新工单' }, { id: 2, status: 'open', title: '新增工单' }]);

    expect(result[0]).toBe(retained);
    expect(retained).toEqual({ id: 1, status: 'assigned', title: '更新工单' });
    expect(result[1]).toEqual({ id: 2, status: 'open', title: '新增工单' });
  });

  it('rejects invalid threshold ranges and records valid changes', async () => {
    const store = useOperationsStore();
    const threshold = store.thresholds[0];
    await expect(store.updateThreshold(threshold, 40, 30)).rejects.toThrow('报警阈值必须大于预警阈值');
    await expect(store.updateThreshold(threshold, Number.NaN, 40)).rejects.toThrow('报警阈值必须大于预警阈值');
    await store.updateThreshold(threshold, 30, 36);
    expect(threshold.warning).toBe(30);
    expect(threshold.alarm).toBe(36);
    expect(threshold.version).toBe(2);
  });

  it('keeps the demo alert, work-order and audit models in sync', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'administrator', 'demo');
    const store = useOperationsStore();
    const alert = store.alerts.find((item) => item.id === 3)!;
    await store.acknowledge(alert);
    const order = await store.createAlertOrder(alert);
    expect(order).toBeDefined();
    await store.transition(order!, 'assigned');
    await store.transition(order!, 'in_progress');
    await store.transition(order!, 'pending_review');
    await store.transition(order!, 'completed');
    expect(alert.status).toBe('resolved');
    expect(store.assets.find((item) => item.code === alert.assetCode)?.status).toBe('normal');
    expect(store.audit.map((entry) => entry.action)).toEqual(expect.arrayContaining(['alert.acknowledged', 'work_order.created_from_alert', 'work_order.transitioned']));
  });

  it('creates a manual work order and records its linked asset', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'operator', 'demo');
    const store = useOperationsStore();
    const order = await store.createWorkOrder({ assetCode: 'ENV-01', title: '复核温湿度监测节点', description: '检查最近一次遥测质量。', priority: 'high' });
    expect(order.status).toBe('open');
    expect(order.assetCode).toBe('ENV-01');
    expect(store.workOrders[0].code).toBe(order.code);
    expect(store.audit[0].action).toBe('work_order.created_manual');
  });

  it('keeps a failed API snapshot read-only until the user reconnects', async () => {
    const store = useOperationsStore();
    store.offline = true;
    await expect(store.createWorkOrder({ assetCode: 'ENV-01', title: '不应写入', priority: 'normal' })).rejects.toThrow('只读状态');
  });

  it('clears the session when an API refresh returns 401', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'operator', 'demo');
    const store = useOperationsStore();
    mockEmptyApiSnapshot();
    vi.mocked(api.dashboard).mockRejectedValue({ response: { status: 401 } });

    await store.refresh('api');

    expect(auth.isAuthenticated).toBe(false);
    expect(store.syncError).toBe('登录状态已过期，请重新登录。');
    expect(store.offline).toBe(true);
  });

  it('clears the session when an API mutation returns 401', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'operator', 'demo');
    const store = useOperationsStore();
    store.source = 'api';
    vi.spyOn(api, 'acknowledge').mockRejectedValue({ response: { status: 401 } } as never);

    await expect(store.acknowledge(store.alerts[0])).rejects.toBeDefined();

    expect(auth.isAuthenticated).toBe(false);
    expect(store.offline).toBe(true);
    expect(store.syncError).toBe('登录状态已过期，请重新登录。');
  });

  it('creates and version-updates asset master data only through the API', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'administrator', 'demo');
    const store = useOperationsStore();
    store.source = 'api';
    const payload = { code: 'ENV-02', name: '备用温湿度节点', zone: 'UT-ZA', type: '环境测点', status: 'unknown' as const, hardwareCode: 'H-12', integrationStatus: 'pending_verification' as const, interface: 'PA2', capabilities: ['环境温度'], mesh: 'MESH_ENV_02', position: { x: 44, y: 50, z: 0 }, latitude: 31.23, longitude: 121.47, locationSource: 'configured' as const, installationNote: '备用节点', isActive: true };
    vi.spyOn(api, 'createAsset').mockResolvedValue({ data: { id: 13, ...payload, lastSeenAt: null, version: 1 } } as never);
    vi.spyOn(api, 'updateAsset').mockResolvedValue({ data: { id: 13, ...payload, name: '备用环境节点', lastSeenAt: null, version: 2 } } as never);
    vi.spyOn(api, 'audit').mockResolvedValue({ data: { items: [] } } as never);

    const created = await store.createAsset(payload);
    expect(created.version).toBe(1);
    expect(store.assets[0].code).toBe('ENV-02');
    const updated = await store.updateAsset(created, { name: '备用环境节点' });
    expect(api.updateAsset).toHaveBeenCalledWith(13, { name: '备用环境节点', version: 1 });
    expect(updated.version).toBe(2);
    expect(store.assets[0].name).toBe('备用环境节点');
  });

  it('rejects asset master-data writes outside administrator API mode', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'operator', 'demo');
    const store = useOperationsStore();
    const asset = store.assets[0];
    await expect(store.updateAsset(asset, { name: '越权修改' })).rejects.toThrow('只有管理员');
    await auth.login('', '', 'administrator', 'demo');
    await expect(store.updateAsset(asset, { name: '演示写入' })).rejects.toThrow('仅允许写入受控数据服务');
  });

  it('imports and version-publishes governed GeoJSON only through the administrator API', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'administrator', 'demo');
    const store = useOperationsStore();
    store.source = 'api';
    const geoJson = { type: 'Feature', id: '81', geometry: { type: 'Point', coordinates: [121.4737, 31.2304] }, properties: { id: 81, code: 'MH-81', name: '测试井口', layerType: 'manhole', source: 'surveyed', sourceReference: '测绘成果 #81', accuracyM: '0.250', capturedAt: null, verifiedAt: null, status: 'draft', description: '', version: 1 } };
    const published = { ...geoJson, properties: { ...geoJson.properties, verifiedAt: '2026-08-28T00:00:00Z', status: 'published', version: 2 } };
    vi.spyOn(api, 'importGisFeatures').mockResolvedValue({ data: { type: 'FeatureCollection', features: [geoJson], meta: { created: 1 } } } as never);
    vi.spyOn(api, 'updateGisFeature').mockResolvedValue({ data: published } as never);
    vi.spyOn(api, 'audit').mockResolvedValue({ data: { items: [] } } as never);

    await store.importGisFeatures({ type: 'FeatureCollection', features: [geoJson] });
    expect(store.spatialFeatures[0]).toMatchObject({ id: 81, code: 'MH-81', status: 'draft' });
    const updated = await store.updateGisFeature(store.spatialFeatures[0], { status: 'published', verifiedAt: '2026-08-28T00:00:00Z' });
    expect(api.updateGisFeature).toHaveBeenCalledWith(81, { status: 'published', verifiedAt: '2026-08-28T00:00:00Z', version: 1 });
    expect(updated).toMatchObject({ id: 81, status: 'published', version: 2 });
  });

  it('summarizes and filters demo telemetry without changing operational telemetry state', async () => {
    const store = useOperationsStore();
    expect(store.telemetry).toHaveLength(24);
    await store.loadTelemetryInsights({ assetCode: 'ENV-01', metricKey: 'temperature', quality: 'suspect' });
    expect(store.telemetryInsights).toHaveLength(1);
    expect(store.telemetrySummary.sampleCount).toBe(1);
    expect(store.telemetrySummary.qualityCounts.suspect).toBe(1);
    expect(store.telemetry).toHaveLength(24);
  });

  it('paginates history without truncating the summary to the current page', async () => {
    const store = useOperationsStore();
    const sample = store.telemetry[0]!;
    store.telemetry = Array.from({ length: 125 }, (_, index) => ({ ...sample, id: index + 1 }));
    await store.loadTelemetryInsights({}, 2);
    expect(store.telemetryInsights).toHaveLength(25);
    expect(store.telemetryInsightsTotal).toBe(125);
    expect(store.telemetrySummary.sampleCount).toBe(125);
    await expect(store.loadTelemetryInsights({}, 0)).rejects.toThrow('页码无效');
  });

  it('does not let a stale history response overwrite a newer query', async () => {
    const store = useOperationsStore();
    store.source = 'api';
    const sample = store.telemetry[0]!;
    let resolveOld!: (value: never) => void;
    vi.spyOn(api, 'telemetry').mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
      .mockResolvedValueOnce({ data: { items: [{ ...sample, id: 999 }], total: 1 } } as never);
    vi.spyOn(api, 'telemetrySummary').mockResolvedValue({ data: summarizeTelemetry([sample]) } as never);
    const old = store.loadTelemetryInsights({ assetCode: 'old' });
    await store.loadTelemetryInsights({ assetCode: 'new' });
    resolveOld({ data: { items: [sample], total: 20 } } as never);
    expect(await old).toBe(false);
    expect(store.telemetryInsights[0]!.id).toBe(999);
    expect(store.telemetryInsightsTotal).toBe(1);
    expect(store.telemetryInsightsLoading).toBe(false);
  });

  it('returns an explicit empty summary for a telemetry query with no samples', () => {
    expect(summarizeTelemetry([])).toEqual({ sampleCount: 0, comparable: true, minimum: null, maximum: null, average: null, startedAt: null, endedAt: null, qualityCounts: { good: 0, suspect: 0, bad: 0, missing: 0 }, latest: null });
  });

  it('does not calculate misleading aggregates across different metrics or units', () => {
    const store = useOperationsStore();
    const mixed = summarizeTelemetry([...store.telemetry, { ...store.telemetry[0], id: 99, metricKey: 'humidity', unit: '%RH' }]);
    expect(mixed.comparable).toBe(false);
    expect(mixed.average).toBeNull();
    expect(mixed.minimum).toBeNull();
  });

  it('rejects an inverted telemetry time range consistently in demo mode', async () => {
    const store = useOperationsStore();
    await expect(store.loadTelemetryInsights({ recordedFrom: '2026-08-28T12:00:00Z', recordedTo: '2026-08-28T11:00:00Z' })).rejects.toThrow('开始时间不能晚于结束时间');
    expect(store.telemetryInsightsLoading).toBe(false);
  });
});
