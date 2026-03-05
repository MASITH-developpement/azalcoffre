import React from 'react';

export type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral';
export type BadgeSize = 'sm' | 'md' | 'lg';

export interface BadgeProps {
  /** Badge visual variant/color */
  variant?: BadgeVariant;
  /** Badge size */
  size?: BadgeSize;
  /** Badge content */
  children: React.ReactNode;
  /** Optional left icon */
  icon?: React.ReactNode;
  /** Make badge pill-shaped (fully rounded) */
  pill?: boolean;
  /** Additional CSS classes */
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  success: 'bg-green-100 text-green-800 border-green-200',
  warning: 'bg-amber-100 text-amber-800 border-amber-200',
  error: 'bg-red-100 text-red-800 border-red-200',
  info: 'bg-primary-100 text-primary-800 border-primary-200',
  neutral: 'bg-gray-100 text-gray-800 border-gray-200',
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-sm',
  lg: 'px-3 py-1.5 text-base',
};

/**
 * Badge component for status indicators and labels.
 * Supports multiple color variants and sizes.
 */
export const Badge: React.FC<BadgeProps> = ({
  variant = 'neutral',
  size = 'md',
  children,
  icon,
  pill = false,
  className = '',
}) => {
  const baseStyles = [
    'inline-flex items-center',
    'font-medium',
    'border',
    'whitespace-nowrap',
  ].join(' ');

  const roundedStyle = pill ? 'rounded-full' : 'rounded-md';

  const classes = [
    baseStyles,
    variantStyles[variant],
    sizeStyles[size],
    roundedStyle,
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <span className={classes}>
      {icon && <span className="mr-1 flex-shrink-0">{icon}</span>}
      {children}
    </span>
  );
};

Badge.displayName = 'Badge';

/**
 * Dot indicator for inline status display.
 */
export const StatusDot: React.FC<{
  variant?: BadgeVariant;
  className?: string;
}> = ({ variant = 'neutral', className = '' }) => {
  const dotColors: Record<BadgeVariant, string> = {
    success: 'bg-green-500',
    warning: 'bg-amber-500',
    error: 'bg-red-500',
    info: 'bg-primary-500',
    neutral: 'bg-gray-500',
  };

  const classes = ['w-2 h-2 rounded-full', dotColors[variant], className]
    .filter(Boolean)
    .join(' ');

  return <span className={classes} aria-hidden="true" />;
};

StatusDot.displayName = 'StatusDot';

export default Badge;
