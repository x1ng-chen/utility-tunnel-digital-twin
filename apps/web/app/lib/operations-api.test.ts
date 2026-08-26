import assert from 'node:assert/strict';
import test from 'node:test';
import { ApiError, mapApiOperationsState, normalizeApiBaseUrl } from './operations-api.ts';

const session = {
  accessToken: 'test-token',
  expiresInSeconds: 900,
  user: { id: 'user-1', email: 'admin@example.invalid', displayName: '系统管理员', roles: ['administrator'] },
};

test('normalizes an API base URL and rejects unsupported schemes', () => {
  assert.equal(normalizeApiBaseUrl('https://api.example.com///'), 'https://api.example.com');
  assert.equal(normalizeApiBaseUrl('https://api.example.com/gateway/'), 'https://api.example.com/gateway');
  assert.throws(() => normalizeApiBaseUrl('ftp://api.example.com'), ApiError);
  assert.throws(() => normalizeApiBaseUrl('https://user:password@api.example.com'), ApiError);
  assert.throws(() => normalizeApiBaseUrl('https://api.example.com?token=not-allowed'), ApiError);
});

test('maps PostgreSQL API payloads into the shared operations model', () => {
  const state = mapApiOperationsState({
    session,
    revision: 7,
    assets: [{ id: 'asset-1', code: 'FAN-01', name: '送风机', zone_code: 'UT-ZB', asset_type: 'actuator', operational_status: 'normal', model_mesh_code: 'MESH_FAN_01', updated_at: '2026-08-26T00:00:00.000Z' }],
    alerts: [{ id: 'alert-1', code: 'ALM-01', asset_code: 'FAN-01', severity: 'warning', category: 'equipment', status: 'open', title: '反馈异常', detail: '需复核', opened_at: '2026-08-26T00:00:00.000Z' }],
    workOrders: [{ id: 'order-1', code: 'WO-01', source_alert_id: 'alert-1', asset_code: 'FAN-01', title: '复核反馈', priority: 'high', status: 'in_progress', due_at: null, created_at: '2026-08-26T00:00:00.000Z', updated_at: '2026-08-26T01:00:00.000Z' }],
    audit: [{ id: 'audit-1', occurred_at: '2026-08-26T00:00:00.000Z', actor_name: '系统管理员', action: 'alert.acknowledge', resource_type: 'alert', resource_id: 'alert-1', detail: { note: '已确认' } }],
    telemetry: [{ id: 'telemetry-1', asset_code: 'FAN-01', metric_code: 'fan.speed', numeric_value: '1248.5', unit: 'rpm', quality: 'good', recorded_at: '2026-08-26T00:00:00.000Z' }],
    thresholds: [{ key: 'temperature', label: '环境温度', unit: '°C', warning: 28, alarm: 32, version: 2 }],
  });

  assert.equal(state.revision, 7);
  assert.equal(state.session.role, 'administrator');
  assert.equal(state.assets[0]?.id, 'asset-1');
  assert.equal(state.alerts[0]?.severity, 'warning');
  assert.equal(state.workOrders[0]?.sourceAlertId, 'alert-1');
  assert.equal(state.telemetry[0]?.value, 1248.5);
  assert.equal(state.thresholds[0]?.version, 2);
  assert.match(state.audit[0]?.detail ?? '', /已确认/);
});
