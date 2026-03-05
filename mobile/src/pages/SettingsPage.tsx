import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../core/auth/useAuth';
import { useMobileConfig, useFeature, ModuleConfig, NavShortcut } from '../core/config/MobileConfigProvider';
import { Icon } from '../components/ui/Icon';

// Storage keys
const STORAGE_KEYS = {
  DARK_MODE: 'azalplus_dark_mode',
  PUSH_ENABLED: 'azalplus_push_enabled',
};

// Load setting from localStorage
const loadSetting = (key: string, defaultValue: boolean): boolean => {
  try {
    const stored = localStorage.getItem(key);
    return stored !== null ? JSON.parse(stored) : defaultValue;
  } catch {
    return defaultValue;
  }
};

// Save setting to localStorage
const saveSetting = (key: string, value: boolean): void => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.error('Failed to save setting:', error);
  }
};

export default function SettingsPage(): React.ReactElement {
  const { user, logout } = useAuth();
  const { config, getAllModules, toggleModuleVisibility, hiddenModules, navShortcuts, setNavShortcuts } = useMobileConfig();
  const navigate = useNavigate();
  const darkModeEnabled = useFeature('darkMode');
  const offlineModeEnabled = useFeature('offlineMode');
  const pushNotificationsEnabled = useFeature('pushNotifications');

  // Get all modules for management
  const allModules = getAllModules();

  // State for shortcut editing
  const [editingShortcut, setEditingShortcut] = useState<number | null>(null);

  // Fixed shortcuts (home and settings)
  const fixedShortcuts = ['home', 'settings'];

  // Handle shortcut module selection
  const handleShortcutChange = (index: number, module: ModuleConfig) => {
    const newShortcuts = [...navShortcuts];
    newShortcuts[index] = {
      moduleId: module.id,
      label: module.displayName,
      icon: module.icon,
      path: `/module/${module.id}`,
    };
    setNavShortcuts(newShortcuts);
    setEditingShortcut(null);
  };

  // Load settings from localStorage on mount
  const [darkMode, setDarkMode] = useState(() => loadSetting(STORAGE_KEYS.DARK_MODE, false));
  const [pushEnabled, setPushEnabled] = useState(() => loadSetting(STORAGE_KEYS.PUSH_ENABLED, false));
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  // Toggle dark mode and persist
  const handleDarkModeToggle = () => {
    const newValue = !darkMode;
    setDarkMode(newValue);
    saveSetting(STORAGE_KEYS.DARK_MODE, newValue);

    // Apply dark mode to document
    if (newValue) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  };

  // Toggle push notifications and persist
  const handlePushToggle = () => {
    const newValue = !pushEnabled;
    setPushEnabled(newValue);
    saveSetting(STORAGE_KEYS.PUSH_ENABLED, newValue);
  };

  // Apply dark mode on mount
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, []);

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
      navigate('/login');
    } catch (error) {
      console.error('Logout failed:', error);
    } finally {
      setIsLoggingOut(false);
    }
  };

  return (
    <div className="p-4 space-y-6">
      {/* Profile Section */}
      <section>
        <h2 className="text-sm font-medium text-gray-500 mb-3">Profil</h2>
        <div className="card p-4">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
              {user?.avatarUrl ? (
                <img
                  src={user.avatarUrl}
                  alt={user.fullName}
                  className="w-full h-full rounded-full object-cover"
                />
              ) : (
                <span className="text-xl sm:text-2xl text-primary-600 font-medium">
                  {user?.firstName?.[0]}{user?.lastName?.[0]}
                </span>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-medium text-gray-900 truncate">{user?.fullName}</h3>
              <p className="text-sm text-gray-500 truncate">{user?.email}</p>
              <p className="text-xs text-gray-400 mt-1">{user?.role}</p>
            </div>
          </div>
        </div>
      </section>

      {/* Preferences Section */}
      <section>
        <h2 className="text-sm font-medium text-gray-500 mb-3">Preferences</h2>
        <div className="card divide-y divide-gray-100">
          {darkModeEnabled && (
            <div className="p-4 flex items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <h3 className="font-medium text-gray-900">Mode sombre</h3>
                <p className="text-sm text-gray-500">Apparence de l'application</p>
              </div>
              <button
                onClick={handleDarkModeToggle}
                className={`relative w-12 h-6 rounded-full transition-colors flex-shrink-0 ${darkMode ? 'bg-primary-600' : 'bg-gray-200'}`}
              >
                <span className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${darkMode ? 'left-7' : 'left-1'}`} />
              </button>
            </div>
          )}

          {offlineModeEnabled && (
            <div className="p-4 flex items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <h3 className="font-medium text-gray-900">Mode hors ligne</h3>
                <p className="text-sm text-gray-500">Synchroniser les donnees</p>
              </div>
              <Link to="/offline" className="text-primary-600 flex-shrink-0">
                Gerer
              </Link>
            </div>
          )}

          {pushNotificationsEnabled && (
            <div className="p-4 flex items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <h3 className="font-medium text-gray-900">Notifications push</h3>
                <p className="text-sm text-gray-500">Recevoir des alertes</p>
              </div>
              <button
                onClick={handlePushToggle}
                className={`relative w-12 h-6 rounded-full transition-colors flex-shrink-0 ${pushEnabled ? 'bg-primary-600' : 'bg-gray-200'}`}
              >
                <span className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${pushEnabled ? 'left-7' : 'left-1'}`} />
              </button>
            </div>
          )}

          {!darkModeEnabled && !offlineModeEnabled && !pushNotificationsEnabled && (
            <div className="p-4 text-center text-gray-500">
              Aucune preference disponible
            </div>
          )}
        </div>
      </section>

      {/* Bottom Nav Shortcuts Section */}
      <section>
        <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Raccourcis du menu</h2>
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">Choisissez les 4 modules affichés dans la barre de navigation</p>
        <div className="card divide-y divide-gray-100 dark:divide-gray-700">
          {navShortcuts.map((shortcut, index) => {
            const isFixed = fixedShortcuts.includes(shortcut.moduleId);
            const isEditing = editingShortcut === index;

            return (
              <div key={index} className="p-4">
                {isEditing ? (
                  <div className="space-y-2">
                    <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Choisir un module :</p>
                    <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto">
                      {allModules.map((module) => (
                        <button
                          key={module.id}
                          onClick={() => handleShortcutChange(index, module)}
                          className="flex items-center gap-2 p-2 rounded-lg bg-gray-50 dark:bg-gray-800 hover:bg-primary-50 dark:hover:bg-primary-900 transition-colors text-left"
                        >
                          <Icon name={module.icon || 'file'} size={18} />
                          <span className="text-sm truncate">{module.displayName}</span>
                        </button>
                      ))}
                    </div>
                    <button
                      onClick={() => setEditingShortcut(null)}
                      className="w-full mt-2 p-2 text-sm text-gray-500 hover:text-gray-700"
                    >
                      Annuler
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div className="w-10 h-10 rounded-lg bg-primary-100 dark:bg-primary-900 flex items-center justify-center flex-shrink-0">
                        <Icon name={shortcut.icon} size={20} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate">{shortcut.label}</h3>
                        <p className="text-xs text-gray-400">Position {index + 1}</p>
                      </div>
                    </div>
                    {!isFixed ? (
                      <button
                        onClick={() => setEditingShortcut(index)}
                        className="px-3 py-1.5 text-sm text-primary-600 bg-primary-50 dark:bg-primary-900 rounded-lg hover:bg-primary-100 transition-colors"
                      >
                        Modifier
                      </button>
                    ) : (
                      <span className="text-xs text-gray-400 italic">Fixe</span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Modules Section */}
      <section>
        <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Modules visibles</h2>
        <div className="card divide-y divide-gray-100 dark:divide-gray-700">
          {allModules.length > 0 ? (
            allModules.map((module) => (
              <div key={module.id} className="p-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="w-10 h-10 rounded-lg bg-primary-100 dark:bg-primary-900 flex items-center justify-center flex-shrink-0">
                    <Icon name={module.icon || 'file'} size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate">{module.displayName}</h3>
                    {module.description && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{module.description}</p>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => toggleModuleVisibility(module.id)}
                  className={`relative w-12 h-6 rounded-full transition-colors flex-shrink-0 ${
                    !hiddenModules.includes(module.id) ? 'bg-primary-600' : 'bg-gray-200 dark:bg-gray-600'
                  }`}
                >
                  <span
                    className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                      !hiddenModules.includes(module.id) ? 'left-7' : 'left-1'
                    }`}
                  />
                </button>
              </div>
            ))
          ) : (
            <div className="p-4 text-center text-gray-500 dark:text-gray-400">
              Aucun module disponible
            </div>
          )}
        </div>
      </section>

      {/* Info Section */}
      <section>
        <h2 className="text-sm font-medium text-gray-500 mb-3">Informations</h2>
        <div className="card divide-y divide-gray-100">
          <div className="p-4 flex items-center justify-between gap-3">
            <span className="text-gray-600">Entreprise</span>
            <span className="text-gray-900 truncate">{config?.company.name}</span>
          </div>
          <div className="p-4 flex items-center justify-between gap-3">
            <span className="text-gray-600">Tenant</span>
            <span className="text-gray-900 truncate">{user?.tenantName}</span>
          </div>
          <div className="p-4 flex items-center justify-between gap-3">
            <span className="text-gray-600">Version</span>
            <span className="text-gray-900">{config?.version || '1.0.0'}</span>
          </div>
        </div>
      </section>

      {/* Support Section */}
      {(config?.company.supportEmail || config?.company.supportPhone) && (
        <section>
          <h2 className="text-sm font-medium text-gray-500 mb-3">Support</h2>
          <div className="card divide-y divide-gray-100">
            {config.company.supportEmail && (
              <a href={`mailto:${config.company.supportEmail}`} className="p-4 flex items-center justify-between gap-3">
                <span className="text-gray-600">Email</span>
                <span className="text-primary-600 truncate">{config.company.supportEmail}</span>
              </a>
            )}
            {config.company.supportPhone && (
              <a href={`tel:${config.company.supportPhone}`} className="p-4 flex items-center justify-between gap-3">
                <span className="text-gray-600">Telephone</span>
                <span className="text-primary-600">{config.company.supportPhone}</span>
              </a>
            )}
          </div>
        </section>
      )}

      {/* Logout */}
      <section>
        <button
          onClick={handleLogout}
          disabled={isLoggingOut}
          className="w-full p-4 rounded-xl bg-red-50 text-red-600 font-medium active:scale-95 transition-transform disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoggingOut ? 'Deconnexion...' : 'Se deconnecter'}
        </button>
      </section>
    </div>
  );
}
