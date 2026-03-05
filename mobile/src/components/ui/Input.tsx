import React, { forwardRef, InputHTMLAttributes, useId } from 'react';

export interface InputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  /** Input label text */
  label?: string;
  /** Error message to display */
  error?: string;
  /** Helper text displayed below input */
  helperText?: string;
  /** Icon displayed on the left side of input */
  leftIcon?: React.ReactNode;
  /** Icon displayed on the right side of input */
  rightIcon?: React.ReactNode;
  /** Input size variant */
  size?: 'sm' | 'md' | 'lg';
  /** Make input full width */
  fullWidth?: boolean;
  /** Additional wrapper className */
  wrapperClassName?: string;
}

const sizeStyles = {
  sm: 'min-h-[44px] px-3 py-2 text-sm',
  md: 'min-h-[44px] px-4 py-2.5 text-base',
  lg: 'min-h-[48px] px-4 py-3 text-lg',
};

const iconPaddingLeft = {
  sm: 'pl-9',
  md: 'pl-10',
  lg: 'pl-11',
};

const iconPaddingRight = {
  sm: 'pr-9',
  md: 'pr-10',
  lg: 'pr-11',
};

/**
 * Text input component with label, icons, and error handling.
 * Mobile-optimized with 44px minimum touch target.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      helperText,
      leftIcon,
      rightIcon,
      size = 'md',
      fullWidth = true,
      disabled,
      className = '',
      wrapperClassName = '',
      id,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const inputId = id || generatedId;
    const errorId = `${inputId}-error`;
    const helperId = `${inputId}-helper`;

    const hasError = Boolean(error);

    const baseInputStyles = [
      'block rounded-lg',
      'border bg-white',
      'text-gray-900 placeholder:text-gray-400',
      'transition-colors duration-200',
      'outline-none',
      'touch-manipulation',
    ].join(' ');

    const stateStyles = hasError
      ? 'border-red-500 focus:border-red-500 focus:ring-2 focus:ring-red-200'
      : 'border-gray-300 focus:border-primary-500 focus:ring-2 focus:ring-primary-200';

    const disabledStyles = disabled
      ? 'bg-gray-100 text-gray-500 cursor-not-allowed'
      : '';

    const inputClasses = [
      baseInputStyles,
      sizeStyles[size],
      stateStyles,
      disabledStyles,
      leftIcon ? iconPaddingLeft[size] : '',
      rightIcon ? iconPaddingRight[size] : '',
      fullWidth ? 'w-full' : '',
      className,
    ]
      .filter(Boolean)
      .join(' ');

    const wrapperClasses = [fullWidth ? 'w-full' : '', wrapperClassName]
      .filter(Boolean)
      .join(' ');

    return (
      <div className={wrapperClasses}>
        {label && (
          <label
            htmlFor={inputId}
            className="block mb-1.5 text-sm font-medium text-gray-700"
          >
            {label}
          </label>
        )}

        <div className="relative">
          {leftIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none">
              {leftIcon}
            </div>
          )}

          <input
            ref={ref}
            id={inputId}
            disabled={disabled}
            aria-invalid={hasError}
            aria-describedby={
              [hasError ? errorId : '', helperText ? helperId : '']
                .filter(Boolean)
                .join(' ') || undefined
            }
            className={inputClasses}
            {...props}
          />

          {rightIcon && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">
              {rightIcon}
            </div>
          )}
        </div>

        {hasError && (
          <p id={errorId} className="mt-1.5 text-sm text-red-600" role="alert">
            {error}
          </p>
        )}

        {helperText && !hasError && (
          <p id={helperId} className="mt-1.5 text-sm text-gray-500">
            {helperText}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export default Input;
