import React, { useState, useEffect } from 'react';
import { WifiOff, Wifi, Trash2, X, CheckCircle } from 'lucide-react';
import { OfflineQueue, QueuedRequest } from '../core/api/client';

export default function OfflinePage(): React.ReactElement {
  const [queuedRequests, setQueuedRequests] = useState<QueuedRequest[]>([]);
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    // Load queued requests
    setQueuedRequests(OfflineQueue.getAll());

    // Listen for online/offline status
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const handleClearQueue = () => {
    OfflineQueue.clear();
    setQueuedRequests([]);
  };

  const handleRemoveRequest = (id: string) => {
    OfflineQueue.remove(id);
    setQueuedRequests(queuedRequests.filter((req) => req.id !== id));
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp).toLocaleString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="p-4 space-y-6">
      {/* Connection Status */}
      <section>
        <div className={`card p-4 flex items-center gap-3 ${isOnline ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'}`}>
          {isOnline ? (
            <Wifi className="w-6 h-6 text-green-500 flex-shrink-0" />
          ) : (
            <WifiOff className="w-6 h-6 text-yellow-500 flex-shrink-0" />
          )}
          <div className="flex-1 min-w-0">
            <h3 className={`font-medium ${isOnline ? 'text-green-700' : 'text-yellow-700'}`}>
              {isOnline ? 'En ligne' : 'Hors ligne'}
            </h3>
            <p className={`text-sm ${isOnline ? 'text-green-600' : 'text-yellow-600'}`}>
              {isOnline
                ? 'Vous etes connecte a Internet'
                : 'Les modifications seront synchronisees une fois en ligne'}
            </p>
          </div>
        </div>
      </section>

      {/* Queued Requests */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-gray-500">
            Requetes en attente ({queuedRequests.length})
          </h2>
          {queuedRequests.length > 0 && (
            <button
              onClick={handleClearQueue}
              className="flex items-center gap-1 text-sm text-red-600"
            >
              <Trash2 className="w-4 h-4" />
              <span className="hidden sm:inline">Tout effacer</span>
            </button>
          )}
        </div>

        {queuedRequests.length === 0 ? (
          <div className="card p-6">
            <div className="flex flex-col items-center text-center">
              <CheckCircle className="w-12 h-12 text-green-300 mb-3" />
              <h3 className="font-medium text-gray-900">Aucune requete en attente</h3>
              <p className="text-sm text-gray-500 mt-1">
                Toutes les modifications ont ete synchronisees.
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {queuedRequests.map((request) => (
              <div key={request.id} className="card p-3 sm:p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`badge text-xs ${
                        request.method === 'POST' ? 'badge-success' :
                        request.method === 'PUT' ? 'badge-warning' :
                        request.method === 'DELETE' ? 'badge-error' :
                        'badge-primary'
                      }`}>
                        {request.method}
                      </span>
                      {request.retryCount > 0 && (
                        <span className="text-xs text-orange-500">
                          Tentative {request.retryCount + 1}
                        </span>
                      )}
                    </div>
                    <p className="font-mono text-xs sm:text-sm text-gray-600 mt-2 truncate">
                      {request.url}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      {formatDate(request.timestamp)}
                    </p>
                  </div>
                  <button
                    onClick={() => handleRemoveRequest(request.id)}
                    className="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-red-500 flex-shrink-0 active:scale-95 transition-transform"
                    aria-label="Supprimer"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Storage Info */}
      <section>
        <h2 className="text-sm font-medium text-gray-500 mb-3">Stockage local</h2>
        <div className="card divide-y divide-gray-100">
          <div className="p-4 flex items-center justify-between gap-3">
            <span className="text-gray-600">Donnees en cache</span>
            <span className="text-gray-900">Calcul en cours...</span>
          </div>
          <div className="p-4">
            <button className="text-red-600 text-sm active:opacity-70 transition-opacity">
              Vider le cache
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
