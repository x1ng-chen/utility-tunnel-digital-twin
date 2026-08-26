export const alertTransitions = {
  open: ['acknowledged'],
  acknowledged: ['resolved'],
  resolved: ['closed', 'acknowledged'],
  closed: [],
} as const;

export const workOrderTransitions = {
  draft: ['open', 'cancelled'],
  open: ['assigned', 'cancelled'],
  assigned: ['in_progress', 'cancelled'],
  in_progress: ['pending_review', 'cancelled'],
  pending_review: ['completed', 'in_progress'],
  completed: [],
  cancelled: [],
} as const;

type TransitionMap = Record<string, readonly string[]>;

export function assertTransition(map: TransitionMap, from: string, to: string): void {
  if (!map[from]?.includes(to)) throw new Error(`Invalid transition: ${from} -> ${to}`);
}
