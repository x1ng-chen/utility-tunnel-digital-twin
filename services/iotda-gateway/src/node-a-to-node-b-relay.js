import mqtt from 'mqtt';

const brokerUrl = process.env.LOCAL_MQTT_URL ?? 'mqtt://127.0.0.1:1884';
const sourceTopic = 'ut/v1/CTRL-01/telemetry';
const targetTopic = 'ut/v1/CTRL-02/cmd/peer';

const client = mqtt.connect(brokerUrl, { reconnectPeriod: 3000, clean: true });

client.on('connect', () => {
  client.subscribe(sourceTopic, { qos: 1 }, (error) => {
    if (error) console.error('Node A relay subscribe failed:', error.message);
    else console.info(`Node A relay listening on ${sourceTopic}`);
  });
});

client.on('message', (topic, rawPayload) => {
  if (topic !== sourceTopic) return;

  try {
    const telemetry = JSON.parse(rawPayload.toString('utf8'));
    if (telemetry.schema !== 'ut.node-a.sht30.v1' || !Array.isArray(telemetry.sht30)) return;

    const reading = telemetry.sht30.find((item) => item.slot === 1);
    if (!reading || !Number.isInteger(reading.temperatureCentiC) || !Number.isInteger(reading.humidityCentiRH)) return;

    const peerPayload = JSON.stringify({
      schema: 'ut.node-b.peer.v1',
      source: 'node-a',
      online: reading.online ? 1 : 0,
      temperatureCentiC: reading.temperatureCentiC,
      humidityCentiRH: reading.humidityCentiRH,
    });
    client.publish(targetTopic, peerPayload, { qos: 1 }, (error) => {
      if (error) console.error('Node A relay publish failed:', error.message);
      else console.info(`Forwarded Node A SHT30 slot 1 to ${targetTopic}`);
    });
  } catch (error) {
    console.warn('Node A relay rejected malformed telemetry:', error instanceof Error ? error.message : error);
  }
});

client.on('error', (error) => console.error('Node A relay MQTT error:', error.message));

const shutdown = () => client.end(true);
process.once('SIGINT', shutdown);
process.once('SIGTERM', shutdown);
