import type { PoolClient } from 'pg';

type AuditInput = {
  actorId?: string;
  action: string;
  resourceType: string;
  resourceId?: string;
  requestId?: string;
  beforeValue?: unknown;
  afterValue?: unknown;
  detail?: unknown;
};

export async function writeAudit(client: PoolClient, entry: AuditInput): Promise<void> {
  await client.query(
    `INSERT INTO audit_log (actor_id, action, resource_type, resource_id, request_id, before_value, after_value, detail)
     VALUES ($1, $2, $3, $4, $5, $6, $7, COALESCE($8::jsonb, '{}'::jsonb))`,
    [
      entry.actorId ?? null,
      entry.action,
      entry.resourceType,
      entry.resourceId ?? null,
      entry.requestId ?? null,
      entry.beforeValue ? JSON.stringify(entry.beforeValue) : null,
      entry.afterValue ? JSON.stringify(entry.afterValue) : null,
      entry.detail ? JSON.stringify(entry.detail) : null,
    ],
  );
}
