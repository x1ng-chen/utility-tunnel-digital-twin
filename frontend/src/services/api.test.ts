import { describe, expect, it } from 'vitest';
import { setApiBaseUrl } from './api';

describe('API base URL validation', () => {
  it('rejects credentials embedded in a connection URL', () => {
    expect(() => setApiBaseUrl('https://operator:secret@example.com/api')).toThrow('不得包含账号或密码');
  });

  it('rejects unsupported protocols before constructing a client URL', () => {
    expect(() => setApiBaseUrl('ftp://example.com/api')).toThrow('必须使用 HTTP 或 HTTPS');
  });
});
