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

    console.debug('[ErrorReporter] Frontend error reporting initialized');
})();
