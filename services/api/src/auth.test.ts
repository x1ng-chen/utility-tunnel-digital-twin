import assert from 'node:assert/strict';
import test from 'node:test';
import type { FastifyReply, FastifyRequest } from 'fastify';
import { requirePermission } from './auth.js';

test('permission guard returns a standardized forbidden response', async () => {
  let statusCode = 0;
  let payload: unknown;
  const reply = {
    code(code: number) {
      statusCode = code;
      return { send(value: unknown) { payload = value; } };
    },
  } as unknown as FastifyReply;
  const request = { user: { id: 'user-1', roles: ['viewer'], permissions: [] } } as unknown as FastifyRequest;

  const guard = requirePermission('setting.write') as unknown as (input: FastifyRequest, output: FastifyReply) => Promise<void>;
  await guard(request, reply);

  assert.equal(statusCode, 403);
  assert.deepEqual(payload, { error: 'forbidden', message: 'Insufficient permission.' });
});
