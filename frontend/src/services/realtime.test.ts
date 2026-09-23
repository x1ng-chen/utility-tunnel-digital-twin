import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createRealtimeClient, resolveWebSocketUrl, type RealtimeEvent } from './realtime';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  sent: string[] = [];
  closes: number[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) { MockWebSocket.instances.push(this); }
  send(data: string) { this.sent.push(data); }
  open() { this.onopen?.(); }
  receive(frame: unknown) { this.onmessage?.({ data: JSON.stringify(frame) }); }
  close(code = 1000) { this.closes.push(code); this.onclose?.({ code }); }
}
const frame = (seq: number) => ({ epoch: 'epoch-a', seq, type: 'alert', entityId: 1, version: seq, updatedAt: null, payload: { id: 1 } });
const control = (type: string, seq = 0) => ({ type, epoch: 'epoch-a', seq });
// Flush serial frame handling without advancing retry or handshake timers.
async function flush() { for (let i = 0; i < 40; i++) await Promise.resolve(); }
function setup(overrides: Partial<Parameters<typeof createRealtimeClient>[0]> = {}) {
  const events: RealtimeEvent[] = [];
  const client = createRealtimeClient({ apiBaseUrl: 'http://localhost:8000/api', getToken: () => 'secret-token',
    WebSocketImpl: MockWebSocket as unknown as typeof WebSocket, reconnectBaseDelayMs: 10,
    onEvent: event => { events.push(event); }, ...overrides });
  client.connect(); const socket = MockWebSocket.instances[0]!; socket.open();
  return { client, socket, events };
}
async function ready(socket: MockWebSocket) { socket.receive(control('reset')); socket.receive(control('ready')); await flush(); }

describe('realtime protocol', () => {
  beforeEach(() => { vi.useFakeTimers(); MockWebSocket.instances = []; });
  afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); });
  it('sends token only in auth frame, never URL', () => {
    const { socket } = setup();
    expect(socket.url).toBe('ws://localhost:8000/ws/events/');
    expect(JSON.parse(socket.sent[0]!)).toEqual({ type: 'auth', token: 'secret-token', cursor: 0 });
    expect(resolveWebSocketUrl('https://example.com/api/')).toBe('wss://example.com/ws/events/');
    for (const url of ['', 'ftp://example.com', 'https://u:p@example.com', 'https://example.com?token=x']) expect(() => resolveWebSocketUrl(url)).toThrow();
  });
  it('awaits snapshot reset before events and ready', async () => {
    let resolve!: () => void;
    const pending = new Promise<void>(r => { resolve = r; });
    const { socket, client, events } = setup({ onCursorInvalid: () => pending });
    socket.receive(control('reset', 5)); socket.receive(frame(6)); socket.receive(control('ready', 6)); await flush();
    expect(client.getState()).toBe('cursor_invalid'); expect(client.getLastSeq()).toBe(0); expect(events).toHaveLength(0);
    resolve(); await flush();
    expect(events.map(e => e.seq)).toEqual([6]); expect(client.getState()).toBe('connected'); expect(client.getLastSeq()).toBe(6);
  });
  it('replays acknowledged cursor and ignores duplicate sequences', async () => {
    const { socket, client, events } = setup(); await ready(socket);
    socket.receive(frame(1)); socket.receive(frame(1)); await flush(); socket.close(1006);
    await vi.advanceTimersByTimeAsync(10);
    const next = MockWebSocket.instances[1]!; next.open();
    expect(JSON.parse(next.sent[0]!)).toMatchObject({ epoch: 'epoch-a', cursor: 1 });
    next.receive(control('hello', 2)); next.receive(frame(1)); next.receive(frame(2)); next.receive(control('ready', 2)); await flush();
    expect(events.map(e => e.seq)).toEqual([1, 2]); expect(client.getState()).toBe('connected');
  });
  it('reconnects on gap without advancing cursor', async () => {
    const { socket, client, events } = setup(); await ready(socket); socket.receive(frame(2)); await flush();
    expect(socket.closes).toContain(4000); expect(client.getLastSeq()).toBe(0); expect(events).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(10); expect(MockWebSocket.instances).toHaveLength(2);
  });
  it('ignores obsolete socket messages after disconnect', async () => {
    const { socket, client, events } = setup(); await ready(socket); client.disconnect();
    socket.receive(frame(1)); await flush(); await vi.advanceTimersByTimeAsync(100);
    expect(events).toHaveLength(0); expect(client.getLastSeq()).toBe(0); expect(MockWebSocket.instances).toHaveLength(1);
  });
  it('does not advance or process queued frames when reset fails', async () => {
    const { socket, client, events } = setup({ onCursorInvalid: async () => { throw new Error('snapshot unavailable'); } });
    socket.receive(control('reset', 9)); socket.receive(frame(10)); socket.receive(control('ready', 10)); await flush();
    expect(client.getLastSeq()).toBe(0); expect(events).toHaveLength(0); expect(socket.closes).toContain(4000);
  });
  it.each([4401, 4403])('does not reconnect after auth rejection %s', async code => {
    const { socket, client } = setup(); socket.close(code); await vi.advanceTimersByTimeAsync(20000);
    expect(MockWebSocket.instances).toHaveLength(1); expect(client.getState()).toBe('disconnected');
  });
  it('recovers malformed JSON', async () => {
    const { socket, client } = setup(); await ready(socket); socket.onmessage?.({ data: '{broken' }); await flush();
    expect(socket.closes).toContain(4000); expect(client.getLastSeq()).toBe(0);
    await vi.advanceTimersByTimeAsync(10); expect(MockWebSocket.instances).toHaveLength(2);
  });
  it('does not acknowledge in-flight events after disconnect', async () => {
    let resolve!: () => void;
    const { socket, client } = setup({ onEvent: () => new Promise<void>(r => { resolve = r; }) }); await ready(socket);
    socket.receive(frame(1)); await flush(); expect(client.getLastSeq()).toBe(0);
    client.disconnect(); resolve(); await flush(); expect(client.getLastSeq()).toBe(0);
  });
});
