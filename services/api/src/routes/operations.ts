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
const assetListQuery = pageQuery.extend({
  q: z.string().trim().min(1).max(160).optional(),
  zone: z.string().trim().min(1).max(32).optional(),
  status: z.enum(['normal', 'warning', 'alarm', 'offline', 'unknown']).optional(),
});
const noteBody = z.object({ note: z.string().trim().min(1).max(2_000) });
const workOrderBody = z.object({
  title: z.string().trim().min(3).max(240).optional(),
  description: z.string().trim().max(10_000).optional(),
  priority: z.enum(['low', 'normal', 'high', 'urgent']).optional(),
  dueAt: z.string().datetime({ offset: true }).optional(),
});
const manualWorkOrderBody = workOrderBody.extend({
  assetId: z.string().uuid(),
  title: z.string().trim().min(3).max(240),
});
const workOrderTransitionBody = z.object({
  to: z.enum(['open', 'assigned', 'in_progress', 'pending_review', 'completed', 'cancelled']),
  note: z.string().trim().min(1).max(2_000),
});
const thresholdKeyParams = z.object({ key: z.string().regex(/^[a-z][a-z0-9_]*$/).max(64) });
const thresholdValue = z.object({
  label: z.string().trim().min(1).max(96),
  unit: z.string().trim().min(1).max(32),
  warning: z.number().finite().min(0),
  alarm: z.number().finite().positive(),
});
const thresholdValueBody = thresholdValue.refine((value) => value.warning < value.alarm, {
  message: 'warning must be lower than alarm',
  path: ['alarm'],
});
const thresholdUpdateBody = thresholdValue.extend({
  version: z.number().int().positive(),
}).refine((value) => value.warning < value.alarm, {
  message: 'warning must be lower than alarm',
  path: ['alarm'],
});
const reportExportBody = z.object({ report: z.enum(['alerts', 'workOrders', 'assets', 'daily']) });

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

function formatExportFileName(report: z.infer<typeof reportExportBody>['report']): string {
  const date = new Date().toISOString().slice(0, 10);
  return `utility-tunnel-${report}-${date}.json`;
}

export async function registerOperationsRoutes(app: FastifyInstance): Promise<void> {
  app.get('/v1/health', async () => {
    return { status: 'ok', service: 'utility-tunnel-api', kind: 'liveness' };
  });

  app.get('/v1/ready', async () => {
    await query('SELECT 1');
    return { status: 'ok', service: 'utility-tunnel-api', kind: 'readiness' };
  });

  app.get('/v1/dashboard/overview', { preHandler: [authenticate, requirePermission('dashboard.read')] }, async () => {
    const [summary, latestAlerts, latestTelemetry] = await Promise.all([
      query<{ online_assets: string; total_assets: string; open_alerts: string; open_work_orders: string }>(
        `SELECT
           count(*) FILTER (WHERE operational_status IN ('normal', 'warning', 'alarm')) AS online_assets,
           count(*) AS total_assets,
           (SELECT count(*) FROM alert WHERE status IN ('open', 'acknowledged')) AS open_alerts,
           (SELECT count(*) FROM work_order WHERE status NOT IN ('completed', 'cancelled')) AS open_work_orders
         FROM asset`,
      ),
      query('SELECT id, code, severity, status, title, opened_at FROM alert WHERE status <> $1 ORDER BY opened_at DESC LIMIT 5', ['closed']),
      query(
        `SELECT DISTINCT ON (reading.asset_id, reading.metric_code)
                reading.id, asset.code AS asset_code, reading.metric_code, reading.numeric_value,
                reading.text_value, reading.unit, reading.quality, reading.recorded_at
         FROM telemetry_reading reading
         JOIN asset ON asset.id = reading.asset_id
         ORDER BY reading.asset_id, reading.metric_code, reading.recorded_at DESC
         LIMIT 20`,
      ),
    ]);
    return { summary: summary.rows[0], latestAlerts: latestAlerts.rows, latestTelemetry: latestTelemetry.rows };
  });

  app.get('/v1/assets', { preHandler: [authenticate, requirePermission('asset.read')] }, async (request, reply) => {
    const parsed = assetListQuery.safeParse(request.query);
    if (!parsed.success) return reply.code(400).send({ error: 'invalid_query', message: 'Invalid asset filter.' });
    const pagination = { ...parsed.data, offset: (parsed.data.page - 1) * parsed.data.pageSize };
    const where: string[] = [];
    const parameters: unknown[] = [];
    if (pagination.q) {
      parameters.push(`%${pagination.q}%`);
      where.push(`(a.code ILIKE $${parameters.length} OR a.name ILIKE $${parameters.length} OR z.code ILIKE $${parameters.length} OR z.name ILIKE $${parameters.length})`);
    }
    if (pagination.zone) {
      parameters.push(pagination.zone);
      where.push(`z.code = $${parameters.length}`);
    }
    if (pagination.status) {
      parameters.push(pagination.status);
      where.push(`a.operational_status = $${parameters.length}`);
    }
    const whereClause = where.length ? `WHERE ${where.join(' AND ')}` : '';
    const dataParameters = [...parameters, pagination.pageSize, pagination.offset];
    const [assets, total] = await Promise.all([
      query(
        `SELECT a.id, a.code, a.name, a.asset_type, a.lifecycle_status, a.operational_status,
                a.model_mesh_code, a.location_x, a.location_y, a.location_z, a.metadata,
                z.code AS zone_code, z.name AS zone_name, a.updated_at
         FROM asset a JOIN zone z ON z.id = a.zone_id
         ${whereClause}
         ORDER BY z.sequence, a.code
         LIMIT $${dataParameters.length - 1} OFFSET $${dataParameters.length}`,
        dataParameters,
      ),
      query<{ count: string }>(`SELECT count(*) FROM asset a JOIN zone z ON z.id = a.zone_id ${whereClause}`, parameters),
    ]);
    return reply.send({ items: assets.rows, page: pagination.page, pageSize: pagination.pageSize, total: Number(total.rows[0]?.count ?? 0) });
  });

  app.get('/v1/alerts', { preHandler: [authenticate, requirePermission('alert.read')] }, async (request, reply) => {
    const pagination = requestPagination(request, reply);
    if (!pagination) return;
    const [alerts, total] = await Promise.all([
      query(
        `SELECT al.id, al.code, al.severity, al.category, al.status, al.title, al.detail, al.opened_at,
                al.acknowledged_at, acknowledger.display_name AS acknowledged_by,
                asset.code AS asset_code, asset.name AS asset_name, zone.code AS zone_code
         FROM alert al
         JOIN asset ON asset.id = al.asset_id
         JOIN zone ON zone.id = asset.zone_id
         LEFT JOIN app_user acknowledger ON acknowledger.id = al.acknowledged_by
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
      if (!['open', 'acknowledged'].includes(alert.status)) return undefined;
      const existingOrder = await client.query<{ id: string }>('SELECT id FROM work_order WHERE source_alert_id = $1 LIMIT 1', [alert.id]);
      if (existingOrder.rowCount) return undefined;
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

    if (created === null) return reply.code(404).send({ error: 'not_found', message: 'Alert not found.' });
    if (created === undefined) return reply.code(409).send({ error: 'conflict', message: 'This alert is closed or already has a work order.' });
    return reply.code(201).send(created);
  });

  app.post('/v1/work-orders', { preHandler: [authenticate, requirePermission('work_order.write')] }, async (request, reply) => {
    const body = manualWorkOrderBody.safeParse(request.body);
    if (!body.success) return reply.code(400).send({ error: 'invalid_request', message: 'A valid asset and work order title are required.' });
    const actor = request as AuthenticatedRequest;

    const created = await inTransaction(async (client) => {
      const assetResult = await client.query<{ id: string; code: string; operational_status: string }>(
        'SELECT id, code, operational_status FROM asset WHERE id = $1 FOR UPDATE',
        [body.data.assetId],
      );
      const asset = assetResult.rows[0];
      if (!asset) return null;
      const priority = body.data.priority ?? (asset.operational_status === 'alarm' ? 'urgent' : asset.operational_status === 'warning' ? 'high' : 'normal');
      const result = await client.query(
        `INSERT INTO work_order (code, asset_id, title, description, priority, status, created_by, due_at)
         VALUES ($1, $2, $3, $4, $5, 'open', $6, $7)
         RETURNING id, code, status, priority, title, created_at, updated_at`,
        [code('WO'), asset.id, body.data.title, body.data.description ?? null, priority, actor.user.id, body.data.dueAt ?? null],
      );
      const workOrder = result.rows[0];
      await client.query(
        `INSERT INTO work_order_event (work_order_id, event_type, to_status, note, actor_id)
         VALUES ($1, 'created_manual', 'open', $2, $3)`,
        [workOrder.id, `手工创建，资产：${asset.code}`, actor.user.id],
      );
      await writeAudit(client, {
        actorId: actor.user.id,
        action: 'work_order.create_manual',
        resourceType: 'work_order',
        resourceId: workOrder.id,
        requestId: request.id,
        afterValue: workOrder,
        detail: { assetId: asset.id, assetCode: asset.code },
      });
      return workOrder;
    });

    if (created === null) return reply.code(404).send({ error: 'not_found', message: 'Asset not found.' });
    return reply.code(201).send(created);
  });

  app.get('/v1/work-orders', { preHandler: [authenticate, requirePermission('work_order.read')] }, async (request, reply) => {
    const pagination = requestPagination(request, reply);
    if (!pagination) return;
    const [orders, total] = await Promise.all([
      query(
        `SELECT wo.id, wo.code, wo.source_alert_id, wo.title, wo.description, wo.priority, wo.status,
                wo.due_at, wo.created_at, wo.updated_at,
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
      const existing = await client.query<{ id: string; status: string; source_alert_id: string | null; asset_id: string | null }>('SELECT id, status, source_alert_id, asset_id FROM work_order WHERE id = $1 FOR UPDATE', [workOrderId]);
      const workOrder = existing.rows[0];
      if (!workOrder) return null;
      assertTransition(workOrderTransitions, workOrder.status, body.data.to);
      const result = await client.query(
        `UPDATE work_order
         SET status = $2::varchar,
             assigned_to = CASE WHEN $2::varchar = 'assigned' THEN $3 ELSE assigned_to END,
             completed_at = CASE WHEN $2::varchar = 'completed' THEN now() ELSE completed_at END,
             reviewed_at = CASE WHEN $2::varchar = 'completed' THEN now() ELSE reviewed_at END,
             reviewed_by = CASE WHEN $2::varchar = 'completed' THEN $3 ELSE reviewed_by END,
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
      let resolvedAlert: { id: string; code: string; status: string } | null = null;
      if (body.data.to === 'completed' && workOrder.source_alert_id) {
        const sourceAlert = await client.query<{ id: string; code: string; status: string }>(
          'SELECT id, code, status FROM alert WHERE id = $1 FOR UPDATE',
          [workOrder.source_alert_id],
        );
        const alert = sourceAlert.rows[0];
        if (alert && ['open', 'acknowledged'].includes(alert.status)) {
          const resolution = await client.query<{ id: string; code: string; status: string }>(
            `UPDATE alert
             SET status = 'resolved', resolved_at = now(), version = version + 1
             WHERE id = $1
             RETURNING id, code, status`,
            [alert.id],
          );
          resolvedAlert = resolution.rows[0] ?? null;
          await client.query(
            `INSERT INTO alert_event (alert_id, event_type, from_status, to_status, note, actor_id)
             VALUES ($1, 'resolved_from_work_order', $2, 'resolved', $3, $4)`,
            [alert.id, alert.status, `工单 ${result.rows[0]?.code ?? workOrderId} 已完成：${body.data.note}`, actor.user.id],
          );
          if (workOrder.asset_id) {
            await client.query(
              `UPDATE asset
               SET operational_status = 'normal'
               WHERE id = $1
                 AND operational_status IN ('warning', 'alarm')
                 AND NOT EXISTS (
                   SELECT 1 FROM alert
                   WHERE asset_id = $1 AND status IN ('open', 'acknowledged')
                 )`,
              [workOrder.asset_id],
            );
          }
          await writeAudit(client, {
            actorId: actor.user.id,
            action: 'alert.resolve_from_work_order',
            resourceType: 'alert',
            resourceId: alert.id,
            requestId: request.id,
            beforeValue: { status: alert.status },
            afterValue: resolvedAlert,
            detail: { workOrderId },
          });
        }
      }
      await writeAudit(client, {
        actorId: actor.user.id,
        action: 'work_order.transition',
        resourceType: 'work_order',
        resourceId: workOrderId,
        requestId: request.id,
        beforeValue: { status: workOrder.status },
        afterValue: result.rows[0],
        detail: { note: body.data.note, resolvedAlertId: resolvedAlert?.id ?? null },
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

  app.get('/v1/thresholds', { preHandler: [authenticate, requirePermission('setting.read')] }, async (_request, reply) => {
    const settings = await query<{ setting_key: string; value: unknown; version: number; updated_at: string }>(
      `SELECT setting_key, value, version, updated_at
       FROM system_setting
       WHERE setting_key LIKE 'threshold.%'
       ORDER BY setting_key`,
    );
    const items = settings.rows.flatMap((setting) => {
      const parsed = thresholdValueBody.safeParse(setting.value);
      if (!parsed.success) return [];
      return [{ key: setting.setting_key.slice('threshold.'.length), ...parsed.data, version: setting.version, updatedAt: setting.updated_at }];
    });
    return reply.send({ items });
  });

  app.put('/v1/thresholds/:key', { preHandler: [authenticate, requirePermission('setting.write')] }, async (request, reply) => {
    const key = thresholdKeyParams.safeParse(request.params);
    const body = thresholdUpdateBody.safeParse(request.body);
    if (!key.success || !body.success) return reply.code(400).send({ error: 'invalid_request', message: 'A valid threshold key and values are required.' });
    const actor = request as AuthenticatedRequest;
    const settingKey = `threshold.${key.data.key}`;
    const updated = await inTransaction(async (client) => {
      const existing = await client.query<{ value: unknown; version: number }>('SELECT value, version FROM system_setting WHERE setting_key = $1 FOR UPDATE', [settingKey]);
      const current = existing.rows[0];
      if (!current) return null;
      if (current.version !== body.data.version) return undefined;
      const result = await client.query<{ setting_key: string; value: unknown; version: number; updated_at: string }>(
        `UPDATE system_setting
         SET value = $2::jsonb, version = version + 1, updated_by = $4
         WHERE setting_key = $1 AND version = $3
         RETURNING setting_key, value, version, updated_at`,
        [settingKey, JSON.stringify({ label: body.data.label, unit: body.data.unit, warning: body.data.warning, alarm: body.data.alarm }), current.version, actor.user.id],
      );
      const setting = result.rows[0];
      if (!setting) return undefined;
      await writeAudit(client, {
        actorId: actor.user.id,
        action: 'setting.threshold.update',
        resourceType: 'system_setting',
        resourceId: undefined,
        requestId: request.id,
        beforeValue: current.value,
        afterValue: setting.value,
        detail: { settingKey, fromVersion: current.version, toVersion: setting.version },
      });
      return setting;
    });
    if (updated === null) return reply.code(404).send({ error: 'not_found', message: 'Threshold not found.' });
    if (updated === undefined) return reply.code(409).send({ error: 'version_conflict', message: 'Threshold was changed by another request. Refresh and retry.' });
    return reply.send({ key: key.data.key, ...body.data, version: updated.version, updatedAt: updated.updated_at });
  });

  app.post('/v1/report-exports', { preHandler: [authenticate, requirePermission('dashboard.read')] }, async (request, reply) => {
    const body = reportExportBody.safeParse(request.body);
    if (!body.success) return reply.code(400).send({ error: 'invalid_request', message: 'A valid report type is required.' });
    const actor = request as AuthenticatedRequest;
    const exportRecord = await inTransaction(async (client) => {
      const result = await client.query<{ id: string; report_type: string; status: string; file_name: string; created_at: string; completed_at: string }>(
        `INSERT INTO report_export (report_type, requested_by, parameters, status, file_name, completed_at)
         VALUES ($1, $2, $3::jsonb, 'completed', $4, now())
         RETURNING id, report_type, status, file_name, created_at, completed_at`,
        [body.data.report, actor.user.id, JSON.stringify({ generatedBy: 'browser-client' }), formatExportFileName(body.data.report)],
      );
      const record = result.rows[0];
      if (!record) throw new Error('Report export did not return a record.');
      await writeAudit(client, {
        actorId: actor.user.id,
        action: 'report.export',
        resourceType: 'report_export',
        resourceId: record.id,
        requestId: request.id,
        afterValue: record,
        detail: { report: body.data.report, delivery: 'browser_download' },
      });
      return record;
    });
    return reply.code(201).send(exportRecord);
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
