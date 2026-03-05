// AZALPLUS - Mobile Configuration Admin Page
// Main page with tabs/sections for mobile app configuration

import React, { useState, useEffect, useCallback } from 'react';
import type {
  MobileConfig,
  MobileModule,
  DashboardWidget,
  QuickAction,
  OfflineSettings,
  PushNotificationSettings,
  ThemeBrandingConfig,
  ScreenType,
  DeviceType,
} from './types';
import {
  DEFAULT_OFFLINE_SETTINGS,
  DEFAULT_PUSH_SETTINGS,
  DEFAULT_THEME_BRANDING,
} from './types';
import { getMobileConfig, updateMobileConfig, uploadLogo } from './api';
import { ModuleConfigurator } from './ModuleConfigurator';
import { DashboardBuilder } from './DashboardBuilder';
import { QuickActionsEditor } from './QuickActionsEditor';
import { ThemeBranding } from './ThemeBranding';
import { MobilePreview } from './MobilePreview';

// -----------------------------------------------------------------------------
// Icons
// -----------------------------------------------------------------------------
const SmartphoneIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
  </svg>
);

const GridIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
  </svg>
);

const LayoutIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
  </svg>
);

const ZapIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
  </svg>
);

const CloudOffIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
  </svg>
);

const BellIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
  </svg>
);

const PaletteIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
  </svg>
);

const EyeIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
  </svg>
);

const SaveIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
  </svg>
);

const LoadingSpinner = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg className={`animate-spin ${className}`} fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
  </svg>
);

// -----------------------------------------------------------------------------
// Tab Configuration
// -----------------------------------------------------------------------------
type TabId = 'general' | 'modules' | 'dashboard' | 'quick-actions' | 'offline' | 'notifications' | 'theme' | 'preview';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

const tabs: Tab[] = [
  { id: 'general', label: 'General', icon: <SmartphoneIcon /> },
  { id: 'modules', label: 'Modules', icon: <GridIcon /> },
  { id: 'dashboard', label: 'Dashboard', icon: <LayoutIcon /> },
  { id: 'quick-actions', label: 'Actions', icon: <ZapIcon /> },
  { id: 'offline', label: 'Hors-ligne', icon: <CloudOffIcon /> },
  { id: 'notifications', label: 'Notifications', icon: <BellIcon /> },
  { id: 'theme', label: 'Theme', icon: <PaletteIcon /> },
  { id: 'preview', label: 'Apercu', icon: <EyeIcon /> },
];

// -----------------------------------------------------------------------------
// Default Mock Data
// -----------------------------------------------------------------------------
const defaultConfig: MobileConfig = {
  id: 'default',
  tenantId: 'tenant-1',
  enabled: true,
  appName: 'AZALPLUS Mobile',
  modules: [
    { id: 'clients', name: 'Clients', icon: 'users', enabled: true, order: 0, offlineEnabled: true, syncPriority: 'high' },
    { id: 'factures', name: 'Factures', icon: 'file-text', enabled: true, order: 1, offlineEnabled: true, syncPriority: 'high' },
    { id: 'devis', name: 'Devis', icon: 'file-text', enabled: true, order: 2, offlineEnabled: true, syncPriority: 'medium' },
    { id: 'produits', name: 'Produits', icon: 'package', enabled: true, order: 3, offlineEnabled: false, syncPriority: 'low' },
    { id: 'projets', name: 'Projets', icon: 'folder', enabled: true, order: 4, offlineEnabled: false, syncPriority: 'low' },
    { id: 'interventions', name: 'Interventions', icon: 'calendar', enabled: false, order: 5, offlineEnabled: false, syncPriority: 'medium' },
  ],
  dashboardWidgets: [
    { id: 'w1', type: 'stat', title: 'Clients actifs', dataSource: { module: 'clients', aggregation: 'count' }, size: 'small', order: 0, color: '#2563eb' },
    { id: 'w2', type: 'stat', title: 'CA du mois', dataSource: { module: 'factures', aggregation: 'sum', field: 'montant_ttc' }, size: 'small', order: 1, color: '#059669' },
    { id: 'w3', type: 'list', title: 'Derniers devis', dataSource: { module: 'devis', limit: 5 }, size: 'medium', order: 2, color: '#7c3aed' },
  ],
  quickActions: [
    { id: 'a1', label: 'Nouveau client', icon: 'users', color: '#2563eb', targetModule: 'clients', action: 'create', order: 0 },
    { id: 'a2', label: 'Nouvelle facture', icon: 'file-text', color: '#059669', targetModule: 'factures', action: 'create', order: 1 },
    { id: 'a3', label: 'Rechercher', icon: 'search', color: '#f59e0b', targetModule: 'clients', action: 'search', order: 2 },
  ],
  offlineSettings: DEFAULT_OFFLINE_SETTINGS,
  pushNotifications: DEFAULT_PUSH_SETTINGS,
  themeBranding: DEFAULT_THEME_BRANDING,
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  version: 1,
};

const availableModules = [
  { id: 'clients', name: 'Clients', icon: 'users' },
  { id: 'factures', name: 'Factures', icon: 'file-text' },
  { id: 'devis', name: 'Devis', icon: 'file-text' },
  { id: 'produits', name: 'Produits', icon: 'package' },
  { id: 'projets', name: 'Projets', icon: 'folder' },
  { id: 'interventions', name: 'Interventions', icon: 'calendar' },
  { id: 'contacts', name: 'Contacts', icon: 'users' },
  { id: 'paiements', name: 'Paiements', icon: 'credit-card' },
];

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------
export function MobileConfigPage() {
  const [config, setConfig] = useState<MobileConfig>(defaultConfig);
  const [activeTab, setActiveTab] = useState<TabId>('general');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [previewScreen, setPreviewScreen] = useState<ScreenType>('dashboard');
  const [previewDevice, setPreviewDevice] = useState<DeviceType>('iphone');

  // Load config
  useEffect(() => {
    const loadConfig = async () => {
      setIsLoading(true);
      try {
        const response = await getMobileConfig();
        if (response && response.config) {
          setConfig(response.config);
        } else {
          // Fallback to default config if API returns empty
          setConfig(defaultConfig);
        }
      } catch (error) {
        console.error('Error loading config:', error);
        // Use default config on error
        setConfig(defaultConfig);
      } finally {
        setIsLoading(false);
      }
    };
    loadConfig();
  }, []);

  // Update handlers
  const updateConfig = useCallback(<K extends keyof MobileConfig>(
    key: K,
    value: MobileConfig[K]
  ) => {
    setConfig(prev => ({ ...prev, [key]: value }));
    setIsDirty(true);
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setSaveMessage(null);
    try {
      await updateMobileConfig({
        enabled: config.enabled,
        appName: config.appName,
        modules: config.modules,
        dashboardWidgets: config.dashboardWidgets,
        quickActions: config.quickActions,
        offlineSettings: config.offlineSettings,
        pushNotifications: config.pushNotifications,
        themeBranding: config.themeBranding,
      });
      setSaveMessage({ type: 'success', text: 'Configuration sauvegardee avec succes' });
      setIsDirty(false);
      setTimeout(() => setSaveMessage(null), 3000);
    } catch (error) {
      console.error('Save error:', error);
      setSaveMessage({ type: 'error', text: 'Erreur lors de la sauvegarde' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleLogoUpload = async (file: File): Promise<string> => {
    // In production, uncomment the API call
    // const response = await uploadLogo(file);
    // return response.url;

    // For demo, create a local URL
    return URL.createObjectURL(file);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <LoadingSpinner className="w-8 h-8 text-blue-600" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-100 rounded-lg text-blue-600">
            <SmartphoneIcon />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Configuration Mobile</h1>
            <p className="text-gray-500">Personnalisez l'application mobile AZALPLUS</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {isDirty && (
            <span className="text-sm text-amber-600">Modifications non sauvegardees</span>
          )}
          <button
            onClick={handleSave}
            disabled={isSaving || !isDirty}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? <LoadingSpinner className="w-5 h-5" /> : <SaveIcon />}
            Sauvegarder
          </button>
        </div>
      </div>

      {/* Save Message */}
      {saveMessage && (
        <div className={`p-4 rounded-lg ${
          saveMessage.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
        }`}>
          {saveMessage.text}
        </div>
      )}

      {/* Enable/Disable Toggle */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Application Mobile</h2>
            <p className="text-gray-500 text-sm">Activer ou desactiver l'acces mobile pour ce tenant</p>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={(e) => updateConfig('enabled', e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
          </label>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-gray-200">
        <nav className="flex space-x-1 overflow-x-auto pb-px">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 whitespace-nowrap transition-colors
                ${activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }
              `}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        {/* General Settings */}
        {activeTab === 'general' && (
          <div className="space-y-6">
            <h3 className="text-lg font-semibold text-gray-900">Parametres generaux</h3>

            <div className="max-w-md">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Nom de l'application
              </label>
              <input
                type="text"
                value={config.appName}
                onChange={(e) => updateConfig('appName', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Mon Application"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4">
              <div className="p-4 bg-gray-50 rounded-lg">
                <div className="text-2xl font-bold text-gray-900">
                  {config.modules.filter(m => m.enabled).length}
                </div>
                <div className="text-sm text-gray-500">Modules actifs</div>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <div className="text-2xl font-bold text-gray-900">
                  {config.dashboardWidgets.length}
                </div>
                <div className="text-sm text-gray-500">Widgets</div>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <div className="text-2xl font-bold text-gray-900">
                  {config.quickActions.length}
                </div>
                <div className="text-sm text-gray-500">Actions rapides</div>
              </div>
            </div>
          </div>
        )}

        {/* Modules */}
        {activeTab === 'modules' && (
          <ModuleConfigurator
            modules={config.modules}
            availableModules={availableModules}
            onChange={(modules) => updateConfig('modules', modules)}
          />
        )}

        {/* Dashboard */}
        {activeTab === 'dashboard' && (
          <DashboardBuilder
            widgets={config.dashboardWidgets}
            availableModules={availableModules}
            onChange={(widgets) => updateConfig('dashboardWidgets', widgets)}
          />
        )}

        {/* Quick Actions */}
        {activeTab === 'quick-actions' && (
          <QuickActionsEditor
            actions={config.quickActions}
            availableModules={availableModules}
            onChange={(actions) => updateConfig('quickActions', actions)}
            maxActions={5}
          />
        )}

        {/* Offline Settings */}
        {activeTab === 'offline' && (
          <div className="space-y-6">
            <h3 className="text-lg font-semibold text-gray-900">Parametres hors-ligne</h3>

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div>
                <div className="font-medium">Mode hors-ligne</div>
                <div className="text-sm text-gray-500">Permettre l'utilisation sans connexion</div>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.offlineSettings.enabled}
                  onChange={(e) => updateConfig('offlineSettings', {
                    ...config.offlineSettings,
                    enabled: e.target.checked,
                  })}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Intervalle de synchronisation (minutes)
                </label>
                <input
                  type="number"
                  value={config.offlineSettings.syncInterval}
                  onChange={(e) => updateConfig('offlineSettings', {
                    ...config.offlineSettings,
                    syncInterval: parseInt(e.target.value),
                  })}
                  min={5}
                  max={120}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Stockage maximum (Mo)
                </label>
                <input
                  type="number"
                  value={config.offlineSettings.maxStorageSize}
                  onChange={(e) => updateConfig('offlineSettings', {
                    ...config.offlineSettings,
                    maxStorageSize: parseInt(e.target.value),
                  })}
                  min={10}
                  max={500}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Resolution des conflits
                </label>
                <select
                  value={config.offlineSettings.conflictResolution}
                  onChange={(e) => updateConfig('offlineSettings', {
                    ...config.offlineSettings,
                    conflictResolution: e.target.value as 'server-wins' | 'client-wins' | 'manual',
                  })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  <option value="server-wins">Le serveur a priorite</option>
                  <option value="client-wins">Le client a priorite</option>
                  <option value="manual">Resolution manuelle</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Retention des donnees (jours)
                </label>
                <input
                  type="number"
                  value={config.offlineSettings.retentionDays}
                  onChange={(e) => updateConfig('offlineSettings', {
                    ...config.offlineSettings,
                    retentionDays: parseInt(e.target.value),
                  })}
                  min={1}
                  max={90}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div className="flex items-center gap-6 pt-4 border-t">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.offlineSettings.autoSync}
                  onChange={(e) => updateConfig('offlineSettings', {
                    ...config.offlineSettings,
                    autoSync: e.target.checked,
                  })}
                  className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Synchronisation automatique</span>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.offlineSettings.syncOnWifi}
                  onChange={(e) => updateConfig('offlineSettings', {
                    ...config.offlineSettings,
                    syncOnWifi: e.target.checked,
                  })}
                  className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Synchroniser uniquement en WiFi</span>
              </label>
            </div>
          </div>
        )}

        {/* Push Notifications */}
        {activeTab === 'notifications' && (
          <div className="space-y-6">
            <h3 className="text-lg font-semibold text-gray-900">Notifications push</h3>

            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div>
                <div className="font-medium">Notifications push</div>
                <div className="text-sm text-gray-500">Activer les notifications push</div>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.pushNotifications.enabled}
                  onChange={(e) => updateConfig('pushNotifications', {
                    ...config.pushNotifications,
                    enabled: e.target.checked,
                  })}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
              </label>
            </div>

            {/* Channels */}
            <div>
              <h4 className="font-medium text-gray-900 mb-3">Canaux de notification</h4>
              <div className="space-y-3">
                {config.pushNotifications.channels.map((channel, index) => (
                  <div key={channel.id} className="p-4 border border-gray-200 rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <div className="font-medium">{channel.name}</div>
                        <div className="text-sm text-gray-500">{channel.description}</div>
                      </div>
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={channel.enabled}
                          onChange={(e) => {
                            const channels = [...config.pushNotifications.channels];
                            channels[index] = { ...channel, enabled: e.target.checked };
                            updateConfig('pushNotifications', {
                              ...config.pushNotifications,
                              channels,
                            });
                          }}
                          className="sr-only peer"
                        />
                        <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                      </label>
                    </div>
                    <div className="flex gap-4 text-sm">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={channel.sound}
                          onChange={(e) => {
                            const channels = [...config.pushNotifications.channels];
                            channels[index] = { ...channel, sound: e.target.checked };
                            updateConfig('pushNotifications', {
                              ...config.pushNotifications,
                              channels,
                            });
                          }}
                          className="w-3.5 h-3.5 text-blue-600 rounded focus:ring-blue-500"
                        />
                        <span className="text-gray-600">Son</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={channel.vibration}
                          onChange={(e) => {
                            const channels = [...config.pushNotifications.channels];
                            channels[index] = { ...channel, vibration: e.target.checked };
                            updateConfig('pushNotifications', {
                              ...config.pushNotifications,
                              channels,
                            });
                          }}
                          className="w-3.5 h-3.5 text-blue-600 rounded focus:ring-blue-500"
                        />
                        <span className="text-gray-600">Vibration</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={channel.badge}
                          onChange={(e) => {
                            const channels = [...config.pushNotifications.channels];
                            channels[index] = { ...channel, badge: e.target.checked };
                            updateConfig('pushNotifications', {
                              ...config.pushNotifications,
                              channels,
                            });
                          }}
                          className="w-3.5 h-3.5 text-blue-600 rounded focus:ring-blue-500"
                        />
                        <span className="text-gray-600">Badge</span>
                      </label>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Quiet Hours */}
            <div className="p-4 border border-gray-200 rounded-lg">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="font-medium">Heures silencieuses</div>
                  <div className="text-sm text-gray-500">Desactiver les notifications pendant certaines heures</div>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.pushNotifications.quietHours.enabled}
                    onChange={(e) => updateConfig('pushNotifications', {
                      ...config.pushNotifications,
                      quietHours: {
                        ...config.pushNotifications.quietHours,
                        enabled: e.target.checked,
                      },
                    })}
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                </label>
              </div>
              {config.pushNotifications.quietHours.enabled && (
                <div className="flex items-center gap-4">
                  <div>
                    <label className="block text-sm text-gray-600 mb-1">Debut</label>
                    <input
                      type="time"
                      value={config.pushNotifications.quietHours.start}
                      onChange={(e) => updateConfig('pushNotifications', {
                        ...config.pushNotifications,
                        quietHours: {
                          ...config.pushNotifications.quietHours,
                          start: e.target.value,
                        },
                      })}
                      className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-600 mb-1">Fin</label>
                    <input
                      type="time"
                      value={config.pushNotifications.quietHours.end}
                      onChange={(e) => updateConfig('pushNotifications', {
                        ...config.pushNotifications,
                        quietHours: {
                          ...config.pushNotifications.quietHours,
                          end: e.target.value,
                        },
                      })}
                      className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Theme & Branding */}
        {activeTab === 'theme' && (
          <ThemeBranding
            config={config.themeBranding}
            onChange={(themeBranding) => updateConfig('themeBranding', themeBranding)}
            onLogoUpload={handleLogoUpload}
          />
        )}

        {/* Preview */}
        {activeTab === 'preview' && (
          <MobilePreview
            config={config}
            screen={previewScreen}
            device={previewDevice}
            onScreenChange={setPreviewScreen}
            onDeviceChange={setPreviewDevice}
          />
        )}
      </div>
    </div>
  );
}

export default MobileConfigPage;
