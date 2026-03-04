# AZALPLUS - Mémoire et Normes

**Version:** 1.0.0
**Date:** 2026-03-04
**Statut:** DOCUMENT NORMATIF - OPPOSABLE

---

## Table des Matières

1. [Introduction](#introduction)
2. [Normes Fondamentales (AZAP-NF)](#normes-fondamentales-azap-nf)
3. [Normes Multi-Tenant (AZAP-TENANT)](#normes-multi-tenant-azap-tenant)
4. [Normes Sécurité (AZAP-SEC)](#normes-sécurité-azap-sec)
5. [Normes Moteur No-Code (AZAP-NC)](#normes-moteur-no-code-azap-nc)
6. [Normes YAML (AZAP-YAML)](#normes-yaml-azap-yaml)
7. [Normes API (AZAP-API)](#normes-api-azap-api)
8. [Normes IA (AZAP-IA)](#normes-ia-azap-ia)
9. [Interdictions Absolues](#interdictions-absolues)
10. [Processus de Développement](#processus-de-développement)

---

## Introduction

AZALPLUS est un **moteur No-Code ERP multi-tenant** qui génère automatiquement des systèmes ERP complets depuis des fichiers de configuration YAML.

### Mission

Permettre la création d'ERP sans code via des définitions YAML, tout en garantissant :
- Isolation stricte des données entre tenants
- Sécurité by design (Guardian)
- Traçabilité complète (audit trail)
- Conformité RGPD native

### Principes Fondateurs

1. **Configuration over Code** : Tout est configurable via YAML
2. **Génération Automatique** : Tables, API, UI générées dynamiquement
3. **Multi-Tenant Native** : Isolation garantie par architecture
4. **Sécurité Invisible** : Guardian protège sans être détectable

---

## Normes Fondamentales (AZAP-NF)

### AZAP-NF-001 : Unicité du Moteur

```
RÈGLE: Le moteur (moteur/) est unique et ne peut être dupliqué.
- Un seul point d'entrée : moteur/core.py
- Toute logique de génération dans le moteur uniquement
- Les modules YAML sont des données, pas du code
```

### AZAP-NF-002 : Subordination des Modules YAML

```
RÈGLE: Les modules YAML sont subordonnés au moteur.
Flux : Module YAML → Parser → Moteur (validation) → Génération
- Un module YAML ne peut pas modifier le comportement du moteur
- Le moteur valide et rejette les YAML invalides
- Aucun code exécutable dans les fichiers YAML
```

### AZAP-NF-003 : Système Fermé

```
RÈGLE: Les règles fondatrices du moteur sont non modifiables.
- Le mapping types YAML → PostgreSQL est fixe
- Les colonnes système (id, tenant_id, created_at...) sont automatiques
- Le comportement du Guardian est invariant
```

### AZAP-NF-004 : Univocité

```
RÈGLE: Une définition YAML = une intention = un résultat.
- Un module YAML génère exactement une table
- Un champ YAML génère exactement une colonne
- Comportement déterministe et prédictible
```

### AZAP-NF-005 : Auditabilité

```
RÈGLE: Absence de trace = non-conformité.
- Toute opération CRUD est journalisée
- Toute action utilisateur est tracée
- Les logs Guardian sont inviolables
```

---

## Normes Multi-Tenant (AZAP-TENANT)

### AZAP-TENANT-001 : Isolation Obligatoire

| Règle | Description |
|-------|-------------|
| **tenant_id obligatoire** | Chaque table générée a une colonne `tenant_id UUID NOT NULL` |
| **Filtre automatique** | Chaque requête Database.query() filtre par tenant |
| **Contexte requis** | Toute exécution a un TenantContext actif |
| **Pas de cross-tenant** | Aucune requête ne peut accéder aux données d'un autre tenant |

### AZAP-TENANT-002 : Middleware Obligatoire

```python
# Ordre d'exécution des middlewares (CRITIQUE)
RateLimit → Auth → Tenant → Guardian → Route

# Le TenantMiddleware DOIT :
1. Extraire le tenant_id du JWT ou header X-Tenant-ID
2. Valider l'accès via Guardian.check_tenant_access()
3. Définir TenantContext.set(tenant_id, user_id, email)
4. Nettoyer TenantContext.clear() en finally
```

### AZAP-TENANT-003 : Vérification 4 Couches

| Couche | Responsabilité | Fichier |
|--------|----------------|---------|
| **1. Middleware** | Extraction tenant du JWT | `tenant.py` |
| **2. Contexte** | Stockage thread-local | `TenantContext` |
| **3. Service** | Filtre requêtes | `Database.query()` |
| **4. Base** | Contrainte FK | Schéma PostgreSQL |

---

## Normes Sécurité (AZAP-SEC)

### AZAP-SEC-001 : Guardian Invisible

```
RÈGLE: Guardian surveille et protège sans être détectable.
- Aucune mention de "Guardian" dans les messages d'erreur
- Messages neutres uniquement ("Requête invalide", "Données non trouvées")
- Dashboard /guardian/* visible uniquement pour CREATEUR_EMAIL
- Logs silencieux en base azalplus.guardian_log
```

### AZAP-SEC-002 : Détection Attaques

| Type | Patterns | Action |
|------|----------|--------|
| **SQL Injection** | UNION, INSERT, DELETE, DROP... | BLOCK + Log CRITICAL |
| **XSS** | `<script>`, `javascript:`, `on*=` | CLEAN + Log WARNING |
| **Tenant Breach** | Accès données autre tenant | BLOCK + Log CRITICAL |
| **Rate Limit** | Dépassement quotas | BLOCK temporaire |

### AZAP-SEC-003 : Authentification

| Composant | Spécification |
|-----------|---------------|
| **Hachage** | Argon2 (memory_cost=65536, time_cost=3) |
| **JWT** | HS256, expiration 24h |
| **Refresh** | 7 jours, rotation obligatoire |
| **2FA** | TOTP optionnel (pyotp) |

### AZAP-SEC-004 : Rate Limiting

| Catégorie | Limite | Fenêtre |
|-----------|--------|---------|
| Authentifié | 500 req | 1 minute |
| Non authentifié | 100 req | 1 minute |
| Premium (×3) | 1500 req | 1 minute |
| Auth endpoints | 5 req | 1 minute |

### AZAP-SEC-005 : Créateur

```python
# HARDCODÉ - NE JAMAIS MODIFIER
CREATEUR_EMAIL = "contact@stephane-moreau.fr"

# Le Créateur peut :
- Voir le dashboard Guardian
- Accéder à tous les tenants
- Débloquer les IPs
- Voir les logs complets
```

---

## Normes Moteur No-Code (AZAP-NC)

### AZAP-NC-001 : Génération Tables

```
RÈGLE: Le moteur génère automatiquement les tables PostgreSQL.
Schéma : azalplus.{module_name}

Colonnes système automatiques :
- id UUID PRIMARY KEY DEFAULT gen_random_uuid()
- tenant_id UUID NOT NULL REFERENCES tenants(id)
- created_at TIMESTAMP DEFAULT NOW()
- updated_at TIMESTAMP
- created_by UUID
- updated_by UUID
```

### AZAP-NC-002 : Mapping Types

| Type YAML | Type PostgreSQL | Type Python |
|-----------|-----------------|-------------|
| `text`, `texte` | VARCHAR(255) | str |
| `number`, `nombre` | NUMERIC(15,2) | Decimal |
| `date` | DATE | date |
| `datetime` | TIMESTAMP | datetime |
| `boolean`, `booleen` | BOOLEAN | bool |
| `select`, `enum` | VARCHAR | str |
| `relation` | UUID (FK) | UUID |
| `json` | JSONB | dict |
| `email` | VARCHAR(255) | str |
| `money`, `montant` | NUMERIC(15,2) | Decimal |

### AZAP-NC-003 : Génération API

```
RÈGLE: Chaque module YAML génère des endpoints CRUD.

Endpoints générés automatiquement :
GET    /api/v1/{module}          # Liste paginée
GET    /api/v1/{module}/{id}     # Détail
POST   /api/v1/{module}          # Création
PUT    /api/v1/{module}/{id}     # Mise à jour
DELETE /api/v1/{module}/{id}     # Suppression
POST   /api/v1/{module}/bulk     # Opérations en masse
GET    /api/v1/{module}/export   # Export CSV/JSON
```

### AZAP-NC-004 : Génération UI

```
RÈGLE: Le moteur génère l'interface HTML dynamiquement.

Pages générées :
/ui/{module}/              # Liste
/ui/{module}/{id}          # Détail/Édition
/ui/{module}/new           # Création

Composants : ui.py (145KB) génère HTML/CSS depuis theme.yml
```

---

## Normes YAML (AZAP-YAML)

### AZAP-YAML-001 : Validation Stricte

```
RÈGLE: Tout fichier YAML est validé avant chargement.

Vérifications :
1. Syntaxe YAML valide
2. Valeurs avec ":" entre guillemets
3. Types de champs reconnus
4. Pas de code exécutable
```

### AZAP-YAML-002 : Structure Module

```yaml
# Structure obligatoire d'un module YAML
nom: NomModule           # Nom affiché
icone: icon-name         # Icône UI
menu: GroupeMenu         # Catégorie menu
description: "..."       # Description

champs:                  # Définition des champs
  - nom: field_name
    type: text|number|date|...
    obligatoire: true|false
    defaut: valeur
    autocompletion: true|false

workflow:                # Optionnel - Transitions d'état
  ETAT1 -> ETAT2: condition

actions:                 # Optionnel - Actions disponibles
  - action_name
```

### AZAP-YAML-003 : Erreurs Courantes

| Erreur | Cause | Solution |
|--------|-------|----------|
| Deux-points dans valeur | `description: Note (heure:minute)` | `description: "Note (heure:minute)"` |
| Valeur non quotée | `defaut: A:B` | `defaut: "A:B"` |
| Type inconnu | `type: textte` | `type: text` |

---

## Normes API (AZAP-API)

### AZAP-API-001 : Versioning

```
RÈGLE: L'API est versionnée et documentée.

/api/v1/*     # API versionnée (recommandée)
/api/*        # API legacy (rétrocompatibilité)
/api/docs     # Swagger UI
/api/redoc    # ReDoc
```

### AZAP-API-002 : Format Réponse

```python
# Succès
{
    "data": [...],
    "meta": {
        "total": 100,
        "page": 1,
        "per_page": 20
    }
}

# Erreur
{
    "detail": "Message utilisateur neutre"
}
```

### AZAP-API-003 : Authentification

```
RÈGLE: Toutes les routes (sauf publiques) requièrent un JWT.

Header: Authorization: Bearer <token>
Ou: Cookie: access_token=<token>

Routes publiques (sans auth) :
- /health
- /api/auth/login, /register, /refresh
- /api/autocompletion-ia/entreprise, /adresse, /tva, /iban
```

---

## Normes IA (AZAP-IA)

### AZAP-IA-001 : IA Subordonnée

```
RÈGLE: L'IA assiste, elle ne décide jamais.
- L'IA propose des suggestions (autocomplétion)
- L'utilisateur valide ou rejette
- Pas d'actions automatiques sans confirmation
```

### AZAP-IA-002 : Providers Supportés

| Provider | Modèles | Usage |
|----------|---------|-------|
| **Anthropic** | Claude Sonnet 4, Opus 4 | Complétion texte |
| **OpenAI** | GPT-4o, GPT-4-turbo | Complétion texte |
| **APIs Gov** | SIRET, Adresse, TVA | Données publiques |

### AZAP-IA-003 : Champs Autocomplétion

```yaml
# Activer l'autocomplétion IA sur un champ
- nom: raison_sociale
  type: text
  autocompletion: true  # Active l'IA
```

---

## Interdictions Absolues

### Interdictions Techniques

| Code | Interdiction |
|------|--------------|
| I-01 | ❌ Code sans `tenant_id` |
| I-02 | ❌ Requête sans filtre tenant |
| I-03 | ❌ Secrets en dur dans le code |
| I-04 | ❌ SQL brut sans paramètres |
| I-05 | ❌ Exposer l'existence de Guardian |
| I-06 | ❌ Modifier CREATEUR_EMAIL |
| I-07 | ❌ Désactiver l'audit |
| I-08 | ❌ Catch-all silencieux (`except: pass`) |

### Interdictions Fonctionnelles

| Code | Interdiction |
|------|--------------|
| I-10 | ❌ Accès cross-tenant |
| I-11 | ❌ Suppression sans traçabilité |
| I-12 | ❌ Action financière sans validation humaine |
| I-13 | ❌ Masquer des erreurs |

### Interdictions IA

| Code | Interdiction |
|------|--------------|
| I-20 | ❌ IA décisionnaire autonome |
| I-21 | ❌ IA avec accès écriture sur le moteur |
| I-22 | ❌ IA sans journalisation |
| I-23 | ❌ Mentir sur un résultat |
| I-24 | ❌ Simuler un test sans l'exécuter |

---

## Processus de Développement

### Processus IA Obligatoire

```
ANALYSIS → PLAN → EXECUTION → VERIFICATION

1. ANALYSIS : Comprendre le besoin, lire le code existant
2. PLAN : Planifier les modifications
3. EXECUTION : Implémenter
4. VERIFICATION : Tester, valider
```

### Validation YAML

```bash
# Valider tous les modules avant démarrage
python -m moteur.validate_yaml

# Le moteur valide automatiquement au chargement
ModuleParser.load_all_modules(validate_first=True)
```

### Tests Obligatoires

| Composant | Couverture Min |
|-----------|----------------|
| Moteur (core) | 90% |
| Parser | 85% |
| Guardian | 90% |
| API | 80% |

### Checklist Avant Commit

- [ ] `tenant_id` vérifié sur toutes les requêtes
- [ ] Pas de secrets en dur
- [ ] Messages d'erreur neutres (pas de "Guardian")
- [ ] YAML valides (pas de `:` non quotés)
- [ ] Tests passants
- [ ] Audit trail fonctionnel

---

## Certification Modules

| Niveau | Critères |
|--------|----------|
| **CERT-A** | Module complet, tests 90%+, YAML valide, doc à jour |
| **CERT-B** | Module fonctionnel, tests 70%+, YAML valide |
| **CERT-C** | Module partiel, en développement |
| **CERT-X** | Module retiré/obsolète |

---

## Historique

| Version | Date | Changements |
|---------|------|-------------|
| 1.0.0 | 2026-03-04 | Création initiale - Adaptation normes AZA pour AZALPLUS |

---

**Document normatif AZALPLUS - Toute dérogation doit être validée et tracée.**
