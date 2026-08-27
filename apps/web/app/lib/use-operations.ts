'use client';

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ApiError, OperationsApiClient, type ApiSession } from './operations-api';
import { operationsRepository, reduceOperations } from './operations';
import type { OperationsAction, OperationsState } from './operations';

export type DataSource = 'local' | 'api';

export type ApiConnectionInput = {
  baseUrl: string;
  email: string;
  password: string;
};

const dataSourceKey = 'ut-ops.data-source.v1';
const apiBaseUrlKey = 'ut-ops.api-base-url.v1';
const defaultApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8080';

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : '操作未完成，请稍后重试。';
}

export function useOperations() {
  const localState = useSyncExternalStore(operationsRepository.subscribe, operationsRepository.getSnapshot, operationsRepository.getSnapshot);
  const [dataSource, setDataSourceState] = useState<DataSource>('local');
  const [apiBaseUrl, setApiBaseUrl] = useState(defaultApiBaseUrl);
  const [apiClient, setApiClient] = useState<OperationsApiClient | null>(null);
  const [apiSession, setApiSession] = useState<ApiSession | null>(null);
  const [apiState, setApiState] = useState<OperationsState | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [apiError, setApiError] = useState('');
  const currentState = dataSource === 'api' && apiState ? apiState : localState;
  const stateRef = useRef(currentState);
  const revisionRef = useRef(0);

  useEffect(() => {
    stateRef.current = currentState;
  }, [currentState]);

  const refresh = useCallback(async (): Promise<OperationsState | null> => {
    if (!apiClient || !apiSession) return null;
    const next = await apiClient.loadState(apiSession, ++revisionRef.current);
    stateRef.current = next;
    setApiState(next);
    setApiError('');
    return next;
  }, [apiClient, apiSession]);

  const disconnect = useCallback((reason?: string) => {
    setApiSession(null);
    setApiState(null);
    setDataSourceState('local');
    if (typeof window !== 'undefined') window.localStorage.setItem(dataSourceKey, 'local');
    if (reason) setApiError(reason);
  }, []);

  const connect = useCallback(async ({ baseUrl, email, password }: ApiConnectionInput): Promise<boolean> => {
    setIsConnecting(true);
    setApiError('');
    try {
      const client = new OperationsApiClient(baseUrl);
      const session = await client.login(email.trim(), password);
      const next = await client.loadState(session, ++revisionRef.current);
      stateRef.current = next;
      setApiBaseUrl(client.baseUrl);
      setApiClient(client);
      setApiSession(session);
      setApiState(next);
      setDataSourceState('api');
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(dataSourceKey, 'api');
        window.localStorage.setItem(apiBaseUrlKey, client.baseUrl);
      }
      return true;
    } catch (error) {
      setApiError(messageFrom(error));
      return false;
    } finally {
      setIsConnecting(false);
    }
  }, []);

  const setDataSource = useCallback((next: DataSource) => {
    setDataSourceState(next);
    setApiError('');
    if (typeof window !== 'undefined') window.localStorage.setItem(dataSourceKey, next);
  }, []);

  const dispatch = useCallback((action: OperationsAction): OperationsState => {
    if (dataSource !== 'api') return operationsRepository.dispatch(action);
    if (!apiClient || !apiSession || !apiState) {
      setApiError('请先连接并登录 API，再执行远程业务操作。');
      return stateRef.current;
    }
    if (action.type === 'session.switchRole' || action.type === 'telemetry.tick') return stateRef.current;

    const previous = stateRef.current;
    const optimistic = reduceOperations(previous, action);
    if (optimistic === previous) return previous;
    stateRef.current = optimistic;
    setApiState(optimistic);
    void apiClient.executeAction(apiSession, previous, action)
      .then(() => refresh())
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 401) {
          disconnect('登录状态已过期，请重新连接 API。');
          return;
        }
        setApiError(messageFrom(error));
        void refresh().catch(() => setApiState(previous));
      });
    return optimistic;
  }, [apiClient, apiSession, apiState, dataSource, disconnect, refresh]);

  const reset = useCallback(() => {
    if (dataSource === 'api') {
      void refresh().catch((error: unknown) => setApiError(messageFrom(error)));
      return;
    }
    operationsRepository.reset();
  }, [dataSource, refresh]);

  useEffect(() => {
    operationsRepository.hydrate();
    const storedBaseUrl = window.localStorage.getItem(apiBaseUrlKey);
    const timer = window.setTimeout(() => {
      if (storedBaseUrl) setApiBaseUrl(storedBaseUrl);
      if (window.localStorage.getItem(dataSourceKey) === 'api') setDataSourceState('api');
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (dataSource === 'local') {
      const timer = window.setInterval(() => operationsRepository.dispatch({ type: 'telemetry.tick' }), 5_000);
      return () => window.clearInterval(timer);
    }
    if (!apiSession || !apiClient) return;
    const timer = window.setInterval(() => {
      void refresh().catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 401) disconnect('登录状态已过期，请重新连接 API。');
        else setApiError(messageFrom(error));
      });
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [apiClient, apiSession, dataSource, disconnect, refresh]);

  useEffect(() => {
    if (dataSource !== 'api' || !apiClient || !apiSession) return;
    return apiClient.streamTelemetry(apiSession, (readings) => {
      setApiState((previous) => {
        if (!previous) return previous;
        const merged = new Map(previous.telemetry.map((reading) => [`${reading.assetCode}:${reading.metric}`, reading]));
        for (const reading of readings) merged.set(`${reading.assetCode}:${reading.metric}`, reading);
        const next = { ...previous, telemetry: [...merged.values()], revision: previous.revision + 1 };
        stateRef.current = next;
        return next;
      });
      setApiError('');
    }, (error) => {
      if (error instanceof ApiError && error.status === 401) disconnect('登录状态已过期，请重新连接 API。');
    });
  }, [apiClient, apiSession, dataSource, disconnect]);

  return {
    state: currentState,
    dispatch,
    reset,
    remote: {
      dataSource,
      apiBaseUrl,
      isReady: dataSource === 'api' && Boolean(apiSession && apiState),
      isConnecting,
      error: apiError,
      connect,
      disconnect,
      setDataSource,
      refresh: () => refresh().catch((error: unknown) => {
        setApiError(messageFrom(error));
        return null;
      }),
      clearError: () => setApiError(''),
    },
  };
}
