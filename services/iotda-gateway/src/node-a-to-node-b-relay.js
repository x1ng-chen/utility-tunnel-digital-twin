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
    let online;
    let temperatureCentiC;
    let humidityCentiRH;

    if (telemetry.schema === 'ut.telemetry.v1' && Array.isArray(telemetry.readings)) {
      const temperature = telemetry.readings.find(
        (item) => item.assetCode === 'ENV-01' && item.metric === 'temperature',
      );
      const humidity = telemetry.readings.find(
        (item) => item.assetCode === 'ENV-01' && item.metric === 'humidity',
      );
      if (!temperature || !humidity ||
          !Number.isFinite(temperature.value) || !Number.isFinite(humidity.value)) return;

      online = temperature.quality === 'good' && humidity.quality === 'good';
      temperatureCentiC = Math.round(temperature.value * 100);
      humidityCentiRH = Math.round(humidity.value * 100);
    } else if (telemetry.schema === 'ut.node-a.sht30.v1' && Array.isArray(telemetry.sht30)) {
      const reading = telemetry.sht30.find((item) => item.slot === 1);
      if (!reading || !Number.isInteger(reading.temperatureCentiC) ||
          !Number.isInteger(reading.humidityCentiRH)) return;

      online = Boolean(reading.online);
      temperatureCentiC = reading.temperatureCentiC;
      humidityCentiRH = reading.humidityCentiRH;
    } else {
      return;
    }

    if (temperatureCentiC < -4500 || temperatureCentiC > 13000 ||
        humidityCentiRH < 0 || humidityCentiRH > 10000) return;

    const peerPayload = JSON.stringify({
      schema: 'ut.node-b.peer.v1',
      source: 'node-a',
      online: online ? 1 : 0,
      temperatureCentiC,
      humidityCentiRH,
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
