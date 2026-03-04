// AZALPLUS - Exemple d'utilisation de l'Autocompletion IA
import React, { useState } from 'react';
import { AutocompleteField } from '../components/AutocompleteField';
import { useAutocompletionIA } from '../hooks/useAutocompletionIA';

/**
 * Exemple 1: Utilisation du composant AutocompleteField
 *
 * Le plus simple - utilisez directement le composant
 */
export function ExampleWithComponent() {
  const [formData, setFormData] = useState({
    nom: '',
    email: '',
    adresse: '',
    description: '',
  });

  return (
    <form className="space-y-4 max-w-lg mx-auto p-6">
      <h2 className="text-xl font-bold mb-4">Nouveau Client</h2>

      {/* Champ nom avec autocomplétion IA */}
      <AutocompleteField
        module="Clients"
        field="nom"
        value={formData.nom}
        onChange={(value) => setFormData((prev) => ({ ...prev, nom: value }))}
        label="Nom de l'entreprise"
        placeholder="Ex: ACME SARL"
        typeCompletion="nom_entreprise"
        required
        showSource
      />

      {/* Champ email */}
      <AutocompleteField
        module="Clients"
        field="email"
        value={formData.email}
        onChange={(value) => setFormData((prev) => ({ ...prev, email: value }))}
        label="Email"
        placeholder="contact@exemple.com"
        type="email"
        typeCompletion="email"
        contexte={{ nom: formData.nom }} // Passer le nom pour suggestions contextuelles
      />

      {/* Champ adresse */}
      <AutocompleteField
        module="Clients"
        field="adresse"
        value={formData.adresse}
        onChange={(value) => setFormData((prev) => ({ ...prev, adresse: value }))}
        label="Adresse"
        placeholder="123 rue de la Paix, 75001 Paris"
        typeCompletion="adresse"
      />

      {/* Champ description (textarea avec complétion) */}
      <AutocompleteField
        module="Clients"
        field="description"
        value={formData.description}
        onChange={(value) => setFormData((prev) => ({ ...prev, description: value }))}
        label="Description"
        placeholder="Description de l'activité..."
        multiline
        rows={4}
        typeCompletion="description"
      />

      <button
        type="submit"
        className="w-full bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700"
      >
        Créer le client
      </button>
    </form>
  );
}

/**
 * Exemple 2: Utilisation du hook seul
 *
 * Pour plus de contrôle, utilisez le hook directement
 */
export function ExampleWithHook() {
  const [value, setValue] = useState('');

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
  } = useAutocompletionIA({
    module: 'Clients',
    champ: 'nom',
    debounceMs: 300,
    minChars: 2,
    maxSuggestions: 5,
    typeCompletion: 'nom_entreprise',
    onSuggestionSelect: (suggestion) => {
      setValue(suggestion.texte);
      console.log('Suggestion sélectionnée:', suggestion);
    },
    onError: (error) => {
      console.error('Erreur autocomplétion:', error);
    },
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setValue(newValue);
    fetchSuggestions(newValue);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions) return;

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
        dismissSuggestions();
        break;
    }
  };

  return (
    <div className="max-w-lg mx-auto p-6">
      <h2 className="text-xl font-bold mb-4">Exemple avec Hook</h2>

      <div className="relative">
        <input
          type="text"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Tapez un nom d'entreprise..."
          className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
        />

        {isLoading && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">
            Chargement...
          </span>
        )}

        {showSuggestions && suggestions.length > 0 && (
          <ul className="absolute z-10 w-full mt-1 bg-white border rounded-lg shadow-lg">
            {suggestions.map((suggestion, index) => (
              <li
                key={suggestion.id}
                className={`px-4 py-2 cursor-pointer ${
                  index === selectedIndex ? 'bg-blue-50' : 'hover:bg-gray-50'
                }`}
                onClick={() => acceptSuggestion(suggestion)}
              >
                {suggestion.texte}
                <span className="text-xs text-gray-400 ml-2">
                  ({suggestion.source})
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Debug info */}
      {meta && (
        <div className="mt-4 p-4 bg-gray-100 rounded text-sm">
          <p>Provider: {meta.provider || 'N/A'}</p>
          <p>Modèle: {meta.model || 'N/A'}</p>
          <p>Latence: {meta.latency_ms}ms</p>
          <p>Cache: {meta.cached ? 'Oui' : 'Non'}</p>
        </div>
      )}
    </div>
  );
}

/**
 * Exemple 3: Formulaire complet d'intervention
 */
export function ExampleInterventionForm() {
  const [intervention, setIntervention] = useState({
    client: '',
    site: '',
    description: '',
    rapport: '',
  });

  const updateField = (field: string) => (value: string) => {
    setIntervention((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <form className="space-y-4 max-w-2xl mx-auto p-6 bg-white rounded-lg shadow">
      <h2 className="text-2xl font-bold mb-6">Nouvelle Intervention</h2>

      <div className="grid grid-cols-2 gap-4">
        <AutocompleteField
          module="Interventions"
          field="client"
          value={intervention.client}
          onChange={updateField('client')}
          label="Client"
          placeholder="Rechercher un client..."
          typeCompletion="nom_entreprise"
          required
        />

        <AutocompleteField
          module="Interventions"
          field="site"
          value={intervention.site}
          onChange={updateField('site')}
          label="Site d'intervention"
          placeholder="Adresse du site..."
          typeCompletion="adresse"
          contexte={{ client: intervention.client }}
        />
      </div>

      <AutocompleteField
        module="Interventions"
        field="description"
        value={intervention.description}
        onChange={updateField('description')}
        label="Description de l'intervention"
        placeholder="Décrivez l'objet de l'intervention..."
        multiline
        rows={3}
        typeCompletion="description"
      />

      <AutocompleteField
        module="Interventions"
        field="rapport"
        value={intervention.rapport}
        onChange={updateField('rapport')}
        label="Rapport d'intervention"
        placeholder="Rédigez le rapport... (Ctrl+Entrée pour compléter avec l'IA)"
        multiline
        rows={6}
        typeCompletion="description"
        contexte={{
          client: intervention.client,
          site: intervention.site,
          description: intervention.description,
        }}
      />

      <div className="flex justify-end gap-4 pt-4">
        <button
          type="button"
          className="px-4 py-2 border rounded-lg hover:bg-gray-50"
        >
          Annuler
        </button>
        <button
          type="submit"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Créer l'intervention
        </button>
      </div>
    </form>
  );
}

export default ExampleWithComponent;
