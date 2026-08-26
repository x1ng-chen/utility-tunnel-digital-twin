import assert from 'node:assert/strict';
import test from 'node:test';
import { FixedWindowRateLimiter } from './rate-limit.js';

test('rate limiter blocks a caller after the configured quota and resets next window', () => {
  const limiter = new FixedWindowRateLimiter(2, 1_000);
  assert.equal(limiter.check('127.0.0.1', 0).allowed, true);
  assert.equal(limiter.check('127.0.0.1', 100).remaining, 0);
  assert.equal(limiter.check('127.0.0.1', 200).allowed, false);
  assert.equal(limiter.check('127.0.0.1', 1_000).allowed, true);
});

test('rate limiter keeps its in-memory key set bounded under a burst of unique callers', () => {
  const limiter = new FixedWindowRateLimiter(2, 1_000, 1);
  assert.equal(limiter.check('first', 0).allowed, true);
  assert.equal(limiter.check('second', 10).allowed, false);
});
