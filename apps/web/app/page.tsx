'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { canPerform, toCsv, toJson } from './lib/operations';
import type { Asset, OperationsAction, OperationsState, ReportKind, UserRole, WorkOrder, WorkOrderStatus } from './lib/operations';
import { useOperations } from './lib/use-operations';

const actor = '王露帆';
const nav = [
  ['overview', '运行总览', '◈'], ['twin', '数字孪生', '◇'], ['alerts', '告警中心', '!'], ['orders', '工单中心', '✓'],
  ['assets', '设备台账', '▦'], ['insights', '数据洞察', '⌁'], ['audit', '审计追踪', '≡'], ['settings', '系统配置', '⚙'],
] as const;
const labels: Record<string, string> = Object.fromEntries(nav.map(([id, label]) => [id, label]));
const roleLabels: Record<UserRole, string> = { administrator: '管理员', operator: '运维员', viewer: '查看者' };
const moduleHeadings: Record<string, [string, string, string]> = {
  twin: ['DIGITAL TWIN', '数字孪生', '以空间为入口查看资产、区域与运行状态。'],
  alerts: ['ALERT MANAGEMENT', '告警中心', '仅处理异常事件的确认、关联工单与闭环。'],
  orders: ['WORK ORDER FLOW', '工单中心', '以任务为单位组织派发、处置、复核与归档。'],
  assets: ['ASSET REGISTRY', '设备台账', '维护设备的身份、位置、能力和生命周期信息。'],
  insights: ['DATA INSIGHTS', '数据洞察', '面向演示数据的趋势、对比、导出和运行报告。'],
  audit: ['AUDIT TRAIL', '审计追踪', '不可篡改地回看每一次关键业务与系统操作。'],
  settings: ['SYSTEM CONFIG', '系统配置', '集中维护规则、映射、角色和演示数据源。'],
};

type ExportFormat = 'csv' | 'json';

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(value));
}

function statusLabel(status: string): string {
  return ({ normal: '运行正常', warning: '预警', alarm: '告警', offline: '离线', open: '待确认', acknowledged: '已确认', resolved: '已恢复', closed: '已关闭', assigned: '已派发', in_progress: '处理中', pending_review: '待复核', completed: '已完成', cancelled: '已取消' } as Record<string, string>)[status] ?? status;
}

function assetTone(status: Asset['status']): string {
  return status === 'normal' ? 'good' : status === 'alarm' ? 'critical' : status === 'offline' ? 'closed' : 'warning';
}

function nextOrderAction(status: WorkOrderStatus): { label: string; to: WorkOrderStatus } | null {
  const transitions: Partial<Record<WorkOrderStatus, { label: string; to: WorkOrderStatus }>> = {
    open: { label: '领取', to: 'assigned' }, assigned: { label: '开始处置', to: 'in_progress' }, in_progress: { label: '提交复核', to: 'pending_review' }, pending_review: { label: '通过复核', to: 'completed' },
  };
  return transitions[status] ?? null;
}

function ModuleHeader({ meta, action, disabled, onAction }: { meta: [string, string, string]; action?: string; disabled?: boolean; onAction?: () => void }) {
  return <section className="module-hero"><div><small>{meta[0]}</small><h1>{meta[1]}</h1><p>{meta[2]}</p></div>{action && <button className="primary" disabled={disabled} onClick={onAction}>{action}</button>}</section>;
}

function PermissionNotice({ role }: { role: UserRole }) {
  const text = role === 'administrator' ? '管理员：可维护阈值、处置业务与导出报告。' : role === 'operator' ? '运维员：可处置告警、创建与流转工单、导出报告；不能改阈值。' : '查看者：仅可浏览和导出，业务处置与配置已被数据层拒绝。';
  return <p className="module-note">{text}</p>;
}

function ExportCenter({ exportReport }: { exportReport: (report: ReportKind, format: ExportFormat) => void }) {
  const reports: Array<[ReportKind, string]> = [['alerts', '告警清单'], ['workOrders', '工单清单'], ['assets', '设备台账'], ['daily', '运行日报']];
  return <section className="card export-center"><div><small>EXPORT CENTER</small><h2>答辩资料导出</h2><p>下载不会上传任何数据；每一次导出都会保留本地审计记录。</p></div><div className="export-list">{reports.map(([report, label]) => <div key={report}><b>{label}</b><button onClick={() => exportReport(report, 'csv')}>CSV</button><button onClick={() => exportReport(report, 'json')}>JSON</button></div>)}</div></section>;
}

type ModuleProps = {
  active: string;
  state: OperationsState;
  dispatch: (action: OperationsAction) => OperationsState;
  go: (id: string) => void;
  notify: (text: string) => void;
  exportReport: (report: ReportKind, format: ExportFormat) => void;
};

function ModuleView({ active, state, dispatch, go, notify, exportReport }: ModuleProps) {
  const meta = moduleHeadings[active];
  const [selectedCode, setSelectedCode] = useState('FAN-01');
  const [assetQuery, setAssetQuery] = useState('');
  const [zone, setZone] = useState('全部区域');
  const [assetStatus, setAssetStatus] = useState('全部状态');
  const [auditQuery, setAuditQuery] = useState('');
  const [manualAsset, setManualAsset] = useState('FAN-01');
  const [manualTitle, setManualTitle] = useState('执行日常巡检与状态复核');
  const selectedAsset = state.assets.find((asset) => asset.code === selectedCode) ?? state.assets[0];
  const selectedTelemetry = state.telemetry.find((reading) => reading.assetCode === selectedAsset?.code);
  const linkedOrders = new Set(state.workOrders.map((order) => order.sourceAlertId).filter(Boolean));
  const allowed = (action: OperationsAction['type']) => canPerform(state.session.role, action);
  const moveOrder = (order: WorkOrder) => {
    const next = nextOrderAction(order.status);
    if (!next || !allowed('workOrder.transition')) return;
    dispatch({ type: 'workOrder.transition', workOrderId: order.id, to: next.to, actor });
    notify(`${order.code} 已${next.label}${next.to === 'completed' ? '，来源告警已自动闭环' : ''}`);
  };

  if (active === 'twin' && selectedAsset) {
    const relatedAlert = state.alerts.find((alert) => alert.assetCode === selectedAsset.code && !['resolved', 'closed'].includes(alert.status));
    return <section className="module-page">
      <ModuleHeader meta={meta} action="回到全景" onAction={() => { setSelectedCode('FAN-01'); notify('已回到管廊全景视角'); }} />
      <PermissionNotice role={state.session.role} />
      <div className="twin-layout"><article className="twin-stage"><div className="stage-toolbar"><button className="active" onClick={() => setSelectedCode('FAN-01')}>全景</button>{['UT-ZA', 'UT-ZB', 'UT-ZC'].map((item) => <button key={item} onClick={() => setSelectedCode(state.assets.find((asset) => asset.zone === item)?.code ?? selectedCode)}>{item}</button>)}<span>点击区域或设备定位 · 演示数据每 5 秒刷新</span></div><div className="twin-map"><i className="lane l1" /><i className="lane l2" /><i className="lane l3" /><i className="pipe-line pl1" /><i className="pipe-line pl2" />{state.assets.slice(0, 3).map((asset, index) => <button type="button" key={asset.code} className={`map-tag ${asset.status !== 'normal' ? 'watch' : ''} t${index + 1}`} onClick={() => { setSelectedCode(asset.code); notify(`已定位 ${asset.code}`); }}>{asset.code}</button>)}<div className="map-compass">N<br /><b>⌃</b></div></div><div className="stage-foot"><span><i className="good-dot" />运行正常 {state.assets.filter((asset) => asset.status === 'normal').length}</span><span><i className="watch-dot" />异常高亮 {state.assets.filter((asset) => asset.status !== 'normal').length}</span><span>模型 V0.3 · 本地模拟数据</span></div></article><aside className="inspector"><small>SELECTED ASSET</small><div className="asset-orb">{selectedAsset.code.slice(0, 1)}</div><h2>{selectedAsset.code}</h2><p>{selectedAsset.zone} · {selectedAsset.type}</p><div className="inspector-state"><i />{statusLabel(selectedAsset.status)} <span>{selectedTelemetry ? `${selectedTelemetry.value} ${selectedTelemetry.unit}` : '暂无读数'}</span></div><dl><div><dt>供电状态</dt><dd>{selectedAsset.status === 'offline' ? '异常' : '正常'}</dd></div><div><dt>最近心跳</dt><dd>{formatTime(selectedAsset.lastSeenAt)}</dd></div><div><dt>映射网格</dt><dd>{selectedAsset.mesh}</dd></div></dl>{relatedAlert && <button className="outline twin-alert-link" onClick={() => go('alerts')}>查看关联告警 {relatedAlert.code}　→</button>}<button className="outline" onClick={() => go('assets')}>查看设备台账　→</button></aside></div>
    </section>;
  }

  if (active === 'alerts') {
    const openAlerts = state.alerts.filter((alert) => alert.status === 'open');
    return <section className="module-page"><ModuleHeader meta={meta} action="导出告警 CSV" onAction={() => exportReport('alerts', 'csv')} /><PermissionNotice role={state.session.role} /><p className="module-note">确认告警只改变事件状态；是否创建工单由“关联工单”单独控制，避免模块职责重叠。</p><div className="alert-summary"><article><i className="critical" /><b>{state.alerts.filter((alert) => alert.severity === 'critical' && alert.status !== 'closed').length.toString().padStart(2, '0')}</b><span>紧急告警</span></article><article><i className="warning" /><b>{openAlerts.length.toString().padStart(2, '0')}</b><span>待确认预警</span></article><article><i className="closed" /><b>{state.alerts.filter((alert) => ['closed', 'resolved'].includes(alert.status)).length.toString().padStart(2, '0')}</b><span>已恢复 / 关闭</span></article><div><span>浏览器本地数据</span><button onClick={() => notify('当前显示全部区域')}>全部区域</button><button onClick={() => notify('当前显示最近 24 小时')}>最近 24 小时</button></div></div><article className="card table-card"><div className="table-head"><span>事件</span><span>位置 / 资产</span><span>触发时间</span><span>状态</span><span>处置</span></div>{state.alerts.map((alert) => <div className="alert-row" key={alert.id}><div><b>{alert.code}</b><small>{alert.title}</small></div><span>{state.assets.find((asset) => asset.code === alert.assetCode)?.zone} / {alert.assetCode}</span><time>{formatTime(alert.openedAt)}</time><em className={alert.status === 'open' ? alert.severity : alert.status === 'acknowledged' ? 'blue' : 'closed'}>{statusLabel(alert.status)}</em><div className="row-actions">{alert.status === 'open' && <button className="row-action" disabled={!allowed('alert.acknowledge')} onClick={() => { dispatch({ type: 'alert.acknowledge', alertId: alert.id, actor }); notify(`${alert.code} 已确认并写入审计`); }}>确认</button>}{linkedOrders.has(alert.id) ? <button className="row-action muted" onClick={() => go('orders')}>查看工单</button> : <button className="row-action" disabled={!allowed('workOrder.create')} onClick={() => { dispatch({ type: 'workOrder.create', alertId: alert.id, actor }); notify(`${alert.code} 已创建关联工单`); }}>关联工单</button>}</div></div>)}</article></section>;
  }

  if (active === 'orders') {
    const unlinkedAlert = state.alerts.find((alert) => !linkedOrders.has(alert.id) && alert.status !== 'closed');
    const columns: Array<{ name: string; statuses: WorkOrderStatus[] }> = [{ name: '待派发', statuses: ['open', 'assigned'] }, { name: '处理中', statuses: ['in_progress'] }, { name: '待复核', statuses: ['pending_review'] }];
    const createManual = () => { if (!manualTitle.trim()) { notify('请填写工单标题'); return; } dispatch({ type: 'workOrder.createManual', assetCode: manualAsset, title: manualTitle, actor }); notify('手工工单已创建并写入审计'); };
    return <section className="module-page"><ModuleHeader meta={meta} action="从告警创建工单" disabled={!allowed('workOrder.create')} onAction={() => { if (!unlinkedAlert) { notify('没有可创建的未关联告警'); return; } dispatch({ type: 'workOrder.create', alertId: unlinkedAlert.id, actor }); notify(`已从 ${unlinkedAlert.code} 创建工单`); }} /><PermissionNotice role={state.session.role} /><section className="card create-order"><div><small>MANUAL WORK ORDER</small><h2>新建手工工单</h2><p>适用于未由告警触发的计划巡检；告警来源工单仍在告警中心创建。</p></div><select value={manualAsset} disabled={!allowed('workOrder.createManual')} onChange={(event) => setManualAsset(event.target.value)} aria-label="选择工单资产">{state.assets.map((asset) => <option key={asset.code} value={asset.code}>{asset.code} · {asset.name}</option>)}</select><input value={manualTitle} disabled={!allowed('workOrder.createManual')} onChange={(event) => setManualTitle(event.target.value)} aria-label="工单标题" /><button className="primary" disabled={!allowed('workOrder.createManual')} onClick={createManual}>新建工单</button></section><p className="module-note">工单状态必须按“派发 → 处置 → 复核 → 完成”顺序流转；完成来源工单会自动闭环其告警并刷新设备状态。</p><div className="kanban">{columns.map((column) => <article className="order-column" key={column.name}><div className="kanban-head"><span>{column.name}</span><b>{state.workOrders.filter((order) => column.statuses.includes(order.status)).length.toString().padStart(2, '0')}</b></div>{state.workOrders.filter((order) => column.statuses.includes(order.status)).map((order) => <WorkOrderTicket key={order.id} order={order} disabled={!allowed('workOrder.transition')} onMove={() => moveOrder(order)} />)}</article>)}<article><div className="kanban-done"><span>今日闭环</span><b>{state.workOrders.filter((order) => order.status === 'completed').length.toString().padStart(2, '0')}</b><p>处置链路<br /><strong>审计留痕</strong></p><button onClick={() => exportReport('workOrders', 'csv')}>导出清单 →</button></div></article></div></section>;
  }

  if (active === 'assets') {
    const filteredAssets = state.assets.filter((asset) => (zone === '全部区域' || asset.zone === zone) && (assetStatus === '全部状态' || asset.status === assetStatus) && `${asset.code}${asset.name}${asset.zone}`.toLowerCase().includes(assetQuery.toLowerCase()));
    return <section className="module-page"><ModuleHeader meta={meta} action="导出资产 CSV" onAction={() => exportReport('assets', 'csv')} /><PermissionNotice role={state.session.role} /><div className="asset-filters"><label className="search">⌕ <input value={assetQuery} onChange={(event) => setAssetQuery(event.target.value)} placeholder="搜索资产编码、名称或位置" aria-label="搜索资产" /></label><select value={zone} onChange={(event) => setZone(event.target.value)} aria-label="按区域筛选"><option>全部区域</option>{Array.from(new Set(state.assets.map((asset) => asset.zone))).map((item) => <option key={item}>{item}</option>)}</select><select value={assetStatus} onChange={(event) => setAssetStatus(event.target.value)} aria-label="按状态筛选"><option>全部状态</option><option value="normal">运行正常</option><option value="warning">预警</option><option value="alarm">告警</option><option value="offline">离线</option></select><span>匹配 {filteredAssets.length} 项资产</span></div><article className="card table-card asset-table"><div className="table-head"><span>资产</span><span>区域</span><span>类型</span><span>运行状态</span><span>最后更新</span></div>{filteredAssets.map((asset) => <div className="asset-row" key={asset.code}><div className="asset-cell"><i>{asset.code.slice(0, 1)}</i><span><b>{asset.code}</b><small>{asset.name}</small></span></div><span>{asset.zone}</span><span>{asset.type}</span><em className={assetTone(asset.status)}>{statusLabel(asset.status)}</em><time>{formatTime(asset.lastSeenAt)}</time></div>)}{filteredAssets.length === 0 && <div className="table-empty">没有匹配的资产，请调整搜索或筛选条件。</div>}</article></section>;
  }

  if (active === 'insights') {
    const completeness = state.assets.length ? Math.round((state.assets.filter((asset) => asset.status !== 'offline').length / state.assets.length) * 1000) / 10 : 0;
    return <section className="module-page"><ModuleHeader meta={meta} action="导出运行日报 JSON" onAction={() => exportReport('daily', 'json')} /><PermissionNotice role={state.session.role} /><div className="insight-grid"><article className="card line-chart"><div className="card-head"><div><small>TELEMETRY TREND</small><h2>UT-ZB 环境与设备信号</h2></div><button onClick={() => notify('趋势图来自本地模拟遥测')}>每 5 秒更新</button></div><div className="line-area"><i /><i /><i /><i /><b /><em /></div><div className="chart-axis"><span>5 个周期前</span><span>当前第 {state.revision + 1} 次采样</span><span>本地模拟</span></div></article><article className="card composition"><small>EVENT COMPOSITION</small><h2>当前事件构成</h2><div className="donut"><b>{state.alerts.length}<small>告警</small></b></div><p><i />紧急 {state.alerts.filter((alert) => alert.severity === 'critical').length}　<i />预警 {state.alerts.filter((alert) => alert.severity === 'warning').length}　<i />工单 {state.workOrders.length}</p></article></div><section className="metrics insight-metrics"><article className="metric blue"><div><span>遥测完整率</span><i>↗</i></div><b>{completeness}<small>%</small></b><p>实时<span> 浏览器模拟</span></p></article><article className="metric mint"><div><span>在线资产</span><i>↗</i></div><b>{state.assets.filter((asset) => asset.status !== 'offline').length}<small> 项</small></b><p>可用<span> 共 {state.assets.length} 项</span></p></article><article className="metric violet"><div><span>告警确认率</span><i>↗</i></div><b>{state.alerts.length ? Math.round((state.alerts.filter((alert) => alert.status !== 'open').length / state.alerts.length) * 100) : 0}<small>%</small></b><p>联动<span> 审计可追溯</span></p></article></section><ExportCenter exportReport={exportReport} /></section>;
  }

  if (active === 'audit') {
    const records = state.audit.filter((entry) => `${entry.actor}${entry.action}${entry.resource}${entry.detail}`.toLowerCase().includes(auditQuery.toLowerCase()));
    return <section className="module-page"><ModuleHeader meta={meta} /><PermissionNotice role={state.session.role} /><div className="audit-filter"><button className="selected-filter" onClick={() => setAuditQuery('')}>全部操作</button><button onClick={() => setAuditQuery('alert')}>告警流转</button><button onClick={() => setAuditQuery('work_order')}>工单流转</button><button onClick={() => setAuditQuery('threshold')}>配置变更</button><label>⌕ <input value={auditQuery} onChange={(event) => setAuditQuery(event.target.value)} placeholder="检索审计记录" aria-label="检索审计记录" /></label></div><article className="card audit-card">{records.map((entry) => <div className="audit-row" key={entry.id}><time>{formatTime(entry.occurredAt)}</time><i className={entry.action.startsWith('alert') ? 'alert' : entry.action.startsWith('work_order') ? 'order' : 'data'}>{entry.actor.slice(0, 1)}</i><div><b>{entry.action} <small>· {entry.actor}</small></b><p>{entry.detail}（{entry.resource}）</p></div><button onClick={() => notify(`审计编号：${entry.id}`)}>查看</button></div>)}{records.length === 0 && <div className="table-empty">没有匹配的审计记录。</div>}</article></section>;
  }

  return <SettingsView meta={meta} role={state.session.role} thresholds={state.thresholds} dispatch={dispatch} notify={notify} />;
}

function WorkOrderTicket({ order, disabled, onMove }: { order: WorkOrder; disabled: boolean; onMove: () => void }) {
  const next = nextOrderAction(order.status);
  return <div className={`ticket ${order.priority === 'urgent' ? 'high' : ''} ${order.status === 'in_progress' ? 'active-ticket' : ''} ${order.status === 'pending_review' ? 'review' : ''}`}><small>{order.code} · {order.priority === 'urgent' ? '紧急' : order.priority === 'high' ? '高优先级' : '常规'}</small><h3>{order.title}</h3><p>关联资产　{order.assetCode}</p><footer><span>{order.dueAt}</span><i>{statusLabel(order.status)}</i></footer>{next && <button className="ticket-action" disabled={disabled} onClick={onMove}>{next.label}</button>}</div>;
}

function SettingsView({ meta, role, thresholds, dispatch, notify }: { meta: [string, string, string]; role: UserRole; thresholds: OperationsState['thresholds']; dispatch: (action: OperationsAction) => OperationsState; notify: (text: string) => void }) {
  const [drafts, setDrafts] = useState<Record<string, { warning: string; alarm: string }>>({});
  const canUpdate = canPerform(role, 'threshold.update');
  const saveThreshold = (key: string) => {
    const source = thresholds.find((item) => item.key === key);
    if (!source) return;
    const draft = drafts[key] ?? { warning: String(source.warning), alarm: String(source.alarm) };
    const warning = Number(draft.warning);
    const alarm = Number(draft.alarm);
    if (!Number.isFinite(warning) || !Number.isFinite(alarm) || warning >= alarm || warning < 0) { notify('阈值无效：预警值须小于报警值，且不能为负数'); return; }
    dispatch({ type: 'threshold.update', key, warning, alarm, actor });
    notify(`${source.label} 阈值已保存并写入审计`);
  };
  return <section className="module-page"><ModuleHeader meta={meta} /><PermissionNotice role={role} /><p className="module-note">阈值编辑只负责规则配置；保存后生成独立审计记录，不直接改变告警或工单。</p><div className="settings-layout"><article className="card settings-nav"><b>规则与策略</b><button className="current">报警阈值</button><button onClick={() => notify('联动策略将在接入后端规则引擎时开放')}>联动策略</button><button onClick={() => notify('数据质量规则由模拟数据层统一维护')}>数据质量</button><b>模型与权限</b><button onClick={() => notify('资产映射已在数字孪生模块展示')}>资产映射</button><button onClick={() => notify('当前可在顶部切换演示角色')}>角色权限</button></article><article className="card setting-form"><div className="card-head"><div><small>ALARM THRESHOLDS</small><h2>报警阈值</h2></div><span>本地版本</span></div>{thresholds.map((threshold) => { const draft = drafts[threshold.key]; return <div className="setting-row" key={threshold.key}><b>{threshold.label}</b><label>预警 <input type="number" disabled={!canUpdate} value={draft?.warning ?? threshold.warning} onChange={(event) => setDrafts({ ...drafts, [threshold.key]: { warning: event.target.value, alarm: draft?.alarm ?? String(threshold.alarm) } })} /> {threshold.unit}</label><label>报警 <input type="number" disabled={!canUpdate} value={draft?.alarm ?? threshold.alarm} onChange={(event) => setDrafts({ ...drafts, [threshold.key]: { warning: draft?.warning ?? String(threshold.warning), alarm: event.target.value } })} /> {threshold.unit}</label><button disabled={!canUpdate} onClick={() => saveThreshold(threshold.key)}>保存</button></div>; })}</article></div></section>;
}

export default function Home() {
  const [active, setActive] = useState('overview');
  const [now, setNow] = useState('');
  const [toast, setToast] = useState('');
  const toastTimer = useRef<number | null>(null);
  const { state, dispatch, reset } = useOperations();
  const openAlerts = useMemo(() => state.alerts.filter((alert) => alert.status === 'open').length, [state.alerts]);
  const activeOrders = useMemo(() => state.workOrders.filter((order) => !['completed', 'cancelled'].includes(order.status)).length, [state.workOrders]);
  const telemetry = state.telemetry.find((reading) => reading.assetCode === 'FAN-01');
  const bars = Array.from({ length: 18 }, (_, index) => 38 + ((index * 13 + state.revision * 7) % 44));
  const onlineAssets = state.assets.filter((asset) => asset.status !== 'offline').length;
  const health = state.assets.length ? Math.round((onlineAssets / state.assets.length) * 1000) / 10 : 0;
  const notify = (text: string) => { if (toastTimer.current) window.clearTimeout(toastTimer.current); setToast(text); toastTimer.current = window.setTimeout(() => setToast(''), 2600); };
  const exportReport = (report: ReportKind, format: ExportFormat) => {
    const next = dispatch({ type: 'report.export', report, actor });
    const content = format === 'csv' ? toCsv(next, report) : toJson(next, report);
    const blob = new Blob([content], { type: format === 'csv' ? 'text/csv;charset=utf-8' : 'application/json;charset=utf-8' });
    const href = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = href;
    link.download = `ut-ops-${report}-${new Date().toISOString().slice(0, 10)}.${format}`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(href), 0);
    notify(`${format.toUpperCase()} 报表已下载，并已记入审计`);
  };
  useEffect(() => { const tick = () => setNow(new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date())); tick(); const timer = window.setInterval(tick, 1000); return () => window.clearInterval(timer); }, []);
  useEffect(() => () => { if (toastTimer.current) window.clearTimeout(toastTimer.current); }, []);
  return <main className="app"><aside className="side"><div className="brand"><span className="mark"><i /><i /><i /></span><span><b>UT / OPS</b><small>UTILITY TUNNEL</small></span></div><nav><p className="caption">运行工作台</p>{nav.slice(0, 4).map(([id, label, icon]) => <button key={id} className={`nav ${active === id ? 'selected' : ''}`} onClick={() => setActive(id)}><i>{icon}</i>{label}{id === 'alerts' && openAlerts > 0 && <em>{openAlerts}</em>}{id === 'orders' && activeOrders > 0 && <em>{activeOrders}</em>}</button>)}<p className="caption lower">资产与系统</p>{nav.slice(4).map(([id, label, icon]) => <button key={id} className={`nav ${active === id ? 'selected' : ''}`} onClick={() => setActive(id)}><i>{icon}</i>{label}</button>)}</nav><div className="user"><span>WL</span><div><b>{actor}</b><small>{roleLabels[state.session.role]}</small></div><button title="重置本地演示数据" onClick={() => { reset(); notify('本地演示数据已重置'); }}>↺</button></div></aside><section className="work"><header><div className="crumb">综合管廊 <i>/</i> <b>{labels[active]}</b></div><div className="top-actions"><span className="env"><i />演示环境</span><span className="data-source">本地持久化</span><label className="role-select">角色 <select value={state.session.role} onChange={(event) => { const role = event.target.value as UserRole; dispatch({ type: 'session.switchRole', role }); notify(`已切换为${roleLabels[role]}，权限已刷新`); }} aria-label="切换演示角色">{(Object.keys(roleLabels) as UserRole[]).map((role) => <option key={role} value={role}>{roleLabels[role]}</option>)}</select></label><button className="bell" onClick={() => { setActive('alerts'); notify(`目前有 ${openAlerts} 项待确认告警`); }}>♧<b>{openAlerts}</b></button><span className="face">WL</span></div></header><div className="page">{active === 'overview' ? <><section className="hero"><div><small>CONTROL ROOM · {now}</small><h1>运行，一眼掌握</h1><p>本地模拟数据持续刷新；关键操作会同步写入浏览器持久化和审计记录。</p></div><button className="primary" onClick={() => exportReport('daily', 'json')}><i>↓</i>导出运行快照</button></section><section className="metrics">{[['在线设备', String(onlineAssets), `/ ${state.assets.length}`, `${health}%`, 'blue'], ['环境健康度', String(health), '%', '模拟数据', 'mint'], ['待确认事件', String(openAlerts).padStart(2, '0'), '项', '需关注', 'amber'], ['进行中工单', String(activeOrders).padStart(2, '0'), '项', '状态可追踪', 'violet']].map(([label, value, suffix, delta, tone]) => <article className={`metric ${tone}`} key={label}><div><span>{label}</span><i>↗</i></div><b>{value}<small>{suffix}</small></b><p>{delta}<span> 当前数据层</span></p></article>)}</section><section className="two"><article className="card"><div className="card-head"><div><small>TWIN PULSE</small><h2>管廊实时态势</h2></div><button onClick={() => setActive('twin')}>进入孪生视图　<span>→</span></button></div><div className="tunnel"><div className="grid" /><i className="arch a1" /><i className="arch a2" /><i className="arch a3" /><i className="pipe p1" /><i className="pipe p2" /><i className="pipe p3" />{state.assets.slice(0, 3).map((asset, index) => <b className={`node ${asset.status !== 'normal' ? 'watch' : ''} n${index + 1}`} key={asset.code}>{asset.code}</b>)}<div className="legend"><span><i />正常 {state.assets.filter((asset) => asset.status === 'normal').length}</span><span><i />关注 {state.assets.filter((asset) => asset.status !== 'normal').length}</span></div></div></article><article className="card signal"><div className="card-head"><div><small>LIVE SIGNAL</small><h2>设备环境信号</h2></div><span className="live">每 5 秒</span></div><div className="temp"><b>{telemetry?.value ?? '--'}</b><span>{telemetry?.unit}</span><small>FAN-01 · 风机转速</small></div><div className="bars">{bars.map((height, index) => <i key={index} className={index > 11 ? 'new' : ''} style={{ height: `${height}%` }} />)}</div><div className="range"><span>历史模拟</span><b>可信质量：良好</b><span>当前</span></div></article></section><section className="two bottom"><article className="card stream"><div className="card-head"><div><small>ACTIVITY STREAM</small><h2>最新运行动态</h2></div><button onClick={() => setActive('audit')}>审计追踪　<span>→</span></button></div><div className="log-list">{state.audit.slice(0, 4).map((entry) => <div className="log" key={entry.id}><i className={entry.action.startsWith('alert') ? 'warn' : entry.action.startsWith('work_order') ? 'blue' : 'good'} /><time>{formatTime(entry.occurredAt)}</time><div><b>{entry.action}</b><p>{entry.detail}</p></div></div>)}</div></article><article className="readiness"><small>SYSTEM READINESS</small><h2>演示就绪度</h2><div><b>94</b><span>/ 100</span></div><i className="progress"><em /></i><p>告警、工单、资产、审计及角色控制已由统一本地数据模型联动。</p><button onClick={() => setActive('insights')}>导出答辩资料　<span>→</span></button></article></section></> : <ModuleView active={active} state={state} dispatch={dispatch} go={setActive} notify={notify} exportReport={exportReport} />}</div></section>{toast && <div className="toast">{toast}</div>}</main>;
}
