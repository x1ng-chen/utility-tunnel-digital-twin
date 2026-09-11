import { createSocket as createDgramSocket } from 'node:dgram';
import { networkInterfaces } from 'node:os';

const PROTOCOL = 'UT-MQTT-DISCOVERY/1';
const DEFAULT_SERVICE_NAME = 'utility-tunnel';

function ipv4ToInteger(address) {
  const octets = address.split('.').map(Number);
  if (octets.length !== 4 || octets.some((value) => !Number.isInteger(value) || value < 0 || value > 255)) {
    throw new Error(`Invalid IPv4 address: ${address}`);
  }
  return octets.reduce((result, octet) => ((result << 8) | octet) >>> 0, 0);
}

function integerToIpv4(value) {
  return [24, 16, 8, 0].map((shift) => (value >>> shift) & 0xff).join('.');
}

export function buildDiscoveryPacket({ mqttPort, serviceName = DEFAULT_SERVICE_NAME }) {
  if (!Number.isInteger(mqttPort) || mqttPort < 1 || mqttPort > 65535) {
    throw new RangeError('mqttPort must be an integer from 1 to 65535');
  }
  if (!serviceName || serviceName.includes('|')) {
    throw new Error('serviceName must be non-empty and cannot contain "|"');
  }
  return Buffer.from(`${PROTOCOL}|${serviceName}|${mqttPort}`, 'utf8');
}

export function directedBroadcastAddresses(interfaces = networkInterfaces()) {
  const addresses = new Set();
  for (const entries of Object.values(interfaces)) {
    for (const entry of entries ?? []) {
      if (entry.family !== 'IPv4' || entry.internal || !entry.address || !entry.netmask) continue;
      try {
        const address = ipv4ToInteger(entry.address);
        const netmask = ipv4ToInteger(entry.netmask);
        addresses.add(integerToIpv4((address | (~netmask >>> 0)) >>> 0));
      } catch {
        // Ignore malformed interface records supplied by the operating system.
      }
    }
  }
  return [...addresses];
}

export function startDiscoveryBroadcaster({
  mqttPort = 1884,
  discoveryPort = 4210,
  intervalMs = 3000,
  serviceName = DEFAULT_SERVICE_NAME,
  interfacesProvider = networkInterfaces,
  createSocket = () => createDgramSocket('udp4'),
  setIntervalFn = setInterval,
  clearIntervalFn = clearInterval,
  setTimeoutFn = setTimeout,
  clearTimeoutFn = clearTimeout,
  retryDelayMs = 1000,
  logger = console,
} = {}) {
  if (!Number.isInteger(discoveryPort) || discoveryPort < 1 || discoveryPort > 65535) {
    throw new RangeError('discoveryPort must be an integer from 1 to 65535');
  }
  if (!Number.isInteger(intervalMs) || intervalMs < 250) {
    throw new RangeError('intervalMs must be an integer of at least 250');
  }

  const packet = buildDiscoveryPacket({ mqttPort, serviceName });
  if (!Number.isInteger(retryDelayMs) || retryDelayMs < 250 || retryDelayMs > 60000) {
    throw new RangeError('retryDelayMs must be an integer from 250 to 60000');
  }

  let socket;
  let intervalToken;
  let retryToken;
  let closed = false;

  const broadcastNow = () => {
    if (closed || !socket) return;
    const activeSocket = socket;
    const addresses = directedBroadcastAddresses(interfacesProvider());
    for (const address of addresses) {
      activeSocket.send(packet, discoveryPort, address, (error) => {
        if (error) logger.warn(`MQTT discovery broadcast to ${address} failed: ${error.message}`);
      });
    }
  };

  const closeSocket = (target) => {
    if (intervalToken !== undefined) {
      clearIntervalFn(intervalToken);
      intervalToken = undefined;
    }
    if (socket === target) socket = undefined;
    try {
      target.close();
    } catch {
      // A failed bind can leave a dgram socket already closed.
    }
  };

  const startSocket = () => {
    if (closed) return;
    const activeSocket = createSocket();
    socket = activeSocket;
    activeSocket.on('error', (error) => {
      if (closed || socket !== activeSocket) return;
      logger.warn(`MQTT discovery socket error: ${error.message}; retrying in ${retryDelayMs} ms.`);
      closeSocket(activeSocket);
      if (retryToken === undefined) {
        retryToken = setTimeoutFn(() => {
          retryToken = undefined;
          startSocket();
        }, retryDelayMs);
      }
    });
    activeSocket.bind(() => {
      if (closed || socket !== activeSocket) return;
      try {
        activeSocket.setBroadcast(true);
        broadcastNow();
        intervalToken = setIntervalFn(broadcastNow, intervalMs);
        logger.info(`MQTT discovery broadcasting UDP/${discoveryPort} for local MQTT/${mqttPort}.`);
      } catch (error) {
        activeSocket.emit('error', error);
      }
    });
  };

  startSocket();

  return {
    broadcastNow,
    close() {
      if (closed) return;
      closed = true;
      if (retryToken !== undefined) {
        clearTimeoutFn(retryToken);
        retryToken = undefined;
      }
      if (socket) closeSocket(socket);
    },
  };
}
