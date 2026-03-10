import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import App from './App';
import './styles/globals.css';

// Error reporting (Guardian/AutoPilot)
import { initializeErrorReporter } from './core/errors/ErrorReporter';
import { ErrorBoundary } from './core/errors/ErrorBoundary';

// Initialize error reporter ASAP
initializeErrorReporter();

// Écouter les messages 401 de l'iframe (UI principale)
window.addEventListener('message', (event) => {
  if (event.data?.type === 'GUARDIAN_401') {
    console.warn('[Guardian Mobile] 401 reçu de l\'iframe - redirection login');
    // Éviter boucle
    const redirectKey = 'guardian_401_mobile';
    const lastRedirect = sessionStorage.getItem(redirectKey);
    const now = Date.now();
    if (!lastRedirect || (now - parseInt(lastRedirect)) > 60000) {
      sessionStorage.setItem(redirectKey, now.toString());
      // Nettoyer tokens et rediriger vers login mobile
      localStorage.removeItem('azalplus_access_token');
      localStorage.removeItem('azalplus_refresh_token');
      window.location.href = '/login';
    }
  }
});

// Configure QueryClient with sensible defaults for mobile
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Keep data fresh for 5 minutes
      staleTime: 5 * 60 * 1000,
      // Cache data for 30 minutes
      gcTime: 30 * 60 * 1000,
      // Retry failed requests up to 3 times
      retry: 3,
      // Exponential backoff for retries
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      // Refetch on window focus for fresh data
      refetchOnWindowFocus: true,
      // Don't refetch on mount if data is fresh
      refetchOnMount: false,
    },
    mutations: {
      // Retry mutations once on failure
      retry: 1,
    },
  },
});

// Get the root element
const container = document.getElementById('root');

if (!container) {
  throw new Error('Root element not found. Make sure there is a <div id="root"></div> in your HTML.');
}

// Create React root and render the app
const root = createRoot(container);

root.render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
);

// Register service worker for PWA functionality
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .then((registration) => {
        console.log('SW registered:', registration.scope);
      })
      .catch((error) => {
        console.error('SW registration failed:', error);
      });
  });
}
