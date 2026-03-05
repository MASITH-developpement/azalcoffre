/**
 * Portal Dashboard Page
 *
 * Client dashboard with summary cards for invoices, quotes, and interventions.
 */

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { usePortalAuth, usePortalApi } from './hooks/usePortalAuth';

interface DashboardData {
  invoices_pending: number;
  invoices_paid: number;
  invoices_total_pending: number;
  quotes_pending: number;
  quotes_accepted: number;
  interventions_planned: number;
  interventions_completed: number;
}

export const PortalDashboard: React.FC = () => {
  const { client } = usePortalAuth();
  const { fetchWithAuth } = usePortalApi();
  const [data, setData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        setIsLoading(true);
        const result = await fetchWithAuth<DashboardData>('/portal/dashboard');
        setData(result);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Erreur de chargement');
      } finally {
        setIsLoading(false);
      }
    };

    loadDashboard();
  }, [fetchWithAuth]);

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('fr-FR', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  };

  if (isLoading) {
    return (
      <div className="p-4 space-y-4">
        <div className="h-8 w-48 bg-gray-200 rounded animate-pulse" />
        <div className="grid grid-cols-1 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
              <div className="h-4 w-24 bg-gray-200 rounded animate-pulse mb-2" />
              <div className="h-8 w-32 bg-gray-200 rounded animate-pulse" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="bg-red-50 text-red-600 rounded-lg p-4 text-sm">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-6">
      {/* Welcome Section */}
      <div className="mb-2">
        <h1 className="text-xl font-bold text-gray-900">
          Bonjour{client?.client_name ? `, ${client.client_name}` : ''}
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Voici un apercu de votre espace client
        </p>
      </div>

      {/* Invoices Section */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">Factures</h2>
          <Link to="/portal/invoices" className="text-sm text-primary-600 font-medium">
            Voir tout
          </Link>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          {data && data.invoices_total_pending > 0 ? (
            <Link to="/portal/invoices?status=ENVOYEE" className="block p-4 hover:bg-gray-50 transition-colors">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center flex-shrink-0">
                  <svg className="w-6 h-6 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">A payer</p>
                  <p className="text-2xl font-bold text-amber-600">
                    {formatCurrency(data.invoices_total_pending)}
                  </p>
                </div>
                <div className="flex-shrink-0">
                  <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-amber-100 text-amber-600 font-semibold text-sm">
                    {data.invoices_pending}
                  </span>
                </div>
              </div>
            </Link>
          ) : (
            <div className="p-4 text-center">
              <div className="w-12 h-12 rounded-xl bg-green-100 flex items-center justify-center mx-auto mb-2">
                <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-sm text-gray-500">Aucune facture en attente</p>
            </div>
          )}

          <div className="border-t border-gray-100 px-4 py-3 bg-gray-50 flex items-center justify-between">
            <span className="text-xs text-gray-500">
              {data?.invoices_paid || 0} facture(s) payee(s)
            </span>
            <Link to="/portal/invoices" className="text-xs text-primary-600 font-medium">
              Historique
            </Link>
          </div>
        </div>
      </section>

      {/* Quotes Section */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">Devis</h2>
          <Link to="/portal/quotes" className="text-sm text-primary-600 font-medium">
            Voir tout
          </Link>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          {data && data.quotes_pending > 0 ? (
            <Link to="/portal/quotes?status=ENVOYE" className="block p-4 hover:bg-gray-50 transition-colors">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-blue-100 flex items-center justify-center flex-shrink-0">
                  <svg className="w-6 h-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">Devis en attente</p>
                  <p className="text-xl font-bold text-blue-600">
                    {data.quotes_pending} devis
                  </p>
                </div>
                <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </Link>
          ) : (
            <div className="p-4 text-center">
              <p className="text-sm text-gray-500">Aucun devis en attente</p>
            </div>
          )}

          <div className="border-t border-gray-100 px-4 py-3 bg-gray-50 flex items-center justify-between">
            <span className="text-xs text-gray-500">
              {data?.quotes_accepted || 0} devis accepte(s)
            </span>
            <Link to="/portal/quotes" className="text-xs text-primary-600 font-medium">
              Historique
            </Link>
          </div>
        </div>
      </section>

      {/* Interventions Section */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">Interventions</h2>
          <Link to="/portal/interventions" className="text-sm text-primary-600 font-medium">
            Voir tout
          </Link>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          {data && data.interventions_planned > 0 ? (
            <Link to="/portal/interventions?status=PLANIFIEE" className="block p-4 hover:bg-gray-50 transition-colors">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-purple-100 flex items-center justify-center flex-shrink-0">
                  <svg className="w-6 h-6 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">Interventions prevues</p>
                  <p className="text-xl font-bold text-purple-600">
                    {data.interventions_planned} intervention(s)
                  </p>
                </div>
                <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </Link>
          ) : (
            <div className="p-4 text-center">
              <p className="text-sm text-gray-500">Aucune intervention prevue</p>
            </div>
          )}

          <div className="border-t border-gray-100 px-4 py-3 bg-gray-50 flex items-center justify-between">
            <span className="text-xs text-gray-500">
              {data?.interventions_completed || 0} intervention(s) terminee(s)
            </span>
            <Link to="/portal/interventions" className="text-xs text-primary-600 font-medium">
              Historique
            </Link>
          </div>
        </div>
      </section>

      {/* Quick Actions */}
      <section className="pt-2">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Acces rapide</h2>
        <div className="grid grid-cols-2 gap-3">
          <Link
            to="/portal/invoices"
            className="bg-white rounded-xl p-4 shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
          >
            <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center mb-2">
              <svg className="w-5 h-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <p className="text-sm font-medium text-gray-900">Mes factures</p>
          </Link>

          <Link
            to="/portal/quotes"
            className="bg-white rounded-xl p-4 shadow-sm border border-gray-100 hover:shadow-md transition-shadow"
          >
            <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center mb-2">
              <svg className="w-5 h-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
              </svg>
            </div>
            <p className="text-sm font-medium text-gray-900">Mes devis</p>
          </Link>
        </div>
      </section>
    </div>
  );
};

export default PortalDashboard;
