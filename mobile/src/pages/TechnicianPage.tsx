/**
 * Technician Dashboard Page
 *
 * Displays the technician dashboard in an iframe.
 * This is a special view for field technicians to manage their interventions.
 */

import React, { useState, useRef } from 'react';
import { RefreshCw, ExternalLink } from 'lucide-react';
import { TokenManager } from '../core/api/client';

// URL de base du backend (moteur UI)
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://57.128.7.20:8000';

export default function TechnicianPage(): React.ReactElement {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // URL de la vue technicien (pas de slash final pour éviter la redirection qui perd le token)
  const token = TokenManager.getAccessToken();
  const technicianUrl = token
    ? `${BACKEND_URL}/ui/technicien/dashboard?token=${encodeURIComponent(token)}`
    : `${BACKEND_URL}/ui/technicien/dashboard`;

  // Rafraîchir l'iframe
  const handleRefresh = () => {
    setIsLoading(true);
    setError(null);
    if (iframeRef.current) {
      iframeRef.current.src = technicianUrl;
    }
  };

  // Ouvrir dans un nouvel onglet
  const handleOpenExternal = () => {
    window.open(technicianUrl, '_blank');
  };

  // Gérer le chargement de l'iframe
  const handleLoad = () => {
    setIsLoading(false);
  };

  const handleError = () => {
    setIsLoading(false);
    setError('Impossible de charger le tableau de bord technicien');
  };

  return (
    <div className="flex flex-col h-full -m-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-white border-b border-gray-100">
        <div className="flex items-center gap-2">
          <svg className="w-6 h-6 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span className="font-medium text-gray-700">Espace Technicien</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleRefresh}
            className="p-2 rounded-full hover:bg-gray-100 active:scale-95 transition-transform"
            aria-label="Rafraichir"
          >
            <RefreshCw className={`w-5 h-5 text-gray-600 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={handleOpenExternal}
            className="p-2 rounded-full hover:bg-gray-100 active:scale-95 transition-transform"
            aria-label="Ouvrir dans un nouvel onglet"
          >
            <ExternalLink className="w-5 h-5 text-gray-600" />
          </button>
        </div>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center p-8">
          <div className="flex flex-col items-center gap-3">
            <RefreshCw className="w-6 h-6 text-primary-500 animate-spin" />
            <p className="text-sm text-gray-500">Chargement...</p>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && !isLoading && (
        <div className="flex flex-col items-center justify-center p-8">
          <p className="text-error-500 mb-3">{error}</p>
          <button onClick={handleRefresh} className="btn btn-secondary text-sm">
            Reessayer
          </button>
        </div>
      )}

      {/* Technician iframe */}
      <iframe
        ref={iframeRef}
        src={technicianUrl}
        className={`flex-1 w-full border-0 ${isLoading || error ? 'hidden' : ''}`}
        title="Espace Technicien"
        sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-modals"
        style={{ minHeight: 'calc(100vh - 180px)' }}
        onLoad={handleLoad}
        onError={handleError}
      />
    </div>
  );
}
