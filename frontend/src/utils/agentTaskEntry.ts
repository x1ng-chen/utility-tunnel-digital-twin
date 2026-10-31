export type AgentTaskKind = 'inspection' | 'diagnosis' | 'draft' | 'review';
export type AgentTaskEntry = {kind: AgentTaskKind; station: string; asset: string; order: string; alert: string};
const kinds = new Set(['inspection', 'diagnosis', 'draft', 'review']);
const identifier = /^[A-Z0-9][A-Z0-9_-]{1,79}$/;
const single = (value: unknown) => typeof value === 'string' ? value : '';

/** URL parameters prepare a form only. They never start a run or grant permission. */
export function readAgentTaskEntry(query: Record<string, unknown>): AgentTaskEntry | null {
  if (['task','station','asset','order','alert'].some(key => query[key] != null && typeof query[key] !== 'string')) return null;
  const kind = single(query.task);
  if (!kinds.has(kind)) return null;
  const station = single(query.station) || (kind === 'inspection' ? 'all' : 'P5');
  if (!/^(all|P[1-5])$/.test(station)) return null;
  const asset = single(query.asset), order = single(query.order), alert = single(query.alert);
  if ([asset, order, alert].some(value => value && !identifier.test(value))) return null;
  return {kind:kind as AgentTaskKind, station, asset, order, alert};
}

export function agentTaskLocation(kind: AgentTaskKind, input: Partial<Omit<AgentTaskEntry, 'kind'>> = {}) {
  const query: Record<string, string> = {task:kind};
  for (const key of ['station', 'asset', 'order', 'alert'] as const) if (input[key]) query[key] = input[key]!;
  return {path:'/agent-workbench', query};
}

export function agentTaskPrompt(entry: AgentTaskEntry) {
  if (entry.kind === 'inspection') return '巡检P1到P5的31路物理传感器：核对覆盖、数据质量和时间，列出异常与缺项，提供可核查证据及设备定位。';
  if (entry.kind === 'review') return `只读复核${entry.order ? `工单${entry.order}` : '所选工单'}：对照处置前后的新鲜观测、活动告警和实际反馈，列出恢复依据及缺项，不自动结单。`;
  if (entry.kind === 'draft') return `核查${entry.asset ? `资产${entry.asset}` : '所选资产'}的证据和已有工单，检索适用规程，生成待人工确认的工单草案，不直接创建。`;
  return `排查${entry.station === 'all' ? '当前检测范围' : entry.station}${entry.alert ? `告警${entry.alert}` : '异常'}${entry.asset ? `，先核对资产${entry.asset}当前归属` : ''}：自主查询本站、邻站、风机反馈和控制记录，检索适用规程；区分事实、候选原因、反证、缺项和下一项检查，交独立复核。`;
}
