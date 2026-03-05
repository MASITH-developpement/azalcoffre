// AZALPLUS - Composant Icon
// Charge les icônes SVG depuis /assets/icons/
import React from 'react';

export interface IconProps {
  /** Nom de l'icône (sans extension .svg) */
  name: string;
  /** Classes CSS additionnelles */
  className?: string;
  /** Taille en pixels (défaut: 20) */
  size?: number;
  /** Couleur de l'icône (appliquée via CSS filter) */
  color?: 'current' | 'primary' | 'success' | 'warning' | 'danger' | 'gray';
  /** Titre pour l'accessibilité */
  title?: string;
}

/**
 * Composant Icon qui charge les icônes SVG depuis le serveur.
 *
 * @example
 * ```tsx
 * <Icon name="users" />
 * <Icon name="receipt" size={24} color="primary" />
 * <Icon name="check-square" className="text-green-500" />
 * ```
 */
export const Icon: React.FC<IconProps> = ({
  name,
  className = '',
  size = 20,
  color = 'current',
  title,
}) => {
  // Map des couleurs vers des filtres CSS
  const colorFilters: Record<string, string> = {
    current: 'none',
    primary: 'invert(37%) sepia(93%) saturate(1352%) hue-rotate(213deg) brightness(97%) contrast(90%)', // blue-600
    success: 'invert(48%) sepia(79%) saturate(457%) hue-rotate(93deg) brightness(95%) contrast(88%)', // green-500
    warning: 'invert(72%) sepia(98%) saturate(1029%) hue-rotate(1deg) brightness(103%) contrast(105%)', // yellow-500
    danger: 'invert(28%) sepia(67%) saturate(4506%) hue-rotate(348deg) brightness(93%) contrast(92%)', // red-500
    gray: 'invert(46%) sepia(0%) saturate(0%) hue-rotate(131deg) brightness(96%) contrast(90%)', // gray-500
  };

  return (
    <img
      src={`/assets/icons/${name}.svg`}
      alt={title || name}
      title={title}
      width={size}
      height={size}
      className={`inline-block ${className}`}
      style={{
        filter: colorFilters[color] || 'none',
        width: `${size}px`,
        height: `${size}px`,
      }}
      onError={(e) => {
        const img = e.target as HTMLImageElement;
        if (!img.src.endsWith('default.svg')) {
          img.src = '/assets/icons/default.svg';
        }
      }}
      loading="lazy"
    />
  );
};

/**
 * Hook pour précharger des icônes
 */
export const usePreloadIcons = (iconNames: string[]) => {
  React.useEffect(() => {
    iconNames.forEach((name) => {
      const img = new Image();
      img.src = `/assets/icons/${name}.svg`;
    });
  }, [iconNames]);
};

/**
 * URL de l'icône pour usage direct
 */
export const getIconUrl = (name: string): string => {
  return `/assets/icons/${name}.svg`;
};

/**
 * URL de l'API pour les métadonnées de l'icône
 */
export const getIconApiUrl = (name: string): string => {
  return `/api/v1/icons/${name}`;
};

export default Icon;
