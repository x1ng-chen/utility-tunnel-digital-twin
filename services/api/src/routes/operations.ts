import { randomUUID } from 'node:crypto';
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { PoolClient } from 'pg';
import { z } from 'zod';
import { writeAudit } from '../audit.js';
import { authenticate, requirePermission } from '../auth.js';
import { inTransaction, query } from '../db.js';
import { alertTransitions, assertTransition, workOrderTransitions } from '../domain/lifecycle.js';

const idParams = z.object({ id: z.string().uuid() });
const pageQuery = z.object({
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(25),
});
const noteBody = z.object({ note: z.string().trim().min(1).max(2_000) });
const workOrderBody = z.object({
  title: z.string().trim().min(3).max(240).optional(),
  description: z.string().trim().max(10_000).optional(),
  priority: z.enum(['low', 'normal', 'high', 'urgent']).optional(),
  dueAt: z.string().datetime({ offset: true }).optional(),
});
const workOrderTransitionBody = z.object({
  to: z.enum(['open', 'assigned', 'in_progress', 'pending_review', 'completed', 'cancelled']),
  note: z.string().trim().min(1).max(2_000),
});

type AuthenticatedRequest = FastifyRequest & { user: { id: string; permissions: string[] } };

function requestPagination(request: FastifyRequest, reply: FastifyReply) {
  const parsed = pageQuery.safeParse(request.query);
  if (!parsed.success) {
    void reply.code(400).send({ error: 'invalid_pagination', message: 'Invalid page or pageSize.' });
    return null;
  }
  return { ...parsed.data, offset: (parsed.data.page - 1) * parsed.data.pageSize };
}

function requireId(request: FastifyRequest, reply: FastifyReply): string | null {
  const parsed = idParams.safeParse(request.params);
  if (!parsed.success) {
    void reply.code(400).send({ error: 'invalid_id', message: 'A valid resource id is required.' });
    return null;
  }
  return parsed.data.id;
}

function code(prefix: 'WO'): string {
  const day = new Date().toISOString().slice(2, 10).replaceAll('-', '');
  return `${prefix}-${day}-${randomUUID().slice(0, 8).toUpperCase()}`;
}

async function findAlertForUpdate(client: PoolClient, id: string) {
  const result = await client.query<{ id: string; code: string; status: string; asset_id: string; severity: string; title: string; detail: string | null }>(
    'SELECT id, code, status, asset_id, severity, title, detail FROM alert WHERE id = $1 FOR UPDATE',
    [id],
  );
  return result.rows[0] ?? null;
}

export async function registerOperationsRoutes(app: FastifyInstance): Promise<void> {
  app.get('/v1/health', async () => {
    await query('SELECT 1');
    return { status: 'ok', service: 'utility-tunnel-api' };
  });

  app.get('/v1/dashboard/overview', { preHandler: [authenticate, requirePermission('dashboard.read')] }, async () => {
    const [summary, latestAlerts, latestTelemetry] = await Promise.all([
      query<{ online_assets: string; total_assets: string; open_alerts: string; open_work_orders: string }>(
        `SELECT
           count(*) FILTER (WHERE operational_status IN ('normal', 'warning', 'alarm')) AS online_assets,
           count(*) AS total_assets,
           (SELECT count(*) FROM alert WHERE status IN ('open', 'acknowledged', 'resolved')) AS open_alerts,
           (SELECT count(*) FROM work_order WHERE status NOT IN ('completed', 'cancelled')) AS open_work_orders
         FROM asset`,
      ),
      query('SELECT id, code, severity, status, title, opened_at FROM alert WHERE status <> $1 ORDER BY opened_at DESC LIMIT 5', ['closed']),
      query(
        `SELECT DISTINCT ON (asset_id, metric_code) asset_id, metric_code, numeric_value, text_value, unit, quality, recorded_at
         FROM telemetry_reading
         ORDER BY asset_id, metric_code, recorded_at DESC
         LIMIT 20`,
      ),
    ]);
    return { summary: summary.rows[0], latestAlerts: latestAlerts.rows, latestTelemetry: latestTelemetry.rows };
  });

  app.get('/v1/assets', { preHandler: [authenticate, requirePermission('asset.read')] }, async (request, reply) => {
    const pagination = requestPagination(request, reply);
    if (!pagination) return;
    const [assets, total] = await Promise.all([
      query(
        `SELECT a.id, a.code, a.name, a.asset_type, a.lifecycle_status, a.operational_status,
                a.model_mesh_code, a.location_x, a.location_y, a.location_z, a.metadata,
                z.code AS zone_code, z.name AS zone_name, a.updated_at
         FROM asset a JOIN zone z ON z.id = a.zone_id
         ORDER BY z.sequence, a.code
         LIMIT $1 OFFSET $2`,
        [pagination.pageSize, pagination.offset],
      ),
      query<{ count: string }>('SELECT count(*) FROM asset'),
    ]);
    return reply.send({ items: assets.rows, page: pagination.page, pageSize: pagination.pageSize, total: Number(total.rows[0]?.count ?? 0) });
  });

  app.get('/v1/alerts', { preHandler: [authenticate, requirePermission('alert.read')] }, async (request, reply) => {
    const pagination = requestPagination(request, reply);
    if (!pagination) return;
    const [alerts, total] = await Promise.all([
      query(
        `SELECT al.id, al.code, al.severity, al.category, al.status, al.title, al.detail, al.opened_at,
                al.acknowledged_at, asset.code AS asset_code, asset.name AS asset_name, zone.code AS zone_code
         FROM alert al
         JOIN asset ON asset.id = al.asset_id
         JOIN zone ON zone.id = asset.zone_id
         ORDER BY al.opened_at DESC
         LIMIT $1 OFFSET $2`,
        [pagination.pageSize, pagination.offset],
      ),
      query<{ count: string }>('SELECT count(*) FROM alert'),
    ]);
    return reply.send({ items: alerts.rows, page: pagination.page, pageSize: pagination.pageSize, total: Number(total.rows[0]?.count ?? 0) });
  });

  app.post('/v1/alerts/:id/acknowledge', { preHandler: [authenticate, requirePermission('alert.acknowledge')] }, async (request, reply) => {
    const alertId = requireId(request, reply);
    const body = noteBody.safeParse(request.body);
    if (!alertId || !body.success) return reply.code(400).send({ error: 'invalid_request', message: 'A note is required.' });
    const actor = request as AuthenticatedRequest;

    const updated = await inTransaction(async (client) => {
      const alert = await findAlertForUpdate(client, alertId);
      if (!alert) return null;
      assertTransition(alertTransitions, alert.status, 'acknowledged');
      const result = await client.query(
        `UPDATE alert
         SET status = 'acknowledged', acknowledged_at = now(), acknowledged_by = $2, version = version + 1
         WHERE id = $1 RETURNING id, code, status, acknowledged_at, version`,
        [alertId, actor.user.id],
      );
      await client.query(
        `INSERT INTO alert_event (alert_id, event_type, from_status, to_status, note, actor_id)
         VALUES ($1, 'acknowledged', $2, 'acknowledged', $3, $4)`,
        [alertId, alert.status, body.data.note, actor.user.id],
      );
      await writeAudit(client, {
        actorId: actor.user.id,
        action: 'alert.acknowledge',
        resourceType: 'alert',
        resourceId: alertId,
        requestId: request.id,
        beforeValue: { status: alert.status },
        afterValue: result.rows[0],
        detail: { note: body.data.note },
      });
      return result.rows[0];
    }).catch((error: Error) => {
      if (error.message.startsWith('Invalid transition')) return undefined;
      throw error;
    });

    if (updated === null) return reply.code(404).send({ error: 'not_found', message: 'Alert not found.' });
    if (updated === undefined) return reply.code(409).send({ error: 'invalid_transition', message: 'Alert cannot be acknowledged in its current state.' });
    return reply.send(updated);
  });

  app.post('/v1/alerts/:id/work-orders', { preHandler: [authenticate, requirePermission('work_order.write')] }, async (request, reply) => {
    const alertId = requireId(request, reply);
    const body = workOrderBody.safeParse(request.body);
    if (!alertId || !body.success) return reply.code(400).send({ error: 'invalid_request', message: 'Invalid work order data.' });
    const actor = request as AuthenticatedRequest;

    const created = await inTransaction(async (client) => {
      const alert = await findAlertForUpdate(client, alertId);
      if (!alert) return null;
      const priority = body.data.priority ?? (alert.severity === 'critical' ? 'urgent' : alert.severity === 'warning' ? 'high' : 'normal');
      const result = await client.query(
        `INSERT INTO work_order (code, source_alert_id, asset_id, title, description, priority, status, created_by, due_at)
         VALUES ($1, $2, $3, $4, $5, $6, 'open', $7, $8)
         RETURNING id, code, status, priority, title, created_at`,
        [
          code('WO'),
          alert.id,
          alert.asset_id,
          body.data.title ?? `处置 ${alert.code}：${alert.title}`,
          body.data.description ?? alert.detail,
          priority,
          actor.user.id,
          body.data.dueAt ?? null,
        ],
      );
      const workOrder = result.rows[0];
      await client.query(
        `INSERT INTO work_order_event (work_order_id, event_type, to_status, note, actor_id)
         VALUES ($1, 'created_from_alert', 'open', $2, $3)`,
        [workOrder.id, `来源告警：${alert.code}`, actor.user.id],
      );
      await writeAudit(client, {
        actorId: actor.user.id,
        action: 'work_order.create_from_alert',
        resourceType: 'work_order',
        resourceId: workOrder.id,
        requestId: request.id,
        afterValue: workOrder,
        detail: { sourceAlertId: alert.id },
      });
      return workOrder;
    });

    if (!created) return reply.code(404).send({ error: 'not_found', message: 'Alert not found.' });
    return reply.code(201).send(created);
  });

  app.get('/v1/work-orders', { preHandler: [authenticate, requirePermission('work_order.read')] }, async (request, reply) => {
    const pagination = requestPagination(request, reply);
    if (!pagination) return;
    const [orders, total] = await Promise.all([
      query(
        `SELECT wo.id, wo.code, wo.title, wo.priority, wo.status, wo.due_at, wo.created_at,
                a.code AS asset_code, al.code AS source_alert_code,
                assignee.display_name AS assignee_name
         FROM work_order wo
         LEFT JOIN asset a ON a.id = wo.asset_id
         LEFT JOIN alert al ON al.id = wo.source_alert_id
         LEFT JOIN app_user assignee ON assignee.id = wo.assigned_to
         ORDER BY wo.created_at DESC
         LIMIT $1 OFFSET $2`,
        [pagination.pageSize, pagination.offset],
      ),
      query<{ count: string }>('SELECT count(*) FROM work_order'),
    ]);
    return reply.send({ items: orders.rows, page: pagination.page, pageSize: pagination.pageSize, total: Number(total.rows[0]?.count ?? 0) });
  });

  app.post('/v1/work-orders/:id/transition', { preHandler: [authenticate, requirePermission('work_order.write')] }, async (request, reply) => {
    const workOrderId = requireId(request, reply);
    const body = workOrderTransitionBody.safeParse(request.body);
    if (!workOrderId || !body.success) return reply.code(400).send({ error: 'invalid_request', message: 'A valid status and note are required.' });
    const actor = request as AuthenticatedRequest;
    if (body.data.to === 'completed' && !actor.user.permissions.includes('work_order.review')) {
      return reply.code(403).send({ error: 'forbidden', message: 'Work order review permission is required.' });
    }

    const updated = await inTransaction(async (client) => {
      const existing = await client.query<{ id: string; status: string }>('SELECT id, status FROM work_order WHERE id = $1 FOR UPDATE', [workOrderId]);
      const workOrder = existing.rows[0];
      if (!workOrder) return null;
      assertTransition(workOrderTransitions, workOrder.status, body.data.to);
      const result = await client.query(
        `UPDATE work_order
         SET status = $2,
             completed_at = CASE WHEN $2 = 'completed' THEN now() ELSE completed_at END,
             reviewed_at = CASE WHEN $2 = 'completed' THEN now() ELSE reviewed_at END,
             reviewed_by = CASE WHEN $2 = 'completed' THEN $3 ELSE reviewed_by END,
             version = version + 1
         WHERE id = $1
         RETURNING id, code, status, version, completed_at, reviewed_at`,
        [workOrderId, body.data.to, actor.user.id],
      );
      await client.query(
        `INSERT INTO work_order_event (work_order_id, event_type, from_status, to_status, note, actor_id)
         VALUES ($1, 'status_changed', $2, $3, $4, $5)`,
        [workOrderId, workOrder.status, body.data.to, body.data.note, actor.user.id],
      );
      await writeAudit(client, {
        actorId: actor.user.id,
        action: 'work_order.transition',
        resourceType: 'work_order',
        resourceId: workOrderId,
        requestId: request.id,
        beforeValue: { status: workOrder.status },
        afterValue: result.rows[0],
        detail: { note: body.data.note },
      });
      return result.rows[0];
    }).catch((error: Error) => {
      if (error.message.startsWith('Invalid transition')) return undefined;
      throw error;
    });

    if (updated === null) return reply.code(404).send({ error: 'not_found', message: 'Work order not found.' });
    if (updated === undefined) return reply.code(409).send({ error: 'invalid_transition', message: 'Invalid work order transition.' });
    return reply.send(updated);
  });

  app.get('/v1/audit', { preHandler: [authenticate, requirePermission('audit.read')] }, async (request, reply) => {
    const pagination = requestPagination(request, reply);
    if (!pagination) return;
    const [entries, total] = await Promise.all([
      query(
        `SELECT audit.id, audit.occurred_at, audit.action, audit.resource_type, audit.resource_id,
                audit.before_value, audit.after_value, audit.detail, actor.display_name AS actor_name
         FROM audit_log audit
         LEFT JOIN app_user actor ON actor.id = audit.actor_id
         ORDER BY audit.occurred_at DESC
         LIMIT $1 OFFSET $2`,
        [pagination.pageSize, pagination.offset],
      ),
      query<{ count: string }>('SELECT count(*) FROM audit_log'),
    ]);
    return reply.send({ items: entries.rows, page: pagination.page, pageSize: pagination.pageSize, total: Number(total.rows[0]?.count ?? 0) });
  });
}
