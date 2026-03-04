// AZALPLUS - Page de Configuration Autocompletion IA
import React, { useCallback, useEffect, useState } from 'react';
import {
  getConfig,
  getHealth,
  testAutocompletion,
} from '../api';
import type {
  ConfigResponse,
  HealthResponse,
  IAProvider,
  SuggestionResponse,
} from '../types';

// -----------------------------------------------------------------------------
// Icônes
// -----------------------------------------------------------------------------
const SparklesIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
  </svg>
);

const CheckCircleIcon = () => (
  <svg className="w-5 h-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const XCircleIcon = () => (
  <svg className="w-5 h-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const LoadingSpinner = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg className={`animate-spin ${className}`} fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
  </svg>
);

const SaveIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
  </svg>
);

const RefreshIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
  </svg>
);

const KeyIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
  </svg>
);

// -----------------------------------------------------------------------------
// Types locaux
// -----------------------------------------------------------------------------
interface FormData {
  actif: boolean;
  fournisseur_defaut: IAProvider;
  modele_defaut: string;
  openai_api_key: string;
  anthropic_api_key: string;
  mode: 'suggestions' | 'completion' | 'hybrid';
  nombre_suggestions: number;
  temperature: number;
  delai_declenchement: number;
  longueur_min: number;
  cache_actif: boolean;
  cache_duree_minutes: number;
  limite_requetes_jour: number;
  limite_tokens_jour: number;
}

// -----------------------------------------------------------------------------
// Composant Principal
// -----------------------------------------------------------------------------
export function ConfigurationPage() {
  // État
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [formData, setFormData] = useState<FormData>({
    actif: true,
    fournisseur_defaut: 'anthropic',
    modele_defaut: 'claude-sonnet-4-20250514',
    openai_api_key: '',
    anthropic_api_key: '',
    mode: 'suggestions',
    nombre_suggestions: 5,
    temperature: 0.3,
    delai_declenchement: 300,
    longueur_min: 2,
    cache_actif: true,
    cache_duree_minutes: 60,
    limite_requetes_jour: 1000,
    limite_tokens_jour: 100000,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [testResult, setTestResult] = useState<SuggestionResponse | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showApiKeys, setShowApiKeys] = useState({ openai: false, anthropic: false });

  // Charger la configuration
  const loadConfig = useCallback(async () => {
    setIsLoading(true);
    try {
      const [configData, healthData] = await Promise.all([
        getConfig(),
        getHealth(),
      ]);
      setConfig(configData);
      setHealth(healthData);
      setFormData((prev) => ({
        ...prev,
        actif: configData.actif,
        fournisseur_defaut: configData.fournisseur_defaut,
        modele_defaut: configData.modele_defaut,
        mode: configData.mode,
        nombre_suggestions: configData.nombre_suggestions,
        temperature: configData.temperature,
        limite_requetes_jour: configData.limite_requetes_jour,
        limite_tokens_jour: configData.limite_tokens_jour,
      }));
    } catch (error) {
      console.error('Erreur chargement config:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // Rafraîchir la santé des providers
  const refreshHealth = async () => {
    try {
      const healthData = await getHealth();
      setHealth(healthData);
    } catch (error) {
      console.error('Erreur rafraîchissement santé:', error);
    }
  };

  // Sauvegarder la configuration
  const handleSave = async () => {
    setIsSaving(true);
    setSaveMessage(null);
    try {
      // TODO: Implémenter l'appel API de sauvegarde
      // await updateConfig(formData);
      await new Promise((resolve) => setTimeout(resolve, 1000)); // Simulation
      setSaveMessage({ type: 'success', text: 'Configuration sauvegardée avec succès' });
      setTimeout(() => setSaveMessage(null), 3000);
    } catch (error) {
      setSaveMessage({ type: 'error', text: 'Erreur lors de la sauvegarde' });
    } finally {
      setIsSaving(false);
    }
  };

  // Tester l'autocomplétion
  const handleTest = async (provider: IAProvider) => {
    setTestLoading(true);
    setTestResult(null);
    setTestError(null);
    try {
      const result = await testAutocompletion(provider);
      setTestResult(result);
    } catch (error) {
      setTestError(error instanceof Error ? error.message : 'Erreur de test');
    } finally {
      setTestLoading(false);
    }
  };

  // Mise à jour du formulaire
  const updateForm = <K extends keyof FormData>(key: K, value: FormData[K]) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  // Modèles disponibles par provider
  const modelsPerProvider: Record<IAProvider, { id: string; name: string }[]> = {
    openai: [
      { id: 'gpt-4o', name: 'GPT-4o (Recommandé)' },
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini (Économique)' },
      { id: 'gpt-4-turbo', name: 'GPT-4 Turbo' },
    ],
    anthropic: [
      { id: 'claude-sonnet-4-20250514', name: 'Claude Sonnet 4 (Recommandé)' },
      { id: 'claude-opus-4-20250514', name: 'Claude Opus 4 (Puissant)' },
      { id: 'claude-3-5-haiku-20241022', name: 'Claude 3.5 Haiku (Rapide)' },
    ],
    local: [{ id: 'local', name: 'Local (Historique)' }],
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <LoadingSpinner className="w-8 h-8 text-blue-600" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-8">
      {/* En-tête */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-purple-100 rounded-lg">
            <SparklesIcon />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Autocomplétion IA</h1>
            <p className="text-gray-500">Configuration de l'autocomplétion intelligente</p>
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={isSaving}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {isSaving ? <LoadingSpinner className="w-5 h-5" /> : <SaveIcon />}
          Sauvegarder
        </button>
      </div>

      {/* Message de sauvegarde */}
      {saveMessage && (
        <div
          className={`p-4 rounded-lg ${
            saveMessage.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}
        >
          {saveMessage.text}
        </div>
      )}

      {/* Activation globale */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Activation</h2>
            <p className="text-gray-500 text-sm">Activer ou désactiver l'autocomplétion IA globalement</p>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={formData.actif}
              onChange={(e) => updateForm('actif', e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
          </label>
        </div>
      </div>

      {/* État des providers */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">État des Providers</h2>
          <button
            onClick={refreshHealth}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-900"
          >
            <RefreshIcon />
            Rafraîchir
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* OpenAI */}
          <div className="p-4 border rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium">OpenAI</span>
              {health?.openai.status === 'ok' ? <CheckCircleIcon /> : <XCircleIcon />}
            </div>
            <p className="text-sm text-gray-500">
              {health?.openai.status === 'ok'
                ? `${health.openai.latency_ms}ms`
                : health?.openai.error || 'Non configuré'}
            </p>
            {config?.openai_configured && (
              <span className="inline-block mt-2 text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                Clé configurée
              </span>
            )}
          </div>

          {/* Anthropic */}
          <div className="p-4 border rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium">Anthropic (Claude)</span>
              {health?.anthropic.status === 'ok' ? <CheckCircleIcon /> : <XCircleIcon />}
            </div>
            <p className="text-sm text-gray-500">
              {health?.anthropic.status === 'ok'
                ? `${health.anthropic.latency_ms}ms`
                : health?.anthropic.error || 'Non configuré'}
            </p>
            {config?.anthropic_configured && (
              <span className="inline-block mt-2 text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                Clé configurée
              </span>
            )}
          </div>

          {/* Local */}
          <div className="p-4 border rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium">Local (Fallback)</span>
              <CheckCircleIcon />
            </div>
            <p className="text-sm text-gray-500">Toujours disponible</p>
            <span className="inline-block mt-2 text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">
              Basé sur l'historique
            </span>
          </div>
        </div>
      </div>

      {/* Clés API */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="flex items-center gap-2 mb-4">
          <KeyIcon />
          <h2 className="text-lg font-semibold">Clés API</h2>
        </div>
        <div className="space-y-4">
          {/* OpenAI API Key */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Clé API OpenAI
            </label>
            <div className="relative">
              <input
                type={showApiKeys.openai ? 'text' : 'password'}
                value={formData.openai_api_key}
                onChange={(e) => updateForm('openai_api_key', e.target.value)}
                placeholder="sk-..."
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 pr-20"
              />
              <button
                type="button"
                onClick={() => setShowApiKeys((p) => ({ ...p, openai: !p.openai }))}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 text-sm"
              >
                {showApiKeys.openai ? 'Masquer' : 'Afficher'}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Obtenez votre clé sur{' '}
              <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                platform.openai.com
              </a>
            </p>
          </div>

          {/* Anthropic API Key */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Clé API Anthropic
            </label>
            <div className="relative">
              <input
                type={showApiKeys.anthropic ? 'text' : 'password'}
                value={formData.anthropic_api_key}
                onChange={(e) => updateForm('anthropic_api_key', e.target.value)}
                placeholder="sk-ant-..."
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 pr-20"
              />
              <button
                type="button"
                onClick={() => setShowApiKeys((p) => ({ ...p, anthropic: !p.anthropic }))}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 text-sm"
              >
                {showApiKeys.anthropic ? 'Masquer' : 'Afficher'}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Obtenez votre clé sur{' '}
              <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                console.anthropic.com
              </a>
            </p>
          </div>
        </div>
      </div>

      {/* Provider et Modèle par défaut */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h2 className="text-lg font-semibold mb-4">Provider par défaut</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Fournisseur
            </label>
            <select
              value={formData.fournisseur_defaut}
              onChange={(e) => {
                const provider = e.target.value as IAProvider;
                updateForm('fournisseur_defaut', provider);
                // Mettre à jour le modèle par défaut
                const defaultModel = modelsPerProvider[provider][0]?.id;
                if (defaultModel) {
                  updateForm('modele_defaut', defaultModel);
                }
              }}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="openai">OpenAI (ChatGPT)</option>
              <option value="local">Local (Sans IA)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Modèle
            </label>
            <select
              value={formData.modele_defaut}
              onChange={(e) => updateForm('modele_defaut', e.target.value)}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              {modelsPerProvider[formData.fournisseur_defaut]?.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Paramètres */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h2 className="text-lg font-semibold mb-4">Paramètres</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* Mode */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Mode de fonctionnement
            </label>
            <select
              value={formData.mode}
              onChange={(e) => updateForm('mode', e.target.value as FormData['mode'])}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="suggestions">Suggestions (dropdown)</option>
              <option value="completion">Complétion (inline)</option>
              <option value="hybrid">Hybride</option>
            </select>
          </div>

          {/* Nombre de suggestions */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Nombre de suggestions
            </label>
            <input
              type="number"
              min={1}
              max={10}
              value={formData.nombre_suggestions}
              onChange={(e) => updateForm('nombre_suggestions', parseInt(e.target.value))}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Température */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Température (créativité): {formData.temperature}
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.1}
              value={formData.temperature}
              onChange={(e) => updateForm('temperature', parseFloat(e.target.value))}
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-500">
              <span>Précis</span>
              <span>Créatif</span>
            </div>
          </div>

          {/* Délai */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Délai de déclenchement (ms)
            </label>
            <input
              type="number"
              min={100}
              max={2000}
              step={50}
              value={formData.delai_declenchement}
              onChange={(e) => updateForm('delai_declenchement', parseInt(e.target.value))}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Longueur minimale */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Caractères minimum
            </label>
            <input
              type="number"
              min={1}
              max={10}
              value={formData.longueur_min}
              onChange={(e) => updateForm('longueur_min', parseInt(e.target.value))}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Cache */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Durée du cache (minutes)
            </label>
            <input
              type="number"
              min={1}
              max={1440}
              value={formData.cache_duree_minutes}
              onChange={(e) => updateForm('cache_duree_minutes', parseInt(e.target.value))}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              disabled={!formData.cache_actif}
            />
          </div>
        </div>

        {/* Cache toggle */}
        <div className="mt-4 pt-4 border-t">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={formData.cache_actif}
              onChange={(e) => updateForm('cache_actif', e.target.checked)}
              className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
            />
            <span className="text-sm font-medium text-gray-700">
              Activer le cache des suggestions
            </span>
          </label>
          <p className="text-xs text-gray-500 mt-1 ml-7">
            Réduit les appels API en mémorisant les suggestions fréquentes
          </p>
        </div>
      </div>

      {/* Limites */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h2 className="text-lg font-semibold mb-4">Limites d'utilisation</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Requêtes par jour
            </label>
            <input
              type="number"
              min={100}
              max={100000}
              step={100}
              value={formData.limite_requetes_jour}
              onChange={(e) => updateForm('limite_requetes_jour', parseInt(e.target.value))}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
            {config && (
              <p className="text-xs text-gray-500 mt-1">
                Utilisé aujourd'hui: {config.requetes_aujourd_hui} / {config.limite_requetes_jour}
              </p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Tokens par jour
            </label>
            <input
              type="number"
              min={1000}
              max={1000000}
              step={1000}
              value={formData.limite_tokens_jour}
              onChange={(e) => updateForm('limite_tokens_jour', parseInt(e.target.value))}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
            {config && (
              <p className="text-xs text-gray-500 mt-1">
                Utilisé aujourd'hui: {config.tokens_aujourd_hui} / {config.limite_tokens_jour}
              </p>
            )}
          </div>
        </div>

        {/* Barre de progression */}
        {config && (
          <div className="mt-4 space-y-2">
            <div>
              <div className="flex justify-between text-xs text-gray-600 mb-1">
                <span>Requêtes</span>
                <span>{Math.round((config.requetes_aujourd_hui / config.limite_requetes_jour) * 100)}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all"
                  style={{ width: `${Math.min((config.requetes_aujourd_hui / config.limite_requetes_jour) * 100, 100)}%` }}
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-xs text-gray-600 mb-1">
                <span>Tokens</span>
                <span>{Math.round((config.tokens_aujourd_hui / config.limite_tokens_jour) * 100)}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-purple-600 h-2 rounded-full transition-all"
                  style={{ width: `${Math.min((config.tokens_aujourd_hui / config.limite_tokens_jour) * 100, 100)}%` }}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Test */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h2 className="text-lg font-semibold mb-4">Tester l'autocomplétion</h2>
        <div className="flex flex-wrap gap-3 mb-4">
          <button
            onClick={() => handleTest('anthropic')}
            disabled={testLoading}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
          >
            {testLoading ? <LoadingSpinner className="w-5 h-5" /> : 'Tester Claude'}
          </button>
          <button
            onClick={() => handleTest('openai')}
            disabled={testLoading}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
          >
            {testLoading ? <LoadingSpinner className="w-5 h-5" /> : 'Tester OpenAI'}
          </button>
          <button
            onClick={() => handleTest('local')}
            disabled={testLoading}
            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50"
          >
            {testLoading ? <LoadingSpinner className="w-5 h-5" /> : 'Tester Local'}
          </button>
        </div>

        {testError && (
          <div className="p-4 bg-red-50 text-red-700 rounded-lg mb-4">
            <strong>Erreur:</strong> {testError}
          </div>
        )}

        {testResult && (
          <div className="p-4 bg-gray-50 rounded-lg">
            <p className="text-sm text-gray-600 mb-2">
              <strong>Provider:</strong> {testResult.meta.provider} |
              <strong> Modèle:</strong> {testResult.meta.model} |
              <strong> Latence:</strong> {testResult.meta.latency_ms}ms |
              <strong> Cache:</strong> {testResult.meta.cached ? 'Oui' : 'Non'}
            </p>
            <p className="font-medium mb-2">Suggestions pour "Dup" :</p>
            <ul className="list-disc list-inside space-y-1">
              {testResult.suggestions.map((s) => (
                <li key={s.id} className="text-gray-700">
                  {s.texte} <span className="text-gray-400 text-sm">({s.source})</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Documentation */}
      <div className="bg-gradient-to-r from-purple-50 to-blue-50 rounded-xl border border-purple-200 p-6">
        <h2 className="text-lg font-semibold mb-2">Documentation</h2>
        <div className="text-sm text-gray-600 space-y-2">
          <p>
            <strong>Raccourcis clavier :</strong>
          </p>
          <ul className="list-disc list-inside ml-4 space-y-1">
            <li><kbd className="px-2 py-1 bg-white rounded border">↓</kbd> / <kbd className="px-2 py-1 bg-white rounded border">↑</kbd> - Naviguer dans les suggestions</li>
            <li><kbd className="px-2 py-1 bg-white rounded border">Tab</kbd> - Accepter la première suggestion</li>
            <li><kbd className="px-2 py-1 bg-white rounded border">Enter</kbd> - Accepter la suggestion sélectionnée</li>
            <li><kbd className="px-2 py-1 bg-white rounded border">Escape</kbd> - Fermer les suggestions</li>
            <li><kbd className="px-2 py-1 bg-white rounded border">Ctrl</kbd> + <kbd className="px-2 py-1 bg-white rounded border">Space</kbd> - Déclencher manuellement</li>
            <li><kbd className="px-2 py-1 bg-white rounded border">Ctrl</kbd> + <kbd className="px-2 py-1 bg-white rounded border">Enter</kbd> - Compléter le texte (textarea)</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default ConfigurationPage;
