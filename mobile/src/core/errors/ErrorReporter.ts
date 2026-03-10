/**
 * AZALPLUS Mobile - Error Reporter
 * Capture automatiquement les erreurs et les envoie à Guardian/AutoPilot
 */

// Utiliser BACKEND_URL (sans /api) pour Guardian
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || import.meta.env.VITE_API_URL?.replace('/api', '') || '';
const REPORT_ENDPOINT = `${BACKEND_URL}/guardian/frontend-error`;
const MAX_ERRORS_PER_MINUTE = 10;

let errorCount = 0;

// Reset counter every minute
setInterval(() => { errorCount = 0; }, 60000);

interface ErrorReport {
  error_type: string;
  message: string;
  url: string;
  source?: string | null;
  line?: number | null;
  column?: number | null;
  stack?: string | null;
  user_agent?: string | null;
}

/**
 * Envoie une erreur à Guardian
 */
export async function reportError(errorData: ErrorReport): Promise<void> {
  if (errorCount >= MAX_ERRORS_PER_MINUTE) {
    console.debug('[ErrorReporter] Rate limit reached');
    return;
  }
  errorCount++;

  try {
    await fetch(REPORT_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(errorData),
    });
  } catch {
    // Silently fail - don't create infinite loop
  }
}

/**
 * Initialise le système de capture d'erreurs globales
 */
export function initializeErrorReporter(): void {
  // Capture les erreurs JavaScript globales
  window.onerror = (message, source, line, column, error) => {
    reportError({
      error_type: 'js_error',
      message: String(message),
      url: window.location.href,
      source: source || null,
      line: line || null,
      column: column || null,
      stack: error?.stack || null,
      user_agent: navigator.userAgent,
    });
    return false;
  };

  // Capture les rejets de Promise non gérés
  window.onunhandledrejection = (event) => {
    reportError({
      error_type: 'promise_rejection',
      message: String(event.reason),
      url: window.location.href,
      source: null,
      line: null,
      column: null,
      stack: event.reason?.stack || null,
      user_agent: navigator.userAgent,
    });
  };

  // Intercepte les erreurs de chargement de ressources
  document.addEventListener('error', (event) => {
    const target = event.target as HTMLElement;
    if (target.tagName === 'IMG' || target.tagName === 'SCRIPT' || target.tagName === 'LINK') {
      const src = (target as HTMLImageElement).src || (target as HTMLLinkElement).href;
      reportError({
        error_type: '404',
        message: `Failed to load ${target.tagName.toLowerCase()}: ${src}`,
        url: window.location.href,
        source: src,
        line: null,
        column: null,
        stack: null,
        user_agent: navigator.userAgent,
      });
    }
  }, true);

  // Intercepte console.warn pour les warnings critiques (React Router v7)
  const originalConsoleWarn = console.warn;
  console.warn = (...args: unknown[]) => {
    originalConsoleWarn.apply(console, args);

    const message = args.map(a => String(a)).join(' ');

    // Capturer les warnings React Router v7
    if (message.includes('React Router') && message.includes('v7')) {
      reportError({
        error_type: 'deprecation_warning',
        message: message.slice(0, 1000),
        url: window.location.href,
        source: 'react-router',
        line: null,
        column: null,
        stack: null,
        user_agent: navigator.userAgent,
      });
    }
  };

  // Intercepte console.error pour capturer les erreurs non-exceptions
  const originalConsoleError = console.error;
  console.error = (...args: unknown[]) => {
    // Appeler l'original
    originalConsoleError.apply(console, args);

    // Ignorer les erreurs connues non-critiques
    const message = args.map(a => String(a)).join(' ');
    const ignoredPatterns = [
      'React DevTools',
      'Download the React DevTools',
      'Warning:',
      'content-script',
      'extension',
    ];

    if (ignoredPatterns.some(p => message.includes(p))) {
      return;
    }

    // Reporter l'erreur
    reportError({
      error_type: 'console_error',
      message: message.slice(0, 1000),
      url: window.location.href,
      source: null,
      line: null,
      column: null,
      stack: new Error().stack || null,
      user_agent: navigator.userAgent,
    });
  };

  console.debug('[ErrorReporter] Mobile error reporting initialized');
}

/**
 * Report une erreur React (pour ErrorBoundary)
 */
export function reportReactError(error: Error, errorInfo?: { componentStack?: string }): void {
  reportError({
    error_type: 'react_error',
    message: error.message,
    url: window.location.href,
    source: null,
    line: null,
    column: null,
    stack: error.stack || null,
    user_agent: navigator.userAgent,
  });
}

/**
 * Report une erreur API
 */
export function reportApiError(endpoint: string, status: number, message: string): void {
  reportError({
    error_type: `api_${status}`,
    message: `API Error ${status}: ${message}`,
    url: window.location.href,
    source: endpoint,
    line: null,
    column: null,
    stack: null,
    user_agent: navigator.userAgent,
  });
}
