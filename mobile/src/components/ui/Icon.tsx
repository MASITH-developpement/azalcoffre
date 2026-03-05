/**
 * AZALPLUS Mobile PWA - Icon Component
 *
 * Loads custom duotone SVG icons from /assets/icons/
 * Supports fallback and loading states.
 */

import React, { useState, useEffect } from 'react';

export interface IconProps {
  /** Icon name (without .svg extension) */
  name: string;
  /** Icon size in pixels (default: 24) */
  size?: number;
  /** Additional CSS classes */
  className?: string;
  /** Alt text for accessibility */
  alt?: string;
  /** Inline styles */
  style?: React.CSSProperties;
  /** Callback when icon fails to load */
  onError?: () => void;
}

// Base URL for icons API - handles both dev and production
const getIconsBaseUrl = (): string => {
  const apiUrl = import.meta.env.VITE_API_URL || '';
  // If API URL is absolute, use it
  if (apiUrl.startsWith('http')) {
    // VITE_API_URL is like http://host:port/api
    // Icons are at /api/icons/{name}
    return apiUrl.replace(/\/?$/, '/icons');
  }
  // Fallback to relative path
  return '/api/icons';
};

/**
 * Icon component that loads duotone SVG icons from the backend.
 * Uses img tag for proper rendering of duotone colors.
 */
export const Icon: React.FC<IconProps> = ({
  name,
  size = 24,
  className = '',
  alt,
  style,
  onError,
}) => {
  const [hasError, setHasError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const baseUrl = getIconsBaseUrl();

  // Reset error state when name changes
  useEffect(() => {
    setHasError(false);
    setIsLoading(true);
  }, [name]);

  const handleError = () => {
    setHasError(true);
    setIsLoading(false);
    onError?.();
  };

  const handleLoad = () => {
    setIsLoading(false);
  };

  // Use API endpoint for icons (includes CORS headers)
  const iconUrl = hasError
    ? `${baseUrl}/default`
    : `${baseUrl}/${name}`;

  return (
    <img
      src={iconUrl}
      alt={alt || name}
      width={size}
      height={size}
      className={`icon ${className}`}
      style={{
        display: 'inline-block',
        verticalAlign: 'middle',
        objectFit: 'contain',
        opacity: isLoading ? 0.5 : 1,
        transition: 'opacity 0.2s ease',
        ...style,
      }}
      onError={handleError}
      onLoad={handleLoad}
      loading="lazy"
    />
  );
};

/**
 * Preload icons for better UX
 */
export const preloadIcons = (iconNames: string[]): void => {
  const baseUrl = getIconsBaseUrl();
  iconNames.forEach((name) => {
    const img = new Image();
    img.src = `${baseUrl}/${name}`;
  });
};

/**
 * Hook to get icon URL
 */
export const useIconUrl = (name: string): string => {
  const baseUrl = getIconsBaseUrl();
  return `${baseUrl}/${name}`;
};

export default Icon;
