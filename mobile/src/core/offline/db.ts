/**
 * Dexie.js IndexedDB Setup for AZALPLUS Mobile PWA
 *
 * Features:
 * - Multi-tenant offline storage with compound keys
 * - Mutation queue for offline CRUD operations
 * - Sync metadata tracking for delta sync
 * - Type-safe table definitions
 */

import Dexie, { Table } from 'dexie';

// ============================================================================
// Types
// ============================================================================

/**
 * Sync status for records in local database
 */
export type SyncStatus = 'synced' | 'pending_create' | 'pending_update' | 'pending_delete' | 'conflict' | 'error';

/**
 * Base interface for all synced records
 */
export interface SyncedRecord {
  /** Unique record ID */
  id: string;
  /** Tenant ID for multi-tenant isolation */
  tenant_id: string;
  /** Server timestamp of last update */
  updated_at: string;
  /** Server timestamp of creation */
  created_at: string;
  /** Local sync status */
  _sync_status: SyncStatus;
  /** Local timestamp of last modification */
  _local_updated_at: number;
  /** Version number for conflict detection */
  _version: number;
  /** Original server data for conflict resolution */
  _server_data?: Record<string, unknown>;
}

/**
 * Client record schema
 */
export interface ClientRecord extends SyncedRecord {
  code?: string;
  nom: string;
  email?: string;
  telephone?: string;
  adresse?: string;
  ville?: string;
  code_postal?: string;
  pays?: string;
  siret?: string;
  tva_intra?: string;
  type?: string;
  statut?: string;
  notes?: string;
}

/**
 * Facture (Invoice) record schema
 */
export interface FactureRecord extends SyncedRecord {
  numero: string;
  client_id: string;
  date_emission: string;
  date_echeance?: string;
  montant_ht: number;
  montant_tva: number;
  montant_ttc: number;
  statut: string;
  lignes?: FactureLigne[];
  notes?: string;
  conditions_paiement?: string;
}

export interface FactureLigne {
  description: string;
  quantite: number;
  prix_unitaire: number;
  tva_taux: number;
  montant_ht: number;
}

/**
 * Devis (Quote) record schema
 */
export interface DevisRecord extends SyncedRecord {
  numero: string;
  client_id: string;
  date_emission: string;
  date_validite?: string;
  montant_ht: number;
  montant_tva: number;
  montant_ttc: number;
  statut: string;
  lignes?: DevisLigne[];
  notes?: string;
}

export interface DevisLigne {
  description: string;
  quantite: number;
  prix_unitaire: number;
  tva_taux: number;
  montant_ht: number;
}

/**
 * Produit (Product) record schema
 */
export interface ProduitRecord extends SyncedRecord {
  code: string;
  nom: string;
  description?: string;
  prix_ht: number;
  tva_taux: number;
  unite?: string;
  categorie?: string;
  stock_quantite?: number;
  stock_minimum?: number;
  actif: boolean;
}

/**
 * Contact record schema
 */
export interface ContactRecord extends SyncedRecord {
  client_id?: string;
  nom: string;
  prenom?: string;
  email?: string;
  telephone?: string;
  mobile?: string;
  fonction?: string;
  principal: boolean;
  notes?: string;
}

/**
 * Intervention record schema
 */
export interface InterventionRecord extends SyncedRecord {
  numero: string;
  client_id: string;
  date_planifiee: string;
  date_debut?: string;
  date_fin?: string;
  technicien_id?: string;
  type: string;
  statut: string;
  description?: string;
  rapport?: string;
  duree_prevue?: number;
  duree_reelle?: number;
  signature_client?: string;
  photos?: string[];
}

/**
 * Temps (Time tracking) record schema
 */
export interface TempsRecord extends SyncedRecord {
  projet_id?: string;
  client_id?: string;
  intervention_id?: string;
  utilisateur_id: string;
  date: string;
  duree: number;
  description?: string;
  facturable: boolean;
  facture_id?: string;
  type?: string;
  statut: string;
}

/**
 * Mutation types for offline operations
 */
export type MutationType = 'create' | 'update' | 'delete';

/**
 * Entry in the mutation queue for offline operations
 */
export interface MutationQueueEntry {
  /** Auto-incremented ID */
  id?: number;
  /** Tenant ID */
  tenant_id: string;
  /** Target module name */
  module: string;
  /** Record ID being modified */
  record_id: string;
  /** Type of mutation */
  mutation_type: MutationType;
  /** Data payload for create/update */
  data?: Record<string, unknown>;
  /** Timestamp of mutation */
  created_at: number;
  /** Number of sync attempts */
  retry_count: number;
  /** Last error message if failed */
  last_error?: string;
  /** Status of the mutation */
  status: 'pending' | 'processing' | 'failed';
}

/**
 * Sync metadata for tracking last sync times per module
 */
export interface SyncMetadata {
  /** Compound key: tenant_id + module */
  id: string;
  /** Tenant ID */
  tenant_id: string;
  /** Module name */
  module: string;
  /** Last successful sync timestamp (ISO string from server) */
  last_sync_at: string;
  /** Last successful pull timestamp (local) */
  last_pull_at: number;
  /** Last successful push timestamp (local) */
  last_push_at: number;
  /** Total records synced */
  total_records: number;
  /** Sync status */
  status: 'idle' | 'syncing' | 'error';
  /** Last error message */
  last_error?: string;
}

// ============================================================================
// Supported Modules
// ============================================================================

/**
 * List of modules available for offline storage
 */
export const OFFLINE_MODULES = [
  'clients',
  'factures',
  'devis',
  'produits',
  'contacts',
  'interventions',
  'temps',
] as const;

export type OfflineModule = (typeof OFFLINE_MODULES)[number];

/**
 * Type mapping for module records
 */
export interface ModuleRecordTypes {
  clients: ClientRecord;
  factures: FactureRecord;
  devis: DevisRecord;
  produits: ProduitRecord;
  contacts: ContactRecord;
  interventions: InterventionRecord;
  temps: TempsRecord;
}

// ============================================================================
// Database Class
// ============================================================================

/**
 * AZALPLUS Offline Database using Dexie.js
 *
 * Schema uses compound indexes for multi-tenant isolation:
 * - [tenant_id+id] as primary compound key
 * - updated_at for delta sync queries
 * - _sync_status for filtering pending changes
 */
export class AzalplusOfflineDB extends Dexie {
  // Module tables
  clients!: Table<ClientRecord, string>;
  factures!: Table<FactureRecord, string>;
  devis!: Table<DevisRecord, string>;
  produits!: Table<ProduitRecord, string>;
  contacts!: Table<ContactRecord, string>;
  interventions!: Table<InterventionRecord, string>;
  temps!: Table<TempsRecord, string>;

  // System tables
  mutationQueue!: Table<MutationQueueEntry, number>;
  syncMetadata!: Table<SyncMetadata, string>;

  constructor() {
    super('AzalplusOfflineDB');

    // Define schema with compound indexes
    // Version 1: Initial schema
    this.version(1).stores({
      // Module tables with compound keys and indexes
      // [tenant_id+id] ensures tenant isolation
      // updated_at for delta sync
      // _sync_status for filtering pending changes
      clients: '[tenant_id+id], tenant_id, updated_at, _sync_status, _local_updated_at',
      factures: '[tenant_id+id], tenant_id, updated_at, _sync_status, _local_updated_at, client_id, statut',
      devis: '[tenant_id+id], tenant_id, updated_at, _sync_status, _local_updated_at, client_id, statut',
      produits: '[tenant_id+id], tenant_id, updated_at, _sync_status, _local_updated_at, categorie, actif',
      contacts: '[tenant_id+id], tenant_id, updated_at, _sync_status, _local_updated_at, client_id',
      interventions: '[tenant_id+id], tenant_id, updated_at, _sync_status, _local_updated_at, client_id, statut, date_planifiee',
      temps: '[tenant_id+id], tenant_id, updated_at, _sync_status, _local_updated_at, projet_id, client_id, date',

      // Mutation queue - auto-increment primary key
      mutationQueue: '++id, tenant_id, module, record_id, status, created_at',

      // Sync metadata - compound key for tenant+module
      syncMetadata: 'id, tenant_id, module, status',
    });
  }

  /**
   * Get table for a specific module
   */
  getTable<T extends OfflineModule>(module: T): Table<ModuleRecordTypes[T], string> {
    return this[module] as Table<ModuleRecordTypes[T], string>;
  }

  /**
   * Clear all data for a specific tenant
   */
  async clearTenantData(tenantId: string): Promise<void> {
    await this.transaction('rw', this.tables, async () => {
      // Clear module tables
      for (const module of OFFLINE_MODULES) {
        const table = this.getTable(module);
        await table.where('tenant_id').equals(tenantId).delete();
      }

      // Clear mutation queue
      await this.mutationQueue.where('tenant_id').equals(tenantId).delete();

      // Clear sync metadata
      await this.syncMetadata.where('tenant_id').equals(tenantId).delete();
    });
  }

  /**
   * Clear all offline data (all tenants)
   */
  async clearAllData(): Promise<void> {
    await this.transaction('rw', this.tables, async () => {
      for (const table of this.tables) {
        await table.clear();
      }
    });
  }

  /**
   * Get sync metadata for a module
   */
  async getSyncMetadata(tenantId: string, module: OfflineModule): Promise<SyncMetadata | undefined> {
    const id = `${tenantId}:${module}`;
    return this.syncMetadata.get(id);
  }

  /**
   * Update sync metadata for a module
   */
  async updateSyncMetadata(tenantId: string, module: OfflineModule, updates: Partial<SyncMetadata>): Promise<void> {
    const id = `${tenantId}:${module}`;
    const existing = await this.syncMetadata.get(id);

    if (existing) {
      await this.syncMetadata.update(id, updates);
    } else {
      await this.syncMetadata.add({
        id,
        tenant_id: tenantId,
        module,
        last_sync_at: new Date(0).toISOString(),
        last_pull_at: 0,
        last_push_at: 0,
        total_records: 0,
        status: 'idle',
        ...updates,
      });
    }
  }

  /**
   * Get pending mutations count for a tenant
   */
  async getPendingMutationsCount(tenantId: string): Promise<number> {
    return this.mutationQueue
      .where('tenant_id')
      .equals(tenantId)
      .and((m) => m.status === 'pending' || m.status === 'failed')
      .count();
  }

  /**
   * Get all pending mutations for a tenant
   */
  async getPendingMutations(tenantId: string): Promise<MutationQueueEntry[]> {
    return this.mutationQueue
      .where('tenant_id')
      .equals(tenantId)
      .and((m) => m.status === 'pending' || m.status === 'failed')
      .sortBy('created_at');
  }

  /**
   * Get records with pending sync status
   */
  async getUnsyncedRecords<T extends OfflineModule>(
    tenantId: string,
    module: T
  ): Promise<ModuleRecordTypes[T][]> {
    const table = this.getTable(module);
    return table
      .where('tenant_id')
      .equals(tenantId)
      .and((r) => r._sync_status !== 'synced')
      .toArray();
  }

  /**
   * Get database size estimate in bytes
   */
  async getStorageEstimate(): Promise<{ usage: number; quota: number }> {
    if (navigator.storage && navigator.storage.estimate) {
      const estimate = await navigator.storage.estimate();
      return {
        usage: estimate.usage || 0,
        quota: estimate.quota || 0,
      };
    }
    return { usage: 0, quota: 0 };
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

/**
 * Singleton database instance
 */
export const offlineDb = new AzalplusOfflineDB();

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Generate a unique ID for new records
 */
export function generateRecordId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

/**
 * Create a new synced record with default sync fields
 */
export function createSyncedRecord<T extends SyncedRecord>(
  tenantId: string,
  data: Omit<T, 'id' | 'tenant_id' | 'created_at' | 'updated_at' | '_sync_status' | '_local_updated_at' | '_version'>
): T {
  const now = new Date().toISOString();
  return {
    ...data,
    id: generateRecordId(),
    tenant_id: tenantId,
    created_at: now,
    updated_at: now,
    _sync_status: 'pending_create' as SyncStatus,
    _local_updated_at: Date.now(),
    _version: 1,
  } as T;
}

/**
 * Mark a record for update
 */
export function markForUpdate<T extends SyncedRecord>(
  record: T,
  updates: Partial<T>
): T {
  return {
    ...record,
    ...updates,
    updated_at: new Date().toISOString(),
    _sync_status: record._sync_status === 'pending_create' ? 'pending_create' : 'pending_update',
    _local_updated_at: Date.now(),
    _version: record._version + 1,
  };
}

/**
 * Mark a record as synced
 */
export function markAsSynced<T extends SyncedRecord>(
  record: T,
  serverData: Partial<T>
): T {
  return {
    ...record,
    ...serverData,
    _sync_status: 'synced' as SyncStatus,
    _local_updated_at: Date.now(),
    _server_data: undefined,
  };
}

/**
 * Check if module is supported for offline storage
 */
export function isOfflineModule(module: string): module is OfflineModule {
  return OFFLINE_MODULES.includes(module as OfflineModule);
}
