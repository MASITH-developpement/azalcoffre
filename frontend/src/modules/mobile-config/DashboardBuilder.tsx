// AZALPLUS - Dashboard Builder Component
// Configure dashboard widgets for mobile app

import React, { useState, useCallback } from 'react';
import type { DashboardWidget, DashboardBuilderProps, WidgetType, ChartType } from './types';
import { PRESET_COLORS } from './types';

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

const ChartBarIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
  </svg>
);

const ListIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
  </svg>
);

const HashIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14" />
  </svg>
);

const CalendarIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
  </svg>
);

const CheckIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const widgetTypeIcons: Record<WidgetType, React.ReactNode> = {
  stat: <HashIcon />,
  list: <ListIcon />,
  chart: <ChartBarIcon />,
  calendar: <CalendarIcon />,
  tasks: <CheckIcon />,
};

const widgetTypeLabels: Record<WidgetType, string> = {
  stat: 'Statistique',
  list: 'Liste',
  chart: 'Graphique',
  calendar: 'Calendrier',
  tasks: 'Taches',
};

const chartTypeLabels: Record<ChartType, string> = {
  line: 'Ligne',
  bar: 'Barres',
  pie: 'Camembert',
  donut: 'Anneau',
};

// -----------------------------------------------------------------------------
// Widget Card Component
// -----------------------------------------------------------------------------
interface WidgetCardProps {
  widget: DashboardWidget;
  availableModules: Array<{ id: string; name: string }>;
  onUpdate: (widget: DashboardWidget) => void;
  onDelete: (id: string) => void;
  onDragStart: (index: number) => void;
  onDragEnter: (index: number) => void;
  onDragEnd: () => void;
  index: number;
  isDragging: boolean;
}

const WidgetCard: React.FC<WidgetCardProps> = ({
  widget,
  availableModules,
  onUpdate,
  onDelete,
  onDragStart,
  onDragEnter,
  onDragEnd,
  index,
  isDragging,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleFieldChange = <K extends keyof DashboardWidget>(
    field: K,
    value: DashboardWidget[K]
  ) => {
    onUpdate({ ...widget, [field]: value });
  };

  const handleDataSourceChange = <K extends keyof DashboardWidget['dataSource']>(
    field: K,
    value: DashboardWidget['dataSource'][K]
  ) => {
    onUpdate({
      ...widget,
      dataSource: { ...widget.dataSource, [field]: value },
    });
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
      {/* Header */}
      <div className="flex items-center gap-3 p-4 bg-gray-50 border-b border-gray-100">
        <div className="cursor-grab active:cursor-grabbing">
          <GripIcon />
        </div>

        <div
          className="p-2 rounded-lg"
          style={{ backgroundColor: widget.color ? `${widget.color}20` : '#e0e7ff' }}
        >
          <span style={{ color: widget.color || '#4f46e5' }}>
            {widgetTypeIcons[widget.type]}
          </span>
        </div>

        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-gray-900 truncate">{widget.title || 'Sans titre'}</h4>
          <p className="text-xs text-gray-500">{widgetTypeLabels[widget.type]} - {widget.size}</p>
        </div>

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
        >
          <svg className={`w-5 h-5 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        <button
          onClick={() => onDelete(widget.id)}
          className="p-2 text-red-400 hover:text-red-600 rounded-lg hover:bg-red-50"
          title="Supprimer"
        >
          <TrashIcon />
        </button>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="p-4 space-y-4">
          {/* Basic Settings */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Titre
              </label>
              <input
                type="text"
                value={widget.title}
                onChange={(e) => handleFieldChange('title', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Titre du widget"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Type
              </label>
              <select
                value={widget.type}
                onChange={(e) => handleFieldChange('type', e.target.value as WidgetType)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                {Object.entries(widgetTypeLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Taille
              </label>
              <select
                value={widget.size}
                onChange={(e) => handleFieldChange('size', e.target.value as 'small' | 'medium' | 'large')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="small">Petit</option>
                <option value="medium">Moyen</option>
                <option value="large">Grand</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Couleur
              </label>
              <div className="flex flex-wrap gap-2">
                {PRESET_COLORS.map((color) => (
                  <button
                    key={color}
                    onClick={() => handleFieldChange('color', color)}
                    className={`w-8 h-8 rounded-lg border-2 transition-all ${
                      widget.color === color ? 'border-gray-900 scale-110' : 'border-transparent'
                    }`}
                    style={{ backgroundColor: color }}
                    title={color}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Chart Type (only for chart widgets) */}
          {widget.type === 'chart' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Type de graphique
              </label>
              <div className="flex flex-wrap gap-2">
                {Object.entries(chartTypeLabels).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => handleFieldChange('chartType', value as ChartType)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      widget.chartType === value
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Data Source */}
          <div className="pt-4 border-t border-gray-100">
            <h5 className="text-sm font-medium text-gray-700 mb-3">Source de donnees</h5>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  Module
                </label>
                <select
                  value={widget.dataSource.module}
                  onChange={(e) => handleDataSourceChange('module', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Selectionner...</option>
                  {availableModules.map((m) => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))}
                </select>
              </div>

              {(widget.type === 'stat' || widget.type === 'chart') && (
                <>
                  <div>
                    <label className="block text-sm text-gray-600 mb-1">
                      Agregation
                    </label>
                    <select
                      value={widget.dataSource.aggregation || 'count'}
                      onChange={(e) => handleDataSourceChange('aggregation', e.target.value as 'count' | 'sum' | 'avg' | 'min' | 'max')}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="count">Compter</option>
                      <option value="sum">Somme</option>
                      <option value="avg">Moyenne</option>
                      <option value="min">Minimum</option>
                      <option value="max">Maximum</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm text-gray-600 mb-1">
                      Champ (pour somme/moyenne)
                    </label>
                    <input
                      type="text"
                      value={widget.dataSource.field || ''}
                      onChange={(e) => handleDataSourceChange('field', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                      placeholder="ex: montant_ttc"
                    />
                  </div>
                </>
              )}

              {widget.type === 'list' && (
                <div>
                  <label className="block text-sm text-gray-600 mb-1">
                    Limite d'elements
                  </label>
                  <input
                    type="number"
                    value={widget.dataSource.limit || 5}
                    onChange={(e) => handleDataSourceChange('limit', parseInt(e.target.value))}
                    min={1}
                    max={20}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  Rafraichissement (secondes)
                </label>
                <input
                  type="number"
                  value={widget.refreshInterval || 300}
                  onChange={(e) => handleFieldChange('refreshInterval', parseInt(e.target.value))}
                  min={30}
                  max={3600}
                  step={30}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// -----------------------------------------------------------------------------
// Add Widget Modal
// -----------------------------------------------------------------------------
interface AddWidgetModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (widget: DashboardWidget) => void;
  availableModules: Array<{ id: string; name: string }>;
}

const AddWidgetModal: React.FC<AddWidgetModalProps> = ({
  isOpen,
  onClose,
  onAdd,
  availableModules,
}) => {
  const [selectedType, setSelectedType] = useState<WidgetType>('stat');

  if (!isOpen) return null;

  const handleAdd = () => {
    const newWidget: DashboardWidget = {
      id: `widget-${Date.now()}`,
      type: selectedType,
      title: `Nouveau ${widgetTypeLabels[selectedType]}`,
      dataSource: {
        module: availableModules[0]?.id || '',
        aggregation: 'count',
        limit: 5,
      },
      size: 'medium',
      order: 999,
      color: PRESET_COLORS[0],
      refreshInterval: 300,
      chartType: selectedType === 'chart' ? 'bar' : undefined,
    };
    onAdd(newWidget);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-white rounded-xl shadow-xl max-w-md w-full mx-4 p-6">
        <h3 className="text-lg font-semibold mb-4">Ajouter un widget</h3>

        <div className="grid grid-cols-2 gap-3 mb-6">
          {Object.entries(widgetTypeLabels).map(([type, label]) => (
            <button
              key={type}
              onClick={() => setSelectedType(type as WidgetType)}
              className={`flex items-center gap-3 p-4 rounded-lg border-2 transition-all ${
                selectedType === type
                  ? 'border-blue-600 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <span className={selectedType === type ? 'text-blue-600' : 'text-gray-400'}>
                {widgetTypeIcons[type as WidgetType]}
              </span>
              <span className={`font-medium ${selectedType === type ? 'text-blue-600' : 'text-gray-700'}`}>
                {label}
              </span>
            </button>
          ))}
        </div>

        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            Annuler
          </button>
          <button
            onClick={handleAdd}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Ajouter
          </button>
        </div>
      </div>
    </div>
  );
};

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------
export function DashboardBuilder({
  widgets,
  availableModules,
  onChange,
}: DashboardBuilderProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);

  const handleAddWidget = useCallback((widget: DashboardWidget) => {
    const updated = [...widgets, { ...widget, order: widgets.length }];
    onChange(updated);
  }, [widgets, onChange]);

  const handleUpdateWidget = useCallback((widget: DashboardWidget) => {
    const updated = widgets.map((w) => (w.id === widget.id ? widget : w));
    onChange(updated);
  }, [widgets, onChange]);

  const handleDeleteWidget = useCallback((id: string) => {
    const updated = widgets.filter((w) => w.id !== id);
    updated.forEach((w, i) => { w.order = i; });
    onChange(updated);
  }, [widgets, onChange]);

  const handleDragStart = useCallback((index: number) => {
    setDragIndex(index);
  }, []);

  const handleDragEnter = useCallback((index: number) => {
    setDragOverIndex(index);
  }, []);

  const handleDragEnd = useCallback(() => {
    if (dragIndex !== null && dragOverIndex !== null && dragIndex !== dragOverIndex) {
      const updated = [...widgets];
      const [removed] = updated.splice(dragIndex, 1);
      updated.splice(dragOverIndex, 0, removed);
      updated.forEach((w, i) => { w.order = i; });
      onChange(updated);
    }
    setDragIndex(null);
    setDragOverIndex(null);
  }, [dragIndex, dragOverIndex, widgets, onChange]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Widgets du tableau de bord</h3>
          <p className="text-sm text-gray-500">
            {widgets.length} widget{widgets.length > 1 ? 's' : ''} configure{widgets.length > 1 ? 's' : ''}
          </p>
        </div>
        <button
          onClick={() => setIsAddModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <PlusIcon />
          Ajouter
        </button>
      </div>

      {/* Widget List */}
      {widgets.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-xl border-2 border-dashed border-gray-200">
          <div className="p-4 bg-gray-100 rounded-full w-16 h-16 mx-auto mb-4 flex items-center justify-center">
            <ChartBarIcon />
          </div>
          <h4 className="text-gray-900 font-medium mb-2">Aucun widget</h4>
          <p className="text-gray-500 text-sm mb-4">
            Ajoutez des widgets pour personnaliser le tableau de bord mobile
          </p>
          <button
            onClick={() => setIsAddModalOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <PlusIcon />
            Ajouter un widget
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {widgets.map((widget, index) => (
            <WidgetCard
              key={widget.id}
              widget={widget}
              availableModules={availableModules}
              onUpdate={handleUpdateWidget}
              onDelete={handleDeleteWidget}
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
      <div className="p-4 bg-blue-50 rounded-lg border border-blue-100">
        <p className="text-sm text-blue-700">
          <strong>Astuce :</strong> Les widgets s'affichent dans l'ordre configure sur le tableau de bord mobile.
          Glissez-deposez pour reorganiser.
        </p>
      </div>

      {/* Add Widget Modal */}
      <AddWidgetModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onAdd={handleAddWidget}
        availableModules={availableModules}
      />
    </div>
  );
}

export default DashboardBuilder;
