import assert from 'node:assert/strict';
import test from 'node:test';
import { hashPassword, verifyPassword } from './password.js';

test('password verification accepts a valid scrypt hash and rejects malformed stored values', async () => {
  const hash = await hashPassword('correct-horse-battery-staple');
  assert.equal(await verifyPassword('correct-horse-battery-staple', hash), true);
  assert.equal(await verifyPassword('incorrect', hash), false);
  assert.equal(await verifyPassword('incorrect', 'scrypt$00$not-a-hex-hash'), false);
  assert.equal(await verifyPassword('incorrect', 'unexpected$00000000000000000000000000000000$00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'), false);
});
