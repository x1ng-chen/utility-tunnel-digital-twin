'use client';

import { useEffect, useSyncExternalStore } from 'react';
import { operationsRepository } from './operations';

export function useOperations() {
  const state = useSyncExternalStore(operationsRepository.subscribe, operationsRepository.getSnapshot, operationsRepository.getSnapshot);

  useEffect(() => {
    operationsRepository.hydrate();
    const timer = window.setInterval(() => operationsRepository.dispatch({ type: 'telemetry.tick' }), 5_000);
    return () => window.clearInterval(timer);
  }, []);

  return { state, dispatch: operationsRepository.dispatch.bind(operationsRepository), reset: operationsRepository.reset.bind(operationsRepository) };
}
