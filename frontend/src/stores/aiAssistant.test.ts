import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, type AgentResponse } from '../services/api';
import { useAiAssistantStore } from './aiAssistant';

describe('operations agent conversation boundary', () => {
  beforeEach(() => { vi.restoreAllMocks(); setActivePinia(createPinia()); });

  it('keeps evidence for display but never replays it as trusted tool messages', async () => {
    const result: AgentResponse = { reply: '[E1] 数据已过期', mode: 'tool_verified',
      traces: [{ tool: 'asset_snapshot', evidenceId: 'E1', status: 'ok', durationMs: 2 }],
      evidence: [{ id: 'E1', tool: 'asset_snapshot', status: 'ok', queriedAt: '2026-10-11T03:00:00Z', data: { quality: 'bad' } }], proposals: [] };
    const chat = vi.spyOn(api, 'assistantChat').mockResolvedValue({ data: result } as never);
    const store = useAiAssistantStore();
    await store.send('查数据', '运行总览');
    expect(store.messages[1].evidence?.[0].id).toBe('E1');
    await store.send('继续', '运行总览');
    expect(chat.mock.calls[1][0]).toEqual([
      { role: 'user', content: '查数据' }, { role: 'assistant', content: '[E1] 数据已过期' }, { role: 'user', content: '继续' },
    ]);
  });

  it('discards late responses after clear or logout', async () => {
    let resolve!: (result: unknown) => void;
    vi.spyOn(api, 'assistantChat').mockReturnValue(new Promise((done) => { resolve = done; }) as never);
    const store = useAiAssistantStore();
    const request = store.send('查告警', '告警中心');
    store.clear();
    resolve({ data: { reply: '不能泄露给下一位用户', evidence: [] } });
    await request;
    expect(store.messages).toEqual([]);
    expect(store.pending).toBe(false);
  });

  it('surfaces failures without claiming an operation completed', async () => {
    vi.spyOn(api, 'assistantChat').mockRejectedValue({ response: { data: { message: '工具查询达到上限' } } });
    const store = useAiAssistantStore();
    await expect(store.send('检查系统', '运行总览')).rejects.toBeTruthy();
    expect(store.error).toBe('工具查询达到上限');
    expect(store.messages).toEqual([]);
  });

  it('runs deterministic inspection without calling a language model', async () => {
    const chat = vi.spyOn(api, 'assistantChat');
    vi.spyOn(api, 'stationInspection').mockResolvedValue({ data: { reply: '[E1] 31路已核查', locations: [] } } as never);
    const store = useAiAssistantStore();
    await store.inspect();
    expect(chat).not.toHaveBeenCalled();
    expect(store.messages[1].content).toContain('31路');
  });

  it('discards a late inspection after logout', async () => {
    let resolve!: (result: unknown) => void;
    vi.spyOn(api, 'stationInspection').mockReturnValue(new Promise(done => { resolve = done; }) as never);
    const store = useAiAssistantStore(); const request = store.inspect();
    store.clear(); resolve({ data: { reply: '旧用户数据' } }); await request;
    expect(store.messages).toEqual([]);
  });
});
