import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from './auth';
import { reconcileRecords, summarizeTelemetry, useOperationsStore } from './operations';
import { api } from '../services/api';

describe('operations store', () => {
  beforeEach(() => setActivePinia(createPinia()));
  afterEach(() => vi.restoreAllMocks());

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
    vi.spyOn(api, 'dashboard').mockRejectedValue({ response: { status: 401 } });
    vi.spyOn(api, 'assets').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'alerts').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'workOrders').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'thresholds').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'telemetry').mockResolvedValue({ data: { items: [] } } as never);
    vi.spyOn(api, 'audit').mockResolvedValue({ data: { items: [] } } as never);

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
