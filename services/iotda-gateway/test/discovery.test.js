import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildDiscoveryPacket,
  directedBroadcastAddresses,
  startDiscoveryBroadcaster,
} from '../src/discovery.js';

test('builds the versioned MQTT discovery packet', () => {
  assert.equal(buildDiscoveryPacket({ mqttPort: 1884, hmacKey: 'bench-discovery-key' }).toString('utf8'),
    'UT-MQTT-DISCOVERY/2|utility-tunnel|1884|0ecd20b0b1069e60760f442846cbdfd028600e21a6f442b385c9de05636671ff');
  assert.throws(() => buildDiscoveryPacket({ mqttPort: 1884, hmacKey: '' }), /hmacKey/);
  assert.throws(() => buildDiscoveryPacket({ mqttPort: 0 }), /mqttPort/);
  assert.throws(() => buildDiscoveryPacket({ mqttPort: 70000 }), /mqttPort/);
});

test('derives one broadcast address for each usable IPv4 interface', () => {
  const interfaces = {
    WiFi: [{ family: 'IPv4', internal: false, address: '10.249.215.113', netmask: '255.255.255.0' }],
    Docker: [{ family: 'IPv4', internal: false, address: '172.26.48.1', netmask: '255.255.240.0' }],
    Loopback: [{ family: 'IPv4', internal: true, address: '127.0.0.1', netmask: '255.0.0.0' }],
    IPv6: [{ family: 'IPv6', internal: false, address: 'fe80::1', netmask: 'ffff:ffff:ffff:ffff::' }],
  };
  assert.deepEqual(directedBroadcastAddresses(interfaces), ['10.249.215.255', '172.26.63.255']);
});

test('broadcasts immediately and periodically, then closes cleanly', () => {
  const sends = [];
  const scheduled = [];
  let closed = false;
  const socket = {
    on() {},
    bind(callback) { callback(); },
    setBroadcast(value) { assert.equal(value, true); },
    send(packet, port, address, callback) {
      sends.push({ packet: packet.toString('utf8'), port, address });
      callback?.();
    },
    close() { closed = true; },
  };
  const broadcaster = startDiscoveryBroadcaster({
    mqttPort: 1884,
    hmacKey: 'bench-discovery-key',
    discoveryPort: 4210,
    interfacesProvider: () => ({
      WiFi: [{ family: 'IPv4', internal: false, address: '10.0.0.9', netmask: '255.255.255.0' }],
    }),
    createSocket: () => socket,
    setIntervalFn: (callback, milliseconds) => {
      assert.equal(milliseconds, 3000);
      scheduled.push(callback);
      return 77;
    },
    clearIntervalFn: (token) => assert.equal(token, 77),
    logger: { info() {}, warn() {} },
  });
  assert.deepEqual(sends, [{
    packet: 'UT-MQTT-DISCOVERY/2|utility-tunnel|1884|0ecd20b0b1069e60760f442846cbdfd028600e21a6f442b385c9de05636671ff',
    port: 4210,
    address: '10.0.0.255',
  }]);
  scheduled[0]();
  assert.equal(sends.length, 2);
  broadcaster.close();
  assert.equal(closed, true);
});

test('also sends authenticated discovery to configured unicast targets', () => {
  const sends = [];
  const socket = {
    on() {},
    bind(callback) { callback(); },
    setBroadcast() {},
    send(_packet, port, address, callback) {
      sends.push({ port, address });
      callback?.();
    },
    close() {},
  };
  const broadcaster = startDiscoveryBroadcaster({
    mqttPort: 1884,
    hmacKey: 'bench-discovery-key',
    discoveryPort: 4210,
    unicastTargets: ['10.0.0.200', '10.0.0.1'],
    interfacesProvider: () => ({
      WiFi: [{ family: 'IPv4', internal: false, address: '10.0.0.9', netmask: '255.255.255.0' }],
    }),
    createSocket: () => socket,
    setIntervalFn: () => 77,
    clearIntervalFn() {},
    logger: { info() {}, warn() {} },
  });
  assert.deepEqual(sends, [
    { port: 4210, address: '10.0.0.255' },
    { port: 4210, address: '10.0.0.200' },
    { port: 4210, address: '10.0.0.1' },
  ]);
  broadcaster.close();
});

test('recreates the UDP socket after a bind or fatal socket error', () => {
  const retryCallbacks = [];
  const sockets = [];
  const createSocket = () => {
    const socket = {
      errorHandler: null,
      closed: false,
      on(event, callback) {
        if (event === 'error') this.errorHandler = callback;
      },
      bind(callback) { this.bindCallback = callback; },
      setBroadcast() {},
      send() {},
      close() { this.closed = true; },
    };
    sockets.push(socket);
    return socket;
  };

  const broadcaster = startDiscoveryBroadcaster({
    mqttPort: 1884,
    hmacKey: 'bench-discovery-key',
    createSocket,
    setTimeoutFn: (callback, milliseconds) => {
      assert.equal(milliseconds, 1000);
      retryCallbacks.push(callback);
      return 91;
    },
    clearTimeoutFn: (token) => assert.equal(token, 91),
    logger: { info() {}, warn() {} },
  });

  assert.equal(sockets.length, 1);
  sockets[0].errorHandler(new Error('bind failed'));
  assert.equal(sockets[0].closed, true);
  assert.equal(retryCallbacks.length, 1);
  retryCallbacks[0]();
  assert.equal(sockets.length, 2);
  broadcaster.close();
  assert.equal(sockets[1].closed, true);
});
