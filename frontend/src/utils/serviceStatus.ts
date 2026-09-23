export function serviceStatus(source: 'demo' | 'api', offline: boolean, lastSyncedAt: string | null) {
  if (source !== 'api') return { label: '演示数据', tone: 'pending' };
  if (offline) return { label: '离线快照', tone: 'offline' };
  if (!lastSyncedAt) return { label: '连接中', tone: 'pending' };
  return { label: '已连接', tone: 'online' };
}
