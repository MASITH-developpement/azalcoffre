import React, { forwardRef, HTMLAttributes } from 'react';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Make card clickable with hover/active states */
  clickable?: boolean;
  /** Remove padding from card body */
  noPadding?: boolean;
  /** Card border style */
  variant?: 'elevated' | 'outlined' | 'flat';
}

export interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  /** Header title */
  title?: string;
  /** Header subtitle */
  subtitle?: string;
  /** Right-side action element */
  action?: React.ReactNode;
}

export interface CardBodyProps extends HTMLAttributes<HTMLDivElement> {
  /** Remove padding */
  noPadding?: boolean;
}

export interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {
  /** Align footer content */
  align?: 'left' | 'center' | 'right' | 'between';
}

const variantStyles = {
  elevated: 'bg-white shadow-md border border-gray-100',
  outlined: 'bg-white border border-gray-200',
  flat: 'bg-gray-50',
};

/**
 * Card container component for grouping related content.
 * Mobile-optimized with appropriate touch feedback when clickable.
 */
export const Card = forwardRef<HTMLDivElement, CardProps>(
  (
    {
      clickable = false,
      noPadding = false,
      variant = 'elevated',
      className = '',
      children,
      ...props
    },
    ref
  ) => {
    const baseStyles = 'rounded-xl overflow-hidden';

    const clickableStyles = clickable
      ? [
          'cursor-pointer',
          'transition-all duration-200',
          'hover:shadow-lg',
          'active:scale-[0.98] active:shadow-sm',
          'touch-manipulation',
        ].join(' ')
      : '';

    const classes = [
      baseStyles,
      variantStyles[variant],
      clickableStyles,
      noPadding ? '' : 'p-4',
      className,
    ]
      .filter(Boolean)
      .join(' ');

    return (
      <div ref={ref} className={classes} {...props}>
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';

/**
 * Card header with title, subtitle, and optional action slot.
 */
export const CardHeader = forwardRef<HTMLDivElement, CardHeaderProps>(
  ({ title, subtitle, action, className = '', children, ...props }, ref) => {
    const classes = [
      'flex items-start justify-between gap-3',
      'pb-3 border-b border-gray-100',
      className,
    ]
      .filter(Boolean)
      .join(' ');

    return (
      <div ref={ref} className={classes} {...props}>
        {children || (
          <>
            <div className="flex-1 min-w-0">
              {title && (
                <h3 className="text-base font-semibold text-gray-900 truncate">
                  {title}
                </h3>
              )}
              {subtitle && (
                <p className="mt-0.5 text-sm text-gray-500 truncate">
                  {subtitle}
                </p>
              )}
            </div>
            {action && <div className="flex-shrink-0">{action}</div>}
          </>
        )}
      </div>
    );
  }
);

CardHeader.displayName = 'CardHeader';

/**
 * Card body content area.
 */
export const CardBody = forwardRef<HTMLDivElement, CardBodyProps>(
  ({ noPadding = false, className = '', children, ...props }, ref) => {
    const classes = [noPadding ? '' : 'py-3', className].filter(Boolean).join(' ');

    return (
      <div ref={ref} className={classes} {...props}>
        {children}
      </div>
    );
  }
);

CardBody.displayName = 'CardBody';

/**
 * Card footer for actions or additional info.
 */
export const CardFooter = forwardRef<HTMLDivElement, CardFooterProps>(
  ({ align = 'right', className = '', children, ...props }, ref) => {
    const alignStyles = {
      left: 'justify-start',
      center: 'justify-center',
      right: 'justify-end',
      between: 'justify-between',
    };

    const classes = [
      'flex items-center gap-2',
      'pt-3 border-t border-gray-100',
      alignStyles[align],
      className,
    ]
      .filter(Boolean)
      .join(' ');

    return (
      <div ref={ref} className={classes} {...props}>
        {children}
      </div>
    );
  }
);

CardFooter.displayName = 'CardFooter';

export default Card;
