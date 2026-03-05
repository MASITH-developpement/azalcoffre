/**
 * Invoice Detail Page
 *
 * Detailed invoice view with line items and PDF download.
 */

import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { usePortalApi } from './hooks/usePortalAuth';

interface InvoiceLine {
  description: string;
  quantite: number;
  prix_unitaire: number;
  remise?: number;
  montant?: number;
}

interface InvoiceDetail {
  id: string;
  numero: string;
  date: string | null;
  echeance: string | null;
  objet?: string;
  total_ht: number;
  tva?: number;
  total_ttc: number;
  montant_paye?: number;
  statut: string;
  lignes?: InvoiceLine[];
  notes?: string;
  conditions?: string;
  pdf_url?: string;
  tenant_nom?: string;
  tenant_adresse?: string;
  tenant_email?: string;
  tenant_telephone?: string;
  tenant_siret?: string;
}

type StatusConfig = { label: string; color: string; bg: string };

const STATUS_CONFIG: { [key: string]: StatusConfig } & { BROUILLON: StatusConfig } = {
  BROUILLON: { label: 'Brouillon', color: 'text-gray-600', bg: 'bg-gray-100' },
  ENVOYEE: { label: 'A payer', color: 'text-amber-600', bg: 'bg-amber-100' },
  PARTIELLE: { label: 'Partiel', color: 'text-orange-600', bg: 'bg-orange-100' },
  PAYEE: { label: 'Payee', color: 'text-green-600', bg: 'bg-green-100' },
  ANNULEE: { label: 'Annulee', color: 'text-red-600', bg: 'bg-red-100' },
};

export const InvoiceDetailPage: React.FC = () => {
  const { invoiceId } = useParams<{ invoiceId: string }>();
  const navigate = useNavigate();
  const { fetchWithAuth } = usePortalApi();
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadInvoice = async () => {
      if (!invoiceId) return;

      try {
        setIsLoading(true);
        const result = await fetchWithAuth<InvoiceDetail>(`/portal/invoices/${invoiceId}`);
        setInvoice(result);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Erreur de chargement');
      } finally {
        setIsLoading(false);
      }
    };

    loadInvoice();
  }, [fetchWithAuth, invoiceId]);

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  };

  const formatCurrency = (amount: number | undefined) => {
    if (amount === undefined) return '-';
    return new Intl.NumberFormat('fr-FR', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  };

  const handleDownloadPdf = () => {
    if (invoice?.pdf_url) {
      window.open(invoice.pdf_url, '_blank');
    }
  };

  const getStatusConfig = (status: string): StatusConfig => {
    return STATUS_CONFIG[status] ?? STATUS_CONFIG.BROUILLON;
  };

  if (isLoading) {
    return (
      <div className="p-4 space-y-4">
        <div className="h-8 w-32 bg-gray-200 rounded animate-pulse" />
        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100 space-y-4">
          <div className="h-6 w-48 bg-gray-200 rounded animate-pulse" />
          <div className="h-4 w-32 bg-gray-200 rounded animate-pulse" />
          <div className="h-24 bg-gray-200 rounded animate-pulse" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="bg-red-50 text-red-600 rounded-lg p-4 text-sm mb-4">
          {error}
        </div>
        <button
          onClick={() => navigate('/portal/invoices')}
          className="text-primary-600 font-medium"
        >
          Retour aux factures
        </button>
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="p-4">
        <div className="bg-gray-50 text-gray-600 rounded-lg p-4 text-sm">
          Facture non trouvee
        </div>
      </div>
    );
  }

  const statusConfig = getStatusConfig(invoice.statut);
  const lignes = invoice.lignes || [];
  const tvaRate = invoice.tva || 20;
  const tvaAmount = invoice.total_ttc - invoice.total_ht;
  const resteAPayer = invoice.total_ttc - (invoice.montant_paye || 0);

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/portal/invoices')}
          className="p-2 -ml-2 rounded-lg hover:bg-gray-100 transition-colors"
        >
          <svg className="w-5 h-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 className="text-xl font-bold text-gray-900">Facture {invoice.numero}</h1>
      </div>

      {/* Status & Main Info */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-4 border-b border-gray-100">
          <div className="flex items-center justify-between mb-3">
            <span className={`px-3 py-1.5 rounded-full text-sm font-medium ${statusConfig.bg} ${statusConfig.color}`}>
              {statusConfig.label}
            </span>
            <span className="text-sm text-gray-500">
              {formatDate(invoice.date)}
            </span>
          </div>

          {invoice.objet && (
            <p className="text-sm text-gray-600 mb-2">{invoice.objet}</p>
          )}

          {invoice.echeance && invoice.statut === 'ENVOYEE' && (
            <div className="flex items-center gap-2 text-sm">
              <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <span className="text-gray-600">Echeance: {formatDate(invoice.echeance)}</span>
            </div>
          )}
        </div>

        {/* Lines */}
        {lignes.length > 0 && (
          <div className="p-4 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
              Detail
            </h3>
            <div className="space-y-3">
              {lignes.map((ligne, idx) => {
                const remise = ligne.remise || 0;
                const total = ligne.montant || ligne.quantite * ligne.prix_unitaire * (1 - remise / 100);

                return (
                  <div key={idx} className="flex items-start justify-between text-sm">
                    <div className="flex-1 min-w-0 pr-4">
                      <p className="font-medium text-gray-900">{ligne.description}</p>
                      <p className="text-gray-500">
                        {ligne.quantite} x {formatCurrency(ligne.prix_unitaire)}
                        {remise > 0 && ` (-${remise}%)`}
                      </p>
                    </div>
                    <p className="font-medium text-gray-900 flex-shrink-0">
                      {formatCurrency(total)}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Totals */}
        <div className="p-4 bg-gray-50">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">Total HT</span>
              <span className="font-medium text-gray-900">{formatCurrency(invoice.total_ht)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">TVA ({tvaRate}%)</span>
              <span className="font-medium text-gray-900">{formatCurrency(tvaAmount)}</span>
            </div>
            <div className="flex justify-between pt-2 border-t border-gray-200">
              <span className="font-semibold text-gray-900">Total TTC</span>
              <span className="font-bold text-gray-900 text-lg">{formatCurrency(invoice.total_ttc)}</span>
            </div>

            {(invoice.montant_paye || 0) > 0 && (
              <>
                <div className="flex justify-between text-green-600">
                  <span>Deja paye</span>
                  <span className="font-medium">- {formatCurrency(invoice.montant_paye)}</span>
                </div>
                <div className="flex justify-between pt-2 border-t border-gray-200">
                  <span className="font-semibold text-amber-600">Reste a payer</span>
                  <span className="font-bold text-amber-600 text-lg">{formatCurrency(resteAPayer)}</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Notes */}
      {invoice.notes && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
          <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Notes
          </h3>
          <p className="text-sm text-gray-600 whitespace-pre-wrap">{invoice.notes}</p>
        </div>
      )}

      {/* Company Info */}
      {invoice.tenant_nom && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
          <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Emetteur
          </h3>
          <div className="text-sm text-gray-600">
            <p className="font-medium text-gray-900">{invoice.tenant_nom}</p>
            {invoice.tenant_adresse && <p>{invoice.tenant_adresse}</p>}
            {invoice.tenant_email && <p>{invoice.tenant_email}</p>}
            {invoice.tenant_telephone && <p>{invoice.tenant_telephone}</p>}
            {invoice.tenant_siret && <p>SIRET: {invoice.tenant_siret}</p>}
          </div>
        </div>
      )}

      {/* Actions */}
      {invoice.pdf_url && (
        <div className="fixed bottom-20 left-4 right-4 z-40">
          <button
            onClick={handleDownloadPdf}
            className="w-full bg-primary-600 text-white py-3 px-6 rounded-xl font-semibold shadow-lg flex items-center justify-center gap-2 hover:bg-primary-700 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Voir le PDF
          </button>
        </div>
      )}
    </div>
  );
};

export default InvoiceDetailPage;
