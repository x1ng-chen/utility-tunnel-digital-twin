import axios, { type InternalAxiosRequestConfig } from 'axios';

export type ControllerAction = 'led_red' | 'led_green' | 'led_blue' | 'led_off' | 'relay_on' | 'relay_off' | 'fan_pwm' | 'fan2_pwm';
export type AssistantMessage = { role: 'user' | 'assistant'; content: string };

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
type RetriableRequestConfig = InternalAxiosRequestConfig & { __safeRetryCount?: number };

export function shouldRetryApiRequest(method: string | undefined, status: number | undefined, retryCount: number): boolean {
  if (!['get', 'head'].includes((method || '').toLowerCase()) || retryCount >= 2) return false;
  return status == null || status === 408 || status === 429 || [502, 503, 504].includes(status);
}

export function apiRetryDelayMs(retryCount: number, retryAfter?: string): number {
  const serverDelay = Number(retryAfter);
  if (Number.isFinite(serverDelay) && serverDelay >= 0) return Math.min(serverDelay * 1000, 1500);
  return Math.min(250 * (2 ** retryCount), 1000);
}

client.interceptors.request.use((config) => {
  // The browser must generate the multipart boundary. Keeping the client's
  // JSON default here makes Django see an empty request.FILES collection.
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) config.headers.delete('Content-Type');
  const token = sessionStorageRef?.getItem('ut-django-token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  const requestId = typeof globalThis.crypto?.randomUUID === 'function' ? globalThis.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  config.headers['X-Request-Id'] = requestId;
  return config;
});
client.interceptors.response.use(undefined, async (error) => {
  const config = error?.config as RetriableRequestConfig | undefined;
  const retryCount = config?.__safeRetryCount ?? 0;
  const status = error?.response?.status as number | undefined;
  if (!config || !shouldRetryApiRequest(config.method, status, retryCount)) return Promise.reject(error);
  config.__safeRetryCount = retryCount + 1;
  const retryAfter = error?.response?.headers?.['retry-after'] as string | undefined;
  await new Promise((resolve) => window.setTimeout(resolve, apiRetryDelayMs(retryCount, retryAfter)));
  return client.request(config);
});

export const api = {
  login: (payload: { email: string; password: string }) => client.post('/auth/login/', payload),
  requestRegistration: (payload: { account: string; displayName: string; role: 'operator' | 'viewer' }) => client.post('/auth/registration-requests/', payload),
  setupRegistrationPassword: (token: string, password: string) => client.post('/auth/registration-requests/setup/', { token, password }),
  me: () => client.get('/auth/me/'),
  logout: () => client.post('/auth/logout/'),
  changePassword: (payload: { currentPassword: string; newPassword: string }) => client.post('/auth/password/', payload),
  adminUsers: (params?: Record<string, string | number>) => client.get('/admin/users/', { params }),
  updateAdminUser: (id: number, payload: Record<string, unknown>) => client.patch(`/admin/users/${id}/`, payload),
  registrationRequests: (params?: Record<string, string | number>) => client.get('/admin/registration-requests/', { params }),
  reviewRegistrationRequest: (id: number, payload: { status: 'approved' | 'rejected'; reviewNote?: string }) => client.patch(`/admin/registration-requests/${id}/`, payload),
  reissueRegistrationSetupToken: (id: number) => client.post(`/admin/registration-requests/${id}/setup-token/`),
  dashboard: () => client.get('/dashboard/'),
  assistantChat: (messages: AssistantMessage[], page: string) => client.post<{ reply: string }>('/assistant/chat/', { messages, page }, { timeout: 35000 }),
  controllerCommand: (action: ControllerAction, dutyPercent?: number) => client.post('/controllers/CTRL-01/commands/', { action, ...(dutyPercent == null ? {} : { dutyPercent }) }),
  twinModelReadiness: () => client.get('/twin/model-readiness/'),
  twinModels: (params?: Record<string, string | number>) => client.get('/twin/models/', { params }),
  uploadTwinModel: (payload: FormData) => client.post('/twin/models/', payload, { timeout: 60000 }),
  activateTwinModel: (id: number) => client.post(`/twin/models/${id}/activate/`),
  twinModelFile: (releaseId: number) => client.get('/twin/model-file/', { params: { release: releaseId }, responseType: 'blob', timeout: 60000 }),
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
  transitionWorkOrder: (id: number, to: string, version?: number, note = '') => client.post(`/work-orders/${id}/transition/`, { to, note, ...(version == null ? {} : { version }) }),
  telemetry: (params?: Record<string, string | number>) => client.get('/telemetry/', { params }),
  telemetrySummary: (params?: Record<string, string | number>) => client.get('/telemetry/summary/', { params }),
  ingestTelemetry: (readings: Record<string, unknown>[]) => client.post('/telemetry/', { readings }),
  thresholds: () => client.get('/thresholds/'),
  updateThreshold: (key: string, payload: Record<string, unknown>) => client.put(`/thresholds/${key}/`, payload),
  audit: (params?: Record<string, string | number>) => client.get('/audit/', { params }),
  report: (report: string, idempotencyKey?: string) => client.post('/report-exports/', { report }, { headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined }),
  downloadReport: (id: number) => client.get(`/report-exports/${id}/download/`, { responseType: 'blob' }),
};

export function setApiBaseUrl(baseUrl: string): void {
  const normalized = resolveApiBaseUrl(baseUrl);
  client.defaults.baseURL = normalized;
  localStorageRef?.setItem('vue-api-url', normalized);
}

export function getApiBaseUrl(): string {
  return String(client.defaults.baseURL || defaultBaseUrl);
}
