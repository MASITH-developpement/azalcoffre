/**
 * Delta Sync Engine for AZALPLUS Mobile PWA
 *
 * Features:
 * - Delta sync with server (only changed records)
 * - Push offline mutations to server
 * - Pull server changes to local
 * - Sync status subscriptions
 * - Conflict detection and handling
 */

import { apiClient, ApiError } from '../api/client';
import {
  offlineDb,
  SyncedRecord,
  SyncMetadata,
  MutationQueueEntry,
  OfflineModule,
  OFFLINE_MODULES,
  ModuleRecordTypes,
  markAsSynced,
  SyncStatus,
} from './db';
import { ConflictResolver, ConflictResolution } from './ConflictResolver';

// ============================================================================
// Types
// ============================================================================

/**
 * Sync status for UI updates
 */
export interface SyncState {
  isOnline: boolean;
  isSyncing: boolean;
  currentModule: OfflineModule | null;
  lastSyncAt: Date | null;
  pendingCount: number;
  error: string | null;
  progress: {
    module: string;
    current: number;
    total: number;
  } | null;
}

/**
 * Sync result for a single module
 */
export interface ModuleSyncResult {
  module: OfflineModule;
  success: boolean;
  pulled: number;
  pushed: number;
  conflicts: number;
  errors: string[];
}

/**
 * Full sync result
 */
export interface SyncResult {
  success: boolean;
  modules: ModuleSyncResult[];
  duration: number;
  timestamp: Date;
}

/**
 * Server response for delta sync
 */
interface DeltaSyncResponse<T> {
  items: T[];
  deleted_ids: string[];
  last_sync_at: string;
  has_more: boolean;
  total: number;
}

/**
 * Server response for mutation
 */
interface MutationResponse {
  id: string;
  success: boolean;
  data?: Record<string, unknown>;
  error?: string;
  conflict?: boolean;
  server_version?: number;
}

type SyncStatusListener = (state: SyncState) => void;

// ============================================================================
// Sync Engine Class
// ============================================================================

/**
 * Delta Sync Engine
 *
 * Orchestrates synchronization between local IndexedDB and server:
 * 1. Push local mutations to server
 * 2. Pull server changes to local
 * 3. Handle conflicts with configurable strategies
 */
export class SyncEngine {
  private listeners: Set<SyncStatusListener> = new Set();
  private state: SyncState;
  private conflictResolver: ConflictResolver;
  private syncInProgress: boolean = false;
  private abortController: AbortController | null = null;

  constructor() {
    this.state = {
      isOnline: navigator.onLine,
      isSyncing: false,
      currentModule: null,
      lastSyncAt: null,
      pendingCount: 0,
      error: null,
      progress: null,
    };

    this.conflictResolver = new ConflictResolver();

    // Listen for online/offline events
    if (typeof window !== 'undefined') {
      window.addEventListener('online', this.handleOnline);
      window.addEventListener('offline', this.handleOffline);
    }
  }

  // ==========================================================================
  // Event Handlers
  // ==========================================================================

  private handleOnline = (): void => {
    this.updateState({ isOnline: true });
  };

  private handleOffline = (): void => {
    this.updateState({ isOnline: false, isSyncing: false });
    this.abortController?.abort();
  };

  // ==========================================================================
  // State Management
  // ==========================================================================

  private updateState(updates: Partial<SyncState>): void {
    this.state = { ...this.state, ...updates };
    this.notifyListeners();
  }

  private notifyListeners(): void {
    for (const listener of this.listeners) {
      try {
        listener(this.state);
      } catch {
        // Ignore listener errors
      }
    }
  }

  /**
   * Subscribe to sync status updates
   */
  subscribe(listener: SyncStatusListener): () => void {
    this.listeners.add(listener);
    // Immediately notify with current state
    listener(this.state);

    return () => {
      this.listeners.delete(listener);
    };
  }

  /**
   * Get current sync state
   */
  getState(): SyncState {
    return { ...this.state };
  }

  // ==========================================================================
  // Main Sync Methods
  // ==========================================================================

  /**
   * Sync a single module
   */
  async syncModule(tenantId: string, module: OfflineModule): Promise<ModuleSyncResult> {
    const result: ModuleSyncResult = {
      module,
      success: false,
      pulled: 0,
      pushed: 0,
      conflicts: 0,
      errors: [],
    };

    if (!this.state.isOnline) {
      result.errors.push('Device is offline');
      return result;
    }

    try {
      this.updateState({ currentModule: module });

      // Update sync metadata status
      await offlineDb.updateSyncMetadata(tenantId, module, { status: 'syncing' });

      // 1. Push local mutations first
      const pushResult = await this.pushMutations(tenantId, module);
      result.pushed = pushResult.pushed;
      result.conflicts += pushResult.conflicts;
      result.errors.push(...pushResult.errors);

      // 2. Pull server changes
      const pullResult = await this.pullChanges(tenantId, module);
      result.pulled = pullResult.pulled;
      result.conflicts += pullResult.conflicts;
      result.errors.push(...pullResult.errors);

      result.success = result.errors.length === 0;

      // Update sync metadata
      await offlineDb.updateSyncMetadata(tenantId, module, {
        status: result.success ? 'idle' : 'error',
        last_sync_at: new Date().toISOString(),
        last_pull_at: Date.now(),
        last_push_at: Date.now(),
        last_error: result.errors.length > 0 ? result.errors.join('; ') : undefined,
      });
    } catch (error) {
      const message = (error as Error).message || 'Unknown sync error';
      result.errors.push(message);
      await offlineDb.updateSyncMetadata(tenantId, module, {
        status: 'error',
        last_error: message,
      });
    }

    return result;
  }

  /**
   * Sync all modules for a tenant
   */
  async syncAll(tenantId: string): Promise<SyncResult> {
    if (this.syncInProgress) {
      return {
        success: false,
        modules: [],
        duration: 0,
        timestamp: new Date(),
      };
    }

    const startTime = Date.now();
    this.syncInProgress = true;
    this.abortController = new AbortController();

    this.updateState({
      isSyncing: true,
      error: null,
      progress: { module: '', current: 0, total: OFFLINE_MODULES.length },
    });

    const results: ModuleSyncResult[] = [];

    try {
      // Update pending count
      const pendingCount = await offlineDb.getPendingMutationsCount(tenantId);
      this.updateState({ pendingCount });

      // Sync each module
      for (let i = 0; i < OFFLINE_MODULES.length; i++) {
        const module = OFFLINE_MODULES[i];

        // Check if aborted
        if (this.abortController.signal.aborted) {
          break;
        }

        this.updateState({
          progress: { module, current: i + 1, total: OFFLINE_MODULES.length },
        });

        const result = await this.syncModule(tenantId, module);
        results.push(result);
      }

      // Update final state
      const newPendingCount = await offlineDb.getPendingMutationsCount(tenantId);
      const allSuccess = results.every((r) => r.success);

      this.updateState({
        isSyncing: false,
        currentModule: null,
        lastSyncAt: new Date(),
        pendingCount: newPendingCount,
        error: allSuccess ? null : 'Some modules failed to sync',
        progress: null,
      });

      return {
        success: allSuccess,
        modules: results,
        duration: Date.now() - startTime,
        timestamp: new Date(),
      };
    } catch (error) {
      const message = (error as Error).message || 'Sync failed';
      this.updateState({
        isSyncing: false,
        currentModule: null,
        error: message,
        progress: null,
      });

      return {
        success: false,
        modules: results,
        duration: Date.now() - startTime,
        timestamp: new Date(),
      };
    } finally {
      this.syncInProgress = false;
      this.abortController = null;
    }
  }

  /**
   * Cancel ongoing sync
   */
  cancelSync(): void {
    this.abortController?.abort();
  }

  // ==========================================================================
  // Push Mutations
  // ==========================================================================

  /**
   * Push offline mutations to server
   */
  async pushMutations(
    tenantId: string,
    module?: OfflineModule
  ): Promise<{ pushed: number; conflicts: number; errors: string[] }> {
    const result = { pushed: 0, conflicts: 0, errors: [] as string[] };

    // Get pending mutations
    let mutations = await offlineDb.getPendingMutations(tenantId);
    if (module) {
      mutations = mutations.filter((m) => m.module === module);
    }

    for (const mutation of mutations) {
      try {
        // Mark as processing
        await offlineDb.mutationQueue.update(mutation.id!, { status: 'processing' });

        const response = await this.executeMutation(tenantId, mutation);

        if (response.success) {
          // Remove from queue and update local record
          await offlineDb.mutationQueue.delete(mutation.id!);

          if (mutation.mutation_type !== 'delete' && response.data) {
            await this.updateLocalRecord(
              tenantId,
              mutation.module as OfflineModule,
              mutation.record_id,
              response.data
            );
          }

          result.pushed++;
        } else if (response.conflict) {
          // Handle conflict
          result.conflicts++;
          await this.handlePushConflict(tenantId, mutation, response);
        } else {
          // Mark as failed
          await offlineDb.mutationQueue.update(mutation.id!, {
            status: 'failed',
            last_error: response.error || 'Unknown error',
            retry_count: mutation.retry_count + 1,
          });
          result.errors.push(response.error || 'Unknown error');
        }
      } catch (error) {
        const message = (error as Error).message || 'Mutation failed';
        await offlineDb.mutationQueue.update(mutation.id!, {
          status: 'failed',
          last_error: message,
          retry_count: mutation.retry_count + 1,
        });
        result.errors.push(message);
      }
    }

    return result;
  }

  private async executeMutation(
    tenantId: string,
    mutation: MutationQueueEntry
  ): Promise<MutationResponse> {
    const baseUrl = `/api/${mutation.module}`;

    try {
      switch (mutation.mutation_type) {
        case 'create': {
          const response = await apiClient.post<{ id: string }>(baseUrl, mutation.data, {
            headers: { 'X-Tenant-ID': tenantId },
          });
          return {
            id: response.data.id,
            success: true,
            data: response.data as unknown as Record<string, unknown>,
          };
        }

        case 'update': {
          const response = await apiClient.put<Record<string, unknown>>(
            `${baseUrl}/${mutation.record_id}`,
            mutation.data,
            { headers: { 'X-Tenant-ID': tenantId } }
          );
          return {
            id: mutation.record_id,
            success: true,
            data: response.data,
          };
        }

        case 'delete': {
          await apiClient.delete(`${baseUrl}/${mutation.record_id}`, {
            headers: { 'X-Tenant-ID': tenantId },
          });
          return { id: mutation.record_id, success: true };
        }

        default:
          return { id: mutation.record_id, success: false, error: 'Invalid mutation type' };
      }
    } catch (error) {
      const apiError = error as ApiError;

      // Check for conflict (409)
      if (apiError.status === 409) {
        return {
          id: mutation.record_id,
          success: false,
          conflict: true,
          error: apiError.message,
          server_version: (apiError.details?.version as number) || undefined,
        };
      }

      return {
        id: mutation.record_id,
        success: false,
        error: apiError.message || 'Request failed',
      };
    }
  }

  private async handlePushConflict(
    tenantId: string,
    mutation: MutationQueueEntry,
    response: MutationResponse
  ): Promise<void> {
    const module = mutation.module as OfflineModule;

    // Fetch server version
    try {
      const serverResponse = await apiClient.get<Record<string, unknown>>(
        `/api/${module}/${mutation.record_id}`,
        { 'X-Tenant-ID': tenantId }
      );

      const serverRecord = serverResponse.data as SyncedRecord;
      const table = offlineDb.getTable(module);
      const localRecord = await table.get([tenantId, mutation.record_id]);

      if (localRecord && serverRecord) {
        // Resolve conflict
        const resolution = await this.conflictResolver.resolve(
          module,
          localRecord,
          serverRecord
        );

        if (resolution.action === 'use_server') {
          // Use server version
          await table.put(markAsSynced(localRecord, serverRecord));
          await offlineDb.mutationQueue.delete(mutation.id!);
        } else if (resolution.action === 'use_local') {
          // Keep local, retry push
          await offlineDb.mutationQueue.update(mutation.id!, {
            status: 'pending',
            data: { ...mutation.data, _version: serverRecord._version + 1 },
          });
        } else if (resolution.action === 'merge') {
          // Use merged data
          await table.put(markAsSynced(localRecord, resolution.mergedData!));
          await offlineDb.mutationQueue.update(mutation.id!, {
            status: 'pending',
            data: resolution.mergedData,
          });
        }
      }
    } catch {
      // Mark as conflict for manual resolution
      await offlineDb.mutationQueue.update(mutation.id!, {
        status: 'failed',
        last_error: 'Conflict resolution failed',
      });

      // Mark local record as conflict
      const table = offlineDb.getTable(module);
      const localRecord = await table.get([tenantId, mutation.record_id]);
      if (localRecord) {
        await table.update([tenantId, mutation.record_id], {
          _sync_status: 'conflict' as SyncStatus,
        });
      }
    }
  }

  // ==========================================================================
  // Pull Changes
  // ==========================================================================

  /**
   * Pull server changes to local database
   */
  async pullChanges(
    tenantId: string,
    module: OfflineModule
  ): Promise<{ pulled: number; conflicts: number; errors: string[] }> {
    const result = { pulled: 0, conflicts: 0, errors: [] as string[] };

    try {
      // Get last sync timestamp
      const syncMeta = await offlineDb.getSyncMetadata(tenantId, module);
      const lastSyncAt = syncMeta?.last_sync_at || new Date(0).toISOString();

      // Fetch changes from server
      let hasMore = true;
      let cursor: string | undefined;

      while (hasMore) {
        const params = new URLSearchParams({
          since: lastSyncAt,
          limit: '100',
        });
        if (cursor) {
          params.set('cursor', cursor);
        }

        const response = await apiClient.get<DeltaSyncResponse<Record<string, unknown>>>(
          `/api/${module}/sync?${params.toString()}`,
          { 'X-Tenant-ID': tenantId }
        );

        const { items, deleted_ids, last_sync_at, has_more } = response.data;

        // Process updated/created items
        for (const item of items) {
          const pullResult = await this.processServerItem(tenantId, module, item as SyncedRecord);
          if (pullResult === 'conflict') {
            result.conflicts++;
          } else if (pullResult === 'success') {
            result.pulled++;
          }
        }

        // Process deleted items
        for (const id of deleted_ids) {
          await this.processServerDelete(tenantId, module, id);
          result.pulled++;
        }

        // Update cursor
        hasMore = has_more;
        if (items.length > 0) {
          cursor = items[items.length - 1].id as string;
        }

        // Update sync metadata
        await offlineDb.updateSyncMetadata(tenantId, module, {
          last_sync_at,
          last_pull_at: Date.now(),
        });
      }

      // Count total records
      const table = offlineDb.getTable(module);
      const totalRecords = await table.where('tenant_id').equals(tenantId).count();
      await offlineDb.updateSyncMetadata(tenantId, module, { total_records: totalRecords });
    } catch (error) {
      const message = (error as Error).message || 'Pull failed';
      result.errors.push(message);
    }

    return result;
  }

  private async processServerItem(
    tenantId: string,
    module: OfflineModule,
    serverItem: SyncedRecord
  ): Promise<'success' | 'conflict' | 'skipped'> {
    const table = offlineDb.getTable(module);
    const localRecord = await table.get([tenantId, serverItem.id]);

    if (!localRecord) {
      // New record from server
      await table.add({
        ...serverItem,
        tenant_id: tenantId,
        _sync_status: 'synced',
        _local_updated_at: Date.now(),
        _version: serverItem._version || 1,
      } as ModuleRecordTypes[typeof module]);
      return 'success';
    }

    // Check for local modifications
    if (localRecord._sync_status !== 'synced') {
      // Local has pending changes - check for conflict
      const localUpdatedAt = new Date(localRecord.updated_at).getTime();
      const serverUpdatedAt = new Date(serverItem.updated_at).getTime();

      if (serverUpdatedAt > localUpdatedAt) {
        // Server is newer - potential conflict
        const resolution = await this.conflictResolver.resolve(module, localRecord, serverItem);

        if (resolution.action === 'use_server') {
          await table.put({
            ...serverItem,
            tenant_id: tenantId,
            _sync_status: 'synced',
            _local_updated_at: Date.now(),
          } as ModuleRecordTypes[typeof module]);
          return 'success';
        } else if (resolution.action === 'use_local') {
          // Keep local changes, mark for re-push
          return 'skipped';
        } else if (resolution.action === 'merge') {
          await table.put({
            ...resolution.mergedData,
            tenant_id: tenantId,
            _sync_status: 'pending_update',
            _local_updated_at: Date.now(),
          } as ModuleRecordTypes[typeof module]);
          return 'conflict';
        }
      }

      // Local is newer - skip server update
      return 'skipped';
    }

    // No local changes - update from server
    await table.put({
      ...serverItem,
      tenant_id: tenantId,
      _sync_status: 'synced',
      _local_updated_at: Date.now(),
    } as ModuleRecordTypes[typeof module]);
    return 'success';
  }

  private async processServerDelete(
    tenantId: string,
    module: OfflineModule,
    recordId: string
  ): Promise<void> {
    const table = offlineDb.getTable(module);
    const localRecord = await table.get([tenantId, recordId]);

    if (localRecord) {
      // Check if local has pending changes
      if (localRecord._sync_status === 'pending_update') {
        // Conflict: server deleted but local modified
        // For now, respect server delete
        // Could add conflict handling here
      }

      await table.delete([tenantId, recordId]);
    }

    // Also remove any pending mutations for this record
    await offlineDb.mutationQueue
      .where('[tenant_id+record_id]')
      .equals([tenantId, recordId])
      .delete();
  }

  private async updateLocalRecord(
    tenantId: string,
    module: OfflineModule,
    recordId: string,
    serverData: Record<string, unknown>
  ): Promise<void> {
    const table = offlineDb.getTable(module);
    const localRecord = await table.get([tenantId, recordId]);

    if (localRecord) {
      await table.put({
        ...localRecord,
        ...serverData,
        _sync_status: 'synced',
        _local_updated_at: Date.now(),
      } as ModuleRecordTypes[typeof module]);
    }
  }

  // ==========================================================================
  // Cleanup
  // ==========================================================================

  /**
   * Cleanup event listeners
   */
  destroy(): void {
    if (typeof window !== 'undefined') {
      window.removeEventListener('online', this.handleOnline);
      window.removeEventListener('offline', this.handleOffline);
    }
    this.listeners.clear();
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

/**
 * Singleton sync engine instance
 */
export const syncEngine = new SyncEngine();
