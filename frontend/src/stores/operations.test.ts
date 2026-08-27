import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from './auth';
import { useOperationsStore } from './operations';

describe('operations store', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('starts with the connected demo model', () => {
    const store = useOperationsStore();
    expect(store.assets).toHaveLength(4);
    expect(store.openAlerts).toBe(2);
    expect(store.activeOrders).toBe(2);
  });

  it('rejects invalid threshold ranges and records valid changes', async () => {
    const store = useOperationsStore();
    const threshold = store.thresholds[0];
    await expect(store.updateThreshold(threshold, 40, 30)).rejects.toThrow('报警阈值必须大于预警阈值');
    await expect(store.updateThreshold(threshold, Number.NaN, 40)).rejects.toThrow('报警阈值必须大于预警阈值');
    await store.updateThreshold(threshold, 30, 36);
    expect(threshold.warning).toBe(30);
    expect(threshold.alarm).toBe(36);
    expect(threshold.version).toBe(2);
  });

  it('keeps the demo alert, work-order and audit models in sync', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'administrator', 'demo');
    const store = useOperationsStore();
    const alert = store.alerts.find((item) => item.id === 3)!;
    await store.acknowledge(alert);
    const order = await store.createAlertOrder(alert);
    expect(order).toBeDefined();
    await store.transition(order!, 'assigned');
    await store.transition(order!, 'in_progress');
    await store.transition(order!, 'pending_review');
    await store.transition(order!, 'completed');
    expect(alert.status).toBe('resolved');
    expect(store.assets.find((item) => item.code === alert.assetCode)?.status).toBe('normal');
    expect(store.audit.map((entry) => entry.action)).toEqual(expect.arrayContaining(['alert.acknowledged', 'work_order.created_from_alert', 'work_order.transitioned']));
  });

  it('creates a manual work order and records its linked asset', async () => {
    const auth = useAuthStore();
    await auth.login('', '', 'operator', 'demo');
    const store = useOperationsStore();
    const order = await store.createWorkOrder({ assetCode: 'GAS-01', title: '复核甲烷监测节点', description: '检查最近一次遥测质量。', priority: 'high' });
    expect(order.status).toBe('open');
    expect(order.assetCode).toBe('GAS-01');
    expect(store.workOrders[0].code).toBe(order.code);
    expect(store.audit[0].action).toBe('work_order.created_manual');
  });

  it('keeps a failed API snapshot read-only until the user reconnects', async () => {
    const store = useOperationsStore();
    store.offline = true;
    await expect(store.createWorkOrder({ assetCode: 'GAS-01', title: '不应写入', priority: 'normal' })).rejects.toThrow('只读状态');
  });
});
