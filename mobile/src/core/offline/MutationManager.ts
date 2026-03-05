/**
 * Mutation Manager for AZALPLUS Mobile PWA
 *
 * Features:
 * - Offline CRUD operations with queue management
 * - Create, update, delete with pending status
 * - Automatic queue management
 * - Retry failed mutations
 * - Pending count tracking
 */

import {
  offlineDb,
  SyncedRecord,
  MutationQueueEntry,
  OfflineModule,
  ModuleRecordTypes,
  generateRecordId,
  SyncStatus,
  isOfflineModule,
} from './db';
import { syncEngine } from './SyncEngine';

// ============================================================================
// Types
// ============================================================================

/**
 * Options for create operation
 */
export interface CreateOptions {
  /** Trigger sync immediately if online */
  syncImmediately?: boolean;
}

/**
 * Options for update operation
 */
export interface UpdateOptions {
  /** Trigger sync immediately if online */
  syncImmediately?: boolean;
  /** Merge with existing data (true) or replace (false) */
  merge?: boolean;
}

/**
 * Options for delete operation
 */
export interface DeleteOptions {
  /** Trigger sync immediately if online */
  syncImmediately?: boolean;
  /** Soft delete (mark as deleted) vs hard delete */
  soft?: boolean;
}

/**
 * Result of a mutation operation
 */
export interface MutationResult<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  queueId?: number;
}

// ============================================================================
// Mutation Manager Class
// ============================================================================

/**
 * Manages offline CRUD operations
 *
 * All operations are queued locally and synced when online.
 * Records are immediately available locally with pending status.
 */
export class MutationManager {
  // ==========================================================================
  // Create Operations
  // ==========================================================================

  /**
   * Create a new record offline
   *
   * @param tenantId - Tenant ID
   * @param module - Target module
   * @param data - Record data (without id, tenant_id, timestamps)
   * @param options - Create options
   * @returns Created record with generated ID
   */
  async create<T extends OfflineModule>(
    tenantId: string,
    module: T,
    data: Omit<
      ModuleRecordTypes[T],
      'id' | 'tenant_id' | 'created_at' | 'updated_at' | '_sync_status' | '_local_updated_at' | '_version'
    >,
    options: CreateOptions = {}
  ): Promise<MutationResult<ModuleRecordTypes[T]>> {
    if (!isOfflineModule(module)) {
      return { success: false, error: `Module '${module}' is not supported for offline storage` };
    }

    try {
      const now = new Date().toISOString();
      const recordId = generateRecordId();

      // Create full record with sync metadata
      const record: ModuleRecordTypes[T] = {
        ...data,
        id: recordId,
        tenant_id: tenantId,
        created_at: now,
        updated_at: now,
        _sync_status: 'pending_create' as SyncStatus,
        _local_updated_at: Date.now(),
        _version: 1,
      } as ModuleRecordTypes[T];

      // Store in local database
      const table = offlineDb.getTable(module);
      await table.add(record);

      // Add to mutation queue
      const queueId = await offlineDb.mutationQueue.add({
        tenant_id: tenantId,
        module,
        record_id: recordId,
        mutation_type: 'create',
        data: data as Record<string, unknown>,
        created_at: Date.now(),
        retry_count: 0,
        status: 'pending',
      });

      // Sync immediately if requested and online
      if (options.syncImmediately && navigator.onLine) {
        syncEngine.pushMutations(tenantId, module).catch(() => {
          // Ignore - will be synced later
        });
      }

      return { success: true, data: record, queueId };
    } catch (error) {
      return { success: false, error: (error as Error).message };
    }
  }

  // ==========================================================================
  // Update Operations
  // ==========================================================================

  /**
   * Update an existing record offline
   *
   * @param tenantId - Tenant ID
   * @param module - Target module
   * @param id - Record ID
   * @param updates - Partial record updates
   * @param options - Update options
   * @returns Updated record
   */
  async update<T extends OfflineModule>(
    tenantId: string,
    module: T,
    id: string,
    updates: Partial<Omit<ModuleRecordTypes[T], 'id' | 'tenant_id' | 'created_at' | '_sync_status' | '_local_updated_at'>>,
    options: UpdateOptions = {}
  ): Promise<MutationResult<ModuleRecordTypes[T]>> {
    if (!isOfflineModule(module)) {
      return { success: false, error: `Module '${module}' is not supported for offline storage` };
    }

    try {
      const table = offlineDb.getTable(module);
      const existing = await table.get([tenantId, id]);

      if (!existing) {
        return { success: false, error: `Record not found: ${id}` };
      }

      // Determine new sync status
      // If already pending_create, keep that status
      // Otherwise mark as pending_update
      const newSyncStatus: SyncStatus =
        existing._sync_status === 'pending_create' ? 'pending_create' : 'pending_update';

      // Prepare updated data
      const mergedUpdates = options.merge !== false ? { ...existing, ...updates } : updates;

      // Create updated record
      const updatedRecord: ModuleRecordTypes[T] = {
        ...existing,
        ...mergedUpdates,
        updated_at: new Date().toISOString(),
        _sync_status: newSyncStatus,
        _local_updated_at: Date.now(),
        _version: existing._version + 1,
        _server_data: existing._sync_status === 'synced' ? (existing as unknown as Record<string, unknown>) : existing._server_data,
      } as ModuleRecordTypes[T];

      // Update in local database
      await table.put(updatedRecord);

      // Add to mutation queue (or update existing if pending_create)
      const existingMutation = await offlineDb.mutationQueue
        .where('record_id')
        .equals(id)
        .and((m) => m.tenant_id === tenantId && m.module === module && m.status !== 'failed')
        .first();

      let queueId: number | undefined;

      if (existingMutation) {
        // Update existing mutation with new data
        await offlineDb.mutationQueue.update(existingMutation.id!, {
          data: { ...existingMutation.data, ...updates } as Record<string, unknown>,
        });
        queueId = existingMutation.id;
      } else {
        // Create new mutation entry
        queueId = await offlineDb.mutationQueue.add({
          tenant_id: tenantId,
          module,
          record_id: id,
          mutation_type: 'update',
          data: updates as Record<string, unknown>,
          created_at: Date.now(),
          retry_count: 0,
          status: 'pending',
        });
      }

      // Sync immediately if requested and online
      if (options.syncImmediately && navigator.onLine) {
        syncEngine.pushMutations(tenantId, module).catch(() => {
          // Ignore - will be synced later
        });
      }

      return { success: true, data: updatedRecord, queueId };
    } catch (error) {
      return { success: false, error: (error as Error).message };
    }
  }

  // ==========================================================================
  // Delete Operations
  // ==========================================================================

  /**
   * Delete a record offline
   *
   * @param tenantId - Tenant ID
   * @param module - Target module
   * @param id - Record ID
   * @param options - Delete options
   * @returns Success status
   */
  async delete<T extends OfflineModule>(
    tenantId: string,
    module: T,
    id: string,
    options: DeleteOptions = {}
  ): Promise<MutationResult<void>> {
    if (!isOfflineModule(module)) {
      return { success: false, error: `Module '${module}' is not supported for offline storage` };
    }

    try {
      const table = offlineDb.getTable(module);
      const existing = await table.get([tenantId, id]);

      if (!existing) {
        return { success: false, error: `Record not found: ${id}` };
      }

      // Check if this was a locally created record that never synced
      if (existing._sync_status === 'pending_create') {
        // Remove from local database and queue - no need to sync delete
        await table.delete([tenantId, id]);
        await offlineDb.mutationQueue
          .where('record_id')
          .equals(id)
          .and((m) => m.tenant_id === tenantId && m.module === module)
          .delete();

        return { success: true };
      }

      if (options.soft) {
        // Soft delete - mark as deleted
        await table.put({
          ...existing,
          _sync_status: 'pending_delete' as SyncStatus,
          _local_updated_at: Date.now(),
          updated_at: new Date().toISOString(),
        } as ModuleRecordTypes[T]);
      } else {
        // Hard delete from local database
        await table.delete([tenantId, id]);
      }

      // Remove any existing pending mutations for this record
      await offlineDb.mutationQueue
        .where('record_id')
        .equals(id)
        .and((m) => m.tenant_id === tenantId && m.module === module)
        .delete();

      // Add delete mutation to queue
      const queueId = await offlineDb.mutationQueue.add({
        tenant_id: tenantId,
        module,
        record_id: id,
        mutation_type: 'delete',
        created_at: Date.now(),
        retry_count: 0,
        status: 'pending',
      });

      // Sync immediately if requested and online
      if (options.syncImmediately && navigator.onLine) {
        syncEngine.pushMutations(tenantId, module).catch(() => {
          // Ignore - will be synced later
        });
      }

      return { success: true, queueId };
    } catch (error) {
      return { success: false, error: (error as Error).message };
    }
  }

  // ==========================================================================
  // Queue Management
  // ==========================================================================

  /**
   * Get count of pending mutations for a tenant
   */
  async getPendingCount(tenantId: string, module?: OfflineModule): Promise<number> {
    let query = offlineDb.mutationQueue
      .where('tenant_id')
      .equals(tenantId)
      .and((m) => m.status === 'pending');

    if (module) {
      query = query.and((m) => m.module === module);
    }

    return query.count();
  }

  /**
   * Get count of failed mutations for a tenant
   */
  async getFailedCount(tenantId: string, module?: OfflineModule): Promise<number> {
    let query = offlineDb.mutationQueue
      .where('tenant_id')
      .equals(tenantId)
      .and((m) => m.status === 'failed');

    if (module) {
      query = query.and((m) => m.module === module);
    }

    return query.count();
  }

  /**
   * Get all pending mutations for a tenant
   */
  async getPendingMutations(tenantId: string, module?: OfflineModule): Promise<MutationQueueEntry[]> {
    let query = offlineDb.mutationQueue
      .where('tenant_id')
      .equals(tenantId)
      .and((m) => m.status === 'pending');

    if (module) {
      query = query.and((m) => m.module === module);
    }

    return query.sortBy('created_at');
  }

  /**
   * Get all failed mutations for a tenant
   */
  async getFailedMutations(tenantId: string, module?: OfflineModule): Promise<MutationQueueEntry[]> {
    let query = offlineDb.mutationQueue
      .where('tenant_id')
      .equals(tenantId)
      .and((m) => m.status === 'failed');

    if (module) {
      query = query.and((m) => m.module === module);
    }

    return query.sortBy('created_at');
  }

  /**
   * Retry all failed mutations
   */
  async retryFailed(tenantId: string, module?: OfflineModule): Promise<{ retried: number; errors: string[] }> {
    const result = { retried: 0, errors: [] as string[] };

    try {
      // Reset failed mutations to pending
      const failedMutations = await this.getFailedMutations(tenantId, module);

      for (const mutation of failedMutations) {
        // Check if max retries exceeded
        if (mutation.retry_count >= 5) {
          result.errors.push(`Mutation ${mutation.id} exceeded max retries`);
          continue;
        }

        await offlineDb.mutationQueue.update(mutation.id!, {
          status: 'pending',
          last_error: undefined,
        });
        result.retried++;
      }

      // Trigger sync if online
      if (navigator.onLine && result.retried > 0) {
        if (module) {
          syncEngine.pushMutations(tenantId, module).catch(() => {
            // Ignore - will be retried later
          });
        } else {
          syncEngine.syncAll(tenantId).catch(() => {
            // Ignore - will be retried later
          });
        }
      }
    } catch (error) {
      result.errors.push((error as Error).message);
    }

    return result;
  }

  /**
   * Clear all failed mutations (give up)
   */
  async clearFailed(tenantId: string, module?: OfflineModule): Promise<number> {
    const failedMutations = await this.getFailedMutations(tenantId, module);
    let cleared = 0;

    for (const mutation of failedMutations) {
      await offlineDb.mutationQueue.delete(mutation.id!);

      // Also update local record sync status if it exists
      if (mutation.module && isOfflineModule(mutation.module)) {
        const table = offlineDb.getTable(mutation.module);
        const record = await table.get([tenantId, mutation.record_id]);
        if (record && record._sync_status === 'error') {
          await table.update([tenantId, mutation.record_id], {
            _sync_status: 'synced' as SyncStatus,
          });
        }
      }

      cleared++;
    }

    return cleared;
  }

  /**
   * Cancel a specific pending mutation
   */
  async cancelMutation(mutationId: number): Promise<boolean> {
    try {
      const mutation = await offlineDb.mutationQueue.get(mutationId);
      if (!mutation) {
        return false;
      }

      // Remove from queue
      await offlineDb.mutationQueue.delete(mutationId);

      // If it was a create, also remove the local record
      if (mutation.mutation_type === 'create' && isOfflineModule(mutation.module)) {
        const table = offlineDb.getTable(mutation.module);
        await table.delete([mutation.tenant_id, mutation.record_id]);
      }

      // If it was an update/delete, restore the record to synced status
      if (
        (mutation.mutation_type === 'update' || mutation.mutation_type === 'delete') &&
        isOfflineModule(mutation.module)
      ) {
        const table = offlineDb.getTable(mutation.module);
        const record = await table.get([mutation.tenant_id, mutation.record_id]);
        if (record) {
          // Restore from server data if available
          const serverData = record._server_data;
          if (serverData) {
            await table.put({
              ...serverData,
              tenant_id: mutation.tenant_id,
              _sync_status: 'synced' as SyncStatus,
              _local_updated_at: Date.now(),
            } as ModuleRecordTypes[typeof mutation.module]);
          } else {
            await table.update([mutation.tenant_id, mutation.record_id], {
              _sync_status: 'synced' as SyncStatus,
            });
          }
        }
      }

      return true;
    } catch {
      return false;
    }
  }

  // ==========================================================================
  // Bulk Operations
  // ==========================================================================

  /**
   * Create multiple records at once
   */
  async bulkCreate<T extends OfflineModule>(
    tenantId: string,
    module: T,
    items: Array<
      Omit<
        ModuleRecordTypes[T],
        'id' | 'tenant_id' | 'created_at' | 'updated_at' | '_sync_status' | '_local_updated_at' | '_version'
      >
    >,
    options: CreateOptions = {}
  ): Promise<MutationResult<ModuleRecordTypes[T][]>> {
    const results: ModuleRecordTypes[T][] = [];
    const errors: string[] = [];

    for (const item of items) {
      const result = await this.create(tenantId, module, item, { syncImmediately: false });
      if (result.success && result.data) {
        results.push(result.data);
      } else if (result.error) {
        errors.push(result.error);
      }
    }

    // Sync if requested
    if (options.syncImmediately && navigator.onLine) {
      syncEngine.pushMutations(tenantId, module).catch(() => {
        // Ignore - will be synced later
      });
    }

    return {
      success: errors.length === 0,
      data: results,
      error: errors.length > 0 ? errors.join('; ') : undefined,
    };
  }

  /**
   * Delete multiple records at once
   */
  async bulkDelete<T extends OfflineModule>(
    tenantId: string,
    module: T,
    ids: string[],
    options: DeleteOptions = {}
  ): Promise<MutationResult<void>> {
    const errors: string[] = [];

    for (const id of ids) {
      const result = await this.delete(tenantId, module, id, { ...options, syncImmediately: false });
      if (!result.success && result.error) {
        errors.push(result.error);
      }
    }

    // Sync if requested
    if (options.syncImmediately && navigator.onLine) {
      syncEngine.pushMutations(tenantId, module).catch(() => {
        // Ignore - will be synced later
      });
    }

    return {
      success: errors.length === 0,
      error: errors.length > 0 ? errors.join('; ') : undefined,
    };
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

/**
 * Singleton mutation manager instance
 */
export const mutationManager = new MutationManager();
