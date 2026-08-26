import assert from 'node:assert/strict';
import test from 'node:test';
import { alertTransitions, assertTransition, workOrderTransitions } from './lifecycle.js';

test('alert lifecycle permits the required operations path', () => {
  assert.doesNotThrow(() => assertTransition(alertTransitions, 'open', 'acknowledged'));
  assert.doesNotThrow(() => assertTransition(alertTransitions, 'acknowledged', 'resolved'));
  assert.doesNotThrow(() => assertTransition(alertTransitions, 'resolved', 'closed'));
});

test('terminal alert state cannot be reopened implicitly', () => {
  assert.throws(() => assertTransition(alertTransitions, 'closed', 'open'), /Invalid transition/);
});

test('work order requires review before completion', () => {
  assert.throws(() => assertTransition(workOrderTransitions, 'in_progress', 'completed'), /Invalid transition/);
  assert.doesNotThrow(() => assertTransition(workOrderTransitions, 'in_progress', 'pending_review'));
  assert.doesNotThrow(() => assertTransition(workOrderTransitions, 'pending_review', 'completed'));
});
