/**
 * My Interventions Page
 *
 * List of client's interventions with status tracking.
 */

import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { usePortalApi } from './hooks/usePortalAuth';

interface Intervention {
  id: string;
  numero: string | null;
  date_planifiee: string | null;
  heure_debut: string | null;
  heure_fin: string | null;
  description: string | null;
  statut: string;
  technicien_nom: string | null;
}

type StatusConfig = { label: string; color: string; bg: string; icon: string };

const STATUS_CONFIG: { [key: string]: StatusConfig } & { PLANIFIEE: StatusConfig } = {
  PLANIFIEE: {
    label: 'Planifiee',
    color: 'text-blue-600',
    bg: 'bg-blue-100',
    icon: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z',
  },
  EN_COURS: {
    label: 'En cours',
    color: 'text-amber-600',
    bg: 'bg-amber-100',
    icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  TERMINEE: {
    label: 'Terminee',
    color: 'text-green-600',
    bg: 'bg-green-100',
    icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  ANNULEE: {
    label: 'Annulee',
    color: 'text-red-600',
    bg: 'bg-red-100',
    icon: 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z',
  },
};

export const MyInterventions: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { fetchWithAuth } = usePortalApi();
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const currentStatus = searchParams.get('status') || '';

  useEffect(() => {
    const loadInterventions = async () => {
      try {
        setIsLoading(true);
        const url = currentStatus
          ? `/portal/interventions?status=${currentStatus}`
          : '/portal/interventions';
        const result = await fetchWithAuth<{ items: Intervention[] }>(url);
        setInterventions(result.items);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Erreur de chargement');
      } finally {
        setIsLoading(false);
      }
    };

    loadInterventions();
  }, [fetchWithAuth, currentStatus]);

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('fr-FR', {
      weekday: 'short',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  };

  const formatTime = (timeStr: string | null) => {
    if (!timeStr) return '';
    // Time comes as HH:MM:SS or HH:MM
    return timeStr.substring(0, 5);
  };

  const handleFilterChange = (status: string) => {
    if (status) {
      setSearchParams({ status });
    } else {
      setSearchParams({});
    }
  };

  const getStatusConfig = (status: string): StatusConfig => {
    return STATUS_CONFIG[status] ?? STATUS_CONFIG.PLANIFIEE;
  };

  const isUpcoming = (dateStr: string | null) => {
    if (!dateStr) return false;
    const date = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return date >= today;
  };

  const isPast = (dateStr: string | null) => {
    if (!dateStr) return false;
    const date = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return date < today;
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
        <h1 className="text-xl font-bold text-gray-900">Mes interventions</h1>
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
          onClick={() => handleFilterChange('PLANIFIEE')}
          className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            currentStatus === 'PLANIFIEE'
              ? 'bg-blue-600 text-white'
              : 'bg-blue-50 text-blue-600 hover:bg-blue-100'
          }`}
        >
          Planifiees
        </button>
        <button
          onClick={() => handleFilterChange('EN_COURS')}
          className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            currentStatus === 'EN_COURS'
              ? 'bg-amber-600 text-white'
              : 'bg-amber-50 text-amber-600 hover:bg-amber-100'
          }`}
        >
          En cours
        </button>
        <button
          onClick={() => handleFilterChange('TERMINEE')}
          className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            currentStatus === 'TERMINEE'
              ? 'bg-green-600 text-white'
              : 'bg-green-50 text-green-600 hover:bg-green-100'
          }`}
        >
          Terminees
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 text-red-600 rounded-lg p-4 text-sm">
          {error}
        </div>
      )}

      {/* Interventions List */}
      {interventions.length === 0 ? (
        <div className="bg-white rounded-xl p-8 text-center shadow-sm border border-gray-100">
          <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <p className="text-gray-500">Aucune intervention trouvee</p>
        </div>
      ) : (
        <div className="space-y-3">
          {interventions.map((intervention) => {
            const statusConfig = getStatusConfig(intervention.statut);
            const upcoming = isUpcoming(intervention.date_planifiee);
            const past = isPast(intervention.date_planifiee);

            return (
              <Link
                key={intervention.id}
                to={`/portal/interventions/${intervention.id}`}
                className="block bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden hover:shadow-md transition-shadow"
              >
                <div className="p-4">
                  {/* Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg ${statusConfig.bg} flex items-center justify-center flex-shrink-0`}>
                        <svg className={`w-5 h-5 ${statusConfig.color}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={statusConfig.icon} />
                        </svg>
                      </div>
                      <div>
                        <p className="font-semibold text-gray-900">
                          {intervention.numero || 'Intervention'}
                        </p>
                        <span className={`text-xs font-medium ${statusConfig.color}`}>
                          {statusConfig.label}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Description */}
                  {intervention.description && (
                    <p className="text-sm text-gray-600 mb-3 line-clamp-2">
                      {intervention.description}
                    </p>
                  )}

                  {/* Date & Time */}
                  <div className="flex items-center gap-4 text-sm">
                    <div className="flex items-center gap-1.5 text-gray-600">
                      <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                      <span className={upcoming && intervention.statut === 'PLANIFIEE' ? 'font-medium text-blue-600' : ''}>
                        {formatDate(intervention.date_planifiee)}
                      </span>
                    </div>

                    {(intervention.heure_debut || intervention.heure_fin) && (
                      <div className="flex items-center gap-1.5 text-gray-600">
                        <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>
                          {formatTime(intervention.heure_debut)}
                          {intervention.heure_fin && ` - ${formatTime(intervention.heure_fin)}`}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Technician */}
                  {intervention.technicien_nom && (
                    <div className="flex items-center gap-1.5 text-sm text-gray-600 mt-2">
                      <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                      <span>{intervention.technicien_nom}</span>
                    </div>
                  )}
                </div>

                {/* Footer for upcoming interventions */}
                {upcoming && intervention.statut === 'PLANIFIEE' && (
                  <div className="border-t border-gray-100 px-4 py-2 bg-blue-50">
                    <p className="text-xs text-blue-600 font-medium">
                      Intervention a venir
                    </p>
                  </div>
                )}

                {/* Footer for past pending interventions */}
                {past && intervention.statut === 'PLANIFIEE' && (
                  <div className="border-t border-gray-100 px-4 py-2 bg-amber-50">
                    <p className="text-xs text-amber-600 font-medium">
                      En attente de realisation
                    </p>
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

export default MyInterventions;
