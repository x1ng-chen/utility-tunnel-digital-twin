import { describe, expect, it } from 'vitest';
import { createThresholdDraft, reconcileThresholdDraft, thresholdDraftConflicts } from './thresholdDraft';

const initial = { key: 'temperature', warning: 30, alarm: 40, version: 1 };
const newer = { ...initial, warning: 32, version: 2 };

describe('阈值编辑草稿与刷新并发', () => {
  it('首次载入并同步未修改的配置', () => {
    const draft = reconcileThresholdDraft(undefined, initial);
    expect(reconcileThresholdDraft(draft, newer)).toMatchObject(newer);
  });
  it('刷新不得覆盖未保存的输入或推进其原始版本', () => {
    const draft = { ...createThresholdDraft(initial), warning: 31 };
    const preserved = reconcileThresholdDraft(draft, newer);
    expect(preserved).toBe(draft);
    expect(preserved.version).toBe(1);
    expect(thresholdDraftConflicts(preserved, newer)).toBe(true);
  });
  it('相同值的新版本也必须被识别为冲突', () => {
    const draft = { ...createThresholdDraft(initial), alarm: 45 };
    expect(thresholdDraftConflicts(reconcileThresholdDraft(draft, { ...initial, version: 2 }), { ...initial, version: 2 })).toBe(true);
  });
  it('撤销输入后重新跟随服务端；显式载入后清除冲突', () => {
    const draft = createThresholdDraft(initial);
    draft.warning = 31;
    draft.warning = initial.warning;
    expect(reconcileThresholdDraft(draft, newer)).toMatchObject(newer);
    expect(thresholdDraftConflicts(createThresholdDraft(newer), newer)).toBe(false);
  });
});
