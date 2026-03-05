import React from 'react';

export type AvatarSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

export interface AvatarProps {
  /** Image source URL */
  src?: string;
  /** Alt text for image */
  alt?: string;
  /** User name for initials fallback */
  name?: string;
  /** Avatar size */
  size?: AvatarSize;
  /** Show online status indicator */
  showStatus?: boolean;
  /** Online status */
  status?: 'online' | 'offline' | 'away' | 'busy';
  /** Additional CSS classes */
  className?: string;
}

const sizeStyles: Record<AvatarSize, string> = {
  xs: 'w-6 h-6 text-xs',
  sm: 'w-8 h-8 text-sm',
  md: 'w-10 h-10 text-base',
  lg: 'w-12 h-12 text-lg',
  xl: 'w-16 h-16 text-xl',
};

const statusSizeStyles: Record<AvatarSize, string> = {
  xs: 'w-1.5 h-1.5 border',
  sm: 'w-2 h-2 border',
  md: 'w-2.5 h-2.5 border-2',
  lg: 'w-3 h-3 border-2',
  xl: 'w-4 h-4 border-2',
};

const statusColors = {
  online: 'bg-green-500',
  offline: 'bg-gray-400',
  away: 'bg-amber-500',
  busy: 'bg-red-500',
};

/**
 * Extract initials from a name string.
 * Takes first letter of first two words.
 */
function getInitials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase();
}

/**
 * Generate a consistent color based on name.
 * Uses a simple hash to pick from a palette.
 */
function getColorFromName(name: string): string {
  const colors = [
    'bg-primary-500',
    'bg-purple-500',
    'bg-pink-500',
    'bg-indigo-500',
    'bg-teal-500',
    'bg-orange-500',
    'bg-cyan-500',
    'bg-emerald-500',
  ];

  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }

  return colors[Math.abs(hash) % colors.length] ?? 'bg-gray-400';
}

/**
 * Avatar component with image, initials fallback, and status indicator.
 * Mobile-optimized with appropriate sizing.
 */
export const Avatar: React.FC<AvatarProps> = ({
  src,
  alt,
  name,
  size = 'md',
  showStatus = false,
  status = 'offline',
  className = '',
}) => {
  const initials = name ? getInitials(name) : '?';
  const bgColor = name ? getColorFromName(name) : 'bg-gray-400';

  const baseStyles = [
    'relative inline-flex items-center justify-center',
    'rounded-full',
    'font-medium text-white',
    'overflow-hidden',
    'flex-shrink-0',
  ].join(' ');

  const classes = [baseStyles, sizeStyles[size], className]
    .filter(Boolean)
    .join(' ');

  const statusClasses = [
    'absolute bottom-0 right-0',
    'rounded-full border-white',
    statusSizeStyles[size],
    statusColors[status],
  ].join(' ');

  return (
    <div className={classes}>
      {src ? (
        <img
          src={src}
          alt={alt || name || 'Avatar'}
          className="w-full h-full object-cover"
          onError={(e) => {
            // Hide broken image and show initials
            (e.target as HTMLImageElement).style.display = 'none';
          }}
        />
      ) : (
        <span
          className={`flex items-center justify-center w-full h-full ${bgColor}`}
          aria-hidden="true"
        >
          {initials}
        </span>
      )}

      {showStatus && (
        <span className={statusClasses} aria-label={`Status: ${status}`} />
      )}
    </div>
  );
};

Avatar.displayName = 'Avatar';

/**
 * Avatar group for displaying multiple avatars with overlap.
 */
export interface AvatarGroupProps {
  /** Maximum avatars to display before showing +N */
  max?: number;
  /** Avatar data array */
  avatars: Array<{
    src?: string;
    name?: string;
    alt?: string;
  }>;
  /** Size of avatars */
  size?: AvatarSize;
  /** Additional CSS classes */
  className?: string;
}

export const AvatarGroup: React.FC<AvatarGroupProps> = ({
  max = 4,
  avatars,
  size = 'md',
  className = '',
}) => {
  const visibleAvatars = avatars.slice(0, max);
  const remainingCount = avatars.length - max;

  const overlapStyles: Record<AvatarSize, string> = {
    xs: '-ml-1.5',
    sm: '-ml-2',
    md: '-ml-2.5',
    lg: '-ml-3',
    xl: '-ml-4',
  };

  return (
    <div
      className={`flex items-center ${className}`}
      role="group"
      aria-label={`${avatars.length} users`}
    >
      {visibleAvatars.map((avatar, index) => (
        <div
          key={index}
          className={`${index > 0 ? overlapStyles[size] : ''} ring-2 ring-white rounded-full`}
        >
          <Avatar
            {...(avatar.src ? { src: avatar.src } : {})}
            {...(avatar.name ? { name: avatar.name } : {})}
            {...(avatar.alt ? { alt: avatar.alt } : {})}
            size={size}
          />
        </div>
      ))}

      {remainingCount > 0 && (
        <div
          className={`${overlapStyles[size]} ring-2 ring-white rounded-full`}
        >
          <span
            className={`
              flex items-center justify-center
              bg-gray-200 text-gray-600 rounded-full font-medium
              ${sizeStyles[size]}
            `}
          >
            +{remainingCount}
          </span>
        </div>
      )}
    </div>
  );
};

AvatarGroup.displayName = 'AvatarGroup';

export default Avatar;
