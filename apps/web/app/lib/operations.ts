export type AssetStatus = 'normal' | 'warning' | 'alarm' | 'offline';
export type AlertStatus = 'open' | 'acknowledged' | 'resolved' | 'closed';
export type WorkOrderStatus = 'open' | 'assigned' | 'in_progress' | 'pending_review' | 'completed' | 'cancelled';
export type UserRole = 'administrator' | 'operator' | 'viewer';
export type ReportKind = 'alerts' | 'workOrders' | 'assets' | 'daily';

export type Session = {
  name: string;
  role: UserRole;
};

export type Asset = {
  code: string;
  name: string;
  zone: string;
  type: string;
  status: AssetStatus;
  mesh: string;
  lastSeenAt: string;
};

export type Alert = {
  id: string;
  code: string;
  assetCode: string;
  severity: 'warning' | 'critical';
  category: string;
  status: AlertStatus;
  title: string;
  detail: string;
  openedAt: string;
  acknowledgedAt?: string;
  acknowledgedBy?: string;
};

export type WorkOrder = {
  id: string;
  code: string;
  sourceAlertId?: string;
  assetCode: string;
  title: string;
  priority: 'normal' | 'high' | 'urgent';
  status: WorkOrderStatus;
  assignee?: string;
  dueAt: string;
  createdAt: string;
  updatedAt: string;
};

export type AuditEntry = {
  id: string;
  occurredAt: string;
  actor: string;
  action: string;
  resource: string;
  detail: string;
};

export type Telemetry = {
  id: string;
  assetCode: string;
  metric: string;
  value: number;
  unit: string;
  quality: 'good' | 'suspect';
  recordedAt: string;
};

export type Threshold = {
  key: string;
  label: string;
  warning: number;
  alarm: number;
  unit: string;
  version: number;
};

export type OperationsState = {
  schemaVersion: 2;
  revision: number;
  assets: Asset[];
  alerts: Alert[];
  workOrders: WorkOrder[];
  audit: AuditEntry[];
  telemetry: Telemetry[];
  thresholds: Threshold[];
  session: Session;
};

export type OperationsAction =
  | { type: 'alert.acknowledge'; alertId: string; actor: string }
  | { type: 'workOrder.create'; alertId: string; actor: string }
  | { type: 'workOrder.createManual'; assetCode: string; title: string; actor: string }
  | { type: 'workOrder.transition'; workOrderId: string; to: WorkOrderStatus; actor: string }
  | { type: 'threshold.update'; key: string; warning: number; alarm: number; actor: string }
  | { type: 'report.export'; report: ReportKind; actor: string }
  | { type: 'session.switchRole'; role: UserRole }
  | { type: 'telemetry.tick' };

const rolePermissions: Record<UserRole, OperationsAction['type'][]> = {
  administrator: ['alert.acknowledge', 'workOrder.create', 'workOrder.createManual', 'workOrder.transition', 'threshold.update', 'report.export'],
  operator: ['alert.acknowledge', 'workOrder.create', 'workOrder.createManual', 'workOrder.transition', 'report.export'],
  viewer: ['report.export'],
};

export function canPerform(role: UserRole, action: OperationsAction['type']): boolean {
  return action === 'telemetry.tick' || action === 'session.switchRole' || rolePermissions[role].includes(action);
}

const storageKey = 'ut-ops.operations.v1';
const actor = '王露帆';
const initialDemoTimestamp = '2026-08-26T00:00:00.000Z';

const workOrderTransitions: Record<WorkOrderStatus, WorkOrderStatus[]> = {
  open: ['assigned', 'cancelled'],
  assigned: ['in_progress', 'cancelled'],
  in_progress: ['pending_review', 'cancelled'],
  pending_review: ['completed', 'in_progress'],
  completed: [],
  cancelled: [],
};

function timestamp(): string {
  return new Date().toISOString();
}

function auditEntry(state: OperationsState, action: string, resource: string, detail: string, by = actor): AuditEntry {
  return {
    id: `AUD-${state.revision + 1}-${state.audit.length + 1}`,
    occurredAt: timestamp(),
    actor: by,
    action,
    resource,
    detail,
  };
}

function nextState(state: OperationsState, patch: Partial<OperationsState>, entry?: AuditEntry): OperationsState {
  return {
    ...state,
    ...patch,
    revision: state.revision + 1,
    audit: entry ? [entry, ...state.audit].slice(0, 200) : patch.audit ?? state.audit,
  };
}

function nextWorkOrderCode(state: OperationsState): string {
  return `WO-${new Date().toISOString().slice(2, 10).replaceAll('-', '')}-${String(state.workOrders.length + 1).padStart(2, '0')}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function hasString(value: Record<string, unknown>, key: string): boolean {
  return typeof value[key] === 'string';
}

function hasAllowedString(value: Record<string, unknown>, key: string, allowed: readonly string[]): boolean {
  return hasString(value, key) && allowed.includes(value[key] as string);
}

function isPersistedOperationsState(value: unknown): value is OperationsState {
  if (!isRecord(value) || value.schemaVersion !== 2 || typeof value.revision !== 'number' || !Number.isFinite(value.revision)) return false;
  if (!Array.isArray(value.assets) || !Array.isArray(value.alerts) || !Array.isArray(value.workOrders) || !Array.isArray(value.audit) || !Array.isArray(value.telemetry) || !Array.isArray(value.thresholds) || !isRecord(value.session)) return false;
  if (!hasString(value.session, 'name') || !['administrator', 'operator', 'viewer'].includes(value.session.role as string)) return false;

  return value.assets.every((item) => isRecord(item) && ['code', 'name', 'zone', 'type', 'mesh', 'lastSeenAt'].every((key) => hasString(item, key)) && hasAllowedString(item, 'status', ['normal', 'warning', 'alarm', 'offline']))
    && value.alerts.every((item) => isRecord(item) && ['id', 'code', 'assetCode', 'category', 'title', 'detail', 'openedAt'].every((key) => hasString(item, key)) && hasAllowedString(item, 'severity', ['warning', 'critical']) && hasAllowedString(item, 'status', ['open', 'acknowledged', 'resolved', 'closed']))
    && value.workOrders.every((item) => isRecord(item) && ['id', 'code', 'assetCode', 'title', 'dueAt', 'createdAt', 'updatedAt'].every((key) => hasString(item, key)) && hasAllowedString(item, 'priority', ['normal', 'high', 'urgent']) && hasAllowedString(item, 'status', ['open', 'assigned', 'in_progress', 'pending_review', 'completed', 'cancelled']))
    && value.audit.every((item) => isRecord(item) && ['id', 'occurredAt', 'actor', 'action', 'resource', 'detail'].every((key) => hasString(item, key)))
    && value.telemetry.every((item) => isRecord(item) && ['id', 'assetCode', 'metric', 'unit', 'recordedAt'].every((key) => hasString(item, key)) && hasAllowedString(item, 'quality', ['good', 'suspect']) && typeof item.value === 'number' && Number.isFinite(item.value))
    && value.thresholds.every((item) => isRecord(item) && ['key', 'label', 'unit'].every((key) => hasString(item, key)) && typeof item.warning === 'number' && Number.isFinite(item.warning) && item.warning >= 0 && typeof item.alarm === 'number' && Number.isFinite(item.alarm) && item.alarm > item.warning && typeof item.version === 'number' && Number.isInteger(item.version) && item.version > 0);
}

export function createInitialOperationsState(initialTimestamp = initialDemoTimestamp): OperationsState {
  const now = initialTimestamp;
  return {
    schemaVersion: 2,
    revision: 0,
    assets: [
      { code: 'CTRL-01', name: '现场控制器', zone: 'UT-ZA', type: '控制器', status: 'normal', mesh: 'MESH_CTRL_01', lastSeenAt: now },
      { code: 'FAN-01', name: '送风机 #01', zone: 'UT-ZB', type: '执行器', status: 'normal', mesh: 'MESH_FAN_01', lastSeenAt: now },
      { code: 'SEEP-W01', name: '渗水监测点', zone: 'UT-ZB', type: '测点', status: 'warning', mesh: 'MESH_SEEP_W01', lastSeenAt: now },
      { code: 'GAS-01', name: '甲烷监测节点', zone: 'UT-ZC', type: '测点', status: 'normal', mesh: 'MESH_GAS_01', lastSeenAt: now },
    ],
    alerts: [
      {
        id: 'alert-seep-001', code: 'ALM-260826-003', assetCode: 'SEEP-W01', severity: 'warning', category: '水浸趋势', status: 'open',
        title: '水浸趋势异常', detail: '渗水趋势上升，需确认现场情况并安排巡检。', openedAt: now,
      },
      {
        id: 'alert-fan-001', code: 'ALM-260826-002', assetCode: 'FAN-01', severity: 'critical', category: '设备反馈', status: 'acknowledged',
        title: '风机反馈丢失', detail: '执行反馈暂未返回，正在等待工单复核。', openedAt: now, acknowledgedAt: now, acknowledgedBy: actor,
      },
      {
        id: 'alert-ctrl-001', code: 'ALM-260826-001', assetCode: 'CTRL-01', severity: 'warning', category: '通信质量', status: 'open',
        title: '控制器通信质量波动', detail: '控制器出现短时延迟抖动，建议建立巡检工单并观察后续遥测。', openedAt: now,
      },
    ],
    workOrders: [
      {
        id: 'wo-seep-001', code: 'WO-260826-08', sourceAlertId: 'alert-seep-001', assetCode: 'SEEP-W01', title: '检查 UT-ZB 接水盘与水位探针',
        priority: 'high', status: 'open', dueAt: '今天 14:00', createdAt: now, updatedAt: now,
      },
      {
        id: 'wo-fan-001', code: 'WO-260826-06', sourceAlertId: 'alert-fan-001', assetCode: 'FAN-01', title: '复核风机反馈与现场状态',
        priority: 'urgent', status: 'in_progress', assignee: '运维组 A', dueAt: '今天 16:00', createdAt: now, updatedAt: now,
      },
    ],
    telemetry: [
      { id: 't-1', assetCode: 'FAN-01', metric: '风机转速', value: 1248, unit: 'rpm', quality: 'good', recordedAt: now },
      { id: 't-2', assetCode: 'SEEP-W01', metric: '积水趋势', value: 68, unit: '%', quality: 'suspect', recordedAt: now },
      { id: 't-3', assetCode: 'GAS-01', metric: '甲烷浓度', value: 0.03, unit: '%LEL', quality: 'good', recordedAt: now },
      { id: 't-4', assetCode: 'CTRL-01', metric: '通信延迟', value: 132, unit: 'ms', quality: 'good', recordedAt: now },
    ],
    thresholds: [
      { key: 'temperature', label: '环境温度', warning: 28, alarm: 32, unit: '°C', version: 1 },
      { key: 'humidity', label: '环境湿度', warning: 75, alarm: 85, unit: '%RH', version: 1 },
      { key: 'water', label: '水浸趋势', warning: 20, alarm: 45, unit: '秒', version: 1 },
    ],
    session: { name: actor, role: 'operator' },
    audit: [
      { id: 'AUD-001', occurredAt: now, actor: '系统', action: 'telemetry.updated', resource: 'HUM-02', detail: '湿度遥测已进入演示数据层。' },
      { id: 'AUD-002', occurredAt: now, actor, action: 'work_order.created', resource: 'WO-260826-08', detail: '工单已关联 ALM-260826-003。' },
    ],
  };
}

export function reduceOperations(state: OperationsState, action: OperationsAction): OperationsState {
  if (action.type === 'session.switchRole') {
    if (action.role === state.session.role) return state;
    const session = { ...state.session, role: action.role };
    return nextState(state, { session }, auditEntry(state, 'session.role_switched', action.role, `演示角色已切换为 ${action.role}`, session.name));
  }

  if (!canPerform(state.session.role, action.type)) return state;

  if (action.type === 'alert.acknowledge') {
    const alert = state.alerts.find((item) => item.id === action.alertId);
    if (!alert || alert.status !== 'open') return state;
    const updated = { ...alert, status: 'acknowledged' as const, acknowledgedAt: timestamp(), acknowledgedBy: action.actor };
    return nextState(state, { alerts: state.alerts.map((item) => item.id === alert.id ? updated : item) }, auditEntry(state, 'alert.acknowledged', alert.code, `已确认：${alert.title}`, action.actor));
  }

  if (action.type === 'workOrder.create') {
    const alert = state.alerts.find((item) => item.id === action.alertId);
    if (!alert || !['open', 'acknowledged'].includes(alert.status) || state.workOrders.some((item) => item.sourceAlertId === alert.id)) return state;
    const now = timestamp();
    const created: WorkOrder = {
      id: `wo-${state.revision + 1}`, code: nextWorkOrderCode(state),
      sourceAlertId: alert.id, assetCode: alert.assetCode, title: `处置 ${alert.code}：${alert.title}`,
      priority: alert.severity === 'critical' ? 'urgent' : 'high', status: 'open', dueAt: '今天 18:00', createdAt: now, updatedAt: now,
    };
    return nextState(state, { workOrders: [created, ...state.workOrders] }, auditEntry(state, 'work_order.created_from_alert', created.code, `来源告警：${alert.code}`, action.actor));
  }

  if (action.type === 'workOrder.createManual') {
    const asset = state.assets.find((item) => item.code === action.assetCode);
    const title = action.title.trim();
    if (!asset || !title) return state;
    const now = timestamp();
    const created: WorkOrder = {
      id: `wo-${state.revision + 1}`, code: nextWorkOrderCode(state), assetCode: asset.code, title,
      priority: asset.status === 'alarm' ? 'urgent' : asset.status === 'warning' ? 'high' : 'normal', status: 'open', dueAt: '今天 18:00', createdAt: now, updatedAt: now,
    };
    return nextState(state, { workOrders: [created, ...state.workOrders] }, auditEntry(state, 'work_order.created_manual', created.code, `手工新建：${created.title}，资产 ${asset.code}`, action.actor));
  }

  if (action.type === 'workOrder.transition') {
    const order = state.workOrders.find((item) => item.id === action.workOrderId);
    if (!order || !workOrderTransitions[order.status].includes(action.to) || (action.to === 'completed' && state.session.role !== 'administrator')) return state;
    const updated = { ...order, status: action.to, assignee: action.to === 'assigned' ? action.actor : order.assignee, updatedAt: timestamp() };
    const patch: Partial<OperationsState> = { workOrders: state.workOrders.map((item) => item.id === order.id ? updated : item) };
    let detail = `${order.status} → ${action.to}`;
    if (action.to === 'completed' && order.sourceAlertId) {
      const sourceAlert = state.alerts.find((item) => item.id === order.sourceAlertId);
      if (sourceAlert && sourceAlert.status !== 'closed') {
        const alerts = state.alerts.map((item) => item.id === sourceAlert.id ? { ...item, status: 'resolved' as const } : item);
        patch.alerts = alerts;
        const hasOtherActiveAlert = alerts.some((item) => item.assetCode === order.assetCode && item.id !== sourceAlert.id && !['resolved', 'closed'].includes(item.status));
        if (!hasOtherActiveAlert) patch.assets = state.assets.map((item) => item.code === order.assetCode ? { ...item, status: 'normal' as const, lastSeenAt: timestamp() } : item);
        detail += `；来源 ${sourceAlert.code} 已自动闭环`;
      }
    }
    return nextState(state, patch, auditEntry(state, action.to === 'completed' ? 'work_order.completed' : 'work_order.transitioned', order.code, detail, action.actor));
  }

  if (action.type === 'threshold.update') {
    const threshold = state.thresholds.find((item) => item.key === action.key);
    if (!threshold || !Number.isFinite(action.warning) || !Number.isFinite(action.alarm) || action.warning >= action.alarm || action.warning < 0 || action.alarm < 0) return state;
    const updated = { ...threshold, warning: action.warning, alarm: action.alarm, version: threshold.version + 1 };
    return nextState(state, { thresholds: state.thresholds.map((item) => item.key === action.key ? updated : item) }, auditEntry(state, 'setting.threshold_updated', threshold.key, `预警 ${action.warning}${threshold.unit}，报警 ${action.alarm}${threshold.unit}`, action.actor));
  }

  if (action.type === 'report.export') {
    return nextState(state, {}, auditEntry(state, 'report.exported', action.report, '已生成本地 CSV 导出文件。', action.actor));
  }

  const now = timestamp();
  const telemetry = state.telemetry.map((reading, index) => {
    const amplitude = reading.metric === '风机转速' ? 18 : reading.metric === '积水趋势' ? 12 : 2;
    const offset = Math.round(Math.sin((state.revision + 1) * (index + 1)) * amplitude * 100) / 100;
    return { ...reading, value: Math.max(0, reading.value + offset), recordedAt: now, id: `${reading.id}-${state.revision + 1}` };
  });
  const seep = telemetry.find((reading) => reading.assetCode === 'SEEP-W01');
  const assets = state.assets.map((item) => item.code === 'SEEP-W01' && seep
    ? { ...item, status: seep.value >= 75 ? 'alarm' as const : 'warning' as const, lastSeenAt: now }
    : { ...item, lastSeenAt: now });
  return nextState(state, { telemetry, assets });
}

type Subscriber = () => void;

export class OperationsRepository {
  private state = createInitialOperationsState();
  private subscribers = new Set<Subscriber>();

  getSnapshot = (): OperationsState => this.state;

  subscribe = (subscriber: Subscriber): (() => void) => {
    this.subscribers.add(subscriber);
    return () => this.subscribers.delete(subscriber);
  };

  hydrate(): void {
    if (typeof window === 'undefined') return;
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return;
    try {
      const parsed: unknown = JSON.parse(raw);
      if (isPersistedOperationsState(parsed)) this.state = parsed;
      else window.localStorage.removeItem(storageKey);
    } catch {
      window.localStorage.removeItem(storageKey);
    }
    this.emit();
  }

  dispatch(action: OperationsAction): OperationsState {
    const next = reduceOperations(this.state, action);
    if (next === this.state) return this.state;
    this.state = next;
    if (typeof window !== 'undefined') window.localStorage.setItem(storageKey, JSON.stringify(next));
    this.emit();
    return this.state;
  }

  reset(): void {
    this.state = createInitialOperationsState(timestamp());
    if (typeof window !== 'undefined') window.localStorage.removeItem(storageKey);
    this.emit();
  }

  private emit(): void {
    this.subscribers.forEach((subscriber) => subscriber());
  }
}

export const operationsRepository = new OperationsRepository();

export function toCsv(state: OperationsState, report: ReportKind): string {
  const escape = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`;
  const rows = report === 'alerts'
    ? [['编码', '资产', '级别', '状态', '标题', '触发时间'], ...state.alerts.map((item) => [item.code, item.assetCode, item.severity, item.status, item.title, item.openedAt])]
    : report === 'workOrders'
      ? [['编码', '资产', '优先级', '状态', '标题', '负责人'], ...state.workOrders.map((item) => [item.code, item.assetCode, item.priority, item.status, item.title, item.assignee])]
      : report === 'assets'
        ? [['编码', '名称', '区域', '类型', '运行状态', '模型网格'], ...state.assets.map((item) => [item.code, item.name, item.zone, item.type, item.status, item.mesh])]
        : [['报告日期', '在线资产', '待确认告警', '活动工单', '审计记录'], [new Date().toISOString().slice(0, 10), state.assets.filter((item) => item.status !== 'offline').length, state.alerts.filter((item) => item.status === 'open').length, state.workOrders.filter((item) => !['completed', 'cancelled'].includes(item.status)).length, state.audit.length]];
  return `\uFEFF${rows.map((row) => row.map(escape).join(',')).join('\n')}`;
}

export function toJson(state: OperationsState, report: ReportKind): string {
  const generatedAt = timestamp();
  const payload = report === 'alerts' ? state.alerts
    : report === 'workOrders' ? state.workOrders
      : report === 'assets' ? state.assets
        : {
          generatedAt,
          metrics: {
            onlineAssets: state.assets.filter((item) => item.status !== 'offline').length,
            openAlerts: state.alerts.filter((item) => item.status === 'open').length,
            activeWorkOrders: state.workOrders.filter((item) => !['completed', 'cancelled'].includes(item.status)).length,
          },
          alerts: state.alerts,
          workOrders: state.workOrders,
          audit: state.audit,
        };
  return JSON.stringify({ schemaVersion: state.schemaVersion, report, generatedAt, data: payload }, null, 2);
}
