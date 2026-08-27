import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
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
    await store.updateThreshold(threshold, 30, 36);
    expect(threshold.warning).toBe(30);
    expect(threshold.alarm).toBe(36);
    expect(threshold.version).toBe(2);
  });
});
