import React from 'react';

export type ChangeType = 'up' | 'down' | 'neutral';

export interface StatCardProps {
  /** Metric title */
  title: string;
  /** Metric value (formatted string) */
  value: string;
  /** Change value (e.g., "+5%", "-2.3%") */
  change?: string;
  /** Change direction indicator */
  changeType?: ChangeType;
  /** Icon element (React node) */
  icon?: React.ReactNode;
  /** Card accent color */
  color?: 'primary' | 'success' | 'warning' | 'error' | 'neutral';
  /** Click handler for navigation */
  onClick?: () => void;
  /** Loading state */
  loading?: boolean;
}

const colorStyles = {
  primary: {
    bg: 'bg-primary-50',
    icon: 'bg-primary-100 text-primary-600',
    border: 'border-primary-100',
  },
  success: {
    bg: 'bg-green-50',
    icon: 'bg-green-100 text-green-600',
    border: 'border-green-100',
  },
  warning: {
    bg: 'bg-amber-50',
    icon: 'bg-amber-100 text-amber-600',
    border: 'border-amber-100',
  },
  error: {
    bg: 'bg-red-50',
    icon: 'bg-red-100 text-red-600',
    border: 'border-red-100',
  },
  neutral: {
    bg: 'bg-gray-50',
    icon: 'bg-gray-100 text-gray-600',
    border: 'border-gray-100',
  },
};

const changeTypeStyles: Record<ChangeType, { text: string; arrow: string }> = {
  up: {
    text: 'text-green-600',
    arrow: 'M5 10l7-7m0 0l7 7m-7-7v18', // Arrow up
  },
  down: {
    text: 'text-red-600',
    arrow: 'M19 14l-7 7m0 0l-7-7m7 7V3', // Arrow down
  },
  neutral: {
    text: 'text-gray-500',
    arrow: 'M5 12h14', // Horizontal line
  },
};

/**
 * Skeleton loader for StatCard
 */
const StatCardSkeleton: React.FC<{ color?: StatCardProps['color'] }> = ({
  color = 'primary',
}) => {
  const styles = colorStyles[color];

  return (
    <div
      className={`
        rounded-xl border p-4
        ${styles.bg} ${styles.border}
        animate-pulse
      `}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 space-y-2">
          <div className="h-4 w-20 bg-gray-200 rounded" />
          <div className="h-8 w-24 bg-gray-200 rounded" />
          <div className="h-3 w-16 bg-gray-200 rounded" />
        </div>
        <div className={`w-10 h-10 rounded-lg ${styles.icon} opacity-50`} />
      </div>
    </div>
  );
};

/**
 * StatCard - Metric display widget for dashboards.
 * Shows a key metric with optional trend indicator and icon.
 * Mobile-optimized with touch-friendly interactions.
 */
export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  change,
  changeType = 'neutral',
  icon,
  color = 'primary',
  onClick,
  loading = false,
}) => {
  if (loading) {
    return <StatCardSkeleton color={color} />;
  }

  const styles = colorStyles[color];
  const changeStyles = changeTypeStyles[changeType];
  const isClickable = !!onClick;

  const baseClasses = [
    'rounded-xl border p-4',
    styles.bg,
    styles.border,
    'transition-all duration-200',
  ];

  const clickableClasses = isClickable
    ? [
        'cursor-pointer',
        'active:scale-[0.98]',
        'hover:shadow-md',
        'touch-manipulation',
      ]
    : [];

  const classes = [...baseClasses, ...clickableClasses].join(' ');

  return (
    <div
      className={classes}
      onClick={onClick}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-600 truncate">{title}</p>
          <p className="mt-1 text-2xl font-bold text-gray-900 truncate">
            {value}
          </p>
          {change && (
            <div className={`mt-1 flex items-center text-sm ${changeStyles.text}`}>
              <svg
                className="w-4 h-4 mr-1"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d={changeStyles.arrow}
                />
              </svg>
              <span className="font-medium">{change}</span>
            </div>
          )}
        </div>
        {icon && (
          <div
            className={`
              flex-shrink-0 w-10 h-10 rounded-lg
              flex items-center justify-center
              ${styles.icon}
            `}
          >
            {icon}
          </div>
        )}
      </div>
    </div>
  );
};

StatCard.displayName = 'StatCard';

export default StatCard;
