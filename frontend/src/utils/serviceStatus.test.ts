import { describe, expect, it } from 'vitest';
import { serviceStatus } from './serviceStatus';

describe('数据服务状态展示', () => {
  it('首次同步前不宣称在线', () => {
    expect(serviceStatus('api', false, null)).toEqual({ label: '连接中', tone: 'pending' });
  });
  it('成功同步只说明数据服务已连接', () => {
    expect(serviceStatus('api', false, '2026-09-07T00:00:00Z')).toEqual({ label: '已连接', tone: 'online' });
  });
  it('离线优先于历史同步记录', () => {
    expect(serviceStatus('api', true, '2026-09-07T00:00:00Z').label).toBe('离线快照');
  });
  it('演示状态不会被标记为真实在线', () => {
    expect(serviceStatus('demo', false, '2026-09-07T00:00:00Z').label).toBe('演示数据');
  });
});
