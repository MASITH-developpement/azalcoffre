/**
 * React Hook for Sync Status in AZALPLUS Mobile PWA
 *
 * Features:
 * - Real-time sync status monitoring
 * - Online/offline state
 * - Pending mutation count
 * - Trigger sync and retry actions
 * - Module-specific sync status
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { syncEngine, SyncState, SyncResult } from './SyncEngine';
import { mutationManager } from './MutationManager';
import { offlineDb, OfflineModule, SyncMetadata } from './db';
import { useAuth } from '../auth/useAuth';

// ============================================================================
// Types
// ============================================================================

/**
 * Extended sync status with additional computed properties
 */
export interface SyncStatusState extends SyncState {
  /** Has pending changes that need to sync */
  hasPendingChanges: boolean;
  /** Has failed mutations that need attention */
  hasFailedMutations: boolean;
  /** Failed mutations count */
  failedCount: number;
  /** Last sync was successful */
  lastSyncSuccessful: boolean;
}

/**
 * Sync status hook return type
 */
export interface UseSyncStatusReturn extends SyncStatusState {
  /** Trigger full sync for all modules */
  triggerSync: () => Promise<SyncResult | null>;
  /** Retry all failed mutations */
  retryFailed: () => Promise<{ retried: number; errors: string[] }>;
  /** Clear all failed mutations */
  clearFailed: () => Promise<number>;
  /** Sync a specific module */
  syncModule: (module: OfflineModule) => Promise<void>;
  /** Cancel ongoing sync */
  cancelSync: () => void;
  /** Refresh status manually */
  refreshStatus: () => Promise<void>;
}

/**
 * Module-specific sync status
 */
export interface ModuleSyncStatus {
  module: OfflineModule;
  lastSyncAt: Date | null;
  totalRecords: number;
  pendingCount: number;
  status: 'idle' | 'syncing' | 'error';
  lastError?: string;
}

/**
 * Module sync status hook return type
 */
export interface UseModuleSyncStatusReturn extends ModuleSyncStatus {
  /** Trigger sync for this module */
  sync: () => Promise<void>;
  /** Is this module currently syncing */
  isSyncing: boolean;
}

// ============================================================================
// Main Hook: useSyncStatus
// ============================================================================

/**
 * Hook to access sync status and trigger sync operations
 *
 * @returns Sync status state and actions
 *
 * @example
 * ```tsx
 * function SyncIndicator() {
 *   const {
 *     isOnline,
 *     isSyncing,
 *     pendingCount,
 *     triggerSync,
 *     retryFailed
 *   } = useSyncStatus();
 *
 *   if (!isOnline) {
 *     return <Badge>Offline</Badge>;
 *   }
 *
 *   if (isSyncing) {
 *     return <Spinner>Syncing...</Spinner>;
 *   }
 *
 *   if (pendingCount > 0) {
 *     return (
 *       <Button onClick={triggerSync}>
 *         Sync ({pendingCount} pending)
 *       </Button>
 *     );
 *   }
 *
 *   return <Badge color="green">Synced</Badge>;
 * }
 * ```
 */
export function useSyncStatus(): UseSyncStatusReturn {
  const { user, isAuthenticated } = useAuth();
  const tenantId = user?.tenantId;

  const [state, setState] = useState<SyncStatusState>(() => ({
    ...syncEngine.getState(),
    hasPendingChanges: false,
    hasFailedMutations: false,
    failedCount: 0,
    lastSyncSuccessful: true,
  }));

  // Subscribe to sync engine updates
  useEffect(() => {
    const unsubscribe = syncEngine.subscribe((engineState) => {
      setState((prev) => ({
        ...prev,
        ...engineState,
      }));
    });

    return unsubscribe;
  }, []);

  // Update pending/failed counts periodically and on sync state changes
  useEffect(() => {
    if (!tenantId) return;

    const updateCounts = async () => {
      try {
        const pendingCount = await mutationManager.getPendingCount(tenantId);
        const failedCount = await mutationManager.getFailedCount(tenantId);

        setState((prev) => ({
          ...prev,
          pendingCount,
          failedCount,
          hasPendingChanges: pendingCount > 0,
          hasFailedMutations: failedCount > 0,
        }));
      } catch {
        // Ignore errors
      }
    };

    updateCounts();

    // Update counts periodically
    const interval = setInterval(updateCounts, 10000); // Every 10 seconds

    return () => clearInterval(interval);
  }, [tenantId, state.isSyncing]);

  // Trigger full sync
  const triggerSync = useCallback(async (): Promise<SyncResult | null> => {
    if (!tenantId || !isAuthenticated) {
      return null;
    }

    const result = await syncEngine.syncAll(tenantId);

    setState((prev) => ({
      ...prev,
      lastSyncSuccessful: result.success,
    }));

    return result;
  }, [tenantId, isAuthenticated]);

  // Retry failed mutations
  const retryFailed = useCallback(async (): Promise<{ retried: number; errors: string[] }> => {
    if (!tenantId) {
      return { retried: 0, errors: ['Not authenticated'] };
    }

    return mutationManager.retryFailed(tenantId);
  }, [tenantId]);

  // Clear failed mutations
  const clearFailed = useCallback(async (): Promise<number> => {
    if (!tenantId) {
      return 0;
    }

    return mutationManager.clearFailed(tenantId);
  }, [tenantId]);

  // Sync specific module
  const syncModule = useCallback(
    async (module: OfflineModule): Promise<void> => {
      if (!tenantId) return;

      await syncEngine.syncModule(tenantId, module);
    },
    [tenantId]
  );

  // Cancel ongoing sync
  const cancelSync = useCallback((): void => {
    syncEngine.cancelSync();
  }, []);

  // Refresh status manually
  const refreshStatus = useCallback(async (): Promise<void> => {
    if (!tenantId) return;

    const pendingCount = await mutationManager.getPendingCount(tenantId);
    const failedCount = await mutationManager.getFailedCount(tenantId);

    setState((prev) => ({
      ...prev,
      pendingCount,
      failedCount,
      hasPendingChanges: pendingCount > 0,
      hasFailedMutations: failedCount > 0,
    }));
  }, [tenantId]);

  return useMemo(
    () => ({
      ...state,
      triggerSync,
      retryFailed,
      clearFailed,
      syncModule,
      cancelSync,
      refreshStatus,
    }),
    [state, triggerSync, retryFailed, clearFailed, syncModule, cancelSync, refreshStatus]
  );
}

// ============================================================================
// Hook: useModuleSyncStatus
// ============================================================================

/**
 * Hook to get sync status for a specific module
 *
 * @param module - The module to get status for
 * @returns Module-specific sync status and actions
 *
 * @example
 * ```tsx
 * function ClientsSyncStatus() {
 *   const { lastSyncAt, pendingCount, sync, isSyncing } = useModuleSyncStatus('clients');
 *
 *   return (
 *     <div>
 *       <p>Last sync: {lastSyncAt?.toLocaleString() || 'Never'}</p>
 *       <p>Pending changes: {pendingCount}</p>
 *       <button onClick={sync} disabled={isSyncing}>
 *         {isSyncing ? 'Syncing...' : 'Sync Now'}
 *       </button>
 *     </div>
 *   );
 * }
 * ```
 */
export function useModuleSyncStatus(module: OfflineModule): UseModuleSyncStatusReturn {
  const { user } = useAuth();
  const tenantId = user?.tenantId;
  const { currentModule, isSyncing: globalSyncing } = useSyncStatus();

  const [status, setStatus] = useState<ModuleSyncStatus>({
    module,
    lastSyncAt: null,
    totalRecords: 0,
    pendingCount: 0,
    status: 'idle',
  });

  // Load module status
  useEffect(() => {
    if (!tenantId) return;

    const loadStatus = async () => {
      try {
        const [metadata, pendingCount] = await Promise.all([
          offlineDb.getSyncMetadata(tenantId, module),
          mutationManager.getPendingCount(tenantId, module),
        ]);

        setStatus({
          module,
          lastSyncAt: metadata?.last_sync_at ? new Date(metadata.last_sync_at) : null,
          totalRecords: metadata?.total_records || 0,
          pendingCount,
          status: metadata?.status || 'idle',
          lastError: metadata?.last_error,
        });
      } catch {
        // Ignore errors
      }
    };

    loadStatus();

    // Refresh when sync state changes
    const interval = setInterval(loadStatus, 5000);
    return () => clearInterval(interval);
  }, [tenantId, module, globalSyncing]);

  // Sync this module
  const sync = useCallback(async (): Promise<void> => {
    if (!tenantId) return;

    setStatus((prev) => ({ ...prev, status: 'syncing' }));

    try {
      await syncEngine.syncModule(tenantId, module);
    } finally {
      // Status will be updated by the effect
    }
  }, [tenantId, module]);

  const isSyncing = globalSyncing && currentModule === module;

  return useMemo(
    () => ({
      ...status,
      sync,
      isSyncing,
    }),
    [status, sync, isSyncing]
  );
}

// ============================================================================
// Hook: useOnlineStatus
// ============================================================================

/**
 * Simple hook for online/offline status
 *
 * @returns Whether the device is online
 *
 * @example
 * ```tsx
 * function NetworkIndicator() {
 *   const isOnline = useOnlineStatus();
 *   return <Badge color={isOnline ? 'green' : 'red'}>{isOnline ? 'Online' : 'Offline'}</Badge>;
 * }
 * ```
 */
export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return isOnline;
}

// ============================================================================
// Hook: usePendingMutations
// ============================================================================

/**
 * Hook to get pending mutations details
 *
 * @param module - Optional module filter
 * @returns Pending and failed mutations with actions
 *
 * @example
 * ```tsx
 * function PendingChanges() {
 *   const { pending, failed, retryAll, clearAll } = usePendingMutations();
 *
 *   return (
 *     <div>
 *       <h3>Pending: {pending.length}</h3>
 *       <h3>Failed: {failed.length}</h3>
 *       {failed.length > 0 && (
 *         <>
 *           <button onClick={retryAll}>Retry All</button>
 *           <button onClick={clearAll}>Clear All</button>
 *         </>
 *       )}
 *     </div>
 *   );
 * }
 * ```
 */
export function usePendingMutations(module?: OfflineModule) {
  const { user } = useAuth();
  const tenantId = user?.tenantId;
  const { isSyncing } = useSyncStatus();

  const [pending, setPending] = useState<
    Array<{ id: number; module: string; type: string; recordId: string; createdAt: Date }>
  >([]);
  const [failed, setFailed] = useState<
    Array<{ id: number; module: string; type: string; recordId: string; error: string; retries: number }>
  >([]);

  // Load mutations
  useEffect(() => {
    if (!tenantId) return;

    const loadMutations = async () => {
      try {
        const [pendingMutations, failedMutations] = await Promise.all([
          mutationManager.getPendingMutations(tenantId, module),
          mutationManager.getFailedMutations(tenantId, module),
        ]);

        setPending(
          pendingMutations.map((m) => ({
            id: m.id!,
            module: m.module,
            type: m.mutation_type,
            recordId: m.record_id,
            createdAt: new Date(m.created_at),
          }))
        );

        setFailed(
          failedMutations.map((m) => ({
            id: m.id!,
            module: m.module,
            type: m.mutation_type,
            recordId: m.record_id,
            error: m.last_error || 'Unknown error',
            retries: m.retry_count,
          }))
        );
      } catch {
        // Ignore errors
      }
    };

    loadMutations();
  }, [tenantId, module, isSyncing]);

  // Retry all failed
  const retryAll = useCallback(async () => {
    if (!tenantId) return;
    await mutationManager.retryFailed(tenantId, module);
  }, [tenantId, module]);

  // Clear all failed
  const clearAll = useCallback(async () => {
    if (!tenantId) return;
    await mutationManager.clearFailed(tenantId, module);
  }, [tenantId, module]);

  // Cancel a specific mutation
  const cancel = useCallback(async (mutationId: number) => {
    await mutationManager.cancelMutation(mutationId);
  }, []);

  return useMemo(
    () => ({
      pending,
      failed,
      retryAll,
      clearAll,
      cancel,
      totalPending: pending.length,
      totalFailed: failed.length,
    }),
    [pending, failed, retryAll, clearAll, cancel]
  );
}

// ============================================================================
// Hook: useAutoSync
// ============================================================================

/**
 * Hook that automatically syncs when coming online
 *
 * @param enabled - Whether auto-sync is enabled
 * @param debounceMs - Debounce delay in milliseconds
 *
 * @example
 * ```tsx
 * function App() {
 *   useAutoSync(true, 2000); // Auto-sync 2 seconds after coming online
 *   return <MainContent />;
 * }
 * ```
 */
export function useAutoSync(enabled: boolean = true, debounceMs: number = 1000): void {
  const { user, isAuthenticated } = useAuth();
  const tenantId = user?.tenantId;
  const isOnline = useOnlineStatus();

  useEffect(() => {
    if (!enabled || !isAuthenticated || !tenantId || !isOnline) {
      return;
    }

    // Debounce sync trigger
    const timeoutId = setTimeout(() => {
      syncEngine.syncAll(tenantId).catch(() => {
        // Ignore errors - will retry on next trigger
      });
    }, debounceMs);

    return () => clearTimeout(timeoutId);
  }, [enabled, isAuthenticated, tenantId, isOnline, debounceMs]);
}
