import { describe, expect, it } from 'vitest';
import { resolveApiBaseUrl, setApiBaseUrl } from './api';
import { csvCell } from '../stores/operations';

describe('API base URL validation', () => {
  it('rejects credentials embedded in a connection URL', () => {
    expect(() => setApiBaseUrl('https://operator:secret@example.com/api')).toThrow('不得包含认证信息');
  });

  it('rejects unsupported protocols before constructing a client URL', () => {
    expect(() => setApiBaseUrl('ftp://example.com/api')).toThrow('数据服务地址配置无效');
  });

  it('normalizes a trailing slash without persisting credentials', () => {
    expect(() => setApiBaseUrl('https://api.example.com/')).not.toThrow();
  });

  it('resolves a build-time same-origin API route for the production reverse proxy', () => {
    expect(resolveApiBaseUrl('/api', true, 'https://ops.example.com')).toBe('https://ops.example.com/api');
  });

  it('rejects query strings and neutralizes spreadsheet formulas in exports', () => {
    expect(() => setApiBaseUrl('https://api.example.com/api?tenant=demo')).toThrow('不得包含无关参数');
    expect(csvCell('=SUM(A1:A2)')).toBe("'=SUM(A1:A2)");
    expect(csvCell(-12)).toBe('-12');
  });
});
