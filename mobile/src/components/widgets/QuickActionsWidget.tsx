import React from 'react';

export interface QuickAction {
  /** Unique identifier */
  id: string;
  /** Action icon (React node) */
  icon: React.ReactNode;
  /** Action label */
  label: string;
  /** Action color */
  color?: 'primary' | 'success' | 'warning' | 'error' | 'neutral';
  /** Whether the action is disabled */
  disabled?: boolean;
}

export interface QuickActionsWidgetProps {
  /** List of actions to display */
  actions: QuickAction[];
  /** Handler when an action is clicked */
  onActionClick?: (action: QuickAction) => void;
  /** Number of columns (default: 2) */
  columns?: 2 | 3 | 4;
  /** Loading state */
  loading?: boolean;
  /** Widget title (optional) */
  title?: string;
}

const colorStyles = {
  primary: {
    bg: 'bg-primary-50 hover:bg-primary-100 active:bg-primary-200',
    icon: 'text-primary-600',
    text: 'text-primary-700',
  },
  success: {
    bg: 'bg-green-50 hover:bg-green-100 active:bg-green-200',
    icon: 'text-green-600',
    text: 'text-green-700',
  },
  warning: {
    bg: 'bg-amber-50 hover:bg-amber-100 active:bg-amber-200',
    icon: 'text-amber-600',
    text: 'text-amber-700',
  },
  error: {
    bg: 'bg-red-50 hover:bg-red-100 active:bg-red-200',
    icon: 'text-red-600',
    text: 'text-red-700',
  },
  neutral: {
    bg: 'bg-gray-50 hover:bg-gray-100 active:bg-gray-200',
    icon: 'text-gray-600',
    text: 'text-gray-700',
  },
};

/**
 * Skeleton loader for action buttons
 */
const ActionSkeleton: React.FC = () => (
  <div className="flex flex-col items-center p-4 rounded-xl bg-gray-50 animate-pulse">
    <div className="w-10 h-10 bg-gray-200 rounded-lg" />
    <div className="mt-2 h-3 w-16 bg-gray-200 rounded" />
  </div>
);

/**
 * Single action button
 */
const ActionButton: React.FC<{
  action: QuickAction;
  onClick?: () => void;
}> = ({ action, onClick }) => {
  const styles = colorStyles[action.color || 'primary'];
  const isDisabled = action.disabled;

  return (
    <button
      type="button"
      onClick={() => !isDisabled && onClick?.()}
      disabled={isDisabled}
      className={`
        flex flex-col items-center justify-center
        p-4 rounded-xl
        transition-all duration-200
        touch-manipulation
        min-h-[88px]
        ${isDisabled ? 'bg-gray-100 opacity-50 cursor-not-allowed' : styles.bg}
        active:scale-[0.97]
      `}
    >
      <div
        className={`
          w-10 h-10 rounded-lg
          flex items-center justify-center
          ${isDisabled ? 'text-gray-400' : styles.icon}
        `}
      >
        {action.icon}
      </div>
      <span
        className={`
          mt-2 text-sm font-medium text-center
          ${isDisabled ? 'text-gray-400' : styles.text}
          line-clamp-2
        `}
      >
        {action.label}
      </span>
    </button>
  );
};

/**
 * QuickActionsWidget - Grid of quick action buttons for dashboards.
 * Supports 2x2, 3x2, or 4x2 grid layouts.
 * Mobile-optimized with large touch targets.
 */
export const QuickActionsWidget: React.FC<QuickActionsWidgetProps> = ({
  actions,
  onActionClick,
  columns = 2,
  loading = false,
  title,
}) => {
  const gridCols = {
    2: 'grid-cols-2',
    3: 'grid-cols-3',
    4: 'grid-cols-4',
  };

  const content = loading ? (
    <div className={`grid ${gridCols[columns]} gap-3`}>
      {Array.from({ length: columns * 2 }).map((_, i) => (
        <ActionSkeleton key={i} />
      ))}
    </div>
  ) : (
    <div className={`grid ${gridCols[columns]} gap-3`}>
      {actions.map((action) => (
        <ActionButton
          key={action.id}
          action={action}
          onClick={() => onActionClick?.(action)}
        />
      ))}
    </div>
  );

  if (title) {
    return (
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100">
          <h3 className="text-base font-semibold text-gray-900">{title}</h3>
        </div>
        <div className="p-4">{content}</div>
      </div>
    );
  }

  return content;
};

QuickActionsWidget.displayName = 'QuickActionsWidget';

export default QuickActionsWidget;
