import assert from 'node:assert/strict';
import test from 'node:test';
import { canPerform, createInitialOperationsState, reduceOperations, toCsv, toJson } from './operations.ts';

test('alert confirmation creates an immutable audit entry', () => {
  const state = createInitialOperationsState();
  const next = reduceOperations(state, { type: 'alert.acknowledge', alertId: 'alert-seep-001', actor: '测试值班员' });
  assert.equal(next.alerts.find((item) => item.id === 'alert-seep-001')?.status, 'acknowledged');
  assert.equal(next.audit[0]?.action, 'alert.acknowledged');
});

test('a linked work order is not duplicated for the same alert', () => {
  const state = createInitialOperationsState();
  const withoutExisting = { ...state, workOrders: state.workOrders.filter((item) => item.sourceAlertId !== 'alert-seep-001') };
  const created = reduceOperations(withoutExisting, { type: 'workOrder.create', alertId: 'alert-seep-001', actor: '测试值班员' });
  const duplicate = reduceOperations(created, { type: 'workOrder.create', alertId: 'alert-seep-001', actor: '测试值班员' });
  assert.equal(created.workOrders.length, 2);
  assert.equal(duplicate.workOrders.length, 2);
});

test('work order completion requires the review state', () => {
  const state = createInitialOperationsState();
  const rejected = reduceOperations(state, { type: 'workOrder.transition', workOrderId: 'wo-fan-001', to: 'completed', actor: '测试运维员' });
  assert.equal(rejected, state);
  const review = reduceOperations(state, { type: 'workOrder.transition', workOrderId: 'wo-fan-001', to: 'pending_review', actor: '测试运维员' });
  const completed = reduceOperations(review, { type: 'workOrder.transition', workOrderId: 'wo-fan-001', to: 'completed', actor: '测试管理员' });
  assert.equal(completed.workOrders.find((item) => item.id === 'wo-fan-001')?.status, 'completed');
  assert.equal(completed.alerts.find((item) => item.id === 'alert-fan-001')?.status, 'resolved');
  assert.equal(completed.assets.find((item) => item.code === 'FAN-01')?.status, 'normal');
});

test('viewer permissions are enforced by the reducer, not only the interface', () => {
  const state = reduceOperations(createInitialOperationsState(), { type: 'session.switchRole', role: 'viewer' });
  const rejected = reduceOperations(state, { type: 'threshold.update', key: 'temperature', warning: 25, alarm: 30, actor: '查看者' });
  assert.equal(canPerform('viewer', 'threshold.update'), false);
  assert.equal(rejected, state);
  assert.equal(canPerform('viewer', 'report.export'), true);
});

test('manual work orders and export payloads use the shared operations state', () => {
  const state = createInitialOperationsState();
  const manual = reduceOperations(state, { type: 'workOrder.createManual', assetCode: 'CTRL-01', title: '控制器月度巡检', actor: '测试运维员' });
  assert.equal(manual.workOrders[0]?.title, '控制器月度巡检');
  assert.match(toCsv(manual, 'daily'), /在线资产/);
  assert.match(toJson(manual, 'assets'), /CTRL-01/);
});

test('the complete alert-to-work-order-to-asset recovery path stays linked', () => {
  const initial = createInitialOperationsState();
  const acknowledged = reduceOperations(initial, { type: 'alert.acknowledge', alertId: 'alert-ctrl-001', actor: '测试运维员' });
  const created = reduceOperations(acknowledged, { type: 'workOrder.create', alertId: 'alert-ctrl-001', actor: '测试运维员' });
  const orderId = created.workOrders[0]?.id;
  assert.ok(orderId);
  const assigned = reduceOperations(created, { type: 'workOrder.transition', workOrderId: orderId, to: 'assigned', actor: '测试运维员' });
  const processing = reduceOperations(assigned, { type: 'workOrder.transition', workOrderId: orderId, to: 'in_progress', actor: '测试运维员' });
  const reviewing = reduceOperations(processing, { type: 'workOrder.transition', workOrderId: orderId, to: 'pending_review', actor: '测试运维员' });
  const completed = reduceOperations(reviewing, { type: 'workOrder.transition', workOrderId: orderId, to: 'completed', actor: '测试管理员' });
  assert.equal(completed.alerts.find((item) => item.id === 'alert-ctrl-001')?.status, 'resolved');
  assert.equal(completed.audit[0]?.action, 'work_order.completed');
});
