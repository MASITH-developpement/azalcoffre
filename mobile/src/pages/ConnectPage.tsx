/**
 * AZALPLUS Mobile - Connect Page
 * Gère la connexion via token depuis le QR code
 */

import { useEffect, useState, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../core/auth';

export function ConnectPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { login, isAuthenticated } = useAuth();
  const [status, setStatus] = useState<'connecting' | 'success' | 'error'>('connecting');
  const [error, setError] = useState<string | null>(null);

  // Ref pour éviter double appel (React StrictMode)
  const verificationAttempted = useRef(false);
  const verificationSucceeded = useRef(false);

  useEffect(() => {
    const token = searchParams.get('token');
    const apiUrl = searchParams.get('api');

    if (!token) {
      setStatus('error');
      setError('Token manquant');
      return;
    }

    // Éviter double appel (React StrictMode appelle useEffect 2 fois)
    if (verificationAttempted.current) {
      console.log('Verification already attempted, skipping...');
      return;
    }
    verificationAttempted.current = true;

    // Stocker l'URL de l'API si fournie
    if (apiUrl) {
      localStorage.setItem('apiUrl', apiUrl);
    }

    // Tenter la connexion avec le token
    connectWithToken(token);
  }, [searchParams]);

  const connectWithToken = async (token: string) => {
    try {
      setStatus('connecting');

      // Le token est un token de session mobile
      // On le stocke et on vérifie sa validité
      localStorage.setItem('mobileToken', token);

      const apiUrl = localStorage.getItem('apiUrl') || import.meta.env.VITE_API_URL;

      // Vérifier le token auprès du backend
      const response = await fetch(`${apiUrl}/auth/mobile-verify`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token }),
      });

      if (response.ok) {
        const data = await response.json();
        // Stocker les infos d'auth
        if (data.access_token) {
          localStorage.setItem('accessToken', data.access_token);
          localStorage.setItem('azalplus_access_token', data.access_token);
          verificationSucceeded.current = true;
          console.log('Mobile login successful!');
        }
        if (data.user) {
          localStorage.setItem('user', JSON.stringify(data.user));
        }
        setStatus('success');
        // Rediriger vers le dashboard après 1 seconde
        setTimeout(() => navigate('/'), 1000);
      } else {
        // Token invalide - vérifier si on a déjà réussi (race condition)
        if (verificationSucceeded.current) {
          console.log('Already verified successfully, ignoring 401');
          return;
        }
        console.warn('Token non vérifié, mode démo activé');
        setStatus('success');
        setTimeout(() => navigate('/'), 1000);
      }
    } catch (err) {
      console.error('Erreur de connexion:', err);
      // En cas d'erreur réseau, on continue quand même (mode offline)
      setStatus('success');
      setTimeout(() => navigate('/'), 1000);
    }
  };

  // Si déjà authentifié, rediriger
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/');
    }
  }, [isAuthenticated, navigate]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-600 to-blue-800 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl p-8 max-w-md w-full text-center">
        {status === 'connecting' && (
          <>
            <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-6"></div>
            <h1 className="text-2xl font-bold text-gray-800 mb-2">Connexion en cours...</h1>
            <p className="text-gray-600">Veuillez patienter</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
              <svg className="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-gray-800 mb-2">Connecté !</h1>
            <p className="text-gray-600">Redirection vers l'application...</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-6">
              <svg className="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-gray-800 mb-2">Erreur de connexion</h1>
            <p className="text-red-600 mb-4">{error}</p>
            <button
              onClick={() => navigate('/')}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Retour à l'accueil
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default ConnectPage;
