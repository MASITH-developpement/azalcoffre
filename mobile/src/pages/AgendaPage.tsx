import React, { useState, useRef } from 'react';
import { RefreshCw, Plus } from 'lucide-react';
import { TokenManager } from '../core/api/client';

// URL de base du backend (moteur UI)
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://57.128.7.20:8000';

export default function AgendaPage(): React.ReactElement {
  const [isLoading, setIsLoading] = useState(true);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // URL du calendrier avec token
  const token = TokenManager.getAccessToken();
  const calendarUrl = token
    ? `${BACKEND_URL}/ui/calendrier?token=${encodeURIComponent(token)}`
    : `${BACKEND_URL}/ui/calendrier`;

  // URL pour créer un nouveau RDV
  const newRdvUrl = token
    ? `${BACKEND_URL}/ui/agenda/nouveau?token=${encodeURIComponent(token)}`
    : `${BACKEND_URL}/ui/agenda/nouveau`;

  const handleLoad = () => {
    setIsLoading(false);
  };

  const handleRefresh = () => {
    setIsLoading(true);
    if (iframeRef.current) {
      iframeRef.current.src = calendarUrl;
    }
  };

  const handleNewRdv = () => {
    if (iframeRef.current) {
      iframeRef.current.src = newRdvUrl;
    }
  };

  return (
    <div className="flex flex-col h-full -m-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-white border-b border-gray-100">
        <span className="font-medium text-gray-700">Calendrier</span>
        <div className="flex items-center gap-1">
          <button
            onClick={handleNewRdv}
            className="flex items-center gap-1 px-3 py-1.5 bg-primary-500 text-white rounded-lg text-sm font-medium hover:bg-primary-600 active:scale-95 transition-all"
          >
            <Plus className="w-4 h-4" />
            Nouveau RDV
          </button>
          <button
            onClick={handleRefresh}
            className="p-2 rounded-full hover:bg-gray-100 active:scale-95 transition-transform"
            aria-label="Rafraichir"
          >
            <RefreshCw className={`w-5 h-5 text-gray-600 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center p-8">
          <div className="flex flex-col items-center gap-3">
            <RefreshCw className="w-6 h-6 text-primary-500 animate-spin" />
            <p className="text-sm text-gray-500">Chargement du calendrier...</p>
          </div>
        </div>
      )}

      {/* Calendar iframe */}
      <iframe
        ref={iframeRef}
        src={calendarUrl}
        onLoad={handleLoad}
        className={`flex-1 w-full border-0 ${isLoading ? 'hidden' : ''}`}
        title="Agenda"
        sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-modals"
        style={{ minHeight: 'calc(100vh - 180px)' }}
      />
    </div>
  );
}
