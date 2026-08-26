import { randomBytes, scrypt as scryptCallback, timingSafeEqual } from 'node:crypto';
import { promisify } from 'node:util';

const scrypt = promisify(scryptCallback);
const keyLength = 64;
const saltPattern = /^[a-f0-9]{32}$/i;
const hashPattern = /^[a-f0-9]{128}$/i;

export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16).toString('hex');
  const derived = await scrypt(password, salt, keyLength) as Buffer;
  return `scrypt$${salt}$${derived.toString('hex')}`;
}

export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  const [algorithm, salt, encoded] = stored.split('$');
  if (algorithm !== 'scrypt' || !salt || !encoded || !saltPattern.test(salt) || !hashPattern.test(encoded)) return false;
  const expected = Buffer.from(encoded, 'hex');
  if (expected.length !== keyLength) return false;
  const actual = await scrypt(password, salt, expected.length) as Buffer;
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}
