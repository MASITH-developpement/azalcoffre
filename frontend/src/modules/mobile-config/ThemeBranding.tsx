// AZALPLUS - Theme & Branding Configuration Component
// Customize app name, logo, colors, and theme settings

import React, { useState, useRef, useCallback } from 'react';
import type { ThemeBrandingProps, ThemeBrandingConfig } from './types';
import { PRESET_COLORS } from './types';

// -----------------------------------------------------------------------------
// Icons
// -----------------------------------------------------------------------------
const UploadIcon = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
  </svg>
);

const TrashIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
  </svg>
);

const SunIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
  </svg>
);

const MoonIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
  </svg>
);

const LoadingSpinner = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg className={`animate-spin ${className}`} fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
  </svg>
);

// -----------------------------------------------------------------------------
// Color Picker Component
// -----------------------------------------------------------------------------
interface ColorPickerProps {
  label: string;
  description?: string;
  value: string;
  onChange: (color: string) => void;
}

const ColorPicker: React.FC<ColorPickerProps> = ({
  label,
  description,
  value,
  onChange,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [customColor, setCustomColor] = useState(value);

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-700">{label}</label>
      {description && (
        <p className="text-xs text-gray-500">{description}</p>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="w-12 h-12 rounded-lg border-2 border-gray-300 shadow-sm hover:border-gray-400 transition-colors"
          style={{ backgroundColor: value }}
          title="Cliquer pour changer"
        />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500"
          placeholder="#2563eb"
        />
      </div>

      {isOpen && (
        <div className="p-3 bg-gray-50 rounded-lg border border-gray-200 space-y-3">
          <div className="flex flex-wrap gap-2">
            {PRESET_COLORS.map((color) => (
              <button
                key={color}
                onClick={() => {
                  onChange(color);
                  setIsOpen(false);
                }}
                className={`w-8 h-8 rounded-lg border-2 transition-all ${
                  value === color ? 'border-gray-900 scale-110' : 'border-transparent hover:border-gray-400'
                }`}
                style={{ backgroundColor: color }}
                title={color}
              />
            ))}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={customColor}
              onChange={(e) => setCustomColor(e.target.value)}
              className="w-8 h-8 rounded cursor-pointer"
            />
            <input
              type="text"
              value={customColor}
              onChange={(e) => setCustomColor(e.target.value)}
              className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm font-mono"
            />
            <button
              onClick={() => {
                onChange(customColor);
                setIsOpen(false);
              }}
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
            >
              OK
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// -----------------------------------------------------------------------------
// Logo Upload Component
// -----------------------------------------------------------------------------
interface LogoUploadProps {
  logoUrl?: string;
  onUpload: (file: File) => Promise<string>;
  onRemove: () => void;
}

const LogoUpload: React.FC<LogoUploadProps> = ({
  logoUrl,
  onUpload,
  onRemove,
}) => {
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file
    if (!file.type.startsWith('image/')) {
      setError('Le fichier doit etre une image');
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      setError('Le fichier doit faire moins de 2 Mo');
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      await onUpload(file);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors du televersement');
    } finally {
      setIsUploading(false);
      if (inputRef.current) {
        inputRef.current.value = '';
      }
    }
  };

  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-gray-700">Logo de l'application</label>
      <p className="text-xs text-gray-500">
        Recommande: PNG ou SVG, 512x512 pixels, fond transparent
      </p>

      <div className="flex items-start gap-4">
        {/* Preview */}
        <div className="w-24 h-24 bg-gray-100 rounded-xl border-2 border-dashed border-gray-300 flex items-center justify-center overflow-hidden">
          {logoUrl ? (
            <img
              src={logoUrl}
              alt="Logo"
              className="w-full h-full object-contain p-2"
            />
          ) : (
            <div className="text-gray-400">
              <UploadIcon />
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex-1 space-y-2">
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            className="hidden"
            id="logo-upload"
          />
          <label
            htmlFor="logo-upload"
            className={`
              inline-flex items-center gap-2 px-4 py-2 rounded-lg cursor-pointer
              ${isUploading
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
              }
            `}
          >
            {isUploading ? (
              <>
                <LoadingSpinner className="w-4 h-4" />
                Televersement...
              </>
            ) : (
              <>
                <UploadIcon />
                Telecharger
              </>
            )}
          </label>

          {logoUrl && (
            <button
              onClick={onRemove}
              className="inline-flex items-center gap-2 px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg"
            >
              <TrashIcon />
              Supprimer
            </button>
          )}

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}
        </div>
      </div>
    </div>
  );
};

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------
export function ThemeBranding({
  config,
  onChange,
  onLogoUpload,
}: ThemeBrandingProps) {
  const handleFieldChange = <K extends keyof ThemeBrandingConfig>(
    field: K,
    value: ThemeBrandingConfig[K]
  ) => {
    onChange({ ...config, [field]: value });
  };

  const handleLogoUpload = useCallback(async (file: File) => {
    const url = await onLogoUpload(file);
    handleFieldChange('logoUrl', url);
    return url;
  }, [onLogoUpload]);

  const handleLogoRemove = useCallback(() => {
    handleFieldChange('logoUrl', undefined);
  }, []);

  const borderRadiusOptions = [
    { value: 'none', label: 'Aucun', example: 'rounded-none' },
    { value: 'small', label: 'Petit', example: 'rounded' },
    { value: 'medium', label: 'Moyen', example: 'rounded-lg' },
    { value: 'large', label: 'Grand', example: 'rounded-xl' },
  ];

  return (
    <div className="space-y-8">
      {/* App Identity */}
      <section className="space-y-6">
        <h3 className="text-lg font-semibold text-gray-900">Identite de l'application</h3>

        {/* App Name */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Nom de l'application
          </label>
          <p className="text-xs text-gray-500 mb-2">
            Affiche sur l'ecran de chargement et dans le titre
          </p>
          <input
            type="text"
            value={config.appName}
            onChange={(e) => handleFieldChange('appName', e.target.value)}
            className="w-full max-w-md px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            placeholder="Mon Application"
          />
        </div>

        {/* Logo */}
        <LogoUpload
          logoUrl={config.logoUrl}
          onUpload={handleLogoUpload}
          onRemove={handleLogoRemove}
        />
      </section>

      {/* Colors */}
      <section className="space-y-6">
        <h3 className="text-lg font-semibold text-gray-900">Couleurs</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <ColorPicker
            label="Couleur principale"
            description="Boutons, liens, elements interactifs"
            value={config.primaryColor}
            onChange={(color) => handleFieldChange('primaryColor', color)}
          />

          <ColorPicker
            label="Couleur secondaire"
            description="Elements d'accentuation secondaires"
            value={config.secondaryColor}
            onChange={(color) => handleFieldChange('secondaryColor', color)}
          />

          <ColorPicker
            label="Couleur d'accent"
            description="Notifications, badges, alertes"
            value={config.accentColor}
            onChange={(color) => handleFieldChange('accentColor', color)}
          />
        </div>

        {/* Color Preview */}
        <div className="p-4 bg-gray-50 rounded-xl border border-gray-200">
          <p className="text-sm text-gray-600 mb-3">Apercu des couleurs</p>
          <div className="flex flex-wrap gap-3">
            <button
              className="px-4 py-2 text-white rounded-lg"
              style={{ backgroundColor: config.primaryColor }}
            >
              Bouton principal
            </button>
            <button
              className="px-4 py-2 text-white rounded-lg"
              style={{ backgroundColor: config.secondaryColor }}
            >
              Bouton secondaire
            </button>
            <span
              className="px-3 py-1 text-white text-sm rounded-full"
              style={{ backgroundColor: config.accentColor }}
            >
              Badge
            </span>
          </div>
        </div>
      </section>

      {/* Theme Mode */}
      <section className="space-y-4">
        <h3 className="text-lg font-semibold text-gray-900">Mode d'affichage</h3>

        <div className="flex gap-4">
          <button
            onClick={() => handleFieldChange('darkMode', false)}
            className={`flex-1 p-4 rounded-xl border-2 transition-all ${
              !config.darkMode
                ? 'border-blue-600 bg-blue-50'
                : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            <div className="flex items-center justify-center gap-3 mb-3">
              <div className="p-2 bg-white rounded-lg shadow-sm">
                <SunIcon />
              </div>
              <span className={`font-medium ${!config.darkMode ? 'text-blue-600' : 'text-gray-700'}`}>
                Mode clair
              </span>
            </div>
            <div className="bg-white rounded-lg p-3 border border-gray-200">
              <div className="h-2 w-16 bg-gray-200 rounded mb-2" />
              <div className="h-2 w-24 bg-gray-100 rounded" />
            </div>
          </button>

          <button
            onClick={() => handleFieldChange('darkMode', true)}
            className={`flex-1 p-4 rounded-xl border-2 transition-all ${
              config.darkMode
                ? 'border-blue-600 bg-blue-50'
                : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            <div className="flex items-center justify-center gap-3 mb-3">
              <div className="p-2 bg-gray-800 rounded-lg">
                <MoonIcon />
              </div>
              <span className={`font-medium ${config.darkMode ? 'text-blue-600' : 'text-gray-700'}`}>
                Mode sombre
              </span>
            </div>
            <div className="bg-gray-800 rounded-lg p-3">
              <div className="h-2 w-16 bg-gray-600 rounded mb-2" />
              <div className="h-2 w-24 bg-gray-700 rounded" />
            </div>
          </button>
        </div>
      </section>

      {/* Border Radius */}
      <section className="space-y-4">
        <h3 className="text-lg font-semibold text-gray-900">Style des coins</h3>
        <p className="text-sm text-gray-500">
          Definit l'arrondi des boutons, cartes et autres elements
        </p>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {borderRadiusOptions.map((option) => (
            <button
              key={option.value}
              onClick={() => handleFieldChange('borderRadius', option.value as ThemeBrandingConfig['borderRadius'])}
              className={`p-4 border-2 transition-all ${
                config.borderRadius === option.value
                  ? 'border-blue-600 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
              style={{
                borderRadius: option.value === 'none' ? '0' :
                             option.value === 'small' ? '4px' :
                             option.value === 'medium' ? '8px' : '12px',
              }}
            >
              <div
                className="w-full h-12 mb-2"
                style={{
                  backgroundColor: config.primaryColor,
                  borderRadius: option.value === 'none' ? '0' :
                               option.value === 'small' ? '4px' :
                               option.value === 'medium' ? '8px' : '12px',
                }}
              />
              <span className={`text-sm font-medium ${
                config.borderRadius === option.value ? 'text-blue-600' : 'text-gray-700'
              }`}>
                {option.label}
              </span>
            </button>
          ))}
        </div>
      </section>

      {/* Custom CSS (Advanced) */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">CSS personnalise</h3>
            <p className="text-sm text-gray-500">Optionnel - pour les utilisateurs avances</p>
          </div>
        </div>

        <textarea
          value={config.customCss || ''}
          onChange={(e) => handleFieldChange('customCss', e.target.value)}
          className="w-full h-32 px-4 py-3 font-mono text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          placeholder="/* Vos styles CSS personnalises */
.mobile-header {
  background: linear-gradient(to right, #000, #333);
}"
        />

        <div className="p-4 bg-amber-50 rounded-lg border border-amber-100">
          <p className="text-sm text-amber-700">
            <strong>Attention :</strong> Le CSS personnalise peut affecter l'apparence de l'application.
            Utilisez avec precaution.
          </p>
        </div>
      </section>
    </div>
  );
}

export default ThemeBranding;
