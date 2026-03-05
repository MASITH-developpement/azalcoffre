// AZALPLUS - Quick Actions Editor Component
// Configure quick actions for FAB menu on mobile

import React, { useState, useCallback } from 'react';
import type { QuickAction, QuickActionsEditorProps } from './types';
import { PRESET_COLORS, AVAILABLE_ICONS } from './types';

// -----------------------------------------------------------------------------
// Icons
// -----------------------------------------------------------------------------
const PlusIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
  </svg>
);

const TrashIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
);

const GripIcon = () => (
  <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8h16M4 16h16" />
  </svg>
);

const PencilIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
  </svg>
);

// Icon mapping for display
const iconComponents: Record<string, React.ReactNode> = {
  plus: <PlusIcon />,
  search: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
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
  calendar: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  ),
  camera: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
  phone: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
    </svg>
  ),
  mail: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  ),
  'map-pin': (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
  check: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
    </svg>
  ),
  star: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
    </svg>
  ),
  default: (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  ),
};

const getIcon = (iconName: string) => iconComponents[iconName] || iconComponents.default;

const actionTypeLabels: Record<string, string> = {
  create: 'Creer',
  list: 'Liste',
  search: 'Rechercher',
  custom: 'Personnalise',
};

// -----------------------------------------------------------------------------
// Action Card Component
// -----------------------------------------------------------------------------
interface ActionCardProps {
  action: QuickAction;
  availableModules: Array<{ id: string; name: string }>;
  onUpdate: (action: QuickAction) => void;
  onDelete: (id: string) => void;
  onDragStart: (index: number) => void;
  onDragEnter: (index: number) => void;
  onDragEnd: () => void;
  index: number;
  isDragging: boolean;
}

const ActionCard: React.FC<ActionCardProps> = ({
  action,
  availableModules,
  onUpdate,
  onDelete,
  onDragStart,
  onDragEnter,
  onDragEnd,
  index,
  isDragging,
}) => {
  const [isEditing, setIsEditing] = useState(false);

  const handleFieldChange = <K extends keyof QuickAction>(
    field: K,
    value: QuickAction[K]
  ) => {
    onUpdate({ ...action, [field]: value });
  };

  return (
    <div
      draggable
      onDragStart={() => onDragStart(index)}
      onDragEnter={() => onDragEnter(index)}
      onDragEnd={onDragEnd}
      onDragOver={(e) => e.preventDefault()}
      className={`
        bg-white border rounded-xl overflow-hidden transition-all
        ${isDragging ? 'opacity-50 border-blue-400 shadow-lg' : 'border-gray-200'}
      `}
    >
      {/* Preview Row */}
      <div className="flex items-center gap-3 p-4">
        <div className="cursor-grab active:cursor-grabbing">
          <GripIcon />
        </div>

        {/* Action Preview (FAB Style) */}
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center text-white shadow-md"
          style={{ backgroundColor: action.color }}
        >
          {getIcon(action.icon)}
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-gray-900 truncate">{action.label}</h4>
          <p className="text-xs text-gray-500">
            {actionTypeLabels[action.action]} - {availableModules.find(m => m.id === action.targetModule)?.name || action.targetModule}
          </p>
        </div>

        <button
          onClick={() => setIsEditing(!isEditing)}
          className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
          title="Modifier"
        >
          <PencilIcon />
        </button>

        <button
          onClick={() => onDelete(action.id)}
          className="p-2 text-red-400 hover:text-red-600 rounded-lg hover:bg-red-50"
          title="Supprimer"
        >
          <TrashIcon />
        </button>
      </div>

      {/* Edit Form */}
      {isEditing && (
        <div className="p-4 border-t border-gray-100 bg-gray-50 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Label
              </label>
              <input
                type="text"
                value={action.label}
                onChange={(e) => handleFieldChange('label', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Nouveau client"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Action
              </label>
              <select
                value={action.action}
                onChange={(e) => handleFieldChange('action', e.target.value as QuickAction['action'])}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                {Object.entries(actionTypeLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Module cible
              </label>
              <select
                value={action.targetModule}
                onChange={(e) => handleFieldChange('targetModule', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Selectionner...</option>
                {availableModules.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>

            {action.action === 'custom' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Route personnalisee
                </label>
                <input
                  type="text"
                  value={action.customRoute || ''}
                  onChange={(e) => handleFieldChange('customRoute', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="/custom/route"
                />
              </div>
            )}
          </div>

          {/* Icon Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Icone
            </label>
            <div className="flex flex-wrap gap-2">
              {Object.keys(iconComponents).filter(k => k !== 'default').map((iconName) => (
                <button
                  key={iconName}
                  onClick={() => handleFieldChange('icon', iconName)}
                  className={`p-2 rounded-lg border-2 transition-all ${
                    action.icon === iconName
                      ? 'border-blue-600 bg-blue-50 text-blue-600'
                      : 'border-gray-200 text-gray-500 hover:border-gray-300'
                  }`}
                  title={iconName}
                >
                  {getIcon(iconName)}
                </button>
              ))}
            </div>
          </div>

          {/* Color Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Couleur
            </label>
            <div className="flex flex-wrap gap-2">
              {PRESET_COLORS.map((color) => (
                <button
                  key={color}
                  onClick={() => handleFieldChange('color', color)}
                  className={`w-10 h-10 rounded-full border-2 transition-all ${
                    action.color === color ? 'border-gray-900 scale-110' : 'border-transparent'
                  }`}
                  style={{ backgroundColor: color }}
                  title={color}
                />
              ))}
            </div>
          </div>

          <div className="flex justify-end">
            <button
              onClick={() => setIsEditing(false)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Terminer
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------
export function QuickActionsEditor({
  actions,
  availableModules,
  onChange,
  maxActions = 5,
}: QuickActionsEditorProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  const handleAddAction = useCallback(() => {
    if (actions.length >= maxActions) return;

    const newAction: QuickAction = {
      id: `action-${Date.now()}`,
      label: 'Nouvelle action',
      icon: 'plus',
      color: PRESET_COLORS[actions.length % PRESET_COLORS.length],
      targetModule: availableModules[0]?.id || '',
      action: 'create',
      order: actions.length,
    };
    onChange([...actions, newAction]);
  }, [actions, availableModules, maxActions, onChange]);

  const handleUpdateAction = useCallback((action: QuickAction) => {
    const updated = actions.map((a) => (a.id === action.id ? action : a));
    onChange(updated);
  }, [actions, onChange]);

  const handleDeleteAction = useCallback((id: string) => {
    const updated = actions.filter((a) => a.id !== id);
    updated.forEach((a, i) => { a.order = i; });
    onChange(updated);
  }, [actions, onChange]);

  const handleDragStart = useCallback((index: number) => {
    setDragIndex(index);
  }, []);

  const handleDragEnter = useCallback((index: number) => {
    setDragOverIndex(index);
  }, []);

  const handleDragEnd = useCallback(() => {
    if (dragIndex !== null && dragOverIndex !== null && dragIndex !== dragOverIndex) {
      const updated = [...actions];
      const [removed] = updated.splice(dragIndex, 1);
      updated.splice(dragOverIndex, 0, removed);
      updated.forEach((a, i) => { a.order = i; });
      onChange(updated);
    }
    setDragIndex(null);
    setDragOverIndex(null);
  }, [dragIndex, dragOverIndex, actions, onChange]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Actions rapides</h3>
          <p className="text-sm text-gray-500">
            {actions.length} / {maxActions} actions configurees
          </p>
        </div>
        <button
          onClick={handleAddAction}
          disabled={actions.length >= maxActions}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <PlusIcon />
          Ajouter
        </button>
      </div>

      {/* FAB Preview */}
      <div className="bg-gradient-to-br from-gray-800 to-gray-900 rounded-xl p-6">
        <p className="text-gray-400 text-sm mb-4 text-center">Apercu du menu FAB</p>
        <div className="flex justify-center items-end gap-4">
          {actions.map((action, index) => (
            <div
              key={action.id}
              className="flex flex-col items-center"
              style={{ transform: `translateY(${index % 2 === 0 ? -10 : 0}px)` }}
            >
              <div
                className="w-12 h-12 rounded-full flex items-center justify-center text-white shadow-lg transition-transform hover:scale-110"
                style={{ backgroundColor: action.color }}
              >
                {getIcon(action.icon)}
              </div>
              <span className="text-xs text-gray-400 mt-2 text-center max-w-[60px] truncate">
                {action.label}
              </span>
            </div>
          ))}
          {actions.length === 0 && (
            <div className="text-gray-500 text-center py-4">
              Aucune action configuree
            </div>
          )}
        </div>
      </div>

      {/* Action List */}
      {actions.length > 0 && (
        <div className="space-y-3">
          {actions.map((action, index) => (
            <ActionCard
              key={action.id}
              action={action}
              availableModules={availableModules}
              onUpdate={handleUpdateAction}
              onDelete={handleDeleteAction}
              onDragStart={handleDragStart}
              onDragEnter={handleDragEnter}
              onDragEnd={handleDragEnd}
              index={index}
              isDragging={dragIndex === index}
            />
          ))}
        </div>
      )}

      {/* Help Text */}
      <div className="p-4 bg-amber-50 rounded-lg border border-amber-100">
        <p className="text-sm text-amber-700">
          <strong>Note :</strong> Les actions rapides apparaissent dans le bouton flottant (FAB) de l'application mobile.
          Maximum {maxActions} actions pour une bonne ergonomie.
        </p>
      </div>
    </div>
  );
}

export default QuickActionsEditor;
