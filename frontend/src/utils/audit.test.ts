import { describe, expect, it } from 'vitest';
import { presentAudit } from './audit';

describe('presentAudit', () => {
  it('turns a technical audit event into a concise business summary', () => {
    const entry = {
      id: 1,
      actorName: '管理员',
      action: 'gis.feature.updated',
      resourceType: 'spatial_feature',
      resourceId: '6',
      detail: { code: 'SEG-E2E-01', fields: ['status', 'version'] },
      requestId: 'request-1',
      occurredAt: '2026-08-28T08:57:12Z',
    };

    expect(presentAudit(entry)).toEqual({
      title: '更新空间对象',
      description: '已更新空间对象 SEG-E2E-01 的信息。',
    });
  });

  it('does not expose raw implementation details for an unknown event', () => {
    const entry = {
      id: 2,
      actorName: '管理员',
      action: 'telemetry.batch_ingested',
      resourceType: 'telemetry_batch',
      resourceId: '',
      detail: { eventId: 'internal-only' },
      requestId: 'request-2',
      occurredAt: '2026-08-28T08:57:12Z',
    };

    expect(presentAudit(entry)).toEqual({
      title: '完成系统操作',
      description: '已完成一项运维管理操作。',
    });
  });
});
