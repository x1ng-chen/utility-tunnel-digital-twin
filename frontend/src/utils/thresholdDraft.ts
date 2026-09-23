export interface ThresholdSnapshot {
  key: string;
  warning: number;
  alarm: number;
  version: number;
}

export interface ThresholdDraft extends ThresholdSnapshot {
  originalWarning: number;
  originalAlarm: number;
}

export function createThresholdDraft(item: ThresholdSnapshot): ThresholdDraft {
  return { ...item, originalWarning: item.warning, originalAlarm: item.alarm };
}

/** Only untouched drafts may follow a refreshed server snapshot. */
export function reconcileThresholdDraft(local: ThresholdDraft | undefined, incoming: ThresholdSnapshot): ThresholdDraft {
  if (!local || (local.warning === local.originalWarning && local.alarm === local.originalAlarm)) {
    return createThresholdDraft(incoming);
  }
  return local;
}

export function thresholdDraftConflicts(local: ThresholdDraft, incoming: ThresholdSnapshot): boolean {
  return local.version !== incoming.version;
}
