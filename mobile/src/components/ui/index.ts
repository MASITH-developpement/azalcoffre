/**
 * AZALPLUS Mobile PWA - Core UI Components
 *
 * Mobile-optimized components with 44px minimum touch targets.
 * Uses AZALPLUS color scheme (#2563EB primary).
 */

// Button components
export { Button } from './Button';
export type { ButtonProps, ButtonVariant, ButtonSize } from './Button';

export { IconButton } from './IconButton';
export type {
  IconButtonProps,
  IconButtonVariant,
  IconButtonSize,
} from './IconButton';

// Card components
export { Card, CardHeader, CardBody, CardFooter } from './Card';
export type {
  CardProps,
  CardHeaderProps,
  CardBodyProps,
  CardFooterProps,
} from './Card';

// Form components
export { Input } from './Input';
export type { InputProps } from './Input';

// Display components
export { Badge, StatusDot } from './Badge';
export type { BadgeProps, BadgeVariant, BadgeSize } from './Badge';

export { Avatar, AvatarGroup } from './Avatar';
export type { AvatarProps, AvatarGroupProps, AvatarSize } from './Avatar';

// Feedback components
export { Spinner } from './Spinner';
export type { SpinnerProps, SpinnerSize, SpinnerColor } from './Spinner';

// Icon component
export { Icon, preloadIcons, useIconUrl } from './Icon';
export type { IconProps } from './Icon';
