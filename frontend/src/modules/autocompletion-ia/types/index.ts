// AZALPLUS - Types Autocompletion IA

// -----------------------------------------------------------------------------
// Enums
// -----------------------------------------------------------------------------
export type IAProvider = 'openai' | 'anthropic' | 'local';

export type CompletionType =
  | 'text'
  | 'email'
  | 'adresse'
  | 'nom_personne'
  | 'nom_entreprise'
  | 'telephone'
  | 'reference'
  | 'description'
  | 'code_postal'
  | 'ville'
  | 'siret'
  | 'tva_intra';

export type SuggestionSource = 'ia' | 'historique' | 'api' | 'cache';

// -----------------------------------------------------------------------------
// Request Types
// -----------------------------------------------------------------------------
export interface SuggestionRequest {
  module: string;
  champ: string;
  valeur: string;
  contexte?: Record<string, unknown>;
  limite?: number;
  type_completion?: CompletionType;
  provider?: IAProvider;
}

export interface CompletionRequest {
  module: string;
  champ: string;
  valeur: string;
  contexte?: Record<string, unknown>;
  max_tokens?: number;
  provider?: IAProvider;
}

export interface FeedbackRequest {
  suggestion_id: string;
  accepted: boolean;
  valeur_finale?: string;
}

// -----------------------------------------------------------------------------
// Response Types
// -----------------------------------------------------------------------------
export interface Suggestion {
  id: string;
  texte: string;
  score: number;
  source: SuggestionSource;
  provider?: IAProvider;
}

export interface SuggestionMeta {
  provider?: IAProvider;
  model?: string;
  cached: boolean;
  latency_ms: number;
  tokens_used?: number;
}

export interface SuggestionResponse {
  suggestions: Suggestion[];
  meta: SuggestionMeta;
}

export interface CompletionResponse {
  completion: string;
  meta: SuggestionMeta;
}

export interface ConfigResponse {
  actif: boolean;
  fournisseur_defaut: IAProvider;
  modele_defaut: string;
  mode: 'suggestions' | 'completion' | 'hybrid';
  nombre_suggestions: number;
  temperature: number;
  openai_configured: boolean;
  anthropic_configured: boolean;
  limite_requetes_jour: number;
  limite_tokens_jour: number;
  requetes_aujourd_hui: number;
  tokens_aujourd_hui: number;
}

export interface HealthStatus {
  status: 'ok' | 'error';
  latency_ms?: number;
  model?: string;
  error?: string;
}

export interface HealthResponse {
  openai: HealthStatus;
  anthropic: HealthStatus;
  local: HealthStatus;
  cache: HealthStatus;
}

// -----------------------------------------------------------------------------
// Hook Options
// -----------------------------------------------------------------------------
export interface UseAutocompletionIAOptions {
  /** Nom du module (ex: 'Clients', 'Factures') */
  module: string;
  /** Nom du champ (ex: 'nom', 'email') */
  champ: string;
  /** Délai avant déclenchement en ms (défaut: 300) */
  debounceMs?: number;
  /** Nombre minimum de caractères (défaut: 2) */
  minChars?: number;
  /** Nombre maximum de suggestions (défaut: 5) */
  maxSuggestions?: number;
  /** Type de complétion forcé */
  typeCompletion?: CompletionType;
  /** Provider forcé */
  provider?: IAProvider;
  /** Contexte additionnel (autres champs du formulaire) */
  contexte?: Record<string, unknown>;
  /** Désactiver l'autocomplétion IA */
  disabled?: boolean;
  /** Callback quand une suggestion est sélectionnée */
  onSuggestionSelect?: (suggestion: Suggestion) => void;
  /** Callback sur erreur */
  onError?: (error: Error) => void;
}

export interface UseAutocompletionIAReturn {
  /** Liste des suggestions */
  suggestions: Suggestion[];
  /** Chargement en cours */
  isLoading: boolean;
  /** Erreur éventuelle */
  error: Error | null;
  /** Afficher les suggestions */
  showSuggestions: boolean;
  /** Index de la suggestion sélectionnée */
  selectedIndex: number;
  /** Métadonnées de la dernière requête */
  meta: SuggestionMeta | null;
  /** Déclencher une recherche de suggestions */
  fetchSuggestions: (value: string) => Promise<void>;
  /** Accepter une suggestion */
  acceptSuggestion: (suggestion: Suggestion) => void;
  /** Rejeter les suggestions (fermer) */
  dismissSuggestions: () => void;
  /** Naviguer dans les suggestions (clavier) */
  navigateSuggestions: (direction: 'up' | 'down') => void;
  /** Accepter la suggestion sélectionnée */
  acceptSelected: () => void;
  /** Compléter un texte long */
  completeText: (value: string, maxTokens?: number) => Promise<string>;
  /** Réinitialiser l'état */
  reset: () => void;
}

// -----------------------------------------------------------------------------
// Component Props
// -----------------------------------------------------------------------------
export interface AutocompleteFieldProps {
  /** Nom du module */
  module: string;
  /** Nom du champ */
  field: string;
  /** Valeur actuelle */
  value: string;
  /** Callback de changement */
  onChange: (value: string) => void;
  /** Placeholder */
  placeholder?: string;
  /** Label du champ */
  label?: string;
  /** Champ désactivé */
  disabled?: boolean;
  /** Champ requis */
  required?: boolean;
  /** Erreur de validation */
  error?: string;
  /** Activer l'autocomplétion IA */
  iaEnabled?: boolean;
  /** Afficher la source des suggestions */
  showSource?: boolean;
  /** Type de complétion */
  typeCompletion?: CompletionType;
  /** Provider forcé */
  provider?: IAProvider;
  /** Contexte additionnel */
  contexte?: Record<string, unknown>;
  /** Callback sélection */
  onSuggestionSelect?: (suggestion: Suggestion) => void;
  /** Classes CSS additionnelles */
  className?: string;
  /** Type d'input (text, email, tel, etc.) */
  type?: string;
  /** Multiline (textarea) */
  multiline?: boolean;
  /** Nombre de lignes pour textarea */
  rows?: number;
}
