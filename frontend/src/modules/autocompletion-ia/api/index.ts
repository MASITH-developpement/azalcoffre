// AZALPLUS - API Client Autocompletion IA
import type {
  CompletionRequest,
  CompletionResponse,
  ConfigResponse,
  FeedbackRequest,
  HealthResponse,
  SuggestionRequest,
  SuggestionResponse,
} from '../types';

// Base URL de l'API (à configurer selon votre environnement)
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v3';

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------
async function fetchAPI<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}/autocompletion${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include', // Pour les cookies de session
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `API Error: ${response.status}`);
  }

  // Pour les réponses 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

// -----------------------------------------------------------------------------
// API Functions
// -----------------------------------------------------------------------------

/**
 * Obtenir des suggestions d'autocomplétion
 */
export async function getSuggestions(
  request: SuggestionRequest
): Promise<SuggestionResponse> {
  return fetchAPI<SuggestionResponse>('/suggest', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Compléter un texte long
 */
export async function completeText(
  request: CompletionRequest
): Promise<CompletionResponse> {
  return fetchAPI<CompletionResponse>('/complete', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Envoyer un feedback sur une suggestion
 */
export async function sendFeedback(request: FeedbackRequest): Promise<void> {
  await fetchAPI<void>('/feedback', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Obtenir la configuration actuelle
 */
export async function getConfig(): Promise<ConfigResponse> {
  return fetchAPI<ConfigResponse>('/config');
}

/**
 * Vérifier l'état des providers
 */
export async function getHealth(): Promise<HealthResponse> {
  return fetchAPI<HealthResponse>('/health');
}

/**
 * Tester l'autocomplétion
 */
export async function testAutocompletion(
  provider?: string
): Promise<SuggestionResponse> {
  const params = provider ? `?provider=${provider}` : '';
  return fetchAPI<SuggestionResponse>(`/test${params}`, {
    method: 'POST',
  });
}

// -----------------------------------------------------------------------------
// React Query Keys (pour invalidation de cache)
// -----------------------------------------------------------------------------
export const autocompletionKeys = {
  all: ['autocompletion'] as const,
  config: () => [...autocompletionKeys.all, 'config'] as const,
  health: () => [...autocompletionKeys.all, 'health'] as const,
  suggestions: (module: string, champ: string, valeur: string) =>
    [...autocompletionKeys.all, 'suggestions', module, champ, valeur] as const,
};

// -----------------------------------------------------------------------------
// React Query Hooks (optionnel, si vous utilisez React Query)
// -----------------------------------------------------------------------------
// import { useQuery, useMutation } from '@tanstack/react-query';
//
// export function useAutocompletionConfig() {
//   return useQuery({
//     queryKey: autocompletionKeys.config(),
//     queryFn: getConfig,
//     staleTime: 5 * 60 * 1000, // 5 minutes
//   });
// }
//
// export function useAutocompletionHealth() {
//   return useQuery({
//     queryKey: autocompletionKeys.health(),
//     queryFn: getHealth,
//     refetchInterval: 30 * 1000, // 30 secondes
//   });
// }
//
// export function useSuggestionsMutation() {
//   return useMutation({
//     mutationFn: getSuggestions,
//   });
// }
//
// export function useFeedbackMutation() {
//   return useMutation({
//     mutationFn: sendFeedback,
//   });
// }
