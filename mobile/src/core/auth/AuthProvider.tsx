import React, { createContext, useState, useEffect, useCallback, useMemo } from 'react';
import { apiClient, TokenManager } from '../api/client';

// Backend URL for auth endpoints
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || import.meta.env.VITE_API_URL?.replace(/\/api\/?$/, '') || '';

// Types - Backend user response
interface BackendUser {
  id: string;
  email: string;
  nom?: string;
  prenom?: string;
  firstName?: string;
  lastName?: string;
  role: string;
  permissions?: string[];
  tenant_id?: string;
  tenantId?: string;
  tenant_name?: string;
  tenantName?: string;
  avatar_url?: string;
  avatarUrl?: string;
  locale?: string;
  timezone?: string;
}

// Frontend user type
export interface User {
  id: string;
  email: string;
  firstName: string;
  lastName: string;
  fullName: string;
  role: string;
  permissions: string[];
  tenantId: string;
  tenantName: string;
  avatarUrl?: string;
  locale: string;
  timezone: string;
}

// Map backend response to frontend User
function mapBackendUser(data: BackendUser): User {
  const firstName = data.prenom || data.firstName || '';
  const lastName = data.nom || data.lastName || '';
  return {
    id: data.id,
    email: data.email,
    firstName,
    lastName,
    fullName: `${firstName} ${lastName}`.trim() || data.email,
    role: data.role || 'user',
    permissions: data.permissions || [],
    tenantId: data.tenant_id || data.tenantId || '',
    tenantName: data.tenant_name || data.tenantName || '',
    avatarUrl: data.avatar_url || data.avatarUrl,
    locale: data.locale || 'fr',
    timezone: data.timezone || 'Europe/Paris',
  };
}

export interface LoginCredentials {
  email: string;
  password: string;
  rememberMe?: boolean;
}

export interface LoginResponse {
  user: User;
  access_token: string;
  refresh_token: string;
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
}

export interface AuthContextValue extends AuthState {
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  clearError: () => void;
  hasPermission: (permission: string) => boolean;
  hasAnyPermission: (permissions: string[]) => boolean;
  hasAllPermissions: (permissions: string[]) => boolean;
}

// Context
export const AuthContext = createContext<AuthContextValue | null>(null);

// Provider props
interface AuthProviderProps {
  children: React.ReactNode;
}

// Provider component
export function AuthProvider({ children }: AuthProviderProps): React.ReactElement {
  const [state, setState] = useState<AuthState>({
    user: null,
    isAuthenticated: false,
    isLoading: true,
    error: null,
  });

  // Initialize auth state from stored token
  useEffect(() => {
    const initializeAuth = async () => {
      const token = TokenManager.getAccessToken();

      if (!token) {
        setState((prev) => ({ ...prev, isLoading: false }));
        return;
      }

      // Check if token is expired
      if (TokenManager.isTokenExpired(token)) {
        TokenManager.clearTokens();
        setState((prev) => ({ ...prev, isLoading: false }));
        return;
      }

      // Fetch current user
      try {
        const response = await fetch(`${BACKEND_URL}/api/auth/me`, {
          headers: { 'Authorization': `Bearer ${token}` },
        });
        if (!response.ok) throw new Error('Failed to fetch user');
        const userData = await response.json();
        // Compatibility: handle both direct user and nested data
        const rawUser = userData.data || userData;
        const user = mapBackendUser(rawUser);
        setState({
          user,
          isAuthenticated: true,
          isLoading: false,
          error: null,
        });
      } catch {
        TokenManager.clearTokens();
        setState({
          user: null,
          isAuthenticated: false,
          isLoading: false,
          error: null,
        });
      }
    };

    initializeAuth();
  }, []);

  // Login function
  const login = useCallback(async (credentials: LoginCredentials): Promise<void> => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      // Note: Auth endpoints are at /api/auth, not /api/v1/auth
      const response = await fetch(`${BACKEND_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || errorData.message || 'Identifiants incorrects');
      }

      const data = await response.json();
      const { access_token, refresh_token } = data;

      // Store tokens
      TokenManager.setTokens(access_token, refresh_token);

      // Fetch user data with the new token
      const userResponse = await fetch(`${BACKEND_URL}/api/auth/me`, {
        headers: { 'Authorization': `Bearer ${access_token}` },
      });

      if (!userResponse.ok) {
        throw new Error('Failed to fetch user data');
      }

      const userData = await userResponse.json();
      const rawUser = userData.data || userData;
      const user = mapBackendUser(rawUser);

      setState({
        user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (error) {
      const message = (error as { message?: string })?.message || 'Échec de connexion';
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
      }));
      throw error;
    }
  }, []);

  // Logout function
  const logout = useCallback(async (): Promise<void> => {
    setState((prev) => ({ ...prev, isLoading: true }));

    try {
      // Call logout endpoint to invalidate token on server
      await fetch(`${BACKEND_URL}/api/auth/logout`, { method: 'POST' });
    } catch {
      // Continue with local logout even if server call fails
    }

    // Clear local state
    TokenManager.clearTokens();
    setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    });
  }, []);

  // Refresh user data
  const refreshUser = useCallback(async (): Promise<void> => {
    if (!TokenManager.getAccessToken()) {
      return;
    }

    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/me`, {
        headers: { 'Authorization': `Bearer ${TokenManager.getAccessToken()}` },
      });
      if (response.ok) {
        const userData = await response.json();
        const rawUser = userData.data || userData;
        const user = mapBackendUser(rawUser);
        setState((prev) => ({
          ...prev,
          user,
        }));
      }
    } catch {
      // Silently fail - user can continue with cached data
    }
  }, []);

  // Clear error
  const clearError = useCallback((): void => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  // Permission checking functions
  const hasPermission = useCallback(
    (permission: string): boolean => {
      if (!state.user) return false;
      return state.user.permissions.includes(permission) || state.user.permissions.includes('*');
    },
    [state.user]
  );

  const hasAnyPermission = useCallback(
    (permissions: string[]): boolean => {
      return permissions.some((p) => hasPermission(p));
    },
    [hasPermission]
  );

  const hasAllPermissions = useCallback(
    (permissions: string[]): boolean => {
      return permissions.every((p) => hasPermission(p));
    },
    [hasPermission]
  );

  // Memoize context value
  const contextValue = useMemo<AuthContextValue>(
    () => ({
      ...state,
      login,
      logout,
      refreshUser,
      clearError,
      hasPermission,
      hasAnyPermission,
      hasAllPermissions,
    }),
    [state, login, logout, refreshUser, clearError, hasPermission, hasAnyPermission, hasAllPermissions]
  );

  return <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>;
}
