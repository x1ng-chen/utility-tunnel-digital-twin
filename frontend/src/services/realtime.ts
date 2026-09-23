/** Credentials travel in the first frame, never in a logged URL. */
export type RealtimeEventType = 'telemetry' | 'alert' | 'asset' | 'workOrder';
export type RealtimeState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'cursor_invalid';
export interface RealtimeEvent<T = unknown> {
  epoch: string; seq: number; type: RealtimeEventType; entityId: number | string;
  version: number | string; updatedAt: string | null; payload: T;
}
export interface RealtimeClientOptions {
  apiBaseUrl: string; getToken: () => string | null;
  onEvent?: (event: RealtimeEvent) => void | Promise<void>;
  onStateChange?: (state: RealtimeState) => void;
  onCursorInvalid?: () => void | Promise<void>;
  onUnauthorized?: () => void;
  reconnectBaseDelayMs?: number; reconnectMaxDelayMs?: number;
  WebSocketImpl?: typeof WebSocket;
}
export function resolveWebSocketUrl(apiBaseUrl: string): string {
  try {
    const base = new URL(apiBaseUrl);
    if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash) throw new Error();
    const url = new URL('/ws/events/', base);
    url.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.toString();
  } catch { throw new Error('实时数据服务地址无效。'); }
}
export function createRealtimeClient(options: RealtimeClientOptions) {
  const Impl = options.WebSocketImpl ?? (typeof WebSocket === 'undefined' ? undefined : WebSocket);
  let socket: WebSocket | null = null;
  let state: RealtimeState = 'idle';
  let stopped = true;
  let epoch: string | undefined;
  let lastSeq = 0;
  let attempt = 0;
  let generation = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let handshake: ReturnType<typeof setTimeout> | undefined;
  const setState = (next: RealtimeState) => { state = next; options.onStateChange?.(next); };
  function clearHandshake() { if (handshake) clearTimeout(handshake); handshake = undefined; }
  function open() {
    if (stopped || socket || !Impl) return;
    const token = options.getToken();
    if (!token) { setState('disconnected'); return; }
    setState('connecting');
    const mine = ++generation;
    let ws: WebSocket;
    try { ws = new Impl(resolveWebSocketUrl(options.apiBaseUrl)); }
    catch { reconnect(); return; }
    socket = ws;
    let chain = Promise.resolve();
    let queued = 0;
    const active = () => !stopped && generation === mine && socket === ws;
    const recover = () => { if (active()) ws.close(4000, 'resync'); };
    handshake = setTimeout(recover, 10000);
    ws.onopen = () => { if (active()) ws.send(JSON.stringify({ type: 'auth', token, epoch, cursor: lastSeq })); };
    ws.onmessage = (message) => {
      if (!active()) return;
      if (++queued > 2000) { recover(); return; }
      chain = chain.then(async () => {
        if (!active()) return;
        const frame = JSON.parse(String(message.data));
        if (!frame || typeof frame.epoch !== 'string' || !Number.isSafeInteger(frame.seq) || frame.seq < 0) throw new Error('invalid frame');
        if (frame.type === 'hello') return;
        if (frame.type === 'reset') {
          setState('cursor_invalid');
          await options.onCursorInvalid?.();
          if (!active()) return;
          epoch = frame.epoch; lastSeq = frame.seq;
          return;
        }
        if (frame.type === 'ready') {
          if (epoch !== frame.epoch || lastSeq !== frame.seq) throw new Error('incomplete replay');
          clearHandshake(); attempt = 0; setState('connected'); return;
        }
        if (frame.epoch !== epoch) throw new Error('stream changed');
        if (frame.seq <= lastSeq) return;
        if (frame.seq !== lastSeq + 1) throw new Error('stream gap');
        if (!['telemetry', 'alert', 'asset', 'workOrder'].includes(frame.type) ||
            !frame.payload || typeof frame.payload !== 'object' || frame.entityId == null ||
            String(frame.payload.id) !== String(frame.entityId)) throw new Error('invalid payload');
        await options.onEvent?.(frame as RealtimeEvent);
        if (active()) lastSeq = frame.seq;
      }).catch(recover).finally(() => { queued = Math.max(0, queued - 1); });
    };
    ws.onerror = () => { /* close or handshake timeout recovers */ };
    ws.onclose = (event) => {
      if (!active()) return;
      socket = null; generation++; clearHandshake();
      if ([4401, 4403].includes(event.code)) {
        stopped = true;
        if (event.code === 4401) options.onUnauthorized?.();
        setState('disconnected');
        return;
      }
      reconnect();
    };
  }
  function reconnect() {
    if (stopped || timer) return;
    setState('reconnecting');
    const delay = Math.min((options.reconnectBaseDelayMs ?? 500) * 2 ** Math.min(attempt++, 10), options.reconnectMaxDelayMs ?? 15000);
    timer = setTimeout(() => { timer = undefined; open(); }, delay);
  }
  return {
    connect() { if (!stopped && (socket || timer)) return; stopped = false; open(); },
    disconnect() {
      stopped = true; generation++; clearHandshake();
      if (timer) clearTimeout(timer); timer = undefined;
      const old = socket; socket = null; old?.close();
      setState('disconnected');
    },
    getState: () => state,
    getLastSeq: () => lastSeq,
  };
}
