# AZALPLUS — Modèle Économique

**Version :** 1.0
**Date :** Mars 2026
**Auteur :** MASITH Développement

---

## Résumé exécutif

AZALPLUS est un **ERP 100% gratuit** pour TPE (artisans, commerces, indépendants).

**Tous les modules sont gratuits, sans limite, sans pub, sans piège.**

La monétisation repose sur **3 sources de revenus** liées aux flux financiers :

| Source | Description | Activation |
|--------|-------------|------------|
| **Paiements Open Banking** | Commission sur les paiements de factures | Dès le lancement |
| **Données anonymisées** | Vente d'insights sectoriels B2B | À partir de 5000 TPE |
| **Compte bancaire intégré** | Revenus bancaires (optionnel) | En parallèle |

---

## Principe fondamental

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   L'ERP est GRATUIT.                                        │
│   La TPE ne paie JAMAIS d'abonnement.                       │
│                                                             │
│   AZALPLUS se rémunère sur les FLUX FINANCIERS             │
│   qui transitent par la plateforme.                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Ce que la TPE obtient gratuitement :**
- Facturation illimitée
- Devis illimités
- Gestion clients / fournisseurs
- Comptabilité
- Gestion de stock
- CRM
- Projets / tâches
- Tous les modules présents et futurs

---

## Source 1 : Paiements Open Banking

### Concept

Chaque facture émise via AZALPLUS inclut un **lien de paiement**.

Le client de la TPE clique → paye par virement instantané → la TPE est payée immédiatement.

```
Facture envoyée par email
        ↓
Client clique "Payer"
        ↓
Redirigé vers sa banque (Open Banking)
        ↓
Valide le virement (pré-rempli)
        ↓
Virement instantané vers la TPE
        ↓
Commission prélevée automatiquement
```

### Partenaire technique

**Fintecture** (établissement de paiement agréé ACPR)

- Paiement par virement initié (Open Banking)
- Virement instantané
- Pas de chargeback (contrairement à la CB)
- Régulé, sécurisé

### Tarification

| Élément | Montant |
|---------|---------|
| Commission Fintecture | 0.99% |
| Marge AZALPLUS | 0.30% |
| **Total client** | **1.29%** |

**Comparaison marché :**

| Solution | Frais | Délai | Risque chargeback |
|----------|-------|-------|-------------------|
| Stripe | 1.5% + 0.25€ | 2-7 jours | Oui |
| PayPal | 2.9% + 0.35€ | 1-3 jours | Oui |
| **AZALPLUS** | **1.29%** | **Instantané** | **Non** |

### Revenus projetés

**Hypothèses :**
- 30 paiements/mois par TPE en moyenne
- Ticket moyen : 400€

| TPE actives | Volume mensuel | Marge 0.30% |
|-------------|----------------|-------------|
| 500 | 6M€ | 18 000€/mois |
| 2 000 | 24M€ | 72 000€/mois |
| 5 000 | 60M€ | 180 000€/mois |
| 10 000 | 120M€ | 360 000€/mois |

---

## Source 2 : Données anonymisées

### Concept

L'ERP collecte des données sur l'activité des TPE. Ces données, **agrégées et anonymisées**, ont une valeur pour :

- Banques (scoring crédit, modèles de risque)
- Assureurs (tarification, sinistralité)
- Cabinets de conseil (études sectorielles)
- Collectivités (politique économique)
- Fédérations professionnelles (benchmark)

### Ce qui est vendu

**Pas les données individuelles.** Des insights agrégés :

| Produit | Exemple | Prix |
|---------|---------|------|
| Étude sectorielle | "Le marché des plombiers en IDF" | 5-15K€ |
| Baromètre mensuel | "Tendances TPE France" | 2-5K€/mois |
| API temps réel | Accès données agrégées | 20-50K€/an |
| Étude sur mesure | Analyse custom | 10-30K€ |

### Cadre légal (RGPD)

- ✅ Données anonymisées = autorisé
- ✅ Agrégation minimum 10-20 TPE par groupe
- ✅ Impossible de remonter à une TPE individuelle
- ❌ Jamais de données personnelles vendues

### Activation

**Seuil minimum : 5000 TPE actives**

En dessous, les données ne sont pas assez représentatives pour être vendables.

### Revenus projetés

| TPE actives | Revenus données |
|-------------|-----------------|
| < 5 000 | 0€ (pas assez de volume) |
| 5 000 | 15 000€/mois |
| 10 000 | 30 000€/mois |
| 20 000 | 50 000€/mois |

---

## Source 3 : Compte bancaire intégré (optionnel)

### Concept

Les TPE peuvent **optionnellement** activer un compte bancaire professionnel intégré à l'ERP.

Ce n'est **pas obligatoire**. C'est une commodité.

```
TPE active le compte (optionnel)
        ↓
Compte pro avec IBAN français
        ↓
Intégré dans l'ERP (solde, transactions)
        ↓
Tap to Pay disponible (encaissement carte)
        ↓
Revenus partagés avec AZALPLUS
```

### Partenaire technique

**Swan** (BaaS - Banking as a Service)

- Compte pro avec IBAN français
- Carte bancaire
- Virements SEPA
- Tap to Pay (encaissement smartphone)
- Régulé, agréé

### Revenus

| Source | Revenu AZALPLUS |
|--------|-----------------|
| Frais de compte | 3-5€/mois par compte |
| Interchange carte | Variable |
| Tap to Pay (commission) | 0.2-0.3% des encaissements |

### Activation

**Optionnel.** Estimation : 20-30% des TPE activeront le compte.

### Revenus projetés

| TPE actives | Comptes activés (25%) | Revenu mensuel |
|-------------|----------------------|----------------|
| 500 | 125 | 1 500€/mois |
| 2 000 | 500 | 6 000€/mois |
| 5 000 | 1 250 | 15 000€/mois |
| 10 000 | 2 500 | 30 000€/mois |

---

## Services complémentaires futurs

### Factoring / Prêt (via partenaire)

**Partenaire envisagé :** Defacto

| Service | Description | Revenu AZALPLUS |
|---------|-------------|-----------------|
| Factoring | Avance sur factures | Commission apporteur |
| Prêt TPE | Crédit court terme | Commission apporteur |

**Intégration :** Demande en 2 clics dans l'ERP, données pré-remplies.

**Activation :** Phase 2 (après validation partenariat)

---

## Synthèse des revenus

### Par phase

| Phase | TPE | Paiements | Données | Banque | Total |
|-------|-----|-----------|---------|--------|-------|
| 1 | 500 | 18K€ | 0€ | 1.5K€ | **19.5K€/mois** |
| 2 | 2 000 | 72K€ | 0€ | 6K€ | **78K€/mois** |
| 3 | 5 000 | 180K€ | 15K€ | 15K€ | **210K€/mois** |
| 4 | 10 000 | 360K€ | 30K€ | 30K€ | **420K€/mois** |

### Revenus annuels

| Phase | TPE | Revenu annuel |
|-------|-----|---------------|
| 1 | 500 | 234K€ |
| 2 | 2 000 | 936K€ |
| 3 | 5 000 | 2.5M€ |
| 4 | 10 000 | 5M€ |

---

## Structure des coûts

### Coûts fixes

| Poste | Coût mensuel |
|-------|--------------|
| Infrastructure (serveurs) | 500-2 000€ |
| Services tiers (APIs) | 200-500€ |
| Frais bancaires/juridiques | 300-500€ |
| **Total fixe** | **~1 000-3 000€/mois** |

### Coûts variables

| Poste | Coût |
|-------|------|
| Fintecture (0.99%) | Intégré dans la commission |
| Swan (frais par compte) | ~5€/compte/mois |
| Support (si externalisé) | Variable |

### Point mort estimé

**~300-400 TPE actives** avec paiements réguliers.

---

## Avantages concurrentiels

| Concurrent | Modèle | Prix TPE | AZALPLUS |
|------------|--------|----------|----------|
| Pennylane | Compta + banque | 50-200€/mois | **Gratuit** |
| Axonaut | ERP | 30-50€/mois | **Gratuit** |
| Henrri | Facturation | Gratuit limité | **Gratuit illimité** |
| Shine | Banque + factu | 9-40€/mois | **Gratuit + banque optionnelle** |

**Positionnement unique :**
- ERP complet gratuit (pas freemium)
- Paiements moins chers et instantanés
- Pas de pub
- Indépendance (partenaires changeables)

---

## Principes non négociables

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   ✅ Gratuit pour les TPE — tous modules, illimité          │
│   ✅ Pas de publicité                                        │
│   ✅ Pas de vente de données personnelles                   │
│   ✅ Pas de dépendance à un partenaire unique               │
│   ✅ Transparence sur les frais                             │
│                                                             │
│   ❌ Jamais de freemium déguisé                             │
│   ❌ Jamais de limite artificielle                          │
│   ❌ Jamais de données individuelles vendues                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Partenaires clés

| Partenaire | Rôle | Statut |
|------------|------|--------|
| **Swan** | Compte bancaire (BaaS) | En discussion |
| **Fintecture** | Paiement Open Banking | En discussion |
| **Defacto** | Factoring / Prêt | En attente |

---

## Roadmap

| Phase | Objectif | Revenus cibles |
|-------|----------|----------------|
| **Phase 1** (0-12 mois) | 500 TPE, paiements activés | 20K€/mois |
| **Phase 2** (12-24 mois) | 2000 TPE, compte bancaire | 80K€/mois |
| **Phase 3** (24-36 mois) | 5000 TPE, données + financement | 200K€/mois |
| **Phase 4** (36+ mois) | 10000+ TPE, écosystème complet | 400K€+/mois |

---

## Risques et mitigations

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Peu de TPE utilisent le paiement intégré | Revenus faibles | UX simple, argument "instantané + moins cher" |
| Partenaire augmente ses tarifs | Marge réduite | Contrat négocié, partenaires alternatifs |
| Concurrence copie le modèle | Parts de marché | Avance technologique, communauté |
| RGPD mal appliqué (données) | Amendes | Audit juridique, seuils stricts |

---

## Conclusion

Le modèle AZALPLUS repose sur un principe simple :

> **L'ERP est gratuit. AZALPLUS se rémunère sur les flux financiers.**

C'est un modèle :
- **Honnête** : pas de piège, pas de freemium déguisé
- **Aligné** : AZALPLUS gagne quand la TPE utilise le système
- **Scalable** : revenus proportionnels au volume
- **Indépendant** : partenaires changeables, code propriétaire

---

*Document MASITH Développement — Mars 2026*
