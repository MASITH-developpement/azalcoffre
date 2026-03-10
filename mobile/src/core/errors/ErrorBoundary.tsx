/**
 * AZALPLUS Mobile - Error Boundary
 * Capture les erreurs React et les envoie à Guardian
 */

import React, { Component, ReactNode } from 'react';
import { reportReactError } from './ErrorReporter';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  override componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    // Envoyer à Guardian/AutoPilot
    reportReactError(error, { componentStack: errorInfo.componentStack || undefined });
  }

  override render(): ReactNode {
    if (this.state.hasError) {
      // Fallback UI
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div style={{
          padding: '20px',
          textAlign: 'center',
          color: '#666',
        }}>
          <h2 style={{ color: '#e74c3c' }}>Oups !</h2>
          <p>Une erreur s'est produite.</p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '10px 20px',
              background: '#3b82f6',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
            }}
          >
            Rafraîchir
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
