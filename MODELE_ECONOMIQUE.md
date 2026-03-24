# AZALBTP — Modèle Économique

## Principe Fondamental

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   AZALPLUS = 100% GRATUIT (et le restera toujours)            │
│                                                                 │
│   AZALBTP, AZALIMMO, AZALMED, AZALCOFFRE = PAYANTS             │
│   → Ce sont des PRODUITS DISTINCTS, pas des "modules premium"  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Pourquoi des Applications Séparées ?

### Cohérence du Discours Commercial

| Approche | Discours | Problème |
|----------|----------|----------|
| ❌ Modules payants dans AZALPLUS | "AZALPLUS gratuit avec options payantes" | Freemium trompeur |
| ✅ Applications séparées | "AZALPLUS 100% gratuit" + "AZALBTP = autre produit payant" | Honnête et clair |

### Le Client Comprend

- **AZALPLUS** : ERP générique gratuit → J'utilise gratuitement
- **AZALBTP** : Logiciel spécialisé BTP → Normal que ce soit payant, c'est un autre produit

→ **Pas de sentiment d'arnaque**
→ **Pas de "fonctions cachées" payantes dans le gratuit**

## Architecture Technique

```
┌─────────────────────────────────────────────────────────────────┐
│                     MOTEUR AZALPLUS                             │
│              (Parser YAML, DB, Auth, UI, API)                   │
│                      JAMAIS MODIFIÉ                             │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   AZALPLUS    │     │   AZALBTP     │     │   AZALIMMO    │
│   (Gratuit)   │     │   (Payant)    │     │   (Payant)    │
│               │     │               │     │               │
│ ERP Générique │     │ Spécial BTP   │     │ Spécial Immo  │
└───────────────┘     └───────────────┘     └───────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   PostgreSQL    │
                    │  (DB Commune)   │
                    │                 │
                    │ tenant_id +     │
                    │ app_scope       │
                    └─────────────────┘
```

## Partage des Données

### Données Communes (via AZALPLUS)
- Clients
- Employés
- Fournisseurs
- Factures
- Inventaire

### Données Spécifiques (par application)
- **AZALBTP** : Chantiers, Situations, Métrés, PPSPS
- **AZALIMMO** : Biens, Baux, Quittances, Mandats
- **AZALMED** : Patients, Consultations, Ordonnances
- **AZALCOFFRE** : Documents archivés, Signatures, Factur-X

## Sécurité Multi-Application

```
Token JWT:
{
  "tenant_id": "xxx",
  "user_id": "yyy",
  "app": "azalbtp",
  "apps_authorized": ["azalplus", "azalbtp"],
  "scopes": {
    "clients": "read",      // Lecture depuis AZALPLUS
    "chantiers": "full"     // Complet dans AZALBTP
  }
}
```

## Tarification (Exemple)

| Produit | Prix | Cible |
|---------|------|-------|
| AZALPLUS | **GRATUIT** | Tous |
| AZALBTP | 49€/mois | Artisans, PME BTP |
| AZALIMMO | 39€/mois | Agences, Gestionnaires |
| AZALMED | 59€/mois | Cabinets médicaux |
| AZALCOFFRE | 29€/mois | Tous (archivage légal) |

## Règles Absolues

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  1. AZALPLUS reste 100% GRATUIT — JAMAIS de fonctions payantes │
│                                                                 │
│  2. Les apps spécialisées sont des PRODUITS SÉPARÉS            │
│     → Pas des "modules" ou "options" d'AZALPLUS                │
│                                                                 │
│  3. Le discours commercial reste cohérent et honnête           │
│     → "Gratuit" signifie vraiment gratuit                      │
│                                                                 │
│  4. Techniquement, les apps partagent le moteur AZALPLUS       │
│     → Mais commercialement, ce sont des produits distincts     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Financement

Les applications payantes (BTP, IMMO, MED, COFFRE) financent :
- Le développement d'AZALPLUS (gratuit)
- L'infrastructure (serveurs, DB)
- Le support
- Les évolutions

→ **Modèle vertueux** : Plus on vend de spécialisés, plus on peut améliorer le gratuit.
