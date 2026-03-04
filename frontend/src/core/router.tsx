// AZALPLUS - Configuration du Router
import React, { lazy, Suspense } from 'react';
import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';

// Layout
import { MainLayout } from '../layouts/MainLayout';

// Loading fallback
const LoadingFallback = () => (
  <div className="flex items-center justify-center min-h-[400px]">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
  </div>
);

// Lazy load des pages
const Dashboard = lazy(() => import('../pages/Dashboard'));
const NotFound = lazy(() => import('../pages/NotFound'));

// Commercial
const ClientsList = lazy(() => import('../pages/clients/ClientsList'));
const ClientDetail = lazy(() => import('../pages/clients/ClientDetail'));
const ContactsList = lazy(() => import('../pages/contacts/ContactsList'));
const LeadsList = lazy(() => import('../pages/leads/LeadsList'));
const DevisList = lazy(() => import('../pages/devis/DevisList'));
const FacturesList = lazy(() => import('../pages/factures/FacturesList'));

// Opérations
const InterventionsList = lazy(() => import('../pages/interventions/InterventionsList'));
const ProjetsList = lazy(() => import('../pages/projets/ProjetsList'));
const TachesList = lazy(() => import('../pages/taches/TachesList'));
const TicketsList = lazy(() => import('../pages/tickets/TicketsList'));

// Inventaire
const ProduitsList = lazy(() => import('../pages/produits/ProduitsList'));
const StockList = lazy(() => import('../pages/stock/StockList'));
const FournisseursList = lazy(() => import('../pages/fournisseurs/FournisseursList'));

// Comptabilité
const PaiementsList = lazy(() => import('../pages/paiements/PaiementsList'));
const ComptesBancairesList = lazy(() => import('../pages/comptes-bancaires/ComptesBancairesList'));

// RH
const EmployesList = lazy(() => import('../pages/employes/EmployesList'));
const CongesList = lazy(() => import('../pages/conges/CongesList'));
const TempsList = lazy(() => import('../pages/temps/TempsList'));
const NotesFraisList = lazy(() => import('../pages/notes-frais/NotesFraisList'));

// Paramètres
const EntrepriseSettings = lazy(() => import('../pages/parametres/EntrepriseSettings'));
const UtilisateursSettings = lazy(() => import('../pages/parametres/UtilisateursSettings'));
const SequencesSettings = lazy(() => import('../pages/parametres/SequencesSettings'));
const WebhooksSettings = lazy(() => import('../pages/parametres/WebhooksSettings'));
const RGPDSettings = lazy(() => import('../pages/parametres/RGPDSettings'));

// Autocomplétion IA - Import direct car déjà créé
import { ConfigurationPage as AutocompletionIASettings } from '../modules/autocompletion-ia';

// -----------------------------------------------------------------------------
// Wrapper avec Suspense
// -----------------------------------------------------------------------------
const SuspenseWrapper = ({ children }: { children: React.ReactNode }) => (
  <Suspense fallback={<LoadingFallback />}>{children}</Suspense>
);

// -----------------------------------------------------------------------------
// Configuration des routes
// -----------------------------------------------------------------------------
export const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    children: [
      // Dashboard
      {
        index: true,
        element: (
          <SuspenseWrapper>
            <Dashboard />
          </SuspenseWrapper>
        ),
      },

      // Commercial
      {
        path: 'clients',
        children: [
          {
            index: true,
            element: (
              <SuspenseWrapper>
                <ClientsList />
              </SuspenseWrapper>
            ),
          },
          {
            path: ':id',
            element: (
              <SuspenseWrapper>
                <ClientDetail />
              </SuspenseWrapper>
            ),
          },
        ],
      },
      {
        path: 'contacts',
        element: (
          <SuspenseWrapper>
            <ContactsList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'leads',
        element: (
          <SuspenseWrapper>
            <LeadsList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'devis',
        element: (
          <SuspenseWrapper>
            <DevisList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'factures',
        element: (
          <SuspenseWrapper>
            <FacturesList />
          </SuspenseWrapper>
        ),
      },

      // Opérations
      {
        path: 'interventions',
        element: (
          <SuspenseWrapper>
            <InterventionsList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'projets',
        element: (
          <SuspenseWrapper>
            <ProjetsList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'taches',
        element: (
          <SuspenseWrapper>
            <TachesList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'tickets',
        element: (
          <SuspenseWrapper>
            <TicketsList />
          </SuspenseWrapper>
        ),
      },

      // Inventaire
      {
        path: 'produits',
        element: (
          <SuspenseWrapper>
            <ProduitsList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'stock',
        element: (
          <SuspenseWrapper>
            <StockList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'fournisseurs',
        element: (
          <SuspenseWrapper>
            <FournisseursList />
          </SuspenseWrapper>
        ),
      },

      // Comptabilité
      {
        path: 'paiements',
        element: (
          <SuspenseWrapper>
            <PaiementsList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'comptes-bancaires',
        element: (
          <SuspenseWrapper>
            <ComptesBancairesList />
          </SuspenseWrapper>
        ),
      },

      // RH
      {
        path: 'employes',
        element: (
          <SuspenseWrapper>
            <EmployesList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'conges',
        element: (
          <SuspenseWrapper>
            <CongesList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'temps',
        element: (
          <SuspenseWrapper>
            <TempsList />
          </SuspenseWrapper>
        ),
      },
      {
        path: 'notes-frais',
        element: (
          <SuspenseWrapper>
            <NotesFraisList />
          </SuspenseWrapper>
        ),
      },

      // Paramètres
      {
        path: 'parametres',
        children: [
          {
            index: true,
            element: <Navigate to="/parametres/entreprise" replace />,
          },
          {
            path: 'entreprise',
            element: (
              <SuspenseWrapper>
                <EntrepriseSettings />
              </SuspenseWrapper>
            ),
          },
          {
            path: 'utilisateurs',
            element: (
              <SuspenseWrapper>
                <UtilisateursSettings />
              </SuspenseWrapper>
            ),
          },
          {
            path: 'autocompletion-ia',
            element: <AutocompletionIASettings />,
          },
          {
            path: 'sequences',
            element: (
              <SuspenseWrapper>
                <SequencesSettings />
              </SuspenseWrapper>
            ),
          },
          {
            path: 'webhooks',
            element: (
              <SuspenseWrapper>
                <WebhooksSettings />
              </SuspenseWrapper>
            ),
          },
          {
            path: 'rgpd',
            element: (
              <SuspenseWrapper>
                <RGPDSettings />
              </SuspenseWrapper>
            ),
          },
        ],
      },

      // 404
      {
        path: '*',
        element: (
          <SuspenseWrapper>
            <NotFound />
          </SuspenseWrapper>
        ),
      },
    ],
  },
]);

export default router;
