// AZALPLUS - Types Mobile Configuration Admin UI

// -----------------------------------------------------------------------------
// Enums & Base Types
// -----------------------------------------------------------------------------
export type WidgetType = 'stat' | 'list' | 'chart' | 'calendar' | 'tasks';
export type ChartType = 'line' | 'bar' | 'pie' | 'donut';
export type ScreenType = 'dashboard' | 'module-list' | 'module-detail' | 'quick-actions';
export type DeviceType = 'iphone' | 'android';

// -----------------------------------------------------------------------------
// Module Configuration
// -----------------------------------------------------------------------------
export interface MobileModule {
  id: string;
  name: string;
  icon: string;
  enabled: boolean;
  order: number;
  offlineEnabled: boolean;
  syncPriority: 'high' | 'medium' | 'low';
}

export interface ModuleVisibility {
  moduleId: string;
  visible: boolean;
  order: number;
}

// -----------------------------------------------------------------------------
// Dashboard Widget Configuration
// -----------------------------------------------------------------------------
export interface WidgetDataSource {
  module: string;
  endpoint?: string;
  filters?: Record<string, unknown>;
  aggregation?: 'count' | 'sum' | 'avg' | 'min' | 'max';
  field?: string;
  limit?: number;
}

export interface DashboardWidget {
  id: string;
  type: WidgetType;
  title: string;
  icon?: string;
  dataSource: WidgetDataSource;
  chartType?: ChartType;
  color?: string;
  size: 'small' | 'medium' | 'large';
  order: number;
  refreshInterval?: number; // in seconds
}

// -----------------------------------------------------------------------------
// Quick Actions Configuration
// -----------------------------------------------------------------------------
export interface QuickAction {
  id: string;
  label: string;
  icon: string;
  color: string;
  targetModule: string;
  action: 'create' | 'list' | 'search' | 'custom';
  customRoute?: string;
  order: number;
}

// -----------------------------------------------------------------------------
// Offline Settings
// -----------------------------------------------------------------------------
export interface OfflineSettings {
  enabled: boolean;
  syncInterval: number; // in minutes
  maxStorageSize: number; // in MB
  priorityModules: string[];
  autoSync: boolean;
  syncOnWifi: boolean;
  conflictResolution: 'server-wins' | 'client-wins' | 'manual';
  retentionDays: number;
}

// -----------------------------------------------------------------------------
// Push Notification Settings
// -----------------------------------------------------------------------------
export interface NotificationChannel {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  sound: boolean;
  vibration: boolean;
  badge: boolean;
}

export interface PushNotificationSettings {
  enabled: boolean;
  channels: NotificationChannel[];
  quietHours: {
    enabled: boolean;
    start: string; // HH:mm format
    end: string;
  };
  frequency: 'realtime' | 'hourly' | 'daily';
}

// -----------------------------------------------------------------------------
// Theme & Branding
// -----------------------------------------------------------------------------
export interface ThemeBrandingConfig {
  appName: string;
  logoUrl?: string;
  faviconUrl?: string;
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  darkMode: boolean;
  fontFamily?: string;
  borderRadius: 'none' | 'small' | 'medium' | 'large';
  customCss?: string;
}

// -----------------------------------------------------------------------------
// Main Mobile Configuration
// -----------------------------------------------------------------------------
export interface MobileConfig {
  id: string;
  tenantId: string;
  enabled: boolean;
  appName: string;
  logoUrl?: string;

  // Module configuration
  modules: MobileModule[];

  // Dashboard widgets
  dashboardWidgets: DashboardWidget[];

  // Quick actions (FAB menu)
  quickActions: QuickAction[];

  // Settings
  offlineSettings: OfflineSettings;
  pushNotifications: PushNotificationSettings;
  themeBranding: ThemeBrandingConfig;

  // Metadata
  createdAt: string;
  updatedAt: string;
  version: number;
}

// -----------------------------------------------------------------------------
// API Request/Response Types
// -----------------------------------------------------------------------------
export interface MobileConfigUpdateRequest {
  enabled?: boolean;
  appName?: string;
  logoUrl?: string;
  modules?: MobileModule[];
  dashboardWidgets?: DashboardWidget[];
  quickActions?: QuickAction[];
  offlineSettings?: Partial<OfflineSettings>;
  pushNotifications?: Partial<PushNotificationSettings>;
  themeBranding?: Partial<ThemeBrandingConfig>;
}

export interface MobileConfigResponse {
  config: MobileConfig;
  availableModules: Array<{
    id: string;
    name: string;
    icon: string;
  }>;
}

export interface UploadLogoResponse {
  url: string;
  filename: string;
}

// -----------------------------------------------------------------------------
// Component Props Types
// -----------------------------------------------------------------------------
export interface ModuleConfiguratorProps {
  modules: MobileModule[];
  availableModules: Array<{ id: string; name: string; icon: string }>;
  onChange: (modules: MobileModule[]) => void;
}

export interface DashboardBuilderProps {
  widgets: DashboardWidget[];
  availableModules: Array<{ id: string; name: string }>;
  onChange: (widgets: DashboardWidget[]) => void;
}

export interface QuickActionsEditorProps {
  actions: QuickAction[];
  availableModules: Array<{ id: string; name: string }>;
  onChange: (actions: QuickAction[]) => void;
  maxActions?: number;
}

export interface ThemeBrandingProps {
  config: ThemeBrandingConfig;
  onChange: (config: ThemeBrandingConfig) => void;
  onLogoUpload: (file: File) => Promise<string>;
}

export interface MobilePreviewProps {
  config: MobileConfig;
  screen: ScreenType;
  device: DeviceType;
  onScreenChange: (screen: ScreenType) => void;
  onDeviceChange: (device: DeviceType) => void;
}

// -----------------------------------------------------------------------------
// Form State Types
// -----------------------------------------------------------------------------
export interface MobileConfigFormState {
  isLoading: boolean;
  isSaving: boolean;
  isDirty: boolean;
  errors: Record<string, string>;
  activeTab: string;
}

// -----------------------------------------------------------------------------
// Default Values
// -----------------------------------------------------------------------------
export const DEFAULT_OFFLINE_SETTINGS: OfflineSettings = {
  enabled: true,
  syncInterval: 15,
  maxStorageSize: 100,
  priorityModules: ['clients', 'factures', 'devis'],
  autoSync: true,
  syncOnWifi: false,
  conflictResolution: 'server-wins',
  retentionDays: 30,
};

export const DEFAULT_PUSH_SETTINGS: PushNotificationSettings = {
  enabled: true,
  channels: [
    {
      id: 'general',
      name: 'General',
      description: 'Notifications generales',
      enabled: true,
      sound: true,
      vibration: true,
      badge: true,
    },
    {
      id: 'alerts',
      name: 'Alertes',
      description: 'Alertes importantes',
      enabled: true,
      sound: true,
      vibration: true,
      badge: true,
    },
    {
      id: 'updates',
      name: 'Mises a jour',
      description: 'Mises a jour de donnees',
      enabled: true,
      sound: false,
      vibration: false,
      badge: true,
    },
  ],
  quietHours: {
    enabled: false,
    start: '22:00',
    end: '07:00',
  },
  frequency: 'realtime',
};

export const DEFAULT_THEME_BRANDING: ThemeBrandingConfig = {
  appName: 'AZALPLUS',
  primaryColor: '#2563eb',
  secondaryColor: '#7c3aed',
  accentColor: '#f59e0b',
  darkMode: false,
  borderRadius: 'medium',
};

export const AVAILABLE_ICONS = [
  'home', 'users', 'file-text', 'folder', 'package', 'truck', 'credit-card',
  'building', 'calendar', 'clock', 'sparkles', 'shield', 'globe', 'hash',
  'plus', 'search', 'bell', 'settings', 'chart', 'list', 'grid', 'star',
  'heart', 'mail', 'phone', 'map-pin', 'briefcase', 'shopping-cart', 'tag',
  'check', 'x', 'alert', 'info', 'help', 'camera', 'image', 'document',
];

export const PRESET_COLORS = [
  '#2563eb', // Blue
  '#7c3aed', // Purple
  '#059669', // Green
  '#dc2626', // Red
  '#f59e0b', // Amber
  '#06b6d4', // Cyan
  '#ec4899', // Pink
  '#84cc16', // Lime
  '#6366f1', // Indigo
  '#f97316', // Orange
];
