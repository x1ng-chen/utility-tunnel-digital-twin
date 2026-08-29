import assert from 'node:assert/strict';
import test from 'node:test';
import { createDeviceCredentials, utcHourTimestamp } from '../src/auth.js';

test('formats the IoTDA UTC hour timestamp', () => {
  assert.equal(utcHourTimestamp(new Date('2025-04-14T01:59:59Z')), '2025041401');
});

test('matches the Huawei Cloud HMAC-SHA256 example', () => {
  const credentials = createDeviceCredentials('device-id', '12345678', new Date('2025-04-14T01:00:00Z'));
  assert.equal(credentials.clientId, 'device-id_0_0_2025041401');
  assert.equal(credentials.username, 'device-id');
  assert.equal(credentials.password, 'c75150e6cb841417396819e4d2ee4358a416344a03a083e3a8567074ddec820a');
});

