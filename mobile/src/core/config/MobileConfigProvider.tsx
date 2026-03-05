import React, { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react';
import { apiClient } from '../api/client';
import { useAuth } from '../auth/useAuth';

// Types - Backend Module Info
interface BackendModuleInfo {
  name: string;
  display_name: string;
  icon?: string;
  menu?: string;
  description?: string;
  fields_count: number;
  fields: Array<Record<string, unknown>>;
  permissions?: string[];
}

// Types - Frontend Module Config
export interface ModuleConfig {
  id: string;
  name: string;
  icon: string;
  route: string;
  permissions: string[];
  enabled: boolean;
  order: number;
  badge?: number;
  color?: string;
  displayName: string;
  menu?: string;
  description?: string;
  fieldsCount: number;
}

export interface DashboardWidget {
  id: string;
  type: 'stats' | 'chart' | 'list' | 'calendar' | 'custom';
  title: string;
  moduleId?: string;
  size: 'small' | 'medium' | 'large' | 'full';
  position: number;
  config: Record<string, unknown>;
  refreshInterval?: number;
}

export interface QuickAction {
  id: string;
  label: string;
  icon: string;
  moduleId: string;
  action: 'create' | 'list' | 'scan' | 'custom';
  route: string;
  color?: string;
}

export interface ThemeColors {
  primary: string;
  primaryLight: string;
  primaryDark: string;
  secondary: string;
  accent: string;
  success: string;
  warning: string;
  error: string;
  background: string;
  surface: string;
  text: string;
  textSecondary: string;
}

export interface MobileConfig {
  modules: ModuleConfig[];
  dashboardWidgets: DashboardWidget[];
  quickActions: QuickAction[];
  theme: ThemeColors;
  features: {
    offlineMode: boolean;
    pushNotifications: boolean;
    biometricAuth: boolean;
    darkMode: boolean;
    scanner: boolean;
  };
  company: {
    name: string;
    logoUrl?: string;
    supportEmail?: string;
    supportPhone?: string;
  };
  version: string;
}

// Types - Bootstrap Response from backend
interface BootstrapUserInfo {
  id: string;
  email: string;
  nom: string;
  prenom?: string;
  role: string;
  avatar_url?: string;
}

interface BootstrapTenantInfo {
  id: string;
  code: string;
  nom: string;
  logo_url?: string;
}

interface BootstrapConfig {
  tenant_id: string;
  theme: string;
  primary_color: string;
  logo_url?: string;
  offline_enabled: boolean;
  sync_interval_minutes: number;
  enabled_modules: string[];
  push_notifications_enabled: boolean;
  biometric_auth_enabled: boolean;
}

interface BootstrapPermissions {
  role: string;
  modules: string[];  // ["*"] pour admin ou liste de modules
  actions: string[];
  special_permissions: string[];
}

interface BootstrapResponse {
  user: BootstrapUserInfo;
  tenant: BootstrapTenantInfo;
  config: BootstrapConfig;
  permissions: BootstrapPermissions;
  modules: BackendModuleInfo[];
  server_time: string;
  api_version: string;
}

export interface MobileConfigState {
  config: MobileConfig | null;
  isLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;
}

export interface MobileConfigContextValue extends MobileConfigState {
  refresh: () => Promise<void>;
  getModule: (moduleId: string) => ModuleConfig | undefined;
  getEnabledModules: () => ModuleConfig[];
  getAllModules: () => ModuleConfig[];
  getWidgets: () => DashboardWidget[];
  getQuickActions: () => QuickAction[];
  hiddenModules: string[];
  toggleModuleVisibility: (moduleId: string) => void;
  setModuleOrder: (moduleId: string, newOrder: number) => void;
  navShortcuts: NavShortcut[];
  setNavShortcuts: (shortcuts: NavShortcut[]) => void;
  resetNavShortcuts: () => void;
}

// Default theme colors
const DEFAULT_THEME: ThemeColors = {
  primary: '#2563eb',
  primaryLight: '#3b82f6',
  primaryDark: '#1d4ed8',
  secondary: '#64748b',
  accent: '#8b5cf6',
  success: '#22c55e',
  warning: '#f59e0b',
  error: '#ef4444',
  background: '#f8fafc',
  surface: '#ffffff',
  text: '#0f172a',
  textSecondary: '#64748b',
};

// Default config
const DEFAULT_CONFIG: MobileConfig = {
  modules: [],
  dashboardWidgets: [],
  quickActions: [],
  theme: DEFAULT_THEME,
  features: {
    offlineMode: true,
    pushNotifications: false,
    biometricAuth: false,
    darkMode: true,
    scanner: true,
  },
  company: {
    name: 'AZALPLUS',
  },
  version: '1.0.0',
};

// Storage keys
const CONFIG_STORAGE_KEY = 'azalplus_mobile_config';
const HIDDEN_MODULES_KEY = 'azalplus_hidden_modules';
const NAV_SHORTCUTS_KEY = 'azalplus_nav_shortcuts';

// Nav shortcut type
export interface NavShortcut {
  moduleId: string;
  label: string;
  icon: string;
  path: string;
}

// Context
const MobileConfigContext = createContext<MobileConfigContextValue | null>(null);

// Load cached config
function loadCachedConfig(): MobileConfig | null {
  try {
    const cached = localStorage.getItem(CONFIG_STORAGE_KEY);
    if (cached) {
      return JSON.parse(cached);
    }
  } catch {
    // Ignore parse errors
  }
  return null;
}

// Save config to cache
function saveConfigToCache(config: MobileConfig): void {
  try {
    localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(config));
  } catch {
    // Ignore storage errors
  }
}

// Load hidden modules from storage
function loadHiddenModules(): string[] {
  try {
    const stored = localStorage.getItem(HIDDEN_MODULES_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch {
    // Ignore parse errors
  }
  return [];
}

// Save hidden modules to storage
function saveHiddenModules(modules: string[]): void {
  try {
    localStorage.setItem(HIDDEN_MODULES_KEY, JSON.stringify(modules));
  } catch {
    // Ignore storage errors
  }
}

// Default nav shortcuts
const DEFAULT_NAV_SHORTCUTS: NavShortcut[] = [
  { moduleId: 'home', label: 'Accueil', icon: 'home', path: '/' },
  { moduleId: 'interventions', label: 'Interventions', icon: 'wrench', path: '/module/interventions' },
  { moduleId: 'clients', label: 'Clients', icon: 'users', path: '/module/clients' },
  { moduleId: 'settings', label: 'Parametres', icon: 'settings', path: '/settings' },
];

// Load nav shortcuts from storage
function loadNavShortcuts(): NavShortcut[] {
  try {
    const stored = localStorage.getItem(NAV_SHORTCUTS_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch {
    // Ignore parse errors
  }
  return DEFAULT_NAV_SHORTCUTS;
}

// Save nav shortcuts to storage
function saveNavShortcuts(shortcuts: NavShortcut[]): void {
  try {
    localStorage.setItem(NAV_SHORTCUTS_KEY, JSON.stringify(shortcuts));
  } catch {
    // Ignore storage errors
  }
}

// Apply theme colors to CSS variables
function applyThemeColors(theme: ThemeColors): void {
  const root = document.documentElement;
  Object.entries(theme).forEach(([key, value]) => {
    // Convert camelCase to kebab-case
    const cssVar = `--color-${key.replace(/([A-Z])/g, '-$1').toLowerCase()}`;
    root.style.setProperty(cssVar, value);
  });
}

// Provider props
interface MobileConfigProviderProps {
  children: React.ReactNode;
}

// Provider component
export function MobileConfigProvider({ children }: MobileConfigProviderProps): React.ReactElement {
  const { isAuthenticated } = useAuth();
  const [state, setState] = useState<MobileConfigState>(() => {
    const cached = loadCachedConfig();
    return {
      config: cached || DEFAULT_CONFIG,
      isLoading: false,
      error: null,
      lastUpdated: cached ? new Date() : null,
    };
  });
  const [hiddenModules, setHiddenModules] = useState<string[]>(() => loadHiddenModules());
  const [navShortcuts, setNavShortcutsState] = useState<NavShortcut[]>(() => loadNavShortcuts());

  // Set nav shortcuts
  const setNavShortcuts = useCallback((shortcuts: NavShortcut[]) => {
    setNavShortcutsState(shortcuts);
    saveNavShortcuts(shortcuts);
  }, []);

  // Reset nav shortcuts to default
  const resetNavShortcuts = useCallback(() => {
    setNavShortcutsState(DEFAULT_NAV_SHORTCUTS);
    saveNavShortcuts(DEFAULT_NAV_SHORTCUTS);
  }, []);

  // Toggle module visibility
  const toggleModuleVisibility = useCallback((moduleId: string) => {
    setHiddenModules((prev) => {
      const newHidden = prev.includes(moduleId)
        ? prev.filter((id) => id !== moduleId)
        : [...prev, moduleId];
      saveHiddenModules(newHidden);
      return newHidden;
    });
  }, []);

  // Set module order
  const setModuleOrder = useCallback((moduleId: string, newOrder: number) => {
    setState((prev) => {
      if (!prev.config) return prev;
      const modules = prev.config.modules.map((m) =>
        m.id === moduleId ? { ...m, order: newOrder } : m
      );
      const newConfig = { ...prev.config, modules };
      saveConfigToCache(newConfig);
      return { ...prev, config: newConfig };
    });
  }, []);

  // Fetch config from API
  const fetchConfig = useCallback(async () => {
    if (!isAuthenticated) return;

    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      // Fetch bootstrap data via direct fetch (endpoint at /api/mobile/bootstrap)
      const token = localStorage.getItem('azalplus_access_token');
      const response = await fetch('/api/mobile/bootstrap', {
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (!response.ok) {
        throw new Error('Erreur chargement configuration');
      }

      const bootstrap: BootstrapResponse = await response.json();

      // Map backend modules to frontend ModuleConfig
      const userModules = bootstrap.permissions.modules;
      const hasAllAccess = userModules.includes('*');

      const modules: ModuleConfig[] = bootstrap.modules
        .filter((m) => hasAllAccess || userModules.includes(m.name))
        .map((m, index) => ({
          id: m.name,
          name: m.name,
          displayName: m.display_name,
          icon: m.icon || 'file',
          route: `/${m.name}`,
          permissions: m.permissions || [],
          enabled: true,
          order: index,
          menu: m.menu,
          description: m.description,
          fieldsCount: m.fields_count,
        }));

      // Build theme from bootstrap config
      const theme: ThemeColors = {
        ...DEFAULT_THEME,
        primary: bootstrap.config.primary_color || DEFAULT_THEME.primary,
      };

      // Build merged config
      const mergedConfig: MobileConfig = {
        ...DEFAULT_CONFIG,
        modules,
        theme,
        features: {
          ...DEFAULT_CONFIG.features,
          offlineMode: bootstrap.config.offline_enabled,
          pushNotifications: bootstrap.config.push_notifications_enabled,
          biometricAuth: bootstrap.config.biometric_auth_enabled,
        },
        company: {
          name: bootstrap.tenant.nom,
          logoUrl: bootstrap.tenant.logo_url || bootstrap.config.logo_url,
        },
      };

      // Apply theme
      applyThemeColors(mergedConfig.theme);

      // Cache config
      saveConfigToCache(mergedConfig);

      setState({
        config: mergedConfig,
        isLoading: false,
        error: null,
        lastUpdated: new Date(),
      });
    } catch (error) {
      const message = (error as { message?: string })?.message || 'Erreur chargement configuration';
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: message,
      }));
    }
  }, [isAuthenticated]);

  // Fetch config when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      fetchConfig();
    }
  }, [isAuthenticated, fetchConfig]);

  // Apply theme on initial load
  useEffect(() => {
    if (state.config?.theme) {
      applyThemeColors(state.config.theme);
    }
  }, []);

  // Helper functions
  const getModule = useCallback(
    (moduleId: string): ModuleConfig | undefined => {
      return state.config?.modules.find((m) => m.id === moduleId);
    },
    [state.config]
  );

  const getEnabledModules = useCallback((): ModuleConfig[] => {
    if (!state.config) return [];
    return state.config.modules
      .filter((m) => m.enabled && !hiddenModules.includes(m.id))
      .sort((a, b) => a.order - b.order);
  }, [state.config, hiddenModules]);

  const getAllModules = useCallback((): ModuleConfig[] => {
    if (!state.config) return [];
    return state.config.modules
      .map((m) => ({ ...m, enabled: !hiddenModules.includes(m.id) }))
      .sort((a, b) => a.order - b.order);
  }, [state.config, hiddenModules]);

  const getWidgets = useCallback((): DashboardWidget[] => {
    if (!state.config) return [];
    return [...state.config.dashboardWidgets].sort((a, b) => a.position - b.position);
  }, [state.config]);

  const getQuickActions = useCallback((): QuickAction[] => {
    return state.config?.quickActions || [];
  }, [state.config]);

  // Memoize context value
  const contextValue = useMemo<MobileConfigContextValue>(
    () => ({
      ...state,
      refresh: fetchConfig,
      getModule,
      getEnabledModules,
      getAllModules,
      getWidgets,
      getQuickActions,
      hiddenModules,
      toggleModuleVisibility,
      setModuleOrder,
      navShortcuts,
      setNavShortcuts,
      resetNavShortcuts,
    }),
    [state, fetchConfig, getModule, getEnabledModules, getAllModules, getWidgets, getQuickActions, hiddenModules, toggleModuleVisibility, setModuleOrder, navShortcuts, setNavShortcuts, resetNavShortcuts]
  );

  return (
    <MobileConfigContext.Provider value={contextValue}>
      {children}
    </MobileConfigContext.Provider>
  );
}

// Hook to access mobile config
export function useMobileConfig(): MobileConfigContextValue {
  const context = useContext(MobileConfigContext);

  if (!context) {
    throw new Error('useMobileConfig must be used within a MobileConfigProvider');
  }

  return context;
}

// Hook to get specific module config
export function useModuleConfig(moduleId: string): ModuleConfig | undefined {
  const { getModule } = useMobileConfig();
  return getModule(moduleId);
}

// Hook to get theme colors
export function useTheme(): ThemeColors {
  const { config } = useMobileConfig();
  return config?.theme || DEFAULT_THEME;
}

// Hook to check feature flags
export function useFeature(feature: keyof MobileConfig['features']): boolean {
  const { config } = useMobileConfig();
  return config?.features[feature] ?? false;
}
