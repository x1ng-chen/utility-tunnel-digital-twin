import { createHmac } from 'node:crypto';

export function utcHourTimestamp(date = new Date()) {
  return date.toISOString().replace(/[-:T]/g, '').slice(0, 10);
}

export function createDeviceCredentials(deviceId, deviceSecret, date = new Date()) {
  const timestamp = utcHourTimestamp(date);
  return {
    clientId: `${deviceId}_0_0_${timestamp}`,
    username: deviceId,
    // IoTDA defines the timestamp as the HMAC key and the device secret as data.
    password: createHmac('sha256', timestamp).update(deviceSecret).digest('hex'),
  };
}

