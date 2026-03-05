import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../core/auth/useAuth';
import { useMobileConfig } from '../core/config/MobileConfigProvider';
import { Icon } from '../components/ui/Icon';

interface DashboardPageProps {
  showModulesOnly?: boolean;
}

export default function DashboardPage({ showModulesOnly = false }: DashboardPageProps): React.ReactElement {
  const { user } = useAuth();
  const { config, isLoading, getEnabledModules } = useMobileConfig();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="spinner" />
      </div>
    );
  }

  // Use getEnabledModules to respect hidden modules settings
  const enabledModules = getEnabledModules();

  // Show only modules grid
  if (showModulesOnly) {
    return (
      <div className="p-4">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {enabledModules.map((module) => (
            <Link
              key={module.id}
              to={`/module/${module.id}`}
              className="card p-4 flex flex-col items-center gap-3 active:scale-95 transition-transform"
            >
              <div className="w-12 h-12 rounded-xl bg-primary-50 flex items-center justify-center">
                <Icon name={module.icon || 'default'} size={28} />
              </div>
              <div className="text-center">
                <h3 className="font-medium text-gray-900 text-sm truncate max-w-full">
                  {module.displayName || module.name}
                </h3>
                {module.badge && (
                  <span className="badge badge-primary mt-1">{module.badge}</span>
                )}
              </div>
            </Link>
          ))}
        </div>

        {enabledModules.length === 0 && (
          <div className="empty-state">
            <p className="text-gray-500">Aucun module disponible</p>
          </div>
        )}
      </div>
    );
  }

  // Full dashboard view
  return (
    <div className="p-4 space-y-6">
      {/* Welcome message (visible on small screens) */}
      <div className="sm:hidden">
        <p className="text-sm text-gray-500">{config?.company.name}</p>
      </div>

      {/* Quick Actions */}
      {config?.quickActions && config.quickActions.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-gray-500 mb-3">Actions rapides</h2>
          <div className="grid grid-cols-4 gap-2 sm:gap-3">
            {config.quickActions.slice(0, 4).map((action) => (
              <Link
                key={action.id}
                to={action.route}
                className="flex flex-col items-center p-2 sm:p-3 rounded-xl bg-white border border-gray-100 active:scale-95 transition-transform"
              >
                <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-primary-50 flex items-center justify-center mb-1 sm:mb-2">
                  <Icon name={action.icon || 'default'} size={24} />
                </div>
                <span className="text-xs text-gray-600 text-center line-clamp-2">
                  {action.label}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Dashboard Widgets */}
      {config?.dashboardWidgets && config.dashboardWidgets.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-gray-500 mb-3">Tableau de bord</h2>
          <div className="space-y-3">
            {config.dashboardWidgets.map((widget) => (
              <div key={widget.id} className="card p-4">
                <h3 className="font-medium text-gray-900">{widget.title}</h3>
                <p className="text-sm text-gray-500 mt-1">Widget: {widget.type}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Modules Grid */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-gray-500">Modules</h2>
          {enabledModules.length > 6 && (
            <Link to="/modules" className="text-sm text-primary-600 font-medium">
              Voir tout
            </Link>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {enabledModules.slice(0, 6).map((module) => (
            <Link
              key={module.id}
              to={`/module/${module.id}`}
              className="card p-3 sm:p-4 flex items-center gap-3 active:scale-95 transition-transform"
            >
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-lg bg-primary-50 flex items-center justify-center flex-shrink-0">
                <Icon name={module.icon || 'default'} size={24} />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-medium text-gray-900 text-sm truncate">
                  {module.displayName || module.name}
                </h3>
                {module.badge && (
                  <span className="badge badge-primary text-xs">{module.badge}</span>
                )}
              </div>
            </Link>
          ))}
        </div>

        {enabledModules.length === 0 && (
          <div className="card p-6 text-center">
            <p className="text-gray-500">Aucun module configure</p>
          </div>
        )}
      </section>
    </div>
  );
}
