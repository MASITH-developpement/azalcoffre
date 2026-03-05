/**
 * My Quotes Page
 *
 * List of client's quotes with accept/reject buttons.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { usePortalApi } from './hooks/usePortalAuth';

interface Quote {
  id: string;
  numero: string;
  date: string | null;
  date_validite: string | null;
  objet: string | null;
  montant_ttc: number;
  statut: string;
  view_url?: string;
}

type StatusConfig = { label: string; color: string; bg: string };

const STATUS_CONFIG: { [key: string]: StatusConfig } & { BROUILLON: StatusConfig } = {
  BROUILLON: { label: 'Brouillon', color: 'text-gray-600', bg: 'bg-gray-100' },
  ENVOYE: { label: 'En attente', color: 'text-blue-600', bg: 'bg-blue-100' },
  ACCEPTE: { label: 'Accepte', color: 'text-green-600', bg: 'bg-green-100' },
  REFUSE: { label: 'Refuse', color: 'text-red-600', bg: 'bg-red-100' },
  EXPIRE: { label: 'Expire', color: 'text-gray-600', bg: 'bg-gray-100' },
};

export const MyQuotes: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { fetchWithAuth } = usePortalApi();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const currentStatus = searchParams.get('status') || '';

  const loadQuotes = useCallback(async () => {
    try {
      setIsLoading(true);
      const url = currentStatus
        ? `/portal/quotes?status=${currentStatus}`
        : '/portal/quotes';
      const result = await fetchWithAuth<{ items: Quote[] }>(url);
      setQuotes(result.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de chargement');
    } finally {
      setIsLoading(false);
    }
  }, [fetchWithAuth, currentStatus]);

  useEffect(() => {
    loadQuotes();
  }, [loadQuotes]);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('fr-FR', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  };

  const handleFilterChange = (status: string) => {
    if (status) {
      setSearchParams({ status });
    } else {
      setSearchParams({});
    }
  };

  const handleAcceptQuote = async (quoteId: string, accepted: boolean) => {
    try {
      setActionLoading(quoteId);
      await fetchWithAuth(`/portal/quotes/${quoteId}/accept`, {
        method: 'POST',
        body: JSON.stringify({ accepted }),
      });
      // Reload quotes
      await loadQuotes();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur');
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusConfig = (status: string): StatusConfig => {
    return STATUS_CONFIG[status] ?? STATUS_CONFIG.BROUILLON;
  };

  const isExpired = (dateValidite: string | null) => {
    if (!dateValidite) return false;
    return new Date(dateValidite) < new Date();
  };

  if (isLoading) {
    return (
      <div className="p-4 space-y-4">
        <div className="h-8 w-32 bg-gray-200 rounded animate-pulse" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
            <div className="h-4 w-24 bg-gray-200 rounded animate-pulse mb-2" />
            <div className="h-6 w-32 bg-gray-200 rounded animate-pulse" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Mes devis</h1>
      </div>

      {/* Filters */}
      <div className="flex gap-2 overflow-x-auto pb-2 -mx-4 px-4">
        <button
          onClick={() => handleFilterChange('')}
          className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            !currentStatus
              ? 'bg-primary-600 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Tous
        </button>
        <button
          onClick={() => handleFilterChange('ENVOYE')}
          className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            currentStatus === 'ENVOYE'
              ? 'bg-blue-600 text-white'
              : 'bg-blue-50 text-blue-600 hover:bg-blue-100'
          }`}
        >
          En attente
        </button>
        <button
          onClick={() => handleFilterChange('ACCEPTE')}
          className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            currentStatus === 'ACCEPTE'
              ? 'bg-green-600 text-white'
              : 'bg-green-50 text-green-600 hover:bg-green-100'
          }`}
        >
          Acceptes
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 text-red-600 rounded-lg p-4 text-sm">
          {error}
        </div>
      )}

      {/* Quotes List */}
      {quotes.length === 0 ? (
        <div className="bg-white rounded-xl p-8 text-center shadow-sm border border-gray-100">
          <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <p className="text-gray-500">Aucun devis trouve</p>
        </div>
      ) : (
        <div className="space-y-3">
          {quotes.map((quote) => {
            const statusConfig = getStatusConfig(quote.statut);
            const expired = isExpired(quote.date_validite) && quote.statut === 'ENVOYE';
            const canRespond = quote.statut === 'ENVOYE' && !expired;

            return (
              <div
                key={quote.id}
                className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden"
              >
                <Link
                  to={`/portal/quotes/${quote.id}`}
                  className="block p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <p className="font-semibold text-gray-900">{quote.numero}</p>
                      {quote.objet && (
                        <p className="text-sm text-gray-500 mt-0.5 line-clamp-1">
                          {quote.objet}
                        </p>
                      )}
                    </div>
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${statusConfig.bg} ${statusConfig.color}`}>
                      {expired ? 'Expire' : statusConfig.label}
                    </span>
                  </div>

                  <div className="flex items-end justify-between">
                    <div>
                      <p className="text-xs text-gray-400">Montant TTC</p>
                      <p className="text-lg font-bold text-gray-900">
                        {formatCurrency(quote.montant_ttc)}
                      </p>
                    </div>

                    <div className="text-right">
                      <p className="text-xs text-gray-400">
                        {quote.statut === 'ENVOYE' ? 'Valide jusqu\'au' : 'Date'}
                      </p>
                      <p className={`text-sm ${expired ? 'text-red-600 font-medium' : 'text-gray-600'}`}>
                        {formatDate(quote.date_validite || quote.date)}
                      </p>
                    </div>
                  </div>
                </Link>

                {/* Action Buttons for pending quotes */}
                {canRespond && (
                  <div className="border-t border-gray-100 p-3 flex gap-2">
                    <button
                      onClick={() => handleAcceptQuote(quote.id, true)}
                      disabled={actionLoading === quote.id}
                      className="flex-1 bg-green-600 text-white py-2 px-4 rounded-lg font-medium text-sm hover:bg-green-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                    >
                      {actionLoading === quote.id ? (
                        <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <>
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                          Accepter
                        </>
                      )}
                    </button>
                    <button
                      onClick={() => handleAcceptQuote(quote.id, false)}
                      disabled={actionLoading === quote.id}
                      className="flex-1 bg-white text-red-600 py-2 px-4 rounded-lg font-medium text-sm border border-red-200 hover:bg-red-50 transition-colors disabled:opacity-50 flex items-center justify-center gap-1"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                      Refuser
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default MyQuotes;
