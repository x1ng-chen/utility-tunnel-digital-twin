import { describe, expect, it } from 'vitest';
import type { Alert } from '../types';
import { newTwinAlert } from './newTwinAlert';
const alert: Alert = { id: 1, code: 'ALM-1', assetCode: 'A', severity: 'warning', status: 'open', title: '告警', detail: '', category: '环境', openedAt: '2026-09-09T00:00:00Z' };
describe('new twin alarm focus policy', () => {
  it('does not refocus on unchanged polling, acknowledgement or resolution', () => {
    expect(newTwinAlert([{ ...alert }], [alert], ['A'])).toBeNull();
    expect(newTwinAlert([{ ...alert, status: 'acknowledged' }], [alert], ['A'])).toBeNull();
    expect(newTwinAlert([{ ...alert, status: 'resolved' }], [alert], ['A'])).toBeNull();
  });
  it('focuses new alarms, reopened alarms and severity escalation', () => {
    expect(newTwinAlert([alert], [], ['A'])?.id).toBe(1);
    expect(newTwinAlert([alert], [{ ...alert, status: 'resolved' }], ['A'])?.id).toBe(1);
    expect(newTwinAlert([{ ...alert, severity: 'critical' }], [alert], ['A'])?.id).toBe(1);
  });
  it('prioritizes critical events and rejects unbound or information events', () => {
    expect(newTwinAlert([alert, { ...alert, id: 2, severity: 'critical' }], [], ['A'])?.id).toBe(2);
    expect(newTwinAlert([alert], [], ['B'])).toBeNull();
    expect(newTwinAlert([{ ...alert, severity: 'info' }], [], ['A'])).toBeNull();
  });
});
