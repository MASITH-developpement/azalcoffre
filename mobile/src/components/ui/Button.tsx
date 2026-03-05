import React, { forwardRef, ButtonHTMLAttributes } from 'react';
import { Spinner } from './Spinner';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Button visual style variant */
  variant?: ButtonVariant;
  /** Button size - all sizes maintain 44px min touch target */
  size?: ButtonSize;
  /** Show loading spinner and disable interactions */
  isLoading?: boolean;
  /** Loading text to display alongside spinner */
  loadingText?: string;
  /** Make button full width of container */
  fullWidth?: boolean;
  /** Left icon element */
  leftIcon?: React.ReactNode;
  /** Right icon element */
  rightIcon?: React.ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
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
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'min-h-[44px] px-3 py-2 text-sm',
  md: 'min-h-[44px] px-4 py-2.5 text-base',
  lg: 'min-h-[48px] px-6 py-3 text-lg',
};

/**
 * Button component with mobile-optimized touch targets.
 * All sizes maintain minimum 44px touch target for accessibility.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      isLoading = false,
      loadingText,
      fullWidth = false,
      leftIcon,
      rightIcon,
      disabled,
      className = '',
      children,
      ...props
    },
    ref
  ) => {
    const isDisabled = disabled || isLoading;

    const baseStyles = [
      'inline-flex items-center justify-center',
      'font-medium rounded-lg',
      'transition-colors duration-200',
      'touch-manipulation select-none',
      'outline-none',
    ].join(' ');

    const classes = [
      baseStyles,
      variantStyles[variant],
      sizeStyles[size],
      fullWidth ? 'w-full' : '',
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
          <>
            <Spinner
              size="sm"
              color={variant === 'primary' ? 'white' : 'primary'}
              className="mr-2"
            />
            {loadingText || children}
          </>
        ) : (
          <>
            {leftIcon && <span className="mr-2 flex-shrink-0">{leftIcon}</span>}
            {children}
            {rightIcon && <span className="ml-2 flex-shrink-0">{rightIcon}</span>}
          </>
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';

export default Button;
