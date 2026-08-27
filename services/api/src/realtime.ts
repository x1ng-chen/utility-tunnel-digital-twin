import type { ServerResponse } from 'node:http';

export type RealtimeTelemetryReading = {
  id: string;
  asset_code: string;
  metric_code: string;
  numeric_value: number;
  unit: string;
  quality: 'good' | 'suspect' | 'bad' | 'missing';
  recorded_at: string;
};

const heartbeatMs = 20_000;

class RealtimeHub {
  private readonly clients = new Set<ServerResponse>();
  private heartbeat: NodeJS.Timeout | undefined;

  add(client: ServerResponse) {
    this.clients.add(client);
    client.write(': connected\n\n');
    if (!this.heartbeat) {
      this.heartbeat = setInterval(() => this.broadcast(': ping\n\n'), heartbeatMs);
      this.heartbeat.unref();
    }
  }

  remove(client: ServerResponse) {
    this.clients.delete(client);
    if (!this.clients.size && this.heartbeat) {
      clearInterval(this.heartbeat);
      this.heartbeat = undefined;
    }
  }

  publish(readings: RealtimeTelemetryReading[]) {
    if (!readings.length) return;
    this.broadcast(`event: telemetry\ndata: ${JSON.stringify({ readings })}\n\n`);
  }

  private broadcast(payload: string) {
    for (const client of this.clients) {
      if (client.writableEnded || client.destroyed) {
        this.remove(client);
        continue;
      }
      client.write(payload);
    }
  }
}

export const realtimeHub = new RealtimeHub();
