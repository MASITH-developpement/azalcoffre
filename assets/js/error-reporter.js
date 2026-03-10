/**
 * AZALPLUS - Frontend Error Reporter
 * Capture automatiquement les erreurs et les envoie à Guardian/AutoPilot
 *
 * Ce script est invisible pour l'utilisateur.
 */
(function() {
    'use strict';

    const REPORT_ENDPOINT = '/guardian/frontend-error';
    const MAX_ERRORS_PER_MINUTE = 10;
    const ERROR_QUEUE = [];
    let errorCount = 0;

    // Reset counter every minute
    setInterval(() => { errorCount = 0; }, 60000);

    /**
     * Envoie une erreur à Guardian
     */
    function reportError(errorData) {
        if (errorCount >= MAX_ERRORS_PER_MINUTE) {
            console.debug('[ErrorReporter] Rate limit reached');
            return;
        }
        errorCount++;

        fetch(REPORT_ENDPOINT, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(errorData)
        }).then(response => response.json())
        .then(data => {
            // Guardian peut demander un reload après correction
            if (data && data.action === 'reload') {
                console.log('[Guardian] Correction appliquée, rechargement...');
                setTimeout(() => {
                    location.reload(true); // Force reload from server
                }, 500);
            }
        }).catch(() => {
            // Silently fail - don't create infinite loop
        });
    }

    /**
     * Capture les erreurs JavaScript globales
     */
    window.onerror = function(message, source, line, column, error) {
        reportError({
            error_type: 'js_error',
            message: String(message),
            url: window.location.href,
            source: source,
            line: line,
            column: column,
            stack: error ? error.stack : null,
            user_agent: navigator.userAgent
        });
        return false; // Don't prevent default handling
    };

    /**
     * Capture les rejets de Promise non gérés
     */
    window.onunhandledrejection = function(event) {
        reportError({
            error_type: 'promise_rejection',
            message: String(event.reason),
            url: window.location.href,
            source: null,
            line: null,
            column: null,
            stack: event.reason && event.reason.stack ? event.reason.stack : null,
            user_agent: navigator.userAgent
        });
    };

    /**
     * Intercepte les erreurs de chargement de ressources (images, scripts, CSS, etc.)
     */
    document.addEventListener('error', function(event) {
        const target = event.target;
        if (target.tagName === 'IMG' || target.tagName === 'SCRIPT' || target.tagName === 'LINK') {
            const src = target.src || target.href;
            reportError({
                error_type: '404',
                message: `Failed to load ${target.tagName.toLowerCase()}: ${src}`,
                url: window.location.href,
                source: src,
                line: null,
                column: null,
                stack: null,
                user_agent: navigator.userAgent
            });
        }
    }, true);

    /**
     * Intercepte les erreurs réseau (fetch)
     */
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
        return originalFetch.apply(this, args).then(response => {
            if (!response.ok && response.status >= 400) {
                // 401 Unauthorized - Redirection vers login (une seule fois)
                if (response.status === 401) {
                    const redirectKey = 'guardian_401_redirect';
                    const lastRedirect = sessionStorage.getItem(redirectKey);
                    const now = Date.now();

                    // Éviter boucle: max 1 redirection par minute
                    if (lastRedirect && (now - parseInt(lastRedirect)) < 60000) {
                        console.warn('[Guardian] 401 répété - arrêt pour éviter boucle');
                        return response;
                    }

                    // Éviter si déjà sur login
                    if (!window.location.pathname.includes('/login') && !window.location.pathname.includes('/auth')) {
                        console.warn('[Guardian] 401 détecté');
                        sessionStorage.setItem(redirectKey, now.toString());

                        // Si dans un iframe (mobile), envoyer message au parent
                        if (window.parent !== window) {
                            console.warn('[Guardian] Dans iframe - notification parent');
                            window.parent.postMessage({ type: 'GUARDIAN_401', url: window.location.href }, '*');
                            return response;
                        }

                        // Sinon redirection directe
                        sessionStorage.setItem('returnUrl', window.location.href);
                        window.location.href = '/login';
                    }
                    return response;
                }

                // 403 Forbidden - Afficher message
                if (response.status === 403) {
                    console.warn('[Guardian] 403 Accès refusé');
                    if (typeof showNotification === 'function') {
                        showNotification('Accès refusé', 'error');
                    }
                }

                reportError({
                    error_type: `http_${response.status}`,
                    message: `HTTP ${response.status}: ${response.statusText}`,
                    url: window.location.href,
                    source: args[0],
                    line: null,
                    column: null,
                    stack: null,
                    user_agent: navigator.userAgent
                });
            }
            return response;
        }).catch(error => {
            reportError({
                error_type: 'network_error',
                message: error.message,
                url: window.location.href,
                source: args[0],
                line: null,
                column: null,
                stack: error.stack,
                user_agent: navigator.userAgent
            });
            throw error;
        });
    };

    /**
     * Intercepte console.error pour capturer les erreurs non-exceptions
     */
    const originalConsoleError = console.error;
    console.error = function(...args) {
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
            user_agent: navigator.userAgent
        });
    };

    /**
     * Intercepte console.warn pour capturer les warnings critiques
     */
    const originalConsoleWarn = console.warn;
    console.warn = function(...args) {
        // Appeler l'original
        originalConsoleWarn.apply(console, args);

        const message = args.map(a => String(a)).join(' ');

        // Ne capturer que les warnings React Router (migrations v7)
        if (message.includes('React Router') && message.includes('v7')) {
            reportError({
                error_type: 'deprecation_warning',
                message: message.slice(0, 1000),
                url: window.location.href,
                source: 'react-router',
                line: null,
                column: null,
                stack: null,
                user_agent: navigator.userAgent
            });
        }
    };

    console.debug('[ErrorReporter] Frontend error reporting initialized');
})();
