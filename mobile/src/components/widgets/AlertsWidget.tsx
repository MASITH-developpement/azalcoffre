import React from 'react';

export type AlertPriority = 'high' | 'medium' | 'low';

export interface AlertItem {
  /** Unique identifier */
  id: string;
  /** Alert priority level */
  priority: AlertPriority;
  /** Alert title */
  title: string;
  /** Alert message/description */
  message?: string;
  /** Timestamp display string */
  timestamp?: string;
  /** Additional metadata */
  meta?: Record<string, unknown>;
}

export interface AlertsWidgetProps {
  /** List of alerts to display */
  alerts: AlertItem[];
  /** Handler when an alert is dismissed */
  onDismiss?: (alert: AlertItem) => void;
  /** Handler when an alert is clicked */
  onAlertClick?: (alert: AlertItem) => void;
  /** Maximum alerts to display (default: 5) */
  maxAlerts?: number;
  /** Loading state */
  loading?: boolean;
  /** Widget title */
  title?: string;
  /** Empty state message */
  emptyMessage?: string;
}

const priorityStyles: Record<
  AlertPriority,
  { bg: string; border: string; icon: string; dot: string }
> = {
  high: {
    bg: 'bg-red-50',
    border: 'border-red-200',
    icon: 'text-red-500',
    dot: 'bg-red-500',
  },
  medium: {
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    icon: 'text-amber-500',
    dot: 'bg-amber-500',
  },
  low: {
    bg: 'bg-primary-50',
    border: 'border-primary-200',
    icon: 'text-primary-500',
    dot: 'bg-primary-500',
  },
};

const priorityIcons: Record<AlertPriority, React.ReactNode> = {
  high: (
    <svg
      className="w-5 h-5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
      />
    </svg>
  ),
  medium: (
    <svg
      className="w-5 h-5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  ),
  low: (
    <svg
      className="w-5 h-5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
      />
    </svg>
  ),
};

/**
 * Skeleton loader for alerts
 */
const AlertSkeleton: React.FC = () => (
  <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 border border-gray-100 animate-pulse">
    <div className="w-5 h-5 bg-gray-200 rounded" />
    <div className="flex-1 space-y-2">
      <div className="h-4 w-32 bg-gray-200 rounded" />
      <div className="h-3 w-48 bg-gray-200 rounded" />
    </div>
    <div className="w-6 h-6 bg-gray-200 rounded" />
  </div>
);

/**
 * Empty state component
 */
const EmptyState: React.FC<{ message: string }> = ({ message }) => (
  <div className="py-8 text-center">
    <svg
      className="w-12 h-12 mx-auto text-gray-300"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
    <p className="mt-3 text-sm text-gray-500">{message}</p>
  </div>
);

/**
 * Single alert item
 */
const AlertItemComponent: React.FC<{
  alert: AlertItem;
  onDismiss?: () => void;
  onClick?: () => void;
}> = ({ alert, onDismiss, onClick }) => {
  const styles = priorityStyles[alert.priority];
  const icon = priorityIcons[alert.priority];

  return (
    <div
      className={`
        flex items-start gap-3 p-3 rounded-lg
        ${styles.bg} ${styles.border} border
        transition-all duration-200
      `}
    >
      {/* Priority icon */}
      <div className={`flex-shrink-0 ${styles.icon}`}>{icon}</div>

      {/* Content */}
      <button
        type="button"
        onClick={onClick}
        disabled={!onClick}
        className={`
          flex-1 min-w-0 text-left
          ${onClick ? 'cursor-pointer' : ''}
        `}
      >
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-gray-900 truncate">
            {alert.title}
          </p>
          {/* Priority dot indicator */}
          <span
            className={`w-2 h-2 rounded-full flex-shrink-0 ${styles.dot}`}
            aria-label={`Priorite ${alert.priority}`}
          />
        </div>
        {alert.message && (
          <p className="mt-0.5 text-sm text-gray-600 line-clamp-2">
            {alert.message}
          </p>
        )}
        {alert.timestamp && (
          <p className="mt-1 text-xs text-gray-400">{alert.timestamp}</p>
        )}
      </button>

      {/* Dismiss button */}
      {onDismiss && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDismiss();
          }}
          className="
            flex-shrink-0 p-1 rounded
            text-gray-400 hover:text-gray-600
            hover:bg-white/50 active:bg-white/80
            transition-colors duration-150
            touch-manipulation
          "
          aria-label="Fermer l'alerte"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      )}
    </div>
  );
};

/**
 * AlertsWidget - Notifications/alerts list for dashboards.
 * Displays priority-based alerts with dismiss capability.
 * Mobile-optimized with touch-friendly interactions.
 */
export const AlertsWidget: React.FC<AlertsWidgetProps> = ({
  alerts,
  onDismiss,
  onAlertClick,
  maxAlerts = 5,
  loading = false,
  title = 'Alertes',
  emptyMessage = 'Aucune alerte',
}) => {
  const displayAlerts = alerts.slice(0, maxAlerts);
  const alertCount = alerts.length;

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold text-gray-900">{title}</h3>
          {alertCount > 0 && (
            <span className="px-2 py-0.5 text-xs font-medium bg-red-100 text-red-700 rounded-full">
              {alertCount}
            </span>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <AlertSkeleton key={i} />
            ))}
          </div>
        ) : displayAlerts.length === 0 ? (
          <EmptyState message={emptyMessage} />
        ) : (
          <div className="space-y-3">
            {displayAlerts.map((alert) => (
              <AlertItemComponent
                key={alert.id}
                alert={alert}
                {...(onDismiss ? { onDismiss: () => onDismiss(alert) } : {})}
                {...(onAlertClick ? { onClick: () => onAlertClick(alert) } : {})}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

AlertsWidget.displayName = 'AlertsWidget';

export default AlertsWidget;
