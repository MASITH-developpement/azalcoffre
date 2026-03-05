/**
 * Offline Storage System for AZALPLUS Mobile PWA
 *
 * This module provides comprehensive offline support including:
 * - IndexedDB storage via Dexie.js
 * - Delta sync with server
 * - Mutation queue for offline CRUD
 * - Conflict resolution strategies
 * - React hooks for sync status
 *
 * @example
 * ```tsx
 * // In your app initialization
 * import { offlineDb, syncEngine, mutationManager } from '@/core/offline';
 *
 * // Create a record offline
 * const result = await mutationManager.create(tenantId, 'clients', {
 *   nom: 'ACME Corp',
 *   email: 'contact@acme.com',
 * });
 *
 * // Use the sync status hook in components
 * function SyncIndicator() {
 *   const { isOnline, isSyncing, pendingCount, triggerSync } = useSyncStatus();
 *
 *   return (
 *     <button onClick={triggerSync} disabled={!isOnline || isSyncing}>
 *       {isSyncing ? 'Syncing...' : `Sync (${pendingCount} pending)`}
 *     </button>
 *   );
 * }
 * ```
 */

// =============================================================================
// Database
// =============================================================================

export {
  // Database class and instance
  AzalplusOfflineDB,
  offlineDb,
  // Types
  type SyncedRecord,
  type SyncStatus,
  type MutationQueueEntry,
  type MutationType,
  type SyncMetadata,
  // Module types
  type ClientRecord,
  type FactureRecord,
  type FactureLigne,
  type DevisRecord,
  type DevisLigne,
  type ProduitRecord,
  type ContactRecord,
  type InterventionRecord,
  type TempsRecord,
  // Module definitions
  OFFLINE_MODULES,
  type OfflineModule,
  type ModuleRecordTypes,
  // Utility functions
  generateRecordId,
  createSyncedRecord,
  markForUpdate,
  markAsSynced,
  isOfflineModule,
} from './db';

// =============================================================================
// Sync Engine
// =============================================================================

export {
  // Sync engine class and instance
  SyncEngine,
  syncEngine,
  // Types
  type SyncState,
  type ModuleSyncResult,
  type SyncResult,
} from './SyncEngine';

// =============================================================================
// Mutation Manager
// =============================================================================

export {
  // Mutation manager class and instance
  MutationManager,
  mutationManager,
  // Types
  type CreateOptions,
  type UpdateOptions,
  type DeleteOptions,
  type MutationResult,
} from './MutationManager';

// =============================================================================
// Conflict Resolver
// =============================================================================

export {
  // Conflict resolver class and instance
  ConflictResolver,
  conflictResolver,
  // Types
  type ConflictAction,
  type ConflictStrategy,
  type ConflictResolution,
  type ConflictDetails,
  type ConflictHandler,
  type ModuleConflictConfig,
} from './ConflictResolver';

// =============================================================================
// React Hooks
// =============================================================================

export {
  // Main sync status hook
  useSyncStatus,
  // Module-specific sync status
  useModuleSyncStatus,
  // Simple online status
  useOnlineStatus,
  // Pending mutations hook
  usePendingMutations,
  // Auto-sync hook
  useAutoSync,
  // Types
  type SyncStatusState,
  type UseSyncStatusReturn,
  type ModuleSyncStatus,
  type UseModuleSyncStatusReturn,
} from './useSyncStatus';
