/**
 * Portal Authentication Hook
 *
 * Manages client authentication state for the portal.
 * Uses magic link authentication instead of password.
 */

import { useState, useCallback, useEffect, createContext, useContext } from 'react';

const STORAGE_KEYS = {
  PORTAL_TOKEN: 'azalplus_portal_token',
  PORTAL_CLIENT: 'azalplus_portal_client',
} as const;

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

interface PortalClient {
  client_name: string;
  client_email: string;
}

interface PortalAuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  client: PortalClient | null;
  token: string | null;
  error: string | null;
}

interface PortalAuthContextValue extends PortalAuthState {
  requestMagicLink: (email: string) => Promise<{ success: boolean; message: string }>;
  verifyMagicLink: (token: string) => Promise<boolean>;
  logout: () => void;
  clearError: () => void;
}

const PortalAuthContext = createContext<PortalAuthContextValue | null>(null);

export function usePortalAuth(): PortalAuthContextValue {
  const context = useContext(PortalAuthContext);

  if (!context) {
    // Return a standalone implementation when not in context
    return usePortalAuthStandalone();
  }

  return context;
}

function usePortalAuthStandalone(): PortalAuthContextValue {
  const [state, setState] = useState<PortalAuthState>(() => {
    // Initialize from localStorage
    const token = localStorage.getItem(STORAGE_KEYS.PORTAL_TOKEN);
    const clientData = localStorage.getItem(STORAGE_KEYS.PORTAL_CLIENT);

    let client: PortalClient | null = null;
    if (clientData) {
      try {
        client = JSON.parse(clientData);
      } catch {
        client = null;
      }
    }

    return {
      isAuthenticated: !!token && !!client,
      isLoading: false,
      client,
      token,
      error: null,
    };
  });

  // Check token validity on mount
  useEffect(() => {
    if (state.token) {
      const isExpired = isTokenExpired(state.token);
      if (isExpired) {
        logout();
      }
    }
  }, []);

  const requestMagicLink = useCallback(async (email: string): Promise<{ success: boolean; message: string }> => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await fetch(`${API_BASE_URL}/portal/auth/magic-link`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email }),
      });

      const data = await response.json();

      setState((prev) => ({ ...prev, isLoading: false }));

      return {
        success: true,
        message: data.message || 'Lien envoye',
      };
    } catch (error) {
      const message = 'Erreur de connexion. Veuillez reessayer.';
      setState((prev) => ({ ...prev, isLoading: false, error: message }));

      return {
        success: false,
        message,
      };
    }
  }, []);

  const verifyMagicLink = useCallback(async (token: string): Promise<boolean> => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await fetch(`${API_BASE_URL}/portal/auth/verify`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Lien invalide ou expire');
      }

      const data = await response.json();

      // Store token and client info
      localStorage.setItem(STORAGE_KEYS.PORTAL_TOKEN, data.access_token);
      localStorage.setItem(
        STORAGE_KEYS.PORTAL_CLIENT,
        JSON.stringify({
          client_name: data.client_name,
          client_email: data.client_email,
        })
      );

      setState({
        isAuthenticated: true,
        isLoading: false,
        client: {
          client_name: data.client_name,
          client_email: data.client_email,
        },
        token: data.access_token,
        error: null,
      });

      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Lien invalide ou expire';
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
      }));

      return false;
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEYS.PORTAL_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.PORTAL_CLIENT);

    setState({
      isAuthenticated: false,
      isLoading: false,
      client: null,
      token: null,
      error: null,
    });
  }, []);

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  return {
    ...state,
    requestMagicLink,
    verifyMagicLink,
    logout,
    clearError,
  };
}

function isTokenExpired(token: string | null): boolean {
  if (!token) return true;
  try {
    const parts = token.split('.');
    const payloadPart = parts[1];
    if (!payloadPart) return true;
    const payload = JSON.parse(atob(payloadPart));
    // Add 30 second buffer before expiration
    return payload.exp * 1000 < Date.now() + 30000;
  } catch {
    return true;
  }
}

// Export context for provider
export { PortalAuthContext };
export type { PortalAuthContextValue, PortalClient, PortalAuthState };

// Portal API client with automatic token injection
export function usePortalApi() {
  const { token, logout } = usePortalAuth();

  const fetchWithAuth = useCallback(
    async <T>(url: string, options: RequestInit = {}): Promise<T> => {
      if (!token) {
        throw new Error('Non authentifie');
      }

      const response = await fetch(`${API_BASE_URL}${url}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          ...options.headers,
        },
      });

      if (response.status === 401) {
        logout();
        throw new Error('Session expiree');
      }

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Erreur');
      }

      return response.json();
    },
    [token, logout]
  );

  return { fetchWithAuth };
}
