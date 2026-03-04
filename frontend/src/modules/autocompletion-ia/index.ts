// AZALPLUS - Module Autocompletion IA
// Autocomplétion intelligente avec ChatGPT et Claude

// Types
export * from './types';

// API
export * from './api';

// Hooks
export { useAutocompletionIA, default as useAutocompletionIADefault } from './hooks/useAutocompletionIA';

// Components
export { AutocompleteField, default as AutocompleteFieldDefault } from './components/AutocompleteField';
export type { AutocompleteFieldRef } from './components/AutocompleteField';
export { ConfigurationPage } from './components/ConfigurationPage';
