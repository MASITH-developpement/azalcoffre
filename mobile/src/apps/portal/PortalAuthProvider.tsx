/**
 * Portal Auth Provider
 *
 * Context provider for portal authentication state.
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  PortalAuthContext,
  PortalAuthContextValue,
  PortalAuthState,
  PortalClient,
} from './hooks/usePortalAuth';

const STORAGE_KEYS = {
  PORTAL_TOKEN: 'azalplus_portal_token',
  PORTAL_CLIENT: 'azalplus_portal_client',
} as const;

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

interface PortalAuthProviderProps {
  children: React.ReactNode;
}

export const PortalAuthProvider: React.FC<PortalAuthProviderProps> = ({ children }) => {
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

  const contextValue: PortalAuthContextValue = {
    ...state,
    requestMagicLink,
    verifyMagicLink,
    logout,
    clearError,
  };

  return (
    <PortalAuthContext.Provider value={contextValue}>
      {children}
    </PortalAuthContext.Provider>
  );
};

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

export default PortalAuthProvider;
