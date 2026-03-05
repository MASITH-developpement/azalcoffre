import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { useModuleConfig } from '../core/config/MobileConfigProvider';

export default function RecordDetailPage(): React.ReactElement {
  const { moduleId, recordId } = useParams<{ moduleId: string; recordId: string }>();
  const moduleConfig = useModuleConfig(moduleId || '');

  if (!moduleConfig) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-lg font-medium text-gray-900">Module non trouve</h1>
          <Link to="/" className="text-primary-600 mt-2 inline-block">
            Retour au tableau de bord
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pb-20 safe-area-top">
      <header className="sticky top-0 z-10 bg-white border-b border-gray-100 px-4 py-3">
        <div className="flex items-center gap-3">
          <Link
            to={`/module/${moduleId}`}
            className="w-10 h-10 flex items-center justify-center -ml-2"
          >
            <svg className="w-6 h-6 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </Link>
          <div className="flex-1">
            <h1 className="text-lg font-semibold text-gray-900">Detail</h1>
            <p className="text-sm text-gray-500">{moduleConfig.name}</p>
          </div>
          <button className="w-10 h-10 flex items-center justify-center">
            <svg className="w-6 h-6 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
            </svg>
          </button>
        </div>
      </header>

      <main className="p-4">
        <div className="card p-4">
          <div className="space-y-4">
            <div>
              <label className="text-sm text-gray-500">ID</label>
              <p className="font-mono text-sm">{recordId}</p>
            </div>
            <div>
              <label className="text-sm text-gray-500">Module</label>
              <p className="font-medium">{moduleConfig.name}</p>
            </div>
          </div>
        </div>

        <div className="mt-4 empty-state">
          <p className="empty-state-description">
            Les details de l'enregistrement seront affiches ici.
          </p>
        </div>
      </main>
    </div>
  );
}
