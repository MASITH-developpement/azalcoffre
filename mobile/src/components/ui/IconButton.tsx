import React, { forwardRef, ButtonHTMLAttributes } from 'react';
import { Spinner } from './Spinner';

export type IconButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type IconButtonSize = 'sm' | 'md' | 'lg';

export interface IconButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Button visual style variant */
  variant?: IconButtonVariant;
  /** Button size - all maintain 44px min touch target */
  size?: IconButtonSize;
  /** Accessible label (required for icon-only buttons) */
  'aria-label': string;
  /** Show loading spinner */
  isLoading?: boolean;
  /** Icon element to display */
  icon: React.ReactNode;
  /** Make button circular instead of rounded square */
  rounded?: boolean;
}

const variantStyles: Record<IconButtonVariant, string> = {
  primary: [
    'bg-primary-600 text-white',
    'hover:bg-primary-700 active:bg-primary-800',
    'disabled:bg-primary-300 disabled:cursor-not-allowed',
    'focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
  ].join(' '),
  secondary: [
    'bg-white text-gray-700 border border-gray-300',
    'hover:bg-gray-50 active:bg-gray-100',
    'disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed',
    'focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
  ].join(' '),
  ghost: [
    'bg-transparent text-gray-700',
    'hover:bg-gray-100 active:bg-gray-200',
    'disabled:text-gray-400 disabled:cursor-not-allowed disabled:hover:bg-transparent',
    'focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
  ].join(' '),
  danger: [
    'bg-red-600 text-white',
    'hover:bg-red-700 active:bg-red-800',
    'disabled:bg-red-300 disabled:cursor-not-allowed',
    'focus:ring-2 focus:ring-red-500 focus:ring-offset-2',
  ].join(' '),
};

// All sizes maintain 44px minimum touch target
const sizeStyles: Record<IconButtonSize, { button: string; icon: string }> = {
  sm: {
    button: 'min-w-[44px] min-h-[44px] p-2.5',
    icon: 'w-5 h-5',
  },
  md: {
    button: 'min-w-[44px] min-h-[44px] p-2.5',
    icon: 'w-6 h-6',
  },
  lg: {
    button: 'min-w-[48px] min-h-[48px] p-3',
    icon: 'w-7 h-7',
  },
};

/**
 * Icon-only button with accessible label.
 * All sizes maintain 44px minimum touch target for mobile accessibility.
 */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  (
    {
      variant = 'ghost',
      size = 'md',
      isLoading = false,
      icon,
      rounded = true,
      disabled,
      className = '',
      ...props
    },
    ref
  ) => {
    const isDisabled = disabled || isLoading;

    const baseStyles = [
      'inline-flex items-center justify-center',
      'transition-colors duration-200',
      'touch-manipulation select-none',
      'outline-none',
    ].join(' ');

    const roundedStyle = rounded ? 'rounded-full' : 'rounded-lg';

    const classes = [
      baseStyles,
      variantStyles[variant],
      sizeStyles[size].button,
      roundedStyle,
      className,
    ]
      .filter(Boolean)
      .join(' ');

    return (
      <button
        ref={ref}
        type="button"
        disabled={isDisabled}
        className={classes}
        {...props}
      >
        {isLoading ? (
          <Spinner
            size="sm"
            color={variant === 'primary' || variant === 'danger' ? 'white' : 'primary'}
          />
        ) : (
          <span className={sizeStyles[size].icon}>{icon}</span>
        )}
      </button>
    );
  }
);

IconButton.displayName = 'IconButton';

export default IconButton;
