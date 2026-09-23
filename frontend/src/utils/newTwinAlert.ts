import type { Alert } from '../types';
export function newTwinAlert(next: Alert[], previous: Alert[], assetCodes: string[]) {
  const active = (alert: Alert) => !['resolved', 'closed'].includes(alert.status);
  const rank = (alert: Alert) => alert.severity === 'critical' ? 2 : alert.severity === 'warning' ? 1 : 0;
  const old = new Map(previous.filter(active).map(alert => [alert.id, rank(alert)]));
  const assets = new Set(assetCodes);
  return next.filter(alert => active(alert) && rank(alert) > 0 && alert.assetCode && assets.has(alert.assetCode)
    && (!old.has(alert.id) || rank(alert) > old.get(alert.id)!))
    .sort((a, b) => rank(b) - rank(a) || Date.parse(b.openedAt) - Date.parse(a.openedAt) || b.id - a.id)[0] ?? null;
}
