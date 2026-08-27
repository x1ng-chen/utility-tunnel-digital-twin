import type { Alert, Asset, AssetStatus, AuditEntry, OperationsAction, OperationsState, ReportKind, Session, Telemetry, Threshold, UserRole, WorkOrder, WorkOrderStatus } from './operations';

type JsonRecord = Record<string, unknown>;

export type ApiSession = {
  accessToken: string;
  expiresInSeconds: number;
  user: {
    id: string;
    email: string;
    displayName: string;
    roles: string[];
  };
};

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null;
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asAssetStatus(value: unknown): AssetStatus {
  return ['normal', 'warning', 'alarm', 'offline', 'unknown'].includes(asString(value)) ? value as AssetStatus : 'unknown';
}

function asWorkOrderStatus(value: unknown): WorkOrderStatus {
  return ['draft', 'open', 'assigned', 'in_progress', 'pending_review', 'completed', 'cancelled'].includes(asString(value)) ? value as WorkOrderStatus : 'open';
}

function asSeverity(value: unknown): Alert['severity'] {
  return ['info', 'warning', 'critical'].includes(asString(value)) ? value as Alert['severity'] : 'info';
}

function asPriority(value: unknown): WorkOrder['priority'] {
  return ['low', 'normal', 'high', 'urgent'].includes(asString(value)) ? value as WorkOrder['priority'] : 'normal';
}

function asQuality(value: unknown): Telemetry['quality'] {
  return ['good', 'suspect', 'bad', 'missing'].includes(asString(value)) ? value as Telemetry['quality'] : 'missing';
}

function asPosition(item: JsonRecord): Asset['position'] | undefined {
  const x = asNumber(item.location_x, Number.NaN);
  const y = asNumber(item.location_y, Number.NaN);
  const z = asNumber(item.location_z, Number.NaN);
  return Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z) ? { x, y, z } : undefined;
}

function apiRole(roles: string[]): UserRole {
  if (roles.includes('administrator')) return 'administrator';
  if (roles.includes('operator') || roles.includes('maintainer')) return 'operator';
  return 'viewer';
}

function readableDetail(value: unknown): string {
  if (typeof value === 'string') return value;
  if (!value || (isRecord(value) && Object.keys(value).length === 0)) return '无补充说明';
  try {
    return JSON.stringify(value);
  } catch {
    return '已记录操作详情';
  }
}

function apiPath(baseUrl: string, path: string): string {
  return `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
}

export function normalizeApiBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, '');
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new ApiError('请输入有效的 API 地址，例如 http://127.0.0.1:8080。');
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) throw new ApiError('API 地址仅支持 HTTP 或 HTTPS。');
  if (parsed.username || parsed.password || parsed.search || parsed.hash) throw new ApiError('API 地址不能包含账号、查询参数或锚点。');
  const path = parsed.pathname === '/' ? '' : parsed.pathname.replace(/\/+$/, '');
  return `${parsed.origin}${path}`;
}

function mapAssets(items: unknown[]): Asset[] {
  return items.flatMap((item) => {
    if (!isRecord(item) || !asString(item.code)) return [];
    return [{
      id: asString(item.id) || undefined,
      code: asString(item.code),
      name: asString(item.name, '未命名资产'),
      zone: asString(item.zone_code, '未分区'),
      type: asString(item.asset_type, '未分类'),
      status: asAssetStatus(item.operational_status),
      mesh: asString(item.model_mesh_code, '未映射'),
      lastSeenAt: asString(item.updated_at, new Date(0).toISOString()),
      position: asPosition(item),
    }];
  });
}

function mapAlerts(items: unknown[]): Alert[] {
  return items.flatMap((item) => {
    if (!isRecord(item) || !asString(item.id) || !asString(item.code)) return [];
    return [{
      id: asString(item.id),
      code: asString(item.code),
      assetCode: asString(item.asset_code, '未关联资产'),
      severity: asSeverity(item.severity),
      category: asString(item.category, '未分类'),
      status: ['open', 'acknowledged', 'resolved', 'closed'].includes(asString(item.status)) ? item.status as Alert['status'] : 'open',
      title: asString(item.title, '未命名告警'),
      detail: asString(item.detail, '无补充说明'),
      openedAt: asString(item.opened_at, new Date(0).toISOString()),
      acknowledgedAt: asString(item.acknowledged_at) || undefined,
      acknowledgedBy: asString(item.acknowledged_by) || undefined,
    }];
  });
}

function mapWorkOrders(items: unknown[]): WorkOrder[] {
  return items.flatMap((item) => {
    if (!isRecord(item) || !asString(item.id) || !asString(item.code)) return [];
    return [{
      id: asString(item.id),
      code: asString(item.code),
      sourceAlertId: asString(item.source_alert_id) || undefined,
      assetCode: asString(item.asset_code, '未关联资产'),
      title: asString(item.title, '未命名工单'),
      priority: asPriority(item.priority),
      status: asWorkOrderStatus(item.status),
      assignee: asString(item.assignee_name) || undefined,
      dueAt: asString(item.due_at, '未设置'),
      createdAt: asString(item.created_at, new Date(0).toISOString()),
      updatedAt: asString(item.updated_at, asString(item.created_at, new Date(0).toISOString())),
    }];
  });
}

export function mapTelemetry(items: unknown[]): Telemetry[] {
  return items.flatMap((item) => {
    if (!isRecord(item) || !asString(item.asset_code) || !asString(item.metric_code)) return [];
    const value = asNumber(item.numeric_value, Number.NaN);
    if (!Number.isFinite(value)) return [];
    return [{
      id: asString(item.id, `${asString(item.asset_code)}-${asString(item.metric_code)}-${asString(item.recorded_at)}`),
      assetCode: asString(item.asset_code),
      metric: asString(item.metric_code),
      value,
      unit: asString(item.unit),
      quality: asQuality(item.quality),
      recordedAt: asString(item.recorded_at, new Date(0).toISOString()),
    }];
  });
}

function mapThresholds(items: unknown[]): Threshold[] {
  return items.flatMap((item) => {
    if (!isRecord(item) || !asString(item.key)) return [];
    const warning = asNumber(item.warning, Number.NaN);
    const alarm = asNumber(item.alarm, Number.NaN);
    if (!Number.isFinite(warning) || !Number.isFinite(alarm) || warning < 0 || warning >= alarm) return [];
    return [{ key: asString(item.key), label: asString(item.label), unit: asString(item.unit), warning, alarm, version: asNumber(item.version, 1) }];
  });
}

function mapAudit(items: unknown[]): AuditEntry[] {
  return items.flatMap((item) => {
    if (!isRecord(item) || !asString(item.id)) return [];
    const resourceType = asString(item.resource_type, 'system');
    const resourceId = asString(item.resource_id);
    return [{
      id: asString(item.id),
      occurredAt: asString(item.occurred_at, new Date(0).toISOString()),
      actor: asString(item.actor_name, '系统'),
      action: asString(item.action, 'system.event'),
      resource: resourceId ? `${resourceType}:${resourceId}` : resourceType,
      detail: readableDetail(item.detail),
    }];
  });
}

export function mapApiOperationsState(input: {
  session: ApiSession;
  assets: unknown[];
  alerts: unknown[];
  workOrders: unknown[];
  audit: unknown[];
  telemetry: unknown[];
  thresholds: unknown[];
  revision?: number;
}): OperationsState {
  const session: Session = { name: input.session.user.displayName, role: apiRole(input.session.user.roles) };
  return {
    schemaVersion: 2,
    revision: input.revision ?? Date.now(),
    assets: mapAssets(input.assets),
    alerts: mapAlerts(input.alerts),
    workOrders: mapWorkOrders(input.workOrders),
    audit: mapAudit(input.audit),
    telemetry: mapTelemetry(input.telemetry),
    thresholds: mapThresholds(input.thresholds),
    session,
  };
}

export class OperationsApiClient {
  readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = normalizeApiBaseUrl(baseUrl);
  }

  async login(email: string, password: string): Promise<ApiSession> {
    const payload = await this.request<unknown>('/v1/auth/login', undefined, {
      method: 'POST',
      body: { email, password },
    });
    if (!isRecord(payload) || !asString(payload.accessToken) || !isRecord(payload.user)) throw new ApiError('登录接口返回的数据格式不正确。');
    return {
      accessToken: asString(payload.accessToken),
      expiresInSeconds: asNumber(payload.expiresInSeconds, 900),
      user: {
        id: asString(payload.user.id),
        email: asString(payload.user.email),
        displayName: asString(payload.user.displayName, 'API 用户'),
        roles: asArray(payload.user.roles).map((role) => asString(role)).filter(Boolean),
      },
    };
  }

  async loadState(session: ApiSession, revision?: number): Promise<OperationsState> {
    const [assets, alerts, workOrders, audit, overview, thresholdResult] = await Promise.all([
      this.collection('/v1/assets', session.accessToken),
      this.collection('/v1/alerts', session.accessToken),
      this.collection('/v1/work-orders', session.accessToken),
      this.collection('/v1/audit', session.accessToken),
      this.request<unknown>('/v1/dashboard/overview', session.accessToken),
      this.request<unknown>('/v1/thresholds', session.accessToken).catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 403) return { items: [] };
        throw error;
      }),
    ]);
    const telemetry = isRecord(overview) ? asArray(overview.latestTelemetry) : [];
    const thresholds = isRecord(thresholdResult) ? asArray(thresholdResult.items) : [];
    return mapApiOperationsState({ session, assets, alerts, workOrders, audit, telemetry, thresholds, revision });
  }

  async executeAction(session: ApiSession, state: OperationsState, action: OperationsAction): Promise<void> {
    const token = session.accessToken;
    if (action.type === 'alert.acknowledge') {
      await this.request(`/v1/alerts/${action.alertId}/acknowledge`, token, { method: 'POST', body: { note: `由 ${action.actor} 在运维平台确认。` } });
      return;
    }
    if (action.type === 'workOrder.create') {
      await this.request(`/v1/alerts/${action.alertId}/work-orders`, token, { method: 'POST', body: {} });
      return;
    }
    if (action.type === 'workOrder.createManual') {
      const asset = state.assets.find((item) => item.code === action.assetCode);
      if (!asset?.id) throw new ApiError('当前资产没有可用的数据库标识，无法创建远程工单。');
      await this.request('/v1/work-orders', token, { method: 'POST', body: { assetId: asset.id, title: action.title } });
      return;
    }
    if (action.type === 'workOrder.transition') {
      await this.request(`/v1/work-orders/${action.workOrderId}/transition`, token, { method: 'POST', body: { to: action.to, note: `由 ${action.actor} 在运维平台执行 ${action.to}。` } });
      return;
    }
    if (action.type === 'threshold.update') {
      const threshold = state.thresholds.find((item) => item.key === action.key);
      if (!threshold) throw new ApiError('未找到需要更新的阈值。');
      await this.request(`/v1/thresholds/${action.key}`, token, {
        method: 'PUT',
        body: { label: threshold.label, unit: threshold.unit, warning: action.warning, alarm: action.alarm, version: threshold.version },
      });
      return;
    }
    if (action.type === 'report.export') {
      await this.registerReportExport(token, action.report);
    }
  }

  async registerReportExport(token: string, report: ReportKind): Promise<void> {
    await this.request('/v1/report-exports', token, { method: 'POST', body: { report } });
  }

  streamTelemetry(session: ApiSession, onTelemetry: (readings: Telemetry[]) => void, onError: (error: unknown) => void): () => void {
    const controller = new AbortController();
    void this.consumeTelemetryStream(session.accessToken, controller.signal, onTelemetry).catch((error: unknown) => {
      if (!(error instanceof DOMException && error.name === 'AbortError')) onError(error);
    });
    return () => controller.abort();
  }

  private async collection(path: string, token: string): Promise<unknown[]> {
    const all: unknown[] = [];
    let page = 1;
    let total = Number.POSITIVE_INFINITY;
    while (all.length < total && page <= 200) {
      const separator = path.includes('?') ? '&' : '?';
      const result = await this.request<unknown>(`${path}${separator}page=${page}&pageSize=100`, token);
      if (!isRecord(result)) throw new ApiError('列表接口返回的数据格式不正确。');
      const items = asArray(result.items);
      all.push(...items);
      total = asNumber(result.total, all.length);
      if (items.length === 0) break;
      page += 1;
    }
    if (all.length < total) throw new ApiError('列表数据超过客户端安全读取上限，请缩小查询范围。');
    return all.slice(0, total);
  }

  private async consumeTelemetryStream(token: string, signal: AbortSignal, onTelemetry: (readings: Telemetry[]) => void) {
    let response: Response;
    try {
      response = await fetch(apiPath(this.baseUrl, '/v1/realtime/telemetry'), {
        headers: { accept: 'text/event-stream', authorization: `Bearer ${token}` },
        signal,
      });
    } catch {
      if (signal.aborted) return;
      throw new ApiError('实时遥测连接失败；将继续使用定时回读。');
    }
    if (!response.ok || !response.body) throw new ApiError(`实时遥测连接失败（HTTP ${response.status}）。`, response.status);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (!signal.aborted) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        const event = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        if (event.startsWith('event: telemetry')) {
          const data = event.split('\n').find((line) => line.startsWith('data:'))?.slice(5).trim();
          if (data) {
            try {
              const payload: unknown = JSON.parse(data);
              const readings = isRecord(payload) ? mapTelemetry(asArray(payload.readings)) : [];
              if (readings.length) onTelemetry(readings);
            } catch {
              // Ignore one malformed event; a later valid device message must still be usable.
            }
          }
        }
        boundary = buffer.indexOf('\n\n');
      }
    }
  }

  private async request<T>(path: string, token?: string, options?: { method?: string; body?: unknown }): Promise<T> {
    let response: Response;
    try {
      response = await fetch(apiPath(this.baseUrl, path), {
        method: options?.method ?? 'GET',
        headers: {
          accept: 'application/json',
          ...(options?.body !== undefined ? { 'content-type': 'application/json' } : {}),
          ...(token ? { authorization: `Bearer ${token}` } : {}),
        },
        body: options?.body === undefined ? undefined : JSON.stringify(options.body),
      });
    } catch {
      throw new ApiError('无法连接 API。请确认服务已启动、地址正确且 CORS 已允许当前前端地址。');
    }
    const body = await response.json().catch(() => null) as unknown;
    if (!response.ok) {
      const message = isRecord(body) ? asString(body.message) : '';
      throw new ApiError(message || `API 请求失败（HTTP ${response.status}）。`, response.status);
    }
    return body as T;
  }
}
