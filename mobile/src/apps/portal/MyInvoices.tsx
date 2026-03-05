/**
 * My Invoices Page
 *
 * List of client's invoices with status, amount, and download.
 */

import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { usePortalApi } from './hooks/usePortalAuth';

interface Invoice {
  id: string;
  numero: string;
  date: string | null;
  date_echeance: string | null;
  montant_ttc: number;
  montant_paye: number;
  reste_a_payer: number;
  statut: string;
  pdf_url?: string;
}

type StatusConfig = { label: string; color: string; bg: string };

const STATUS_CONFIG: { [key: string]: StatusConfig } & { BROUILLON: StatusConfig } = {
  BROUILLON: { label: 'Brouillon', color: 'text-gray-600', bg: 'bg-gray-100' },
  ENVOYEE: { label: 'A payer', color: 'text-amber-600', bg: 'bg-amber-100' },
  PARTIELLE: { label: 'Partiel', color: 'text-orange-600', bg: 'bg-orange-100' },
  PAYEE: { label: 'Payee', color: 'text-green-600', bg: 'bg-green-100' },
  ANNULEE: { label: 'Annulee', color: 'text-red-600', bg: 'bg-red-100' },
};

export const MyInvoices: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { fetchWithAuth } = usePortalApi();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const currentStatus = searchParams.get('status') || '';

  useEffect(() => {
    const loadInvoices = async () => {
      try {
        setIsLoading(true);
        const url = currentStatus
          ? `/portal/invoices?status=${currentStatus}`
          : '/portal/invoices';
        const result = await fetchWithAuth<{ items: Invoice[] }>(url);
        setInvoices(result.items);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Erreur de chargement');
      } finally {
        setIsLoading(false);
      }
    };

    loadInvoices();
  }, [fetchWithAuth, currentStatus]);

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

  const getStatusConfig = (status: string): StatusConfig => {
    return STATUS_CONFIG[status] ?? STATUS_CONFIG.BROUILLON;
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
        <h1 className="text-xl font-bold text-gray-900">Mes factures</h1>
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
          Toutes
        </button>
        <button
          onClick={() => handleFilterChange('ENVOYEE')}
          className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            currentStatus === 'ENVOYEE'
              ? 'bg-amber-600 text-white'
              : 'bg-amber-50 text-amber-600 hover:bg-amber-100'
          }`}
        >
          A payer
        </button>
        <button
          onClick={() => handleFilterChange('PAYEE')}
          className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            currentStatus === 'PAYEE'
              ? 'bg-green-600 text-white'
              : 'bg-green-50 text-green-600 hover:bg-green-100'
          }`}
        >
          Payees
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 text-red-600 rounded-lg p-4 text-sm">
          {error}
        </div>
      )}

      {/* Invoices List */}
      {invoices.length === 0 ? (
        <div className="bg-white rounded-xl p-8 text-center shadow-sm border border-gray-100">
          <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <p className="text-gray-500">Aucune facture trouvee</p>
        </div>
      ) : (
        <div className="space-y-3">
          {invoices.map((invoice) => {
            const statusConfig = getStatusConfig(invoice.statut);

            return (
              <Link
                key={invoice.id}
                to={`/portal/invoices/${invoice.id}`}
                className="block bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden hover:shadow-md transition-shadow"
              >
                <div className="p-4">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <p className="font-semibold text-gray-900">{invoice.numero}</p>
                      <p className="text-sm text-gray-500">
                        {formatDate(invoice.date)}
                      </p>
                    </div>
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${statusConfig.bg} ${statusConfig.color}`}>
                      {statusConfig.label}
                    </span>
                  </div>

                  <div className="flex items-end justify-between">
                    <div>
                      <p className="text-xs text-gray-400">Montant TTC</p>
                      <p className="text-lg font-bold text-gray-900">
                        {formatCurrency(invoice.montant_ttc)}
                      </p>
                    </div>

                    {invoice.reste_a_payer > 0 && invoice.reste_a_payer < invoice.montant_ttc && (
                      <div className="text-right">
                        <p className="text-xs text-gray-400">Reste a payer</p>
                        <p className="text-sm font-semibold text-amber-600">
                          {formatCurrency(invoice.reste_a_payer)}
                        </p>
                      </div>
                    )}

                    {invoice.date_echeance && invoice.statut === 'ENVOYEE' && (
                      <div className="text-right">
                        <p className="text-xs text-gray-400">Echeance</p>
                        <p className="text-sm text-gray-600">
                          {formatDate(invoice.date_echeance)}
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {invoice.pdf_url && (
                  <div className="border-t border-gray-100 px-4 py-2 bg-gray-50 flex items-center justify-between">
                    <span className="text-xs text-gray-500">PDF disponible</span>
                    <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default MyInvoices;
