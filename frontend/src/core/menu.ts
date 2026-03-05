// AZALPLUS - Configuration du Menu Principal
import type { ReactNode } from 'react';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------
export interface MenuItem {
  id: string;
  label: string;
  icon?: string;
  path?: string;
  children?: MenuItem[];
  badge?: string | number;
  badgeColor?: 'blue' | 'green' | 'red' | 'yellow' | 'purple';
  roles?: string[];
  disabled?: boolean;
  external?: boolean;
  separator?: boolean;
}

export interface MenuSection {
  id: string;
  title?: string;
  items: MenuItem[];
}

// -----------------------------------------------------------------------------
// Configuration du Menu
// -----------------------------------------------------------------------------
export const menuConfig: MenuSection[] = [
  // Section principale
  {
    id: 'main',
    items: [
      {
        id: 'dashboard',
        label: 'Tableau de bord',
        icon: 'home',
        path: '/',
      },
    ],
  },

  // Commercial
  {
    id: 'commercial',
    title: 'Commercial',
    items: [
      {
        id: 'clients',
        label: 'Clients',
        icon: 'users',
        path: '/clients',
      },
      {
        id: 'contacts',
        label: 'Contacts',
        icon: 'contact',
        path: '/contacts',
      },
      {
        id: 'leads',
        label: 'Prospects',
        icon: 'user-plus',
        path: '/leads',
      },
      {
        id: 'devis',
        label: 'Devis',
        icon: 'file-text',
        path: '/devis',
      },
      {
        id: 'factures',
        label: 'Factures',
        icon: 'file-invoice',
        path: '/factures',
      },
      {
        id: 'opportunites',
        label: 'Opportunités',
        icon: 'target',
        path: '/opportunites',
      },
    ],
  },

  // Opérations
  {
    id: 'operations',
    title: 'Opérations',
    items: [
      {
        id: 'interventions',
        label: 'Interventions',
        icon: 'wrench',
        path: '/interventions',
      },
      {
        id: 'projets',
        label: 'Projets',
        icon: 'folder',
        path: '/projets',
      },
      {
        id: 'taches',
        label: 'Tâches',
        icon: 'check-square',
        path: '/taches',
      },
      {
        id: 'tickets',
        label: 'Tickets',
        icon: 'ticket',
        path: '/tickets',
      },
    ],
  },

  // Inventaire
  {
    id: 'inventaire',
    title: 'Inventaire',
    items: [
      {
        id: 'produits',
        label: 'Produits',
        icon: 'package',
        path: '/produits',
      },
      {
        id: 'stock',
        label: 'Stock',
        icon: 'warehouse',
        path: '/stock',
      },
      {
        id: 'fournisseurs',
        label: 'Fournisseurs',
        icon: 'truck',
        path: '/fournisseurs',
      },
    ],
  },

  // Comptabilité
  {
    id: 'comptabilite',
    title: 'Comptabilité',
    items: [
      {
        id: 'paiements',
        label: 'Paiements',
        icon: 'credit-card',
        path: '/paiements',
      },
      {
        id: 'comptes-bancaires',
        label: 'Comptes bancaires',
        icon: 'landmark',
        path: '/comptes-bancaires',
      },
      {
        id: 'ecritures',
        label: 'Écritures',
        icon: 'book-open',
        path: '/ecritures',
      },
    ],
  },

  // RH
  {
    id: 'rh',
    title: 'Ressources Humaines',
    items: [
      {
        id: 'employes',
        label: 'Employés',
        icon: 'users',
        path: '/employes',
      },
      {
        id: 'conges',
        label: 'Congés',
        icon: 'calendar',
        path: '/conges',
      },
      {
        id: 'temps',
        label: 'Temps',
        icon: 'clock',
        path: '/temps',
      },
      {
        id: 'notes-frais',
        label: 'Notes de frais',
        icon: 'receipt',
        path: '/notes-frais',
      },
    ],
  },

  // Paramètres
  {
    id: 'parametres',
    title: 'Paramètres',
    items: [
      {
        id: 'entreprise',
        label: 'Entreprise',
        icon: 'building',
        path: '/parametres/entreprise',
      },
      {
        id: 'utilisateurs',
        label: 'Utilisateurs',
        icon: 'users-cog',
        path: '/parametres/utilisateurs',
      },
      {
        id: 'autocompletion-ia',
        label: 'Autocomplétion IA',
        icon: 'sparkles',
        path: '/parametres/autocompletion-ia',
        badge: 'Nouveau',
        badgeColor: 'purple',
      },
      {
        id: 'sequences',
        label: 'Séquences',
        icon: 'hash',
        path: '/parametres/sequences',
      },
      {
        id: 'webhooks',
        label: 'Webhooks',
        icon: 'globe',
        path: '/parametres/webhooks',
      },
      {
        id: 'rgpd',
        label: 'RGPD',
        icon: 'shield',
        path: '/parametres/rgpd',
      },
      {
        id: 'mobile-config',
        label: 'Application Mobile',
        icon: 'smartphone',
        path: '/parametres/mobile',
      },
    ],
  },
];

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

/**
 * Trouver un item de menu par son chemin
 */
export function findMenuItemByPath(path: string): MenuItem | undefined {
  for (const section of menuConfig) {
    for (const item of section.items) {
      if (item.path === path) return item;
      if (item.children) {
        const child = item.children.find((c) => c.path === path);
        if (child) return child;
      }
    }
  }
  return undefined;
}

/**
 * Trouver un item de menu par son ID
 */
export function findMenuItemById(id: string): MenuItem | undefined {
  for (const section of menuConfig) {
    for (const item of section.items) {
      if (item.id === id) return item;
      if (item.children) {
        const child = item.children.find((c) => c.id === id);
        if (child) return child;
      }
    }
  }
  return undefined;
}

/**
 * Obtenir le fil d'Ariane pour un chemin
 */
export function getBreadcrumb(path: string): MenuItem[] {
  const breadcrumb: MenuItem[] = [];
  const item = findMenuItemByPath(path);

  if (item) {
    // Trouver la section parente
    for (const section of menuConfig) {
      const found = section.items.find(
        (i) => i.path === path || i.children?.some((c) => c.path === path)
      );
      if (found) {
        if (found.path !== path && found.children) {
          breadcrumb.push(found);
          const child = found.children.find((c) => c.path === path);
          if (child) breadcrumb.push(child);
        } else {
          breadcrumb.push(found);
        }
        break;
      }
    }
  }

  return breadcrumb;
}

export default menuConfig;
