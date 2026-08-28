import axios from 'axios';

const localStorageRef = typeof window !== 'undefined' ? window.localStorage : null;
const sessionStorageRef = typeof window !== 'undefined' ? window.sessionStorage : null;
const fallbackBaseUrl = typeof window !== 'undefined' && window.location.protocol === 'https:'
  ? `${window.location.origin}/api`
  : 'http://127.0.0.1:8000/api';

export function resolveApiBaseUrl(baseUrl: string, allowSameOriginPath = false, sameOrigin = typeof window !== 'undefined' ? window.location.origin : ''): string {
  let normalized = baseUrl.trim().replace(/\/+$/, '');
  if (allowSameOriginPath && normalized.startsWith('/')) {
    if (!sameOrigin) throw new Error('相对数据服务地址只能在浏览器中使用。');
    normalized = new URL(normalized, sameOrigin).toString().replace(/\/+$/, '');
  }
  if (!/^https?:\/\//i.test(normalized)) throw new Error('数据服务地址配置无效。');
  const parsed = new URL(normalized);
  if (parsed.username || parsed.password) throw new Error('数据服务地址不得包含认证信息。');
  if (parsed.search || parsed.hash || !parsed.hostname) throw new Error('数据服务地址不得包含无关参数。');
  if (typeof window !== 'undefined' && window.location.protocol === 'https:' && parsed.protocol !== 'https:') {
    throw new Error('HTTPS 页面只能连接 HTTPS API。');
  }
  return normalized;
}

function initialApiBaseUrl(): string {
  const stored = localStorageRef?.getItem('vue-api-url') || '';
  const candidates = [
    { value: stored, allowSameOriginPath: false },
    { value: import.meta.env.VITE_API_BASE_URL || '', allowSameOriginPath: true },
    { value: fallbackBaseUrl, allowSameOriginPath: false },
  ].filter((candidate) => candidate.value);
  for (const candidate of candidates) {
    try {
      return resolveApiBaseUrl(candidate.value, candidate.allowSameOriginPath);
    } catch {
      if (candidate.value === stored) localStorageRef?.removeItem('vue-api-url');
    }
  }
  return fallbackBaseUrl;
}

const defaultBaseUrl = initialApiBaseUrl();
const client = axios.create({ baseURL: defaultBaseUrl, timeout: 8000, headers: { 'Content-Type': 'application/json' } });
client.interceptors.request.use((config) => {
  const token = sessionStorageRef?.getItem('ut-django-token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  const requestId = typeof globalThis.crypto?.randomUUID === 'function' ? globalThis.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  config.headers['X-Request-Id'] = requestId;
  return config;
});

export const api = {
  login: (payload: { email: string; password: string }) => client.post('/auth/login/', payload),
  me: () => client.get('/auth/me/'),
  logout: () => client.post('/auth/logout/'),
  adminUsers: (params?: Record<string, string | number>) => client.get('/admin/users/', { params }),
  updateAdminUser: (id: number, payload: Record<string, unknown>) => client.patch(`/admin/users/${id}/`, payload),
  dashboard: () => client.get('/dashboard/'),
  assets: (params?: Record<string, string | number>) => client.get('/assets/', { params }),
  createAsset: (payload: Record<string, unknown>) => client.post('/assets/', payload),
  updateAsset: (id: number, payload: Record<string, unknown>) => client.patch(`/assets/${id}/`, payload),
  gisFeatures: (params?: Record<string, string | number>) => client.get('/gis/features/', { params }),
  createGisFeature: (payload: Record<string, unknown>) => client.post('/gis/features/', payload),
  updateGisFeature: (id: number, payload: Record<string, unknown>) => client.patch(`/gis/features/${id}/`, payload),
  importGisFeatures: (payload: Record<string, unknown>) => client.post('/gis/features/import/', payload),
  hardwareBindings: (params?: Record<string, string | number>) => client.get('/hardware-bindings/', { params }),
  createHardwareBinding: (payload: Record<string, unknown>) => client.post('/hardware-bindings/', payload),
  updateHardwareBinding: (id: number, payload: Record<string, unknown>) => client.patch(`/hardware-bindings/${id}/`, payload),
  alerts: (params?: Record<string, string | number>) => client.get('/alerts/', { params }),
  acknowledge: (id: number) => client.post(`/alerts/${id}/acknowledge/`),
  createAlertWorkOrder: (id: number) => client.post(`/alerts/${id}/work-order/`),
  workOrders: (params?: Record<string, string | number>) => client.get('/work-orders/', { params }),
  createWorkOrder: (payload: Record<string, unknown>, idempotencyKey?: string) => client.post('/work-orders/', payload, { headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined }),
  transitionWorkOrder: (id: number, to: string, version?: number) => client.post(`/work-orders/${id}/transition/`, { to, ...(version == null ? {} : { version }) }),
  telemetry: (params?: Record<string, string | number>) => client.get('/telemetry/', { params }),
  telemetrySummary: (params?: Record<string, string | number>) => client.get('/telemetry/summary/', { params }),
  ingestTelemetry: (readings: Record<string, unknown>[]) => client.post('/telemetry/', { readings }),
  thresholds: () => client.get('/thresholds/'),
  updateThreshold: (key: string, payload: Record<string, unknown>) => client.put(`/thresholds/${key}/`, payload),
  audit: (params?: Record<string, string | number>) => client.get('/audit/', { params }),
  report: (report: string, idempotencyKey?: string) => client.post('/report-exports/', { report }, { headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined }),
};

export function setApiBaseUrl(baseUrl: string): void {
  const normalized = resolveApiBaseUrl(baseUrl);
  client.defaults.baseURL = normalized;
  localStorageRef?.setItem('vue-api-url', normalized);
}

export function getApiBaseUrl(): string {
  return String(client.defaults.baseURL || defaultBaseUrl);
}
