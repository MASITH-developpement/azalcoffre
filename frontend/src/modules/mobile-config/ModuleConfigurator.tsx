// AZALPLUS - Module Configurator Component
// Drag-drop to reorder and toggle module visibility

import React, { useState, useCallback } from 'react';
import type { MobileModule, ModuleConfiguratorProps } from './types';

// -----------------------------------------------------------------------------
// Icons
// -----------------------------------------------------------------------------
const GripIcon = () => (
  <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8h16M4 16h16" />
  </svg>
);

const EyeIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
  </svg>
);

const EyeOffIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
  </svg>
);

const CloudIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
  </svg>
);

const ChevronUpIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
  </svg>
);

const ChevronDownIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
  </svg>
);

// Module icon mapping
const moduleIcons: Record<string, React.ReactNode> = {
  home: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
    </svg>
  ),
  users: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
    </svg>
  ),
  'file-text': (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  ),
  folder: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
    </svg>
  ),
  package: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
    </svg>
  ),
  'credit-card': (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
    </svg>
  ),
  calendar: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  ),
  default: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  ),
};

const getModuleIcon = (iconName: string) => moduleIcons[iconName] || moduleIcons.default;

// -----------------------------------------------------------------------------
// Module Item Component
// -----------------------------------------------------------------------------
interface ModuleItemProps {
  module: MobileModule;
  index: number;
  totalCount: number;
  isDragging: boolean;
  onToggleEnabled: (id: string) => void;
  onToggleOffline: (id: string) => void;
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
  onDragStart: (index: number) => void;
  onDragEnter: (index: number) => void;
  onDragEnd: () => void;
  onSyncPriorityChange: (id: string, priority: 'high' | 'medium' | 'low') => void;
}

const ModuleItem: React.FC<ModuleItemProps> = ({
  module,
  index,
  totalCount,
  isDragging,
  onToggleEnabled,
  onToggleOffline,
  onMoveUp,
  onMoveDown,
  onDragStart,
  onDragEnter,
  onDragEnd,
  onSyncPriorityChange,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      draggable
      onDragStart={() => onDragStart(index)}
      onDragEnter={() => onDragEnter(index)}
      onDragEnd={onDragEnd}
      onDragOver={(e) => e.preventDefault()}
      className={`
        bg-white border rounded-lg transition-all
        ${isDragging ? 'opacity-50 border-blue-400' : 'border-gray-200'}
        ${!module.enabled ? 'bg-gray-50' : ''}
      `}
    >
      {/* Main Row */}
      <div className="flex items-center gap-3 p-3">
        {/* Drag Handle */}
        <div className="cursor-grab active:cursor-grabbing">
          <GripIcon />
        </div>

        {/* Module Icon */}
        <div className={`p-2 rounded-lg ${module.enabled ? 'bg-blue-50 text-blue-600' : 'bg-gray-100 text-gray-400'}`}>
          {getModuleIcon(module.icon)}
        </div>

        {/* Module Name */}
        <div className="flex-1 min-w-0">
          <h4 className={`font-medium truncate ${!module.enabled ? 'text-gray-400' : 'text-gray-900'}`}>
            {module.name}
          </h4>
          <div className="flex items-center gap-2 mt-0.5">
            {module.offlineEnabled && (
              <span className="inline-flex items-center gap-1 text-xs text-green-600">
                <CloudIcon />
                Hors-ligne
              </span>
            )}
            {module.syncPriority === 'high' && (
              <span className="text-xs text-amber-600">Priorite haute</span>
            )}
          </div>
        </div>

        {/* Visibility Toggle */}
        <button
          onClick={() => onToggleEnabled(module.id)}
          className={`p-2 rounded-lg transition-colors ${
            module.enabled
              ? 'text-blue-600 hover:bg-blue-50'
              : 'text-gray-400 hover:bg-gray-100'
          }`}
          title={module.enabled ? 'Masquer' : 'Afficher'}
        >
          {module.enabled ? <EyeIcon /> : <EyeOffIcon />}
        </button>

        {/* Move Up/Down */}
        <div className="flex flex-col gap-0.5">
          <button
            onClick={() => onMoveUp(index)}
            disabled={index === 0}
            className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-30 disabled:cursor-not-allowed"
            title="Monter"
          >
            <ChevronUpIcon />
          </button>
          <button
            onClick={() => onMoveDown(index)}
            disabled={index === totalCount - 1}
            className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-30 disabled:cursor-not-allowed"
            title="Descendre"
          >
            <ChevronDownIcon />
          </button>
        </div>

        {/* Expand Button */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
        >
          <svg className={`w-5 h-5 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {/* Expanded Settings */}
      {isExpanded && (
        <div className="px-4 pb-4 pt-2 border-t border-gray-100 bg-gray-50/50 rounded-b-lg">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Offline Toggle */}
            <div>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={module.offlineEnabled}
                  onChange={() => onToggleOffline(module.id)}
                  className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Disponible hors-ligne</span>
              </label>
              <p className="text-xs text-gray-500 mt-1 ml-7">
                Les donnees seront synchronisees localement
              </p>
            </div>

            {/* Sync Priority */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Priorite de synchronisation
              </label>
              <select
                value={module.syncPriority}
                onChange={(e) => onSyncPriorityChange(module.id, e.target.value as 'high' | 'medium' | 'low')}
                disabled={!module.offlineEnabled}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
              >
                <option value="high">Haute</option>
                <option value="medium">Moyenne</option>
                <option value="low">Basse</option>
              </select>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------
export function ModuleConfigurator({
  modules,
  availableModules,
  onChange,
}: ModuleConfiguratorProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [filter, setFilter] = useState<'all' | 'visible' | 'hidden'>('all');
  const [search, setSearch] = useState('');

  // Filter and search modules
  const filteredModules = modules
    .filter((m) => {
      if (filter === 'visible') return m.enabled;
      if (filter === 'hidden') return !m.enabled;
      return true;
    })
    .filter((m) =>
      m.name.toLowerCase().includes(search.toLowerCase())
    );

  // Handlers
  const handleToggleEnabled = useCallback((id: string) => {
    const updated = modules.map((m) =>
      m.id === id ? { ...m, enabled: !m.enabled } : m
    );
    onChange(updated);
  }, [modules, onChange]);

  const handleToggleOffline = useCallback((id: string) => {
    const updated = modules.map((m) =>
      m.id === id ? { ...m, offlineEnabled: !m.offlineEnabled } : m
    );
    onChange(updated);
  }, [modules, onChange]);

  const handleMoveUp = useCallback((index: number) => {
    if (index === 0) return;
    const updated = [...modules];
    [updated[index - 1], updated[index]] = [updated[index], updated[index - 1]];
    updated.forEach((m, i) => { m.order = i; });
    onChange(updated);
  }, [modules, onChange]);

  const handleMoveDown = useCallback((index: number) => {
    if (index === modules.length - 1) return;
    const updated = [...modules];
    [updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
    updated.forEach((m, i) => { m.order = i; });
    onChange(updated);
  }, [modules, onChange]);

  const handleDragStart = useCallback((index: number) => {
    setDragIndex(index);
  }, []);

  const handleDragEnter = useCallback((index: number) => {
    setDragOverIndex(index);
  }, []);

  const handleDragEnd = useCallback(() => {
    if (dragIndex !== null && dragOverIndex !== null && dragIndex !== dragOverIndex) {
      const updated = [...modules];
      const [removed] = updated.splice(dragIndex, 1);
      updated.splice(dragOverIndex, 0, removed);
      updated.forEach((m, i) => { m.order = i; });
      onChange(updated);
    }
    setDragIndex(null);
    setDragOverIndex(null);
  }, [dragIndex, dragOverIndex, modules, onChange]);

  const handleSyncPriorityChange = useCallback((id: string, priority: 'high' | 'medium' | 'low') => {
    const updated = modules.map((m) =>
      m.id === id ? { ...m, syncPriority: priority } : m
    );
    onChange(updated);
  }, [modules, onChange]);

  const handleShowAll = useCallback(() => {
    const updated = modules.map((m) => ({ ...m, enabled: true }));
    onChange(updated);
  }, [modules, onChange]);

  const handleHideAll = useCallback(() => {
    const updated = modules.map((m) => ({ ...m, enabled: false }));
    onChange(updated);
  }, [modules, onChange]);

  const visibleCount = modules.filter((m) => m.enabled).length;
  const hiddenCount = modules.filter((m) => !m.enabled).length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Modules</h3>
          <p className="text-sm text-gray-500">
            {visibleCount} visible{visibleCount > 1 ? 's' : ''}, {hiddenCount} masque{hiddenCount > 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleShowAll}
            className="px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50 rounded-lg"
          >
            Tout afficher
          </button>
          <button
            onClick={handleHideAll}
            className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
          >
            Tout masquer
          </button>
        </div>
      </div>

      {/* Search and Filter */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher un module..."
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          />
          <svg className="w-5 h-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <div className="flex rounded-lg border border-gray-300 overflow-hidden">
          {(['all', 'visible', 'hidden'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                filter === f
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-700 hover:bg-gray-50'
              }`}
            >
              {f === 'all' ? 'Tous' : f === 'visible' ? 'Visibles' : 'Masques'}
            </button>
          ))}
        </div>
      </div>

      {/* Module List */}
      <div className="space-y-2">
        {filteredModules.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            Aucun module trouve
          </div>
        ) : (
          filteredModules.map((module, index) => (
            <ModuleItem
              key={module.id}
              module={module}
              index={index}
              totalCount={filteredModules.length}
              isDragging={dragIndex === index}
              onToggleEnabled={handleToggleEnabled}
              onToggleOffline={handleToggleOffline}
              onMoveUp={handleMoveUp}
              onMoveDown={handleMoveDown}
              onDragStart={handleDragStart}
              onDragEnter={handleDragEnter}
              onDragEnd={handleDragEnd}
              onSyncPriorityChange={handleSyncPriorityChange}
            />
          ))
        )}
      </div>

      {/* Help Text */}
      <div className="p-4 bg-blue-50 rounded-lg border border-blue-100">
        <p className="text-sm text-blue-700">
          <strong>Astuce :</strong> Glissez-deposez les modules pour les reorganiser.
          L'ordre determine leur position dans le menu de l'application mobile.
        </p>
      </div>
    </div>
  );
}

export default ModuleConfigurator;
