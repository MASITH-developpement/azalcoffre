/**
 * Portal Login Page
 *
 * Magic link login form for client portal.
 * Clients enter their email to receive a login link.
 */

import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { usePortalAuth } from './hooks/usePortalAuth';

type LoginStep = 'email' | 'sent' | 'verifying' | 'error';

export const PortalLogin: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { requestMagicLink, verifyMagicLink, isLoading, error, clearError, isAuthenticated } =
    usePortalAuth();

  const [step, setStep] = useState<LoginStep>('email');
  const [email, setEmail] = useState('');
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_, setMessage] = useState('');

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/portal');
    }
  }, [isAuthenticated, navigate]);

  // Check for magic link token in URL
  useEffect(() => {
    const token = searchParams.get('token');
    if (token) {
      setStep('verifying');
      verifyMagicLink(token).then((success) => {
        if (success) {
          navigate('/portal');
        } else {
          setStep('error');
        }
      });
    }
  }, [searchParams, verifyMagicLink, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();

    if (!email.trim()) {
      return;
    }

    const result = await requestMagicLink(email.trim().toLowerCase());

    if (result.success) {
      setMessage(result.message);
      setStep('sent');
    }
  };

  const handleRetry = () => {
    setStep('email');
    setEmail('');
    clearError();
  };

  // Verifying state
  if (step === 'verifying') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-gray-50">
        <div className="w-full max-w-sm text-center">
          <div className="w-12 h-12 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-600">Verification en cours...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (step === 'error') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-gray-50">
        <div className="w-full max-w-sm">
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-gray-900">Lien invalide</h1>
            <p className="text-gray-500 mt-2">
              {error || 'Ce lien de connexion est invalide ou a expire.'}
            </p>
          </div>

          <button onClick={handleRetry} className="btn btn-primary w-full">
            Demander un nouveau lien
          </button>
        </div>
      </div>
    );
  }

  // Link sent state
  if (step === 'sent') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-gray-50">
        <div className="w-full max-w-sm">
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-gray-900">Email envoye</h1>
            <p className="text-gray-500 mt-2">
              Un lien de connexion a ete envoye a <strong>{email}</strong>.
            </p>
          </div>

          <div className="bg-blue-50 rounded-lg p-4 text-sm text-blue-700 mb-6">
            <p className="font-medium mb-1">Consultez votre boite mail</p>
            <p>Le lien est valable pendant 15 minutes. Pensez a verifier vos spams.</p>
          </div>

          <button
            onClick={handleRetry}
            className="btn btn-secondary w-full"
          >
            Utiliser une autre adresse
          </button>
        </div>
      </div>
    );
  }

  // Email input state
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-gray-50">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-xl bg-primary-600 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Espace Client</h1>
          <p className="text-gray-500 mt-2">
            Consultez vos factures, devis et interventions
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-red-50 text-red-600 text-sm">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
              Votre adresse email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-200 focus:border-primary-500 outline-none transition-colors"
              placeholder="vous@exemple.com"
              required
              autoComplete="email"
              autoFocus
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || !email.trim()}
            className="btn btn-primary w-full py-3"
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Envoi en cours...
              </span>
            ) : (
              'Recevoir un lien de connexion'
            )}
          </button>
        </form>

        <p className="text-center text-xs text-gray-400 mt-6">
          Un lien de connexion securise sera envoye a votre adresse email.
          <br />
          Aucun mot de passe requis.
        </p>
      </div>

      {/* Inline styles for buttons */}
      <style>{`
        .btn {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 0.75rem 1.5rem;
          font-size: 0.875rem;
          font-weight: 600;
          border-radius: 0.5rem;
          transition: all 0.2s;
          cursor: pointer;
          border: none;
        }

        .btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .btn-primary {
          background: #2563EB;
          color: white;
        }

        .btn-primary:hover:not(:disabled) {
          background: #1d4ed8;
        }

        .btn-secondary {
          background: white;
          color: #374151;
          border: 1px solid #d1d5db;
        }

        .btn-secondary:hover:not(:disabled) {
          background: #f9fafb;
        }
      `}</style>
    </div>
  );
};

export default PortalLogin;
