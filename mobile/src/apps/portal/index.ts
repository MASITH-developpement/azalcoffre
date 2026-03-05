/**
 * Portal App Exports
 *
 * Client portal for viewing invoices, quotes, and interventions.
 */

// Provider
export { PortalAuthProvider } from './PortalAuthProvider';

// Layout
export { PortalLayout } from './PortalLayout';

// Pages
export { PortalLogin } from './PortalLogin';
export { PortalDashboard } from './PortalDashboard';
export { MyInvoices } from './MyInvoices';
export { InvoiceDetailPage } from './InvoiceDetail';
export { MyQuotes } from './MyQuotes';
export { MyInterventions } from './MyInterventions';

// Hooks
export { usePortalAuth, usePortalApi } from './hooks/usePortalAuth';
export type { PortalClient, PortalAuthState, PortalAuthContextValue } from './hooks/usePortalAuth';
