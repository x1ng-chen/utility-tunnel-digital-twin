import mqtt, { type MqttClient } from 'mqtt';
import { config } from './config.js';
import { parseTelemetry, persistTelemetry } from './telemetry.js';

export class MqttTelemetryAdapter {
  private client: MqttClient | undefined;

  start() {
    if (!config.MQTT_URL) return;
    this.client = mqtt.connect(config.MQTT_URL, {
      username: config.MQTT_USERNAME,
      password: config.MQTT_PASSWORD,
      reconnectPeriod: 2_000,
      connectTimeout: 8_000,
      clientId: `ut-api-${process.pid}`,
      clean: true,
    });
    this.client.on('connect', () => {
      this.client?.subscribe(config.MQTT_TELEMETRY_TOPIC, { qos: 0 }, (error) => {
        if (error) console.error('MQTT telemetry subscription failed', error);
      });
    });
    this.client.on('message', (topic, payload) => {
      void this.handleMessage(topic, payload);
    });
    this.client.on('error', (error) => console.error('MQTT telemetry client error', error));
  }

  async stop() {
    if (!this.client) return;
    const client = this.client;
    this.client = undefined;
    await new Promise<void>((resolve) => client.end(false, {}, () => resolve()));
  }

  private async handleMessage(topic: string, payload: Buffer) {
    try {
      const telemetry = parseTelemetry(topic, payload);
      await persistTelemetry(telemetry);
    } catch (error) {
      console.error('Rejected MQTT telemetry message', { topic, error: error instanceof Error ? error.message : 'unknown error' });
    }
  }
}
