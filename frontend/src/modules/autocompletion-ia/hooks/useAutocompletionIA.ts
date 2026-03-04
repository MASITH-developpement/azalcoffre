// AZALPLUS - Hook Autocompletion IA
import { useCallback, useEffect, useRef, useState } from 'react';
import { completeText as apiCompleteText, getSuggestions, sendFeedback } from '../api';
import type {
  Suggestion,
  SuggestionMeta,
  UseAutocompletionIAOptions,
  UseAutocompletionIAReturn,
} from '../types';

/**
 * Hook React pour l'autocomplétion intelligente avec IA (ChatGPT / Claude)
 *
 * @example
 * ```tsx
 * const {
 *   suggestions,
 *   isLoading,
 *   fetchSuggestions,
 *   acceptSuggestion,
 * } = useAutocompletionIA({
 *   module: 'Clients',
 *   champ: 'nom',
 *   debounceMs: 300,
 * });
 *
 * // Dans un input
 * <input
 *   onChange={(e) => fetchSuggestions(e.target.value)}
 *   onKeyDown={handleKeyDown}
 * />
 * ```
 */
export function useAutocompletionIA(
  options: UseAutocompletionIAOptions
): UseAutocompletionIAReturn {
  const {
    module,
    champ,
    debounceMs = 300,
    minChars = 2,
    maxSuggestions = 5,
    typeCompletion,
    provider,
    contexte,
    disabled = false,
    onSuggestionSelect,
    onError,
  } = options;

  // State
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [meta, setMeta] = useState<SuggestionMeta | null>(null);

  // Refs
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastValueRef = useRef<string>('');

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  /**
   * Récupérer les suggestions depuis l'API
   */
  const fetchSuggestions = useCallback(
    async (value: string) => {
      // Ne rien faire si désactivé
      if (disabled) {
        return;
      }

      // Annuler le timer précédent
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      // Annuler la requête précédente
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      // Réinitialiser si la valeur est trop courte
      if (value.length < minChars) {
        setSuggestions([]);
        setShowSuggestions(false);
        setSelectedIndex(-1);
        return;
      }

      // Sauvegarder la valeur
      lastValueRef.current = value;

      // Debounce
      debounceTimerRef.current = setTimeout(async () => {
        setIsLoading(true);
        setError(null);

        // Créer un nouveau controller pour cette requête
        abortControllerRef.current = new AbortController();

        try {
          const response = await getSuggestions({
            module,
            champ,
            valeur: value,
            limite: maxSuggestions,
            type_completion: typeCompletion,
            provider,
            contexte,
          });

          // Vérifier que la valeur n'a pas changé pendant la requête
          if (lastValueRef.current === value) {
            setSuggestions(response.suggestions);
            setMeta(response.meta);
            setShowSuggestions(response.suggestions.length > 0);
            setSelectedIndex(-1);
          }
        } catch (err) {
          // Ignorer les erreurs d'annulation
          if (err instanceof Error && err.name === 'AbortError') {
            return;
          }

          const error = err instanceof Error ? err : new Error('Unknown error');
          setError(error);
          onError?.(error);
          setSuggestions([]);
          setShowSuggestions(false);
        } finally {
          setIsLoading(false);
        }
      }, debounceMs);
    },
    [
      module,
      champ,
      debounceMs,
      minChars,
      maxSuggestions,
      typeCompletion,
      provider,
      contexte,
      disabled,
      onError,
    ]
  );

  /**
   * Accepter une suggestion
   */
  const acceptSuggestion = useCallback(
    (suggestion: Suggestion) => {
      // Envoyer le feedback (fire and forget)
      sendFeedback({
        suggestion_id: suggestion.id,
        accepted: true,
        valeur_finale: suggestion.texte,
      }).catch(() => {
        // Ignorer les erreurs de feedback
      });

      // Fermer les suggestions
      setSuggestions([]);
      setShowSuggestions(false);
      setSelectedIndex(-1);

      // Callback
      onSuggestionSelect?.(suggestion);
    },
    [onSuggestionSelect]
  );

  /**
   * Rejeter/fermer les suggestions
   */
  const dismissSuggestions = useCallback(() => {
    setShowSuggestions(false);
    setSelectedIndex(-1);

    // Envoyer un feedback négatif pour la première suggestion si présente
    if (suggestions.length > 0) {
      sendFeedback({
        suggestion_id: suggestions[0].id,
        accepted: false,
      }).catch(() => {
        // Ignorer les erreurs
      });
    }
  }, [suggestions]);

  /**
   * Naviguer dans les suggestions avec le clavier
   */
  const navigateSuggestions = useCallback(
    (direction: 'up' | 'down') => {
      if (!showSuggestions || suggestions.length === 0) {
        return;
      }

      setSelectedIndex((prev) => {
        if (direction === 'down') {
          return prev < suggestions.length - 1 ? prev + 1 : 0;
        } else {
          return prev > 0 ? prev - 1 : suggestions.length - 1;
        }
      });
    },
    [showSuggestions, suggestions.length]
  );

  /**
   * Accepter la suggestion actuellement sélectionnée
   */
  const acceptSelected = useCallback(() => {
    if (selectedIndex >= 0 && selectedIndex < suggestions.length) {
      acceptSuggestion(suggestions[selectedIndex]);
    } else if (suggestions.length > 0) {
      // Si rien n'est sélectionné, accepter la première
      acceptSuggestion(suggestions[0]);
    }
  }, [selectedIndex, suggestions, acceptSuggestion]);

  /**
   * Compléter un texte long (pour textarea)
   */
  const completeText = useCallback(
    async (value: string, maxTokens = 100): Promise<string> => {
      if (disabled || value.length < minChars) {
        return '';
      }

      setIsLoading(true);
      setError(null);

      try {
        const response = await apiCompleteText({
          module,
          champ,
          valeur: value,
          max_tokens: maxTokens,
          provider,
          contexte,
        });

        setMeta(response.meta);
        return response.completion;
      } catch (err) {
        const error = err instanceof Error ? err : new Error('Unknown error');
        setError(error);
        onError?.(error);
        return '';
      } finally {
        setIsLoading(false);
      }
    },
    [module, champ, provider, contexte, disabled, minChars, onError]
  );

  /**
   * Réinitialiser l'état
   */
  const reset = useCallback(() => {
    setSuggestions([]);
    setIsLoading(false);
    setError(null);
    setShowSuggestions(false);
    setSelectedIndex(-1);
    setMeta(null);
    lastValueRef.current = '';

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  return {
    suggestions,
    isLoading,
    error,
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
  };
}

export default useAutocompletionIA;
