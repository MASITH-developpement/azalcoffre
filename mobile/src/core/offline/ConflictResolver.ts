/**
 * Conflict Resolver for AZALPLUS Mobile PWA
 *
 * Features:
 * - Last-write-wins strategy
 * - Field-level merge option
 * - Module-specific conflict rules
 * - Custom conflict handlers
 */

import { SyncedRecord, OfflineModule } from './db';

// ============================================================================
// Types
// ============================================================================

/**
 * Conflict resolution action
 */
export type ConflictAction = 'use_server' | 'use_local' | 'merge' | 'manual';

/**
 * Conflict resolution strategies
 */
export type ConflictStrategy = 'server_wins' | 'local_wins' | 'last_write_wins' | 'field_merge' | 'manual';

/**
 * Result of conflict resolution
 */
export interface ConflictResolution {
  action: ConflictAction;
  mergedData?: Record<string, unknown>;
  conflictFields?: string[];
  reason?: string;
}

/**
 * Conflict details for manual resolution
 */
export interface ConflictDetails {
  module: OfflineModule;
  recordId: string;
  localRecord: SyncedRecord;
  serverRecord: SyncedRecord;
  conflictFields: string[];
  suggestedResolution: ConflictResolution;
}

/**
 * Custom conflict handler function type
 */
export type ConflictHandler = (
  module: OfflineModule,
  localRecord: SyncedRecord,
  serverRecord: SyncedRecord
) => ConflictResolution | Promise<ConflictResolution>;

/**
 * Module-specific conflict configuration
 */
export interface ModuleConflictConfig {
  strategy: ConflictStrategy;
  /** Fields that always use server value */
  serverWinsFields?: string[];
  /** Fields that always use local value */
  localWinsFields?: string[];
  /** Fields to ignore in conflict detection */
  ignoreFields?: string[];
  /** Custom handler for this module */
  customHandler?: ConflictHandler;
}

// ============================================================================
// Default Configuration
// ============================================================================

/**
 * Default conflict configurations per module
 *
 * - factures: server_wins (invoices are critical, server is source of truth)
 * - devis: last_write_wins (quotes can be edited by multiple people)
 * - clients: field_merge (merge changes where possible)
 * - produits: server_wins (product data should be consistent)
 * - contacts: last_write_wins
 * - interventions: field_merge (technicians may update different fields)
 * - temps: local_wins (time tracking is user-specific)
 */
const DEFAULT_MODULE_CONFIGS: Record<OfflineModule, ModuleConflictConfig> = {
  factures: {
    strategy: 'server_wins',
    ignoreFields: ['_sync_status', '_local_updated_at', '_version', '_server_data'],
  },
  devis: {
    strategy: 'last_write_wins',
    serverWinsFields: ['numero', 'client_id'],
    ignoreFields: ['_sync_status', '_local_updated_at', '_version', '_server_data'],
  },
  clients: {
    strategy: 'field_merge',
    serverWinsFields: ['code', 'siret', 'tva_intra'],
    ignoreFields: ['_sync_status', '_local_updated_at', '_version', '_server_data'],
  },
  produits: {
    strategy: 'server_wins',
    localWinsFields: ['stock_quantite'], // Local stock adjustments preserved
    ignoreFields: ['_sync_status', '_local_updated_at', '_version', '_server_data'],
  },
  contacts: {
    strategy: 'last_write_wins',
    ignoreFields: ['_sync_status', '_local_updated_at', '_version', '_server_data'],
  },
  interventions: {
    strategy: 'field_merge',
    serverWinsFields: ['numero', 'client_id', 'statut'],
    localWinsFields: ['rapport', 'signature_client', 'photos', 'duree_reelle'],
    ignoreFields: ['_sync_status', '_local_updated_at', '_version', '_server_data'],
  },
  temps: {
    strategy: 'local_wins',
    serverWinsFields: ['facture_id'], // Billing reference comes from server
    ignoreFields: ['_sync_status', '_local_updated_at', '_version', '_server_data'],
  },
};

/**
 * System fields that should always be ignored in conflict detection
 */
const SYSTEM_FIELDS = [
  'id',
  'tenant_id',
  'created_at',
  '_sync_status',
  '_local_updated_at',
  '_version',
  '_server_data',
];

// ============================================================================
// Conflict Resolver Class
// ============================================================================

/**
 * Resolves conflicts between local and server records
 */
export class ConflictResolver {
  private moduleConfigs: Map<OfflineModule, ModuleConflictConfig>;
  private globalHandler: ConflictHandler | null = null;
  private pendingConflicts: Map<string, ConflictDetails> = new Map();

  constructor(configs?: Partial<Record<OfflineModule, ModuleConflictConfig>>) {
    this.moduleConfigs = new Map();

    // Initialize with defaults
    for (const [module, config] of Object.entries(DEFAULT_MODULE_CONFIGS)) {
      this.moduleConfigs.set(module as OfflineModule, config);
    }

    // Override with custom configs
    if (configs) {
      for (const [module, config] of Object.entries(configs)) {
        if (config) {
          this.moduleConfigs.set(module as OfflineModule, {
            ...DEFAULT_MODULE_CONFIGS[module as OfflineModule],
            ...config,
          });
        }
      }
    }
  }

  // ==========================================================================
  // Configuration
  // ==========================================================================

  /**
   * Set configuration for a specific module
   */
  setModuleConfig(module: OfflineModule, config: Partial<ModuleConflictConfig>): void {
    const existing = this.moduleConfigs.get(module) || DEFAULT_MODULE_CONFIGS[module];
    this.moduleConfigs.set(module, { ...existing, ...config });
  }

  /**
   * Set a global conflict handler (called for all conflicts)
   */
  setGlobalHandler(handler: ConflictHandler | null): void {
    this.globalHandler = handler;
  }

  /**
   * Get module configuration
   */
  getModuleConfig(module: OfflineModule): ModuleConflictConfig {
    return this.moduleConfigs.get(module) || DEFAULT_MODULE_CONFIGS[module];
  }

  // ==========================================================================
  // Conflict Resolution
  // ==========================================================================

  /**
   * Resolve a conflict between local and server records
   */
  async resolve(
    module: OfflineModule,
    localRecord: SyncedRecord,
    serverRecord: SyncedRecord
  ): Promise<ConflictResolution> {
    const config = this.getModuleConfig(module);

    // Use global handler if set
    if (this.globalHandler) {
      return this.globalHandler(module, localRecord, serverRecord);
    }

    // Use module-specific custom handler if set
    if (config.customHandler) {
      return config.customHandler(module, localRecord, serverRecord);
    }

    // Apply strategy-based resolution
    switch (config.strategy) {
      case 'server_wins':
        return this.resolveServerWins(localRecord, serverRecord, config);

      case 'local_wins':
        return this.resolveLocalWins(localRecord, serverRecord, config);

      case 'last_write_wins':
        return this.resolveLastWriteWins(localRecord, serverRecord, config);

      case 'field_merge':
        return this.resolveFieldMerge(localRecord, serverRecord, config);

      case 'manual':
        return this.resolveManual(module, localRecord, serverRecord);

      default:
        // Default to server wins for safety
        return this.resolveServerWins(localRecord, serverRecord, config);
    }
  }

  /**
   * Server wins strategy - server data takes precedence
   */
  private resolveServerWins(
    localRecord: SyncedRecord,
    serverRecord: SyncedRecord,
    config: ModuleConflictConfig
  ): ConflictResolution {
    // Preserve local-wins fields if configured
    if (config.localWinsFields && config.localWinsFields.length > 0) {
      const mergedData: Record<string, unknown> = { ...serverRecord };
      for (const field of config.localWinsFields) {
        if (field in localRecord) {
          mergedData[field] = (localRecord as Record<string, unknown>)[field];
        }
      }
      return {
        action: 'merge',
        mergedData,
        reason: 'Server wins with local field preservation',
      };
    }

    return {
      action: 'use_server',
      reason: 'Server wins strategy',
    };
  }

  /**
   * Local wins strategy - local data takes precedence
   */
  private resolveLocalWins(
    localRecord: SyncedRecord,
    serverRecord: SyncedRecord,
    config: ModuleConflictConfig
  ): ConflictResolution {
    // Preserve server-wins fields if configured
    if (config.serverWinsFields && config.serverWinsFields.length > 0) {
      const mergedData: Record<string, unknown> = { ...localRecord };
      for (const field of config.serverWinsFields) {
        if (field in serverRecord) {
          mergedData[field] = (serverRecord as Record<string, unknown>)[field];
        }
      }
      return {
        action: 'merge',
        mergedData,
        reason: 'Local wins with server field preservation',
      };
    }

    return {
      action: 'use_local',
      reason: 'Local wins strategy',
    };
  }

  /**
   * Last write wins strategy - most recently updated record wins
   */
  private resolveLastWriteWins(
    localRecord: SyncedRecord,
    serverRecord: SyncedRecord,
    config: ModuleConflictConfig
  ): ConflictResolution {
    const localTime = new Date(localRecord.updated_at).getTime();
    const serverTime = new Date(serverRecord.updated_at).getTime();

    if (localTime >= serverTime) {
      return this.resolveLocalWins(localRecord, serverRecord, config);
    } else {
      return this.resolveServerWins(localRecord, serverRecord, config);
    }
  }

  /**
   * Field-level merge strategy - merge non-conflicting fields
   */
  private resolveFieldMerge(
    localRecord: SyncedRecord,
    serverRecord: SyncedRecord,
    config: ModuleConflictConfig
  ): ConflictResolution {
    const ignoreFields = new Set([
      ...SYSTEM_FIELDS,
      ...(config.ignoreFields || []),
    ]);

    const mergedData: Record<string, unknown> = { ...serverRecord };
    const conflictFields: string[] = [];
    const localData = localRecord as Record<string, unknown>;
    const serverData = serverRecord as Record<string, unknown>;

    // Get original server data if available
    const originalData = (localRecord._server_data || {}) as Record<string, unknown>;

    // Process each field
    for (const field of Object.keys(localData)) {
      if (ignoreFields.has(field)) continue;

      const localValue = localData[field];
      const serverValue = serverData[field];
      const originalValue = originalData[field];

      // Check if field should use specific source
      if (config.serverWinsFields?.includes(field)) {
        mergedData[field] = serverValue;
        continue;
      }

      if (config.localWinsFields?.includes(field)) {
        mergedData[field] = localValue;
        continue;
      }

      // Three-way merge logic
      const localChanged = !this.isEqual(localValue, originalValue);
      const serverChanged = !this.isEqual(serverValue, originalValue);

      if (localChanged && serverChanged) {
        // Both changed - conflict
        if (!this.isEqual(localValue, serverValue)) {
          conflictFields.push(field);
          // Use last write wins for conflict fields
          const localTime = new Date(localRecord.updated_at).getTime();
          const serverTime = new Date(serverRecord.updated_at).getTime();
          mergedData[field] = localTime >= serverTime ? localValue : serverValue;
        }
      } else if (localChanged) {
        // Only local changed
        mergedData[field] = localValue;
      } else {
        // Only server changed or neither changed
        mergedData[field] = serverValue;
      }
    }

    // Include any new fields from server
    for (const field of Object.keys(serverData)) {
      if (!(field in mergedData) && !ignoreFields.has(field)) {
        mergedData[field] = serverData[field];
      }
    }

    return {
      action: 'merge',
      mergedData,
      conflictFields: conflictFields.length > 0 ? conflictFields : undefined,
      reason: conflictFields.length > 0
        ? `Field merge with ${conflictFields.length} auto-resolved conflicts`
        : 'Clean field merge',
    };
  }

  /**
   * Manual resolution - store conflict for user decision
   */
  private resolveManual(
    module: OfflineModule,
    localRecord: SyncedRecord,
    serverRecord: SyncedRecord
  ): ConflictResolution {
    const conflictFields = this.detectConflictFields(localRecord, serverRecord);
    const conflictKey = `${module}:${localRecord.id}`;

    // Store for manual resolution
    this.pendingConflicts.set(conflictKey, {
      module,
      recordId: localRecord.id,
      localRecord,
      serverRecord,
      conflictFields,
      suggestedResolution: this.resolveLastWriteWins(
        localRecord,
        serverRecord,
        this.getModuleConfig(module)
      ),
    });

    return {
      action: 'manual',
      conflictFields,
      reason: 'Requires manual resolution',
    };
  }

  // ==========================================================================
  // Conflict Detection
  // ==========================================================================

  /**
   * Detect which fields have conflicts between two records
   */
  detectConflictFields(localRecord: SyncedRecord, serverRecord: SyncedRecord): string[] {
    const conflicts: string[] = [];
    const localData = localRecord as Record<string, unknown>;
    const serverData = serverRecord as Record<string, unknown>;

    const allFields = new Set([...Object.keys(localData), ...Object.keys(serverData)]);

    for (const field of allFields) {
      if (SYSTEM_FIELDS.includes(field)) continue;

      const localValue = localData[field];
      const serverValue = serverData[field];

      if (!this.isEqual(localValue, serverValue)) {
        conflicts.push(field);
      }
    }

    return conflicts;
  }

  /**
   * Check if there would be a conflict between local and server
   */
  hasConflict(localRecord: SyncedRecord, serverRecord: SyncedRecord): boolean {
    return this.detectConflictFields(localRecord, serverRecord).length > 0;
  }

  // ==========================================================================
  // Manual Conflict Management
  // ==========================================================================

  /**
   * Get all pending conflicts awaiting manual resolution
   */
  getPendingConflicts(): ConflictDetails[] {
    return Array.from(this.pendingConflicts.values());
  }

  /**
   * Get a specific pending conflict
   */
  getPendingConflict(module: OfflineModule, recordId: string): ConflictDetails | undefined {
    return this.pendingConflicts.get(`${module}:${recordId}`);
  }

  /**
   * Resolve a pending conflict manually
   */
  resolvePendingConflict(
    module: OfflineModule,
    recordId: string,
    action: ConflictAction,
    mergedData?: Record<string, unknown>
  ): ConflictResolution {
    const conflictKey = `${module}:${recordId}`;
    const conflict = this.pendingConflicts.get(conflictKey);

    if (!conflict) {
      return { action: 'use_server', reason: 'Conflict not found' };
    }

    // Remove from pending
    this.pendingConflicts.delete(conflictKey);

    if (action === 'merge' && mergedData) {
      return { action: 'merge', mergedData, reason: 'Manual merge' };
    }

    return { action, reason: 'Manual resolution' };
  }

  /**
   * Clear all pending conflicts
   */
  clearPendingConflicts(): void {
    this.pendingConflicts.clear();
  }

  // ==========================================================================
  // Utility Methods
  // ==========================================================================

  /**
   * Deep equality check for values
   */
  private isEqual(a: unknown, b: unknown): boolean {
    if (a === b) return true;
    if (a === null || b === null) return a === b;
    if (a === undefined || b === undefined) return a === b;

    if (typeof a !== typeof b) return false;

    if (Array.isArray(a) && Array.isArray(b)) {
      if (a.length !== b.length) return false;
      return a.every((val, idx) => this.isEqual(val, b[idx]));
    }

    if (typeof a === 'object' && typeof b === 'object') {
      const aObj = a as Record<string, unknown>;
      const bObj = b as Record<string, unknown>;
      const aKeys = Object.keys(aObj);
      const bKeys = Object.keys(bObj);

      if (aKeys.length !== bKeys.length) return false;
      return aKeys.every((key) => this.isEqual(aObj[key], bObj[key]));
    }

    return false;
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

/**
 * Singleton conflict resolver instance
 */
export const conflictResolver = new ConflictResolver();
