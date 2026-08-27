import { describe, expect, it } from 'vitest';
import { setApiBaseUrl } from './api';
import { csvCell } from '../stores/operations';

describe('API base URL validation', () => {
  it('rejects credentials embedded in a connection URL', () => {
    expect(() => setApiBaseUrl('https://operator:secret@example.com/api')).toThrow('不得包含账号或密码');
  });

  it('rejects unsupported protocols before constructing a client URL', () => {
    expect(() => setApiBaseUrl('ftp://example.com/api')).toThrow('必须使用 HTTP 或 HTTPS');
  });

  it('normalizes a trailing slash without persisting credentials', () => {
    expect(() => setApiBaseUrl('https://api.example.com/')).not.toThrow();
  });

  it('rejects query strings and neutralizes spreadsheet formulas in exports', () => {
    expect(() => setApiBaseUrl('https://api.example.com/api?tenant=demo')).toThrow('查询参数');
    expect(csvCell('=SUM(A1:A2)')).toBe("'=SUM(A1:A2)");
    expect(csvCell(-12)).toBe('-12');
  });
});
