import 'dotenv/config';
import { SerialPort } from 'serialport';
import { z } from 'zod';

const environment = z.object({
  SERIAL_PORT: z.string().min(1),
  SERIAL_BAUD_RATE: z.coerce.number().int().min(1200).max(921600).default(9600),
  API_URL: z.string().url(),
  DEVICE_ID: z.string().regex(/^[a-z0-9-]{1,64}$/i),
  DEVICE_INGEST_TOKEN: z.string().min(32),
  API_TIMEOUT_MS: z.coerce.number().int().min(500).max(60000).default(5000),
  SERIAL_QUEUE_MAX: z.coerce.number().int().min(1).max(10000).default(256),
});

const parsed = environment.safeParse(process.env);
if (!parsed.success) {
  throw new Error(`Invalid gateway configuration: ${parsed.error.issues.map((issue) => issue.path.join('.')).join(', ')}`);
}
const config = parsed.data;
let pendingText = '';
const deliveryQueue = [];
let draining = false;
let opening = false;
let reopenTimer = null;
let stopping = false;

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
    signal: AbortSignal.timeout(config.API_TIMEOUT_MS),
  });
  if (!response.ok) {
    console.warn(`API rejected telemetry: HTTP ${response.status}.`);
    return;
  }
  console.info(`Forwarded telemetry at ${new Date().toLocaleTimeString()}.`);
}

async function drainDeliveryQueue() {
  if (draining || stopping) return;
  draining = true;
  try {
    while (deliveryQueue.length && !stopping) {
      const line = deliveryQueue.shift();
      try {
        await forwardLine(line);
      } catch (error) {
        console.error('Failed to forward telemetry.', error instanceof Error ? error.message : error);
      }
    }
  } finally {
    draining = false;
  }
}

function enqueueLine(line) {
  if (deliveryQueue.length >= config.SERIAL_QUEUE_MAX) {
    deliveryQueue.shift();
    console.warn('Dropped the oldest serial frame because the delivery queue is full.');
  }
  deliveryQueue.push(line);
  void drainDeliveryQueue();
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
    enqueueLine(line);
  }
});

port.on('error', (error) => {
  console.error('Serial gateway error:', error.message);
  if (!port.isOpen) scheduleOpen();
});

port.on('close', () => {
  if (!stopping) scheduleOpen();
});

function scheduleOpen() {
  if (stopping || reopenTimer || opening || port.isOpen) return;
  reopenTimer = setTimeout(() => {
    reopenTimer = null;
    openPort();
  }, 3000);
}

function openPort() {
  if (opening || port.isOpen) return;
  opening = true;
  port.open((error) => {
    opening = false;
    if (error) {
      console.warn(`${config.SERIAL_PORT} is not ready; retrying in 3 seconds (${error.message}).`);
      scheduleOpen();
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
  stopping = true;
  if (reopenTimer) clearTimeout(reopenTimer);
  if (port.isOpen) port.close();
};
process.once('SIGINT', shutdown);
process.once('SIGTERM', shutdown);
