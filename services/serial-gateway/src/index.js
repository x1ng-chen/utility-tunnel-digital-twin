import 'dotenv/config';
import { SerialPort } from 'serialport';
import { z } from 'zod';

const environment = z.object({
  SERIAL_PORT: z.string().min(1),
  SERIAL_BAUD_RATE: z.coerce.number().int().min(1200).max(921600).default(9600),
  API_URL: z.string().url(),
  DEVICE_ID: z.string().regex(/^[a-z0-9-]{1,64}$/i),
  DEVICE_INGEST_TOKEN: z.string().min(32),
});

const parsed = environment.safeParse(process.env);
if (!parsed.success) {
  throw new Error(`Invalid gateway configuration: ${parsed.error.issues.map((issue) => issue.path.join('.')).join(', ')}`);
}
const config = parsed.data;
let pendingText = '';
let deliveryQueue = Promise.resolve();
let opening = false;

async function forwardLine(line) {
  if (!line.trim()) return;
  let telemetry;
  try {
    telemetry = JSON.parse(line);
  } catch {
    console.warn('Discarded a non-JSON serial line.');
    return;
  }

  const response = await fetch(config.API_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-device-id': config.DEVICE_ID,
      'x-device-ingest-token': config.DEVICE_INGEST_TOKEN,
    },
    body: JSON.stringify(telemetry),
  });
  if (!response.ok) {
    console.warn(`API rejected telemetry: HTTP ${response.status}.`);
    return;
  }
  console.info(`Forwarded telemetry at ${new Date().toLocaleTimeString()}.`);
}

const port = new SerialPort({
  path: config.SERIAL_PORT,
  baudRate: config.SERIAL_BAUD_RATE,
  autoOpen: false,
});

port.on('data', (chunk) => {
  pendingText += chunk.toString('utf8');
  if (pendingText.length > 8192) {
    console.warn('Discarded an oversized serial frame.');
    pendingText = '';
    return;
  }
  const lines = pendingText.split(/\r?\n/);
  pendingText = lines.pop() ?? '';
  for (const line of lines) {
    deliveryQueue = deliveryQueue.then(() => forwardLine(line)).catch((error) => {
      console.error('Failed to forward telemetry.', error instanceof Error ? error.message : error);
    });
  }
});

port.on('error', (error) => {
  console.error('Serial gateway error:', error.message);
});

function openPort() {
  if (opening || port.isOpen) return;
  opening = true;
  port.open((error) => {
    opening = false;
    if (error) {
      console.warn(`COM10 is not ready; retrying in 3 seconds (${error.message}).`);
      setTimeout(openPort, 3000);
      return;
    }
    // Windows may defer opening an SPP session until the first write. The STM32
    // currently ignores received bytes, so this delimiter safely triggers it.
    port.write('\r\n');
    console.info(`Listening for JDY-31 telemetry on ${config.SERIAL_PORT} at ${config.SERIAL_BAUD_RATE} baud.`);
  });
}

openPort();

const shutdown = () => {
  if (port.isOpen) port.close();
};
process.once('SIGINT', shutdown);
process.once('SIGTERM', shutdown);
