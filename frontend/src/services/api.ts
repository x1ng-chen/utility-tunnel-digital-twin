import axios from 'axios';

const storage = typeof window !== 'undefined' ? window.localStorage : null;
const defaultBaseUrl = storage?.getItem('vue-api-url') || import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';
const client = axios.create({ baseURL: defaultBaseUrl, timeout: 8000, headers: { 'Content-Type': 'application/json' } });
client.interceptors.request.use((config) => {
  const token = storage?.getItem('ut-django-token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  const requestId = typeof globalThis.crypto?.randomUUID === 'function' ? globalThis.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  config.headers['X-Request-Id'] = requestId;
  return config;
});

export const api = {
  login: (payload: { email: string; password: string }) => client.post('/auth/login/', payload),
  me: () => client.get('/auth/me/'),
  logout: () => client.post('/auth/logout/'),
  dashboard: () => client.get('/dashboard/'),
  assets: (params?: Record<string, string | number>) => client.get('/assets/', { params }),
  alerts: (params?: Record<string, string | number>) => client.get('/alerts/', { params }),
  acknowledge: (id: number) => client.post(`/alerts/${id}/acknowledge/`),
  createAlertWorkOrder: (id: number) => client.post(`/alerts/${id}/work-order/`),
  workOrders: (params?: Record<string, string | number>) => client.get('/work-orders/', { params }),
  createWorkOrder: (payload: Record<string, unknown>) => client.post('/work-orders/', payload),
  transitionWorkOrder: (id: number, to: string) => client.post(`/work-orders/${id}/transition/`, { to }),
  telemetry: (params?: Record<string, string | number>) => client.get('/telemetry/', { params }),
  thresholds: () => client.get('/thresholds/'),
  updateThreshold: (key: string, payload: Record<string, unknown>) => client.put(`/thresholds/${key}/`, payload),
  audit: (params?: Record<string, string | number>) => client.get('/audit/', { params }),
  report: (report: string) => client.post('/report-exports/', { report }),
};

export function setApiBaseUrl(baseUrl: string): void {
  const normalized = baseUrl.trim().replace(/\/$/, '');
  if (!/^https?:\/\//i.test(normalized)) throw new Error('API 地址必须使用 HTTP 或 HTTPS。');
  client.defaults.baseURL = normalized;
  storage?.setItem('vue-api-url', normalized);
}
