import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { RefreshCw, ExternalLink } from 'lucide-react';
import { useModuleConfig } from '../core/config/MobileConfigProvider';
import { TokenManager } from '../core/api/client';
import { Icon } from '../components/ui/Icon';

// URL de base du backend (moteur UI)
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://57.128.7.20:8000';

export default function ModulePage(): React.ReactElement {
  const { moduleId } = useParams<{ moduleId: string }>();
  const moduleConfig = useModuleConfig(moduleId || '');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // URL de l'UI du module (générée par le moteur)
  const token = TokenManager.getAccessToken();
  const moduleUrl = token
    ? `${BACKEND_URL}/ui/${moduleId}/?token=${encodeURIComponent(token)}`
    : `${BACKEND_URL}/ui/${moduleId}/`;

  // Gérer le chargement de l'iframe
  useEffect(() => {
    if (!iframeRef.current) return;

    const handleLoad = () => {
      setIsLoading(false);
    };

    const handleError = () => {
      setIsLoading(false);
      setError('Impossible de charger le module');
    };

    const iframe = iframeRef.current;
    iframe.addEventListener('load', handleLoad);
    iframe.addEventListener('error', handleError);

    return () => {
      iframe.removeEventListener('load', handleLoad);
      iframe.removeEventListener('error', handleError);
    };
  }, [moduleId]);

  // Rafraîchir l'iframe
  const handleRefresh = () => {
    setIsLoading(true);
    setError(null);
    if (iframeRef.current) {
      iframeRef.current.src = moduleUrl;
    }
  };

  // Ouvrir dans un nouvel onglet
  const handleOpenExternal = () => {
    window.open(moduleUrl, '_blank');
  };

  if (!moduleConfig) {
    return (
      <div className="flex flex-col items-center justify-center p-8 min-h-[50vh]">
        <div className="text-center">
          <h1 className="text-lg font-medium text-gray-900 mb-2">Module non trouve</h1>
          <p className="text-sm text-gray-500 mb-4">
            Le module "{moduleId}" n'existe pas ou n'est pas accessible.
          </p>
          <Link to="/" className="btn btn-primary">
            Retour a l'accueil
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full -m-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-white border-b border-gray-100">
        <div className="flex items-center gap-2">
          <Icon name={moduleConfig.icon || 'default'} size={24} />
          <span className="font-medium text-gray-700">{moduleConfig.displayName || moduleConfig.name}</span>
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
            <p className="text-sm text-gray-500">Chargement du module...</p>
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

      {/* Module iframe */}
      <iframe
        ref={iframeRef}
        src={moduleUrl}
        className={`flex-1 w-full border-0 ${isLoading || error ? 'hidden' : ''}`}
        title={moduleConfig.name}
        sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
        style={{ minHeight: 'calc(100vh - 180px)' }}
      />
    </div>
  );
}
