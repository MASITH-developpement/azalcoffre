// AZALPLUS - Composant AutocompleteField avec IA
import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import { useAutocompletionIA } from '../hooks/useAutocompletionIA';
import type { AutocompleteFieldProps, Suggestion } from '../types';

// Icônes (à remplacer par vos icônes)
const SparklesIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
  </svg>
);

const LoadingSpinner = () => (
  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
  </svg>
);

// Source badges
const sourceBadges: Record<string, { label: string; className: string }> = {
  ia: { label: 'IA', className: 'bg-purple-100 text-purple-700' },
  cache: { label: 'Cache', className: 'bg-gray-100 text-gray-600' },
  historique: { label: 'Historique', className: 'bg-blue-100 text-blue-700' },
  api: { label: 'API', className: 'bg-green-100 text-green-700' },
};

export interface AutocompleteFieldRef {
  focus: () => void;
  blur: () => void;
  reset: () => void;
}

/**
 * Champ de saisie avec autocomplétion IA
 *
 * @example
 * ```tsx
 * <AutocompleteField
 *   module="Clients"
 *   field="nom"
 *   value={nom}
 *   onChange={setNom}
 *   label="Nom du client"
 *   placeholder="Commencez à taper..."
 * />
 * ```
 */
export const AutocompleteField = forwardRef<AutocompleteFieldRef, AutocompleteFieldProps>(
  (props, ref) => {
    const {
      module,
      field,
      value,
      onChange,
      placeholder,
      label,
      disabled = false,
      required = false,
      error,
      iaEnabled = true,
      showSource = false,
      typeCompletion,
      provider,
      contexte,
      onSuggestionSelect,
      className = '',
      type = 'text',
      multiline = false,
      rows = 3,
    } = props;

    // Refs
    const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);

    // État local
    const [isFocused, setIsFocused] = useState(false);

    // Hook d'autocomplétion
    const {
      suggestions,
      isLoading,
      showSuggestions,
      selectedIndex,
      meta,
      fetchSuggestions,
      acceptSuggestion,
      dismissSuggestions,
      navigateSuggestions,
      acceptSelected,
      completeText,
      reset,
    } = useAutocompletionIA({
      module,
      champ: field,
      typeCompletion,
      provider,
      contexte,
      disabled: disabled || !iaEnabled,
      onSuggestionSelect: (suggestion) => {
        onChange(suggestion.texte);
        onSuggestionSelect?.(suggestion);
      },
    });

    // Exposer les méthodes via ref
    useImperativeHandle(ref, () => ({
      focus: () => inputRef.current?.focus(),
      blur: () => inputRef.current?.blur(),
      reset,
    }));

    // Gérer le clic en dehors pour fermer les suggestions
    useEffect(() => {
      const handleClickOutside = (event: MouseEvent) => {
        if (
          dropdownRef.current &&
          !dropdownRef.current.contains(event.target as Node) &&
          inputRef.current &&
          !inputRef.current.contains(event.target as Node)
        ) {
          dismissSuggestions();
        }
      };

      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [dismissSuggestions]);

    // Gérer les changements de valeur
    const handleChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        const newValue = e.target.value;
        onChange(newValue);
        fetchSuggestions(newValue);
      },
      [onChange, fetchSuggestions]
    );

    // Gérer les touches clavier
    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent) => {
        if (!showSuggestions) {
          // Ctrl+Space pour déclencher manuellement
          if (e.ctrlKey && e.key === ' ') {
            e.preventDefault();
            fetchSuggestions(value);
          }
          // Ctrl+Enter pour compléter (textarea)
          if (multiline && e.ctrlKey && e.key === 'Enter') {
            e.preventDefault();
            completeText(value, 200).then((completion) => {
              if (completion) {
                onChange(value + completion);
              }
            });
          }
          return;
        }

        switch (e.key) {
          case 'ArrowDown':
            e.preventDefault();
            navigateSuggestions('down');
            break;
          case 'ArrowUp':
            e.preventDefault();
            navigateSuggestions('up');
            break;
          case 'Enter':
            if (selectedIndex >= 0) {
              e.preventDefault();
              acceptSelected();
            }
            break;
          case 'Tab':
            if (suggestions.length > 0) {
              e.preventDefault();
              acceptSelected();
            }
            break;
          case 'Escape':
            e.preventDefault();
            dismissSuggestions();
            break;
        }
      },
      [
        showSuggestions,
        selectedIndex,
        suggestions.length,
        value,
        multiline,
        fetchSuggestions,
        navigateSuggestions,
        acceptSelected,
        dismissSuggestions,
        completeText,
        onChange,
      ]
    );

    // Clic sur une suggestion
    const handleSuggestionClick = useCallback(
      (suggestion: Suggestion) => {
        acceptSuggestion(suggestion);
        inputRef.current?.focus();
      },
      [acceptSuggestion]
    );

    // Classes CSS
    const inputClasses = `
      w-full px-3 py-2 border rounded-lg transition-colors
      focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
      ${error ? 'border-red-500' : 'border-gray-300'}
      ${disabled ? 'bg-gray-100 cursor-not-allowed' : 'bg-white'}
      ${iaEnabled ? 'pr-10' : ''}
      ${className}
    `.trim();

    // Rendu
    return (
      <div className="relative">
        {/* Label */}
        {label && (
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {label}
            {required && <span className="text-red-500 ml-1">*</span>}
            {iaEnabled && (
              <span className="ml-2 text-purple-600" title="Autocomplétion IA activée">
                <SparklesIcon />
              </span>
            )}
          </label>
        )}

        {/* Input container */}
        <div className="relative">
          {/* Input ou Textarea */}
          {multiline ? (
            <textarea
              ref={inputRef as React.RefObject<HTMLTextAreaElement>}
              value={value}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={placeholder}
              disabled={disabled}
              required={required}
              rows={rows}
              className={inputClasses}
            />
          ) : (
            <input
              ref={inputRef as React.RefObject<HTMLInputElement>}
              type={type}
              value={value}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={placeholder}
              disabled={disabled}
              required={required}
              className={inputClasses}
            />
          )}

          {/* Indicateur IA / Loading */}
          {iaEnabled && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              {isLoading ? (
                <span className="text-purple-500">
                  <LoadingSpinner />
                </span>
              ) : (
                <span className="text-gray-400 hover:text-purple-500 cursor-pointer" title="Ctrl+Espace pour suggestions">
                  <SparklesIcon />
                </span>
              )}
            </div>
          )}
        </div>

        {/* Dropdown des suggestions */}
        {showSuggestions && suggestions.length > 0 && (
          <div
            ref={dropdownRef}
            className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-auto"
          >
            {suggestions.map((suggestion, index) => (
              <div
                key={suggestion.id}
                className={`
                  px-4 py-2 cursor-pointer flex items-center justify-between
                  ${index === selectedIndex ? 'bg-blue-50' : 'hover:bg-gray-50'}
                  ${index !== suggestions.length - 1 ? 'border-b border-gray-100' : ''}
                `}
                onClick={() => handleSuggestionClick(suggestion)}
                onMouseEnter={() => {}}
              >
                <span className="text-gray-900">{suggestion.texte}</span>
                <div className="flex items-center gap-2">
                  {/* Score (optionnel) */}
                  {suggestion.score < 1 && (
                    <span className="text-xs text-gray-400">
                      {Math.round(suggestion.score * 100)}%
                    </span>
                  )}
                  {/* Badge source */}
                  {showSource && sourceBadges[suggestion.source] && (
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${sourceBadges[suggestion.source].className}`}
                    >
                      {sourceBadges[suggestion.source].label}
                    </span>
                  )}
                </div>
              </div>
            ))}

            {/* Footer avec infos */}
            {meta && (
              <div className="px-4 py-2 bg-gray-50 text-xs text-gray-500 flex justify-between border-t">
                <span>
                  {meta.cached ? 'Cache' : meta.provider || 'IA'}
                  {meta.model && ` · ${meta.model}`}
                </span>
                <span>{meta.latency_ms}ms</span>
              </div>
            )}
          </div>
        )}

        {/* Message d'erreur */}
        {error && <p className="mt-1 text-sm text-red-500">{error}</p>}

        {/* Hint pour textarea */}
        {multiline && iaEnabled && isFocused && (
          <p className="mt-1 text-xs text-gray-400">
            Ctrl+Entrée pour compléter avec l'IA
          </p>
        )}
      </div>
    );
  }
);

AutocompleteField.displayName = 'AutocompleteField';

export default AutocompleteField;
