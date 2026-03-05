// AZALPLUS - API Client Mobile Configuration

import type {
  MobileConfig,
  MobileConfigResponse,
  MobileConfigUpdateRequest,
  UploadLogoResponse,
} from './types';

// Base URL de l'API (a configurer selon votre environnement)
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------
async function fetchAPI<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}/mobile${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `API Error: ${response.status}`);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

// -----------------------------------------------------------------------------
// API Functions
// -----------------------------------------------------------------------------

/**
 * Obtenir la configuration mobile actuelle
 */
export async function getMobileConfig(): Promise<MobileConfigResponse> {
  return fetchAPI<MobileConfigResponse>('');
}

/**
 * Mettre a jour la configuration mobile
 */
export async function updateMobileConfig(
  data: MobileConfigUpdateRequest
): Promise<MobileConfig> {
  return fetchAPI<MobileConfig>('', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * Mettre a jour partiellement la configuration mobile
 */
export async function patchMobileConfig(
  data: Partial<MobileConfigUpdateRequest>
): Promise<MobileConfig> {
  return fetchAPI<MobileConfig>('', {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

/**
 * Activer/Desactiver l'application mobile
 */
export async function toggleMobileEnabled(enabled: boolean): Promise<MobileConfig> {
  return fetchAPI<MobileConfig>('/toggle', {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  });
}

/**
 * Telecharger un logo
 */
export async function uploadLogo(file: File): Promise<UploadLogoResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const url = `${API_BASE_URL}/mobile-config/logo`;
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Erreur lors du televersement');
  }

  return response.json();
}

/**
 * Supprimer le logo
 */
export async function deleteLogo(): Promise<void> {
  await fetchAPI<void>('/logo', {
    method: 'DELETE',
  });
}

/**
 * Obtenir la liste des modules disponibles
 */
export async function getAvailableModules(): Promise<
  Array<{ id: string; name: string; icon: string }>
> {
  return fetchAPI<Array<{ id: string; name: string; icon: string }>>('/modules/available');
}

/**
 * Reinitialiser la configuration par defaut
 */
export async function resetToDefault(): Promise<MobileConfig> {
  return fetchAPI<MobileConfig>('/reset', {
    method: 'POST',
  });
}

/**
 * Exporter la configuration
 */
export async function exportConfig(): Promise<Blob> {
  const url = `${API_BASE_URL}/mobile-config/export`;
  const response = await fetch(url, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error('Erreur lors de l\'export');
  }

  return response.blob();
}

/**
 * Importer une configuration
 */
export async function importConfig(file: File): Promise<MobileConfig> {
  const formData = new FormData();
  formData.append('file', file);

  const url = `${API_BASE_URL}/mobile-config/import`;
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Erreur lors de l\'import');
  }

  return response.json();
}

/**
 * Tester la configuration push notifications
 */
export async function testPushNotification(): Promise<{ success: boolean; message: string }> {
  return fetchAPI<{ success: boolean; message: string }>('/push/test', {
    method: 'POST',
  });
}

/**
 * Obtenir les statistiques d'utilisation mobile
 */
export async function getMobileStats(): Promise<{
  activeUsers: number;
  totalSessions: number;
  offlineDataSize: number;
  lastSync: string;
}> {
  return fetchAPI<{
    activeUsers: number;
    totalSessions: number;
    offlineDataSize: number;
    lastSync: string;
  }>('/stats');
}

// -----------------------------------------------------------------------------
// React Query Keys (pour invalidation de cache)
// -----------------------------------------------------------------------------
export const mobileConfigKeys = {
  all: ['mobile-config'] as const,
  config: () => [...mobileConfigKeys.all, 'config'] as const,
  modules: () => [...mobileConfigKeys.all, 'modules'] as const,
  stats: () => [...mobileConfigKeys.all, 'stats'] as const,
};
